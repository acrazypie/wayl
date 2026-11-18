from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow():
    """Naive UTC timestamp (what the DB stores). Pass as `default=utcnow`, without parentheses."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
