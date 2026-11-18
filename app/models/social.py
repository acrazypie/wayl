"""Social features (follows between users of this instance). Optional: see WAYL_SOCIAL.

The model is always imported (app/__init__.py) so Alembic keeps seeing the `follows` table,
whether or not the social routes are switched on.
"""
from app.models import db, utcnow


class Follow(db.Model):
    __tablename__ = "follows"
    __table_args__ = (db.UniqueConstraint("follower_id", "followed_id"),)

    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    followed_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow)
