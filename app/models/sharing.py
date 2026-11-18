"""Sharing between WAYL instances: what you publish (ShareSettings, Playlist.share_token) and
what you follow from other instances (Subscription). See docs/sharing-protocol.md."""
from app.models import db, utcnow


class ShareSettings(db.Model):
    """Your public profile link and what it includes. No row = never set up = not shared."""

    __tablename__ = "share_settings"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    profile_share_token = db.Column(db.String(32), unique=True, nullable=True)  # None = profile not shared
    share_listens = db.Column(db.Boolean, nullable=False, default=False)
    share_top_artists = db.Column(db.Boolean, nullable=False, default=False)
    display_name = db.Column(db.String(60), nullable=True)  # None = username
    user = db.relationship("UserModel")


class Subscription(db.Model):
    """A share document from another instance that you follow, with its last good copy.

    Playlists opened from a subscribed profile are cached as child rows (parent_id set); they
    don't appear in the subscriptions list and are deleted with their parent.
    """

    __tablename__ = "subscriptions"
    __table_args__ = (db.UniqueConstraint("user_id", "url"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("subscriptions.id"), nullable=True, index=True)
    url = db.Column(db.String(500), nullable=False)  # normalized share URL
    kind = db.Column(db.String(20), nullable=False)  # "playlist" | "profile"
    title = db.Column(db.String(300), nullable=False)
    owner_name = db.Column(db.String(60), nullable=True)
    payload = db.Column(db.Text, nullable=False)  # last good, validated document (JSON)
    etag = db.Column(db.String(200), nullable=True)
    last_modified = db.Column(db.String(100), nullable=True)
    fetched_at = db.Column(db.DateTime, nullable=True)  # last successful fetch (200 or 304)
    checked_at = db.Column(db.DateTime, nullable=True)  # last attempt, for the error backoff
    last_error = db.Column(db.String(300), nullable=True)
    error_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=utcnow)
