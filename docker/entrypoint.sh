#!/bin/sh
# web    -> apply database migrations, then serve the app with gunicorn
# worker -> background sync with Plex / Navidrome
# other  -> run that command (e.g. "flask db upgrade", "sh")
set -e

case "$1" in
    web)
        flask db upgrade
        exec gunicorn --config docker/gunicorn.conf.py app:app
        ;;
    worker)
        exec python -m app.worker
        ;;
    *)
        exec "$@"
        ;;
esac
