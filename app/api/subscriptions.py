"""Subscribing: follow share links from other WAYL instances (or this one)."""
from flask import g
from flask_restful import Resource

from app.models import db
from app.models.sharing import Subscription
from app.services import catalog
from app.services.remote_share import ShareError
from app.services.subscriptions import (
    copy_to_playlist,
    open_playlist,
    refresh,
    subscribe,
    subscription_detail,
    subscription_summary,
)
from app.utility import auth_required, json_body, limiter


def _mine(sub_id):
    sub = db.session.get(Subscription, sub_id)
    if sub is None or sub.user_id != g.current_user.id:
        return None
    return sub


NOT_FOUND = {"error": "Subscription not found"}, 404


class SubscriptionList(Resource):
    @auth_required
    def get(self):
        subs = (
            Subscription.query.filter_by(user_id=g.current_user.id, parent_id=None)
            .order_by(Subscription.created_at.desc(), Subscription.id.desc())
            .all()
        )
        return {"items": [subscription_summary(s) for s in subs]}

    @auth_required
    @limiter.limit("30 per hour")
    def post(self):
        """{"url": "<share link>"}: fetched right away; 201 new, 200 if you already had it."""
        url = json_body().get("url")
        if not isinstance(url, str) or not url.strip():
            return {"error": "Paste a share link"}, 400
        try:
            sub, created = subscribe(g.current_user, url)
        except ShareError as exc:
            return {"error": str(exc)}, 400
        return subscription_summary(sub), 201 if created else 200


class SubscriptionDetail(Resource):
    @auth_required
    def get(self, sub_id):
        sub = _mine(sub_id)
        return subscription_detail(g.current_user, sub) if sub else NOT_FOUND

    @auth_required
    def delete(self, sub_id):
        sub = _mine(sub_id)
        if sub is None:
            return NOT_FOUND
        Subscription.query.filter_by(user_id=g.current_user.id, parent_id=sub.id).delete()
        db.session.delete(sub)
        db.session.commit()
        return {"message": "Removed"}


class SubscriptionRefresh(Resource):
    decorators = [limiter.limit("30 per hour")]

    @auth_required
    def post(self, sub_id):
        sub = _mine(sub_id)
        if sub is None:
            return NOT_FOUND
        refresh(sub)
        return subscription_detail(g.current_user, sub)


class SubscriptionOpen(Resource):
    """POST {"url": "<playlist link from this profile>"}: open one of a profile's playlists."""

    decorators = [limiter.limit("120 per hour")]

    @auth_required
    def post(self, sub_id):
        sub = _mine(sub_id)
        if sub is None or sub.kind != "profile":
            return NOT_FOUND
        try:
            child = open_playlist(g.current_user, sub, str(json_body().get("url") or ""))
        except ShareError as exc:
            return {"error": str(exc)}, 400
        return subscription_detail(g.current_user, child)


class SubscriptionCopy(Resource):
    """POST: copy a subscribed playlist into your playlists. For a profile, pass the
    {"playlist_url"} of one of its playlists."""

    decorators = [limiter.limit("30 per hour")]

    @auth_required
    def post(self, sub_id):
        sub = _mine(sub_id)
        if sub is None:
            return NOT_FOUND
        try:
            if sub.kind == "profile":
                sub = open_playlist(g.current_user, sub, str(json_body().get("playlist_url") or ""))
            playlist, skipped = copy_to_playlist(g.current_user, sub)
        except ShareError as exc:
            return {"error": str(exc)}, 400
        except catalog.CatalogError:
            db.session.rollback()
            return {"error": "The music database is not responding right now. Try again in a moment."}, 502
        return {"message": f"Copied to “{playlist.name}”", "playlist_id": playlist.id, "skipped": skipped}, 201
