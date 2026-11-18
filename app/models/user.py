from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import db, utcnow


class UserModel(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)  # stored lowercased
    username = db.Column(db.String(30), unique=True, nullable=False)
    bio = db.Column(db.String(160), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    # Bumped on password change/reset: invalidates other sessions, JWTs and reset links.
    session_version = db.Column(db.Integer, nullable=False, default=0)
    refresh_token = db.Column(db.String(500), nullable=True)  # sha256 of the refresh JWT
    created_at = db.Column(db.DateTime, default=utcnow)

    playlists = db.relationship("Playlist", backref="user", lazy=True)
    history = db.relationship("ListeningHistory", backref="user", lazy=True)

    def __repr__(self) -> str:
        return f"User(id={self.id}, username={self.username})"

    def get_id(self):
        # Stored in the session cookie; the version part logs out old sessions after a reset.
        return f"{self.id}:{self.session_version or 0}"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password) -> bool:
        return bool(self.password_hash) and check_password_hash(self.password_hash, password)

