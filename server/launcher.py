"""Standalone Burn server entry point used by the macOS bundle."""

from __future__ import annotations

import argparse

import uvicorn

from server.main import app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        log_level="warning",
        server_header=False,
    )


if __name__ == "__main__":
    main()
