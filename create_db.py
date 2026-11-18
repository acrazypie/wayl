"""Create or update the database tables (same as `flask --app app db upgrade`)."""
from flask_migrate import upgrade

from app import app

with app.app_context():
    upgrade()
    print("Database is up to date.")
