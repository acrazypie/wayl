"""Email + password authentication with password reset by email.

Browsers get the Flask-Login session cookie. API clients can pass {"tokens": true} to
/auth/login to also receive a Bearer access token and a refresh token.
"""
import re

from flask import session
from flask_login import login_user, logout_user
from flask_restful import Resource
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import db
from app.models.user import UserModel
from app.utility import (
    config,
    create_jwt,
    hash_token,
    json_body,
    json_only,
    limiter,
    user_from_jwt_payload,
    verify_jwt,
)
from app.utility.mail import send_email

ACCESS_TTL = 60 * 60  # 1 hour
REFRESH_TTL = 60 * 60 * 24 * 30  # 30 days

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{2,30}$")
PASSWORD_MIN, PASSWORD_MAX = 8, 128

# Hash checked when the email is unknown, so a wrong email takes as long as a wrong password.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def normalize_email(value):
    return str(value or "").strip().lower()[:255]


def validate_username(username, *, exclude_id=None):
    if not USERNAME_RE.match(username):
        return "Username must be 2-30 characters: letters, numbers, _ or ."
    q = UserModel.query.filter(db.func.lower(UserModel.username) == username.lower())
    if exclude_id is not None:
        q = q.filter(UserModel.id != exclude_id)
    if q.first():
        return "That username is taken"
    return None


def validate_password(password):
    if not isinstance(password, str) or not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        return f"Password must be {PASSWORD_MIN}-{PASSWORD_MAX} characters"
    return None


def me_dict(user):
    """The signed-in user's own view of their account (includes email)."""
    from app.api.user import public_user

    return {**public_user(user), "email": user.email}


def start_session(user, remember=True):
    session.clear()  # new session id on login: no session fixation
    login_user(user, remember=remember)


# --- password reset tokens --------------------------------------------------------


def _reset_serializer():
    return URLSafeTimedSerializer(config.SECRET_KEY, salt="wayl-password-reset")


def make_reset_token(user):
    # Tied to the current session_version: once the password changes, the link stops working.
    return _reset_serializer().dumps({"uid": user.id, "v": user.session_version or 0})


def user_from_reset_token(token):
    try:
        data = _reset_serializer().loads(token, max_age=config.PASSWORD_RESET_MAX_AGE)
    except (SignatureExpired, BadSignature):
        return None
    if not isinstance(data, dict):
        return None
    user = db.session.get(UserModel, data.get("uid")) if isinstance(data.get("uid"), int) else None
    if user is None or data.get("v") != (user.session_version or 0):
        return None
    return user


# --- resources --------------------------------------------------------------------


class SessionInfo(Resource):
    """GET /auth/session: who is signed in ({"user": null} when nobody). Never 401, so the
    page can check on load without an error showing up in the browser console."""

    def get(self):
        from app.utility import get_current_user

        user, _ = get_current_user()
        return {"user": me_dict(user) if user else None}


class Register(Resource):
    decorators = [json_only, limiter.limit("10 per hour")]

    def post(self):
        data = json_body()
        email = normalize_email(data.get("email"))
        username = str(data.get("username") or "").strip()
        password = data.get("password")

        if not EMAIL_RE.match(email):
            return {"error": "Enter a valid email address"}, 400
        error = validate_username(username) or validate_password(password)
        if error:
            return {"error": error}, 400
        if UserModel.query.filter_by(email=email).first():
            return {"error": "An account with this email already exists. Try signing in."}, 409

        user = UserModel(email=email, username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        start_session(user)
        return {"message": "Welcome to WAYL!", "user": me_dict(user)}, 201


class Login(Resource):
    decorators = [json_only, limiter.limit("10 per minute; 50 per hour")]

    def post(self):
        data = json_body()
        email = normalize_email(data.get("email"))
        password = data.get("password")
        user = UserModel.query.filter_by(email=email).first() if email else None

        if not isinstance(password, str) or not password:
            return {"error": "Incorrect email or password"}, 401
        if user is None:
            check_password_hash(_DUMMY_HASH, password)
        if user is None or not user.check_password(password):
            return {"error": "Incorrect email or password"}, 401

        start_session(user, remember=bool(data.get("remember", True)))
        body = {"message": "Signed in", "user": me_dict(user)}
        if data.get("tokens"):
            refresh_token = create_jwt(user, REFRESH_TTL, refresh=True)
            user.refresh_token = hash_token(refresh_token)
            db.session.commit()
            body["access_token"] = create_jwt(user, ACCESS_TTL)
            body["refresh_token"] = refresh_token
        return body


class Logout(Resource):
    decorators = [json_only]

    def post(self):
        # Clear first: logout_user() leaves a flag in the session that deletes the remember-me
        # cookie, and clearing afterwards would wipe that flag and keep the user signed in.
        session.clear()
        logout_user()
        return {"message": "Signed out"}


class ForgotPassword(Resource):
    decorators = [json_only, limiter.limit("5 per hour")]

    def post(self):
        email = normalize_email(json_body().get("email"))
        if not EMAIL_RE.match(email):
            return {"error": "Enter a valid email address"}, 400
        user = UserModel.query.filter_by(email=email).first()
        if user:
            link = f"{config.APP_URL}/reset?token={make_reset_token(user)}"
            minutes = config.PASSWORD_RESET_MAX_AGE // 60
            send_email(
                user.email,
                "Reset your WAYL password",
                f"Hi {user.username},\n\n"
                f"Someone (hopefully you) asked to reset your WAYL password. "
                f"Open this link to choose a new one. It works once and expires in {minutes} minutes:\n\n"
                f"{link}\n\n"
                "If you didn't ask for this, you can ignore this email; your password won't change.\n",
            )
        # Same answer either way, so this can't be used to find out who has an account.
        return {"message": "If an account exists for that email, we've sent a link to reset the password."}


class ResetPassword(Resource):
    decorators = [json_only, limiter.limit("10 per hour")]

    def post(self):
        data = json_body()
        token = data.get("token")
        user = user_from_reset_token(token) if isinstance(token, str) else None
        if user is None:
            return {"error": "This reset link is invalid or has expired. Request a new one."}, 400
        error = validate_password(data.get("password"))
        if error:
            return {"error": error}, 400

        user.set_password(data["password"])
        user.session_version = (user.session_version or 0) + 1  # signs out every other session
        user.refresh_token = None
        db.session.commit()
        start_session(user)
        return {"message": "Password updated. You're signed in.", "user": me_dict(user)}


class RefreshToken(Resource):
    decorators = [limiter.limit("30 per hour")]

    def post(self):
        token = json_body().get("refresh_token")
        payload = verify_jwt(token, expected_type="refresh") if isinstance(token, str) else None
        user = user_from_jwt_payload(payload) if payload else None
        if not user or user.refresh_token != hash_token(token):
            return {"error": "Invalid or expired refresh token"}, 401
        return {"access_token": create_jwt(user, ACCESS_TTL)}
