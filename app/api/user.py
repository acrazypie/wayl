"""Core user endpoints: your own account, profiles and public playlists.

Follower counts and "is_following" only appear when social features are on (WAYL_SOCIAL);
the social endpoints themselves live in app/api/social.py.
"""
from flask import g, session
from flask_login import logout_user
from flask_restful import Resource
from sqlalchemy import or_

from app.models import db
from app.models.music import ListeningHistory, Playlist, SavedSong
from app.models.social import Follow
from app.models.user import UserModel
from app.utility import auth_required, get_current_user, iso, json_body, limiter, social_enabled


def public_user(user):
    """The only user fields other people may see. Never include email here."""
    return {"id": user.id, "username": user.username, "bio": user.bio, "joined_at": iso(user.created_at)}


class Me(Resource):
    @auth_required
    def get(self):
        from app.api.auth import me_dict

        user = g.current_user
        social = {}
        if social_enabled():
            from app.api.social import follow_counts

            social = follow_counts(user)
        return {
            **me_dict(user),
            **social,
            "saved_songs": SavedSong.query.filter_by(user_id=user.id).count(),
            "listens": ListeningHistory.query.filter_by(user_id=user.id).count(),
            "playlists": Playlist.query.filter_by(user_id=user.id).count(),
        }

    @auth_required
    def patch(self):
        from app.api.auth import me_dict, validate_username

        user = g.current_user
        data = json_body()
        if "username" in data:
            username = str(data.get("username") or "").strip()
            error = validate_username(username, exclude_id=user.id)
            if error:
                return {"error": error}, 409 if error == "That username is taken" else 400
            user.username = username
        if "bio" in data:
            bio = str(data.get("bio") or "").strip()
            if len(bio) > 160:
                return {"error": "Bio must be at most 160 characters"}, 400
            user.bio = bio or None
        db.session.commit()
        return me_dict(user)

    @auth_required
    def delete(self):
        """Delete the signed-in account and everything attached to it. Needs {"password"}."""
        user = g.current_user
        if not user.check_password(str(json_body().get("password") or "")):
            return {"error": "Password is incorrect"}, 403
        uid = user.id
        # Follows are deleted whether or not social features are switched on.
        Follow.query.filter(or_(Follow.follower_id == uid, Follow.followed_id == uid)).delete(
            synchronize_session=False
        )
        ListeningHistory.query.filter_by(user_id=uid).delete(synchronize_session=False)
        SavedSong.query.filter_by(user_id=uid).delete(synchronize_session=False)
        from app.models.server import IncomingListen, ListenToken, MediaServer
        from app.models.sharing import ShareSettings, Subscription

        ShareSettings.query.filter_by(user_id=uid).delete(synchronize_session=False)
        # children (playlists opened from a subscribed profile) before their parents
        Subscription.query.filter(Subscription.user_id == uid, Subscription.parent_id.isnot(None)).delete(synchronize_session=False)
        Subscription.query.filter_by(user_id=uid).delete(synchronize_session=False)

        IncomingListen.query.filter_by(user_id=uid).delete(synchronize_session=False)
        ListenToken.query.filter_by(user_id=uid).delete(synchronize_session=False)
        for server in MediaServer.query.filter_by(user_id=uid).all():
            db.session.delete(server)  # cascades to its tracks and playlist links
        db.session.flush()
        for playlist in Playlist.query.filter_by(user_id=uid).all():
            db.session.delete(playlist)
        db.session.delete(user)
        db.session.commit()
        session.clear()
        logout_user()  # after clear(), so the remember-me cookie gets deleted too
        return {"message": "Account deleted"}


class ChangePassword(Resource):
    decorators = [limiter.limit("10 per hour")]

    @auth_required
    def post(self):
        from app.api.auth import me_dict, start_session, validate_password

        user = g.current_user
        data = json_body()
        if not user.check_password(str(data.get("current_password") or "")):
            return {"error": "Current password is incorrect"}, 403
        error = validate_password(data.get("new_password"))
        if error:
            return {"error": error}, 400
        user.set_password(data["new_password"])
        user.session_version = (user.session_version or 0) + 1  # signs out other devices
        user.refresh_token = None
        db.session.commit()
        start_session(user)  # keep this browser signed in with the new version
        return {"message": "Password changed", "user": me_dict(user)}


class UserProfile(Resource):
    def get(self, user_id):
        user = db.session.get(UserModel, user_id)
        if user is None:
            return {"error": "User not found"}, 404
        viewer, _ = get_current_user()
        data = {**public_user(user), "is_me": bool(viewer and viewer.id == user.id)}
        if social_enabled():  # otherwise leave the fields out entirely, so clients hide them
            from app.api.social import profile_extras

            data.update(profile_extras(viewer, user))
        return data


class UserPlaylists(Resource):
    """A user's public playlists (all of them if it's you)."""

    def get(self, user_id):
        from app.api.music import playlist_dict

        user = db.session.get(UserModel, user_id)
        if user is None:
            return {"error": "User not found"}, 404
        viewer, _ = get_current_user()
        query = Playlist.query.filter_by(user_id=user.id)
        if not (viewer and viewer.id == user.id):
            query = query.filter_by(is_public=True)
        return {"items": [playlist_dict(p) for p in query.order_by(Playlist.id.desc()).all()]}
