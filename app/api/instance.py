from flask_restful import Resource

from app.utility import limiter, social_enabled
from app.version import API_VERSION, APP_VERSION


class InstanceInfo(Resource):
    """GET /api/instance: what this WAYL instance is and which features it has on. Public, so
    clients (the web app, a future mobile app, other instances) can adapt before signing in."""

    decorators = [limiter.limit("120 per minute")]

    def get(self):
        return {
            "name": "WAYL",
            "version": APP_VERSION,
            "api_version": API_VERSION,
            "features": {"social": social_enabled(), "sharing": True, "streaming": True},
        }
