"""MISSMINUTES entry point.

Usage:
    python main.py                      # default config
    python main.py --host 0.0.0.0       # custom bind
    python main.py --port 9000          # custom port
    python main.py --headless           # CI / fake providers only
    python main.py --config path.toml   # custom config file
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="MISSMINUTES AI agent")
    parser.add_argument("--host", default=None, help="Bind host (default: from config)")
    parser.add_argument("--port", type=int, default=None, help="Bind port (default: from config)")
    parser.add_argument("--config", default=None, help="Path to TOML config file")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run with all fake providers (no API keys needed)",
    )
    args = parser.parse_args()

    from app.config.settings import load_config
    from app.runtime.runtime import MissMinutesRuntime

    _project_root = Path(__file__).resolve().parent.parent
    config_path = Path(args.config) if args.config is not None else _project_root / "config" / "missminutes.toml"
    config = load_config(path=config_path)

    # CLI overrides
    if args.host is not None:
        config.app.host = args.host
    if args.port is not None:
        config.app.port = args.port

    # Configure logging
    log_level = config.app.log_level.upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("missminutes")

    if args.headless:
        runtime = MissMinutesRuntime.create_headless(config)
        logger.info("Running in headless mode (all fakes)")
    else:
        runtime = MissMinutesRuntime(config)

    import uvicorn

    from app.api.app import create_app

    app_instance = create_app(runtime=runtime)

    def _handle_signal(signum: int, _frame: object) -> None:
        logger.info("Received signal %s, shutting down...", signum)
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    host = config.app.host
    port = config.app.port
    logger.info("Starting MISSMINUTES on %s:%d", host, port)

    uvicorn.run(
        app_instance,
        host=host,
        port=port,
        log_level=log_level.lower(),
    )


if __name__ == "__main__":
    main()
