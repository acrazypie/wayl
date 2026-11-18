"""Pull data from connected media servers: library index, listens, playlists.

Runs from the background worker (python -m app.worker) on a schedule and from "Sync now" in
the settings page. A per-server lock (syncing_since) keeps the two from running at once.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from app.models import db, utcnow
from app.models.music import Playlist, PlaylistSong
from app.models.server import ImportedPlaylist, IncomingListen, MediaServer, ServerTrack
from app.services import catalog
from app.services.matching import process_incoming, record_listen, resolve_server_track, upsert_server_track
from app.services.media import MediaServerError, client_for
from app.utility import config

log = logging.getLogger(__name__)

PLEX_OWNER_ACCOUNT_ID = 1  # on a Plex server, the owner's local account id
LOCK_TIMEOUT = timedelta(minutes=30)
LIBRARY_SYNC_INTERVAL = timedelta(hours=12)


def _from_unix(ts):
    return datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None)


def acquire(server_id):
    now = utcnow()
    res = db.session.execute(
        update(MediaServer)
        .where(MediaServer.id == server_id)
        .where((MediaServer.syncing_since.is_(None)) | (MediaServer.syncing_since < now - LOCK_TIMEOUT))
        .values(syncing_since=now)
    )
    db.session.commit()
    return res.rowcount == 1


def release(server):
    server.syncing_since = None
    db.session.commit()


def queue_listen(user_id, source, remote, listened_at, status="pending"):
    """Keep a listen we couldn't record yet (no match, or catalog down), without duplicates."""
    window = timedelta(seconds=max(90, int((remote.duration or 180) * 0.6)))
    exists = IncomingListen.query.filter(
        IncomingListen.user_id == user_id,
        IncomingListen.title == remote.title[:300],
        IncomingListen.artist == remote.artist[:300],
        IncomingListen.listened_at >= listened_at - window,
        IncomingListen.listened_at <= listened_at + window,
    ).first()
    if exists is None:
        db.session.add(IncomingListen(
            user_id=user_id, source=source, artist=remote.artist[:300], title=remote.title[:300],
            album=(remote.album or None) and remote.album[:300], mbid=remote.mbid, duration=remote.duration,
            listened_at=listened_at, status=status,
        ))


def _log_play(server, st, listened_at, stats):
    try:
        song = resolve_server_track(st)
    except catalog.CatalogError:
        queue_listen(server.user_id, server.kind, st, listened_at, status="pending")
        stats["pending"] += 1
        return
    if song is None:
        queue_listen(server.user_id, server.kind, st, listened_at, status="unmatched")
        stats["unmatched"] += 1
    elif record_listen(server.user_id, song, listened_at, server.kind):
        stats["added"] += 1


# --- the three jobs -------------------------------------------------------------------------


def sync_library(server, client):
    started = utcnow()
    count = 0
    for remote in client.all_tracks():
        upsert_server_track(server, remote, seen=True)
        count += 1
        if count % 500 == 0:
            db.session.commit()
    # tracks no longer on the server
    ServerTrack.query.filter(
        ServerTrack.server_id == server.id,
        (ServerTrack.seen_at.is_(None)) | (ServerTrack.seen_at < started),
    ).delete(synchronize_session=False)
    server.library_count = count
    server.last_library_sync_at = utcnow()
    db.session.commit()
    return {"tracks": count}


def sync_listens(server, client):
    stats = {"added": 0, "unmatched": 0, "pending": 0}
    if server.kind == "plex":
        since = server.listen_cursor or int((utcnow() - timedelta(days=config.HISTORY_IMPORT_DAYS)).replace(tzinfo=timezone.utc).timestamp())
        account = PLEX_OWNER_ACCOUNT_ID if server.plex_owned else None
        plays = client.history(since, account_id=account)
        newest = since
        for rating_key, viewed_at in reversed(plays):  # oldest first
            st = ServerTrack.query.filter_by(server_id=server.id, remote_id=rating_key).first()
            if st is None:
                remote = client.track(rating_key)
                if remote is None:
                    continue
                st = upsert_server_track(server, remote)
            _log_play(server, st, _from_unix(viewed_at), stats)
            newest = max(newest, viewed_at)
            server.listen_cursor = newest
            db.session.commit()
    else:
        now = utcnow()
        for remote, minutes_ago in client.now_playing():
            st = upsert_server_track(server, remote)
            _log_play(server, st, now - timedelta(minutes=minutes_ago), stats)
    server.last_listen_sync_at = utcnow()
    db.session.commit()
    return stats


def sync_playlists(server, client):
    imported = unmatched_total = 0
    for remote_pl in client.playlists():
        tracks = client.playlist_tracks(remote_pl["id"])
        songs, unmatched = [], 0
        for remote in tracks:
            st = upsert_server_track(server, remote)
            try:
                song = resolve_server_track(st)
            except catalog.CatalogError:
                song = None
            if song and song.id not in {s.id for s in songs}:
                songs.append(song)
            elif not song:
                unmatched += 1

        link = ImportedPlaylist.query.filter_by(server_id=server.id, remote_id=remote_pl["id"]).first()
        if link is None or db.session.get(Playlist, link.playlist_id) is None:
            playlist = Playlist(name=remote_pl["name"][:120], user_id=server.user_id, is_public=False)
            db.session.add(playlist)
            db.session.flush()
            if link is None:
                link = ImportedPlaylist(server_id=server.id, remote_id=remote_pl["id"], playlist_id=playlist.id)
                db.session.add(link)
            else:
                link.playlist_id = playlist.id
        else:
            playlist = db.session.get(Playlist, link.playlist_id)
            playlist.name = remote_pl["name"][:120]
        # mirror the server's order and contents
        PlaylistSong.query.filter_by(playlist_id=playlist.id).delete()
        for song in songs:
            db.session.add(PlaylistSong(playlist_id=playlist.id, song_id=song.id))
        link.unmatched = unmatched
        link.synced_at = utcnow()
        db.session.commit()
        imported += 1
        unmatched_total += unmatched
    server.last_playlist_sync_at = utcnow()
    db.session.commit()
    return {"playlists": imported, "unmatched_tracks": unmatched_total}


# --- orchestration -----------------------------------------------------------------------------


def due_jobs(server, now=None):
    now = now or utcnow()
    jobs = []
    if not server.last_library_sync_at or now - server.last_library_sync_at > LIBRARY_SYNC_INTERVAL:
        jobs.append("library")
    if server.sync_listens:
        interval = config.PLEX_HISTORY_INTERVAL if server.kind == "plex" else config.WORKER_INTERVAL
        if not server.last_listen_sync_at or (now - server.last_listen_sync_at).total_seconds() >= interval - 5:
            jobs.append("listens")
    if server.sync_playlists:
        if not server.last_playlist_sync_at or (now - server.last_playlist_sync_at).total_seconds() >= config.PLAYLIST_SYNC_INTERVAL:
            jobs.append("playlists")
    return jobs


def sync_server(server_id, jobs):
    """Run jobs ("library", "listens", "playlists") for one server. Returns a summary dict, or
    None if another sync of this server is already running."""
    if not acquire(server_id):
        return None
    server = db.session.get(MediaServer, server_id)
    summary = {}
    try:
        client = client_for(server)
        for job in jobs:
            if job == "library":
                summary["library"] = sync_library(server, client)
            elif job == "listens" and server.sync_listens:
                summary["listens"] = sync_listens(server, client)
            elif job == "playlists" and server.sync_playlists:
                summary["playlists"] = sync_playlists(server, client)
        server.last_error = None
    except (MediaServerError, catalog.CatalogError) as exc:
        db.session.rollback()
        server = db.session.get(MediaServer, server_id)
        server.last_error = str(exc)[:500]
        log.warning("Sync of server %s failed: %s", server_id, exc)
    except Exception:
        db.session.rollback()
        server = db.session.get(MediaServer, server_id)
        server.last_error = "Unexpected error while syncing (see the logs)"
        log.exception("Sync of server %s crashed", server_id)
    finally:
        release(server)
    return summary


def process_pending(limit=100, user_id=None, include_unmatched=False):
    """Match queued listens. Returns {"added", "duplicate", "unmatched", "pending"} counts."""
    statuses = ["pending", "unmatched"] if include_unmatched else ["pending"]
    q = IncomingListen.query.filter(IncomingListen.status.in_(statuses))
    if user_id is not None:
        q = q.filter_by(user_id=user_id)
    counts = {"added": 0, "duplicate": 0, "unmatched": 0, "pending": 0}
    for listen in q.order_by(IncomingListen.id).limit(limit).all():
        try:
            counts[process_incoming(listen)] += 1
        except catalog.CatalogError:
            counts["pending"] += 1
            break  # catalog is down: stop for now
        db.session.commit()
    db.session.commit()
    return counts


def run_round():
    """One worker round: every server's due jobs, then queued listens."""
    for (server_id,) in db.session.query(MediaServer.id).all():
        server = db.session.get(MediaServer, server_id)
        jobs = due_jobs(server)
        if jobs:
            sync_server(server_id, jobs)
    process_pending()
