from __future__ import annotations

import asyncio
import logging

from config import load_config
from polygon_provider import PolygonProvider
from scanner import Scanner
from state_store import StateStore


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def _main() -> None:
    setup_logging()
    config = load_config()
    provider = PolygonProvider(api_key=config.polygon_api_key)
    state_store = StateStore(config.sqlite_path)
    scanner = Scanner(config, provider, state_store)
    try:
        await scanner.run()
    finally:
        state_store.close()


if __name__ == "__main__":
    asyncio.run(_main())
