from flask import g, request, session
from flask_login import logout_user
from flask_restful import Resource
from sqlalchemy import or_

from app.models import db
from app.models.music import ListeningHistory, Playlist, SavedSong
from app.models.user import Follow, UserModel
from app.utility import auth_required, get_current_user, int_arg, iso, json_body, limiter


def public_user(user):
    """The only user fields other people may see. Never include email here."""
    return {"id": user.id, "username": user.username, "bio": user.bio, "joined_at": iso(user.created_at)}


def _follow_counts(user):
    return {
        "followers": Follow.query.filter_by(followed_id=user.id).count(),
        "following": Follow.query.filter_by(follower_id=user.id).count(),
    }


def _following_ids(viewer):
    if viewer is None:
        return set()
    return {row.followed_id for row in Follow.query.filter_by(follower_id=viewer.id).all()}


def _can_see_listens(viewer, user):
    """Listens are visible to the owner and to their followers."""
    if viewer is None:
        return False
    if viewer.id == user.id:
        return True
    return Follow.query.filter_by(follower_id=viewer.id, followed_id=user.id).first() is not None


class Me(Resource):
    @auth_required
    def get(self):
        from app.api.auth import me_dict

        user = g.current_user
        return {
            **me_dict(user),
            **_follow_counts(user),
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
        Follow.query.filter(or_(Follow.follower_id == uid, Follow.followed_id == uid)).delete(
            synchronize_session=False
        )
        ListeningHistory.query.filter_by(user_id=uid).delete(synchronize_session=False)
        SavedSong.query.filter_by(user_id=uid).delete(synchronize_session=False)
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


class UserSearch(Resource):
    """Find people to follow by username. Requires sign-in; returns public fields only."""

    @auth_required
    def get(self):
        me = g.current_user
        q = request.args.get("q", "").strip()[:40]
        if len(q) < 2:
            return {"items": []}
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        users = (
            UserModel.query.filter(UserModel.username.ilike(pattern, escape="\\"), UserModel.id != me.id)
            .order_by(UserModel.username)
            .limit(20)
            .all()
        )
        following = _following_ids(me)
        return {"items": [{**public_user(u), "is_following": u.id in following} for u in users]}


class UserProfile(Resource):
    def get(self, user_id):
        user = db.session.get(UserModel, user_id)
        if user is None:
            return {"error": "User not found"}, 404
        viewer, _ = get_current_user()
        return {
            **public_user(user),
            **_follow_counts(user),
            "is_me": bool(viewer and viewer.id == user.id),
            "is_following": user.id in _following_ids(viewer),
            "listens_visible": _can_see_listens(viewer, user),
        }


class UserListens(Resource):
    """A user's recent listens. Only they and their followers can see them; to anyone else the
    list looks missing (404)."""

    def get(self, user_id):
        user = db.session.get(UserModel, user_id)
        viewer, _ = get_current_user()
        if user is None or not _can_see_listens(viewer, user):
            return {"error": "Not found"}, 404
        limit = int_arg("limit", 20, 1, 100)
        entries = (
            ListeningHistory.query.filter_by(user_id=user.id)
            .order_by(ListeningHistory.listened_at.desc(), ListeningHistory.id.desc())
            .limit(limit)
            .all()
        )
        from app.api.music import listens_for

        return {"items": listens_for(viewer, entries)}


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


class FollowList(Resource):
    """/api/me/following and /api/me/followers"""

    def __init__(self, direction):
        self.direction = direction

    @auth_required
    def get(self):
        me = g.current_user
        if self.direction == "following":
            rows = (
                db.session.query(UserModel)
                .join(Follow, Follow.followed_id == UserModel.id)
                .filter(Follow.follower_id == me.id)
            )
        else:
            rows = (
                db.session.query(UserModel)
                .join(Follow, Follow.follower_id == UserModel.id)
                .filter(Follow.followed_id == me.id)
            )
        users = rows.order_by(Follow.created_at.desc()).all()
        following = _following_ids(me)
        return {"items": [{**public_user(u), "is_following": u.id in following} for u in users]}


class FollowUser(Resource):
    @auth_required
    def post(self, user_id):
        me = g.current_user
        if user_id == me.id:
            return {"error": "You cannot follow yourself"}, 400
        if db.session.get(UserModel, user_id) is None:
            return {"error": "User not found"}, 404
        if not Follow.query.filter_by(follower_id=me.id, followed_id=user_id).first():
            db.session.add(Follow(follower_id=me.id, followed_id=user_id))
            db.session.commit()
        return {"is_following": True}

    @auth_required
    def delete(self, user_id):
        Follow.query.filter_by(follower_id=g.current_user.id, followed_id=user_id).delete()
        db.session.commit()
        return {"is_following": False}
