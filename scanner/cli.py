"""
CLI entry point.

Usage:
  tv-scanner worker          # Start the scanner worker
  tv-scanner dashboard       # Start the FastAPI dashboard
  tv-scanner self-test       # Run smoke tests
"""

from __future__ import annotations

import asyncio
import sys

import typer

app = typer.Typer(name="tv-scanner", help="Live US stock scanner CLI")


@app.command()
def worker(
    config: str = typer.Option("", help="Path to YAML config file"),
) -> None:
    """Start the scanner worker process."""
    from .config import load_config
    from .worker import ScannerWorker
    import structlog

    structlog.configure()
    cfg = load_config(config or None)
    w = ScannerWorker(cfg)
    asyncio.run(w.run())


@app.command()
def dashboard(
    host: str = typer.Option("", help="Override dashboard host"),
    port: int = typer.Option(0, help="Override dashboard port"),
    config: str = typer.Option("", help="Path to YAML config file"),
) -> None:
    """Start the FastAPI dashboard (read-only)."""
    import uvicorn
    from .config import load_config

    cfg = load_config(config or None)
    h = host or cfg.dashboard.host
    p = port or cfg.dashboard.port

    uvicorn.run(
        "scanner.api.routes:app",
        host=h,
        port=p,
        log_level="info",
    )


@app.command(name="self-test")
def self_test() -> None:
    """Run smoke tests."""
    from tests.smoke_test import run_smoke_tests
    run_smoke_tests()


if __name__ == "__main__":
    app()
