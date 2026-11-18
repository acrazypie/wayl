from flask import Flask
from flask_login import LoginManager

from app.api import register_routes
from app.models import db
from app.models.user import UserModel
from app.routes.main import main_bp

from .utility import config, limiter

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
app.config["RATELIMIT_ENABLED"] = config.RATELIMIT_ENABLED
app.config["RATELIMIT_HEADERS_ENABLED"] = True
app.secret_key = config.SECRET_KEY

login_manager = LoginManager(app)


@login_manager.user_loader
def load_user(session_id):
    """Session ids look like "<user id>:<session version>"; a stale version means signed out."""
    try:
        user_id, version = str(session_id).split(":", 1)
        user = db.session.get(UserModel, int(user_id))
        if user is None or int(version) != (user.session_version or 0):
            return None
        return user
    except (TypeError, ValueError):
        return None


db.init_app(app)
limiter.init_app(app)


@app.errorhandler(429)
def too_many_requests(_error):
    return {"error": "Too many attempts. Please wait a bit and try again."}, 429


register_routes(app)

app.register_blueprint(main_bp)
