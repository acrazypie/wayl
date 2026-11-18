"""Background worker: keeps connected media servers in sync.

    python -m app.worker          # loop forever (what the Docker "worker" service runs)
    python -m app.worker --once   # one round, then exit (handy for cron or debugging)
"""
import logging
import signal
import sys
import time

from app import app
from app.services.sync import run_round
from app.utility import config

log = logging.getLogger("wayl.worker")


def _stop(signum, _frame):
    log.info("Stopping (signal %s)", signum)
    raise SystemExit(0)


def main(argv):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # As PID 1 in a container, Python gets no default SIGTERM handler: stop cleanly on
    # `docker compose stop` instead of being killed after the timeout.
    signal.signal(signal.SIGTERM, _stop)
    once = "--once" in argv
    log.info("WAYL worker started (every %ss)", config.WORKER_INTERVAL)
    while True:
        started = time.monotonic()
        with app.app_context():
            try:
                run_round()
            except Exception:  # keep the loop alive (e.g. tables not created yet on first start)
                log.exception("Worker round failed")
        if once:
            return
        time.sleep(max(5, config.WORKER_INTERVAL - (time.monotonic() - started)))


if __name__ == "__main__":
    main(sys.argv[1:])
