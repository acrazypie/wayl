"""Connections to people's own music servers (Plex, Navidrome) and what we learned from them."""
from app.models import db, utcnow

SERVER_KINDS = ("plex", "navidrome")


class MediaServer(db.Model):
    __tablename__ = "media_servers"
    __table_args__ = (db.UniqueConstraint("user_id", "kind"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)  # "plex" | "navidrome"
    name = db.Column(db.String(120), nullable=False)
    base_url = db.Column(db.String(500), nullable=False)
    username = db.Column(db.String(200), nullable=True)  # Navidrome login
    secret = db.Column(db.Text, nullable=False)  # encrypted: Navidrome password or Plex server token
    plex_owned = db.Column(db.Boolean, nullable=False, default=False)  # you own the Plex server

    sync_listens = db.Column(db.Boolean, nullable=False, default=True)
    sync_playlists = db.Column(db.Boolean, nullable=False, default=False)

    listen_cursor = db.Column(db.Integer, nullable=True)  # Plex: newest viewedAt already imported
    last_listen_sync_at = db.Column(db.DateTime, nullable=True)
    last_playlist_sync_at = db.Column(db.DateTime, nullable=True)
    last_library_sync_at = db.Column(db.DateTime, nullable=True)
    library_count = db.Column(db.Integer, nullable=False, default=0)
    syncing_since = db.Column(db.DateTime, nullable=True)  # simple lock between web and worker
    last_error = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    tracks = db.relationship("ServerTrack", backref="server", lazy=True, cascade="all, delete-orphan")
    imported_playlists = db.relationship(
        "ImportedPlaylist", backref="server", lazy=True, cascade="all, delete-orphan"
    )


class ServerTrack(db.Model):
    """A track on someone's server, and the catalog song it matched (if any)."""

    __tablename__ = "server_tracks"
    __table_args__ = (
        db.UniqueConstraint("server_id", "remote_id"),
        db.Index("ix_server_tracks_song", "server_id", "song_id"),
        db.Index("ix_server_tracks_norm", "server_id", "norm_title"),
    )

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey("media_servers.id"), nullable=False)
    remote_id = db.Column(db.String(200), nullable=False)  # Subsonic song id / Plex ratingKey
    title = db.Column(db.String(300), nullable=False)
    artist = db.Column(db.String(300), nullable=False)
    album = db.Column(db.String(300), nullable=True)
    duration = db.Column(db.Integer, nullable=True)
    mbid = db.Column(db.String(36), nullable=True)
    stream_key = db.Column(db.String(500), nullable=True)  # Plex media part path
    # Normalized for "do I own this song?" checks and library search (see services.matching).
    norm_title = db.Column(db.String(300), nullable=False, default="")
    norm_artist = db.Column(db.String(300), nullable=False, default="")
    song_id = db.Column(db.Integer, db.ForeignKey("songs.id"), nullable=True)
    matched_at = db.Column(db.DateTime, nullable=True)  # set once matching was attempted
    seen_at = db.Column(db.DateTime, nullable=True)  # last library sync that saw it
    song = db.relationship("Song")


class ImportedPlaylist(db.Model):
    __tablename__ = "imported_playlists"
    __table_args__ = (db.UniqueConstraint("server_id", "remote_id"),)

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey("media_servers.id"), nullable=False)
    remote_id = db.Column(db.String(200), nullable=False)
    playlist_id = db.Column(db.Integer, db.ForeignKey("playlists.id"), nullable=False)
    unmatched = db.Column(db.Integer, nullable=False, default=0)
    synced_at = db.Column(db.DateTime, default=utcnow)
    playlist = db.relationship("Playlist")


class IncomingListen(db.Model):
    """A listen reported by a server or scrobbler that isn't in the history yet: either waiting
    to be matched to a catalog song ("pending") or that could not be matched ("unmatched")."""

    __tablename__ = "incoming_listens"
    __table_args__ = (db.Index("ix_incoming_user_status", "user_id", "status"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    source = db.Column(db.String(30), nullable=False)
    artist = db.Column(db.String(300), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    album = db.Column(db.String(300), nullable=True)
    mbid = db.Column(db.String(36), nullable=True)
    duration = db.Column(db.Integer, nullable=True)
    listened_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, default=utcnow)


class ListenToken(db.Model):
    """Token for the ListenBrainz-compatible scrobble API (Navidrome, other players)."""

    __tablename__ = "listen_tokens"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    last_used_at = db.Column(db.DateTime, nullable=True)
