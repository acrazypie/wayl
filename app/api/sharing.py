"""Publishing: turn share links for your playlists and your profile on and off.

The documents themselves are served by app/routes/share.py; their contents are defined in
app/services/share_docs.py and docs/sharing-protocol.md.
"""
from flask import g
from flask_restful import Resource

from app.models import db
from app.models.sharing import ShareSettings
from app.services.share_docs import app_url_warning, new_token, playlist_share_url, profile_share_url
from app.utility import auth_required, json_body, limiter


def _with_warning(data):
    warning = app_url_warning()
    return {**data, "warning": warning} if warning else data


def playlist_share_info(playlist):
    return _with_warning({
        "shared": playlist.share_token is not None,
        "url": playlist_share_url(playlist.share_token) if playlist.share_token else None,
    })


def _own_playlist(playlist_id):
    from app.api.music import find_playlist

    return find_playlist(playlist_id, write=True)  # 404 unless it's yours


class PlaylistShare(Resource):
    """PUT: share (creates the link if missing). DELETE: stop sharing (the link dies)."""

    @auth_required
    def get(self, playlist_id):
        playlist, error = _own_playlist(playlist_id)
        return error or playlist_share_info(playlist)

    @auth_required
    def put(self, playlist_id):
        playlist, error = _own_playlist(playlist_id)
        if error:
            return error
        if playlist.share_token is None:
            playlist.share_token = new_token()
            db.session.commit()
        return playlist_share_info(playlist)

    @auth_required
    def delete(self, playlist_id):
        playlist, error = _own_playlist(playlist_id)
        if error:
            return error
        playlist.share_token = None
        db.session.commit()
        return playlist_share_info(playlist)


class PlaylistShareReset(Resource):
    decorators = [limiter.limit("30 per hour")]

    @auth_required
    def post(self, playlist_id):
        playlist, error = _own_playlist(playlist_id)
        if error:
            return error
        playlist.share_token = new_token()  # the old link stops working
        db.session.commit()
        return playlist_share_info(playlist)


def _settings(user, create=False):
    settings = db.session.get(ShareSettings, user.id)
    if settings is None and create:
        settings = ShareSettings(user_id=user.id, share_listens=False, share_top_artists=False)
        db.session.add(settings)
    return settings


def sharing_info(user):
    s = _settings(user)
    return _with_warning({
        "enabled": bool(s and s.profile_share_token),
        "url": profile_share_url(s.profile_share_token) if s and s.profile_share_token else None,
        "share_listens": bool(s and s.share_listens),
        "share_top_artists": bool(s and s.share_top_artists),
        "display_name": (s.display_name if s and s.display_name else user.username),
    })


class MySharing(Resource):
    """GET/PATCH /api/me/sharing: {enabled, share_listens, share_top_artists, display_name}."""

    @auth_required
    def get(self):
        return sharing_info(g.current_user)

    @auth_required
    def patch(self):
        user = g.current_user
        data = json_body()
        s = _settings(user, create=True)
        if "display_name" in data:
            name = str(data.get("display_name") or "").strip()
            if len(name) > 60:
                return {"error": "Display name must be at most 60 characters"}, 400
            s.display_name = name or None
        for key in ("share_listens", "share_top_artists"):
            if key in data:
                setattr(s, key, bool(data[key]))
        if "enabled" in data:
            if data["enabled"] and not s.profile_share_token:
                s.profile_share_token = new_token()
            elif not data["enabled"]:
                s.profile_share_token = None
        db.session.commit()
        return sharing_info(user)


class MySharingReset(Resource):
    decorators = [limiter.limit("30 per hour")]

    @auth_required
    def post(self):
        s = _settings(g.current_user, create=True)
        s.profile_share_token = new_token()
        db.session.commit()
        return sharing_info(g.current_user)
