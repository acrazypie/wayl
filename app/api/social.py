"""Social features between users of this instance: follows, feed, people search, followers'
view of listens. Registered only when WAYL_SOCIAL is on (see register_social_routes).

Core modules must not import this at module level; import inside functions, and only when
social_enabled() is true.
"""
from flask import g, request
from flask_restful import Resource
from sqlalchemy import desc

from app.models import db
from app.models.music import ListeningHistory
from app.models.social import Follow
from app.models.user import UserModel
from app.utility import auth_required, get_current_user, int_arg


def follow_counts(user):
    return {
        "followers": Follow.query.filter_by(followed_id=user.id).count(),
        "following": Follow.query.filter_by(follower_id=user.id).count(),
    }


def following_ids(viewer):
    if viewer is None:
        return set()
    return {row.followed_id for row in Follow.query.filter_by(follower_id=viewer.id).all()}


def can_see_listens(viewer, user):
    """Listens are visible to the owner and to their followers."""
    if viewer is None:
        return False
    if viewer.id == user.id:
        return True
    return Follow.query.filter_by(follower_id=viewer.id, followed_id=user.id).first() is not None


def profile_extras(viewer, user):
    """What the social layer adds to a user profile."""
    return {
        **follow_counts(user),
        "is_following": user.id in following_ids(viewer),
        "listens_visible": can_see_listens(viewer, user),
    }


class FeedList(Resource):
    """What the people you follow have been listening to."""

    @auth_required
    def get(self):
        from app.api.music import listens_for

        limit = int_arg("limit", 30, 1, 100)
        followed = db.session.query(Follow.followed_id).filter(Follow.follower_id == g.current_user.id)
        entries = (
            ListeningHistory.query.filter(ListeningHistory.user_id.in_(followed))
            .order_by(desc(ListeningHistory.listened_at), desc(ListeningHistory.id))
            .limit(limit)
            .all()
        )
        return {"items": listens_for(g.current_user, entries, with_user=True)}


class UserSearch(Resource):
    """Find people to follow by username. Requires sign-in; returns public fields only."""

    @auth_required
    def get(self):
        from app.api.user import public_user

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
        following = following_ids(me)
        return {"items": [{**public_user(u), "is_following": u.id in following} for u in users]}


class UserListens(Resource):
    """A user's recent listens. Only they and their followers can see them; to anyone else the
    list looks missing (404)."""

    def get(self, user_id):
        from app.api.music import listens_for

        user = db.session.get(UserModel, user_id)
        viewer, _ = get_current_user()
        if user is None or not can_see_listens(viewer, user):
            return {"error": "Not found"}, 404
        limit = int_arg("limit", 20, 1, 100)
        entries = (
            ListeningHistory.query.filter_by(user_id=user.id)
            .order_by(ListeningHistory.listened_at.desc(), ListeningHistory.id.desc())
            .limit(limit)
            .all()
        )
        return {"items": listens_for(viewer, entries)}


class FollowList(Resource):
    """/api/me/following and /api/me/followers"""

    def __init__(self, direction):
        self.direction = direction

    @auth_required
    def get(self):
        from app.api.user import public_user

        me = g.current_user
        if self.direction == "following":
            rows = db.session.query(UserModel).join(Follow, Follow.followed_id == UserModel.id).filter(Follow.follower_id == me.id)
        else:
            rows = db.session.query(UserModel).join(Follow, Follow.follower_id == UserModel.id).filter(Follow.followed_id == me.id)
        users = rows.order_by(Follow.created_at.desc()).all()
        following = following_ids(me)
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


def register_social_routes(add):
    """`add(resource, path, **kwargs)` is the route helper from app.api (adds /api/v1 too)."""
    add(FeedList, "/api/feed")
    add(UserSearch, "/api/users")
    add(UserListens, "/api/users/<int:user_id>/listens")
    add(FollowUser, "/api/users/<int:user_id>/follow")
    add(FollowList, "/api/me/following", endpoint="my_following", resource_class_args=("following",))
    add(FollowList, "/api/me/followers", endpoint="my_followers", resource_class_args=("followers",))
