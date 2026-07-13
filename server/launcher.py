"""Start Burn locally and open its browser interface."""

from __future__ import annotations

import argparse
import contextlib
import json
import signal
import threading
import time
import urllib.error
import urllib.request
import webbrowser

import uvicorn
from uvicorn.server import HANDLED_SIGNALS

from server import main as burn_main

DEFAULT_PORT = 8765
STARTUP_TIMEOUT_SECONDS = 20
IDLE_TIMEOUT_SECONDS = 10 * 60


class BurnServer(uvicorn.Server):
    """Uvicorn server that shuts down cleanly without replaying Ctrl+C."""

    @contextlib.contextmanager
    def capture_signals(self):
        if threading.current_thread() is not threading.main_thread():
            yield
            return
        original_handlers = {
            handled: signal.signal(handled, self.handle_exit)
            for handled in HANDLED_SIGNALS
        }
        try:
            yield
        finally:
            for handled, original in original_handlers.items():
                signal.signal(handled, original)


def _burn_is_ready(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/health", timeout=1
        ) as response:
            payload = json.load(response)
        return payload.get("status") == "ok" and payload.get("app", "burn") == "burn"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def _open_when_ready(port: int, server: uvicorn.Server) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline and not server.should_exit:
        if _burn_is_ready(port):
            webbrowser.open(f"http://127.0.0.1:{port}/", new=2)
            return
        time.sleep(0.1)
    server.should_exit = True


def _stop_when_idle(server: uvicorn.Server, timeout: int) -> None:
    while not server.should_exit:
        if burn_main.seconds_since_browser_activity() >= timeout:
            server.should_exit = True
            return
        time.sleep(min(5, timeout))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Open the private Burn dashboard in your default browser."
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="start the local server without opening a browser tab",
    )
    parser.add_argument(
        "--idle-timeout",
        type=int,
        default=IDLE_TIMEOUT_SECONDS,
        help="stop after this many seconds without a browser heartbeat; 0 disables",
    )
    args = parser.parse_args()

    if not args.no_browser and _burn_is_ready(args.port):
        webbrowser.open(f"http://127.0.0.1:{args.port}/", new=2)
        return

    config = uvicorn.Config(
        burn_main.app,
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        log_level="warning",
        server_header=False,
    )
    server = BurnServer(config)
    if not args.no_browser:
        threading.Thread(
            target=_open_when_ready, args=(args.port, server), daemon=True
        ).start()
    if args.idle_timeout > 0:
        threading.Thread(
            target=_stop_when_idle, args=(server, args.idle_timeout), daemon=True
        ).start()
    try:
        server.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
