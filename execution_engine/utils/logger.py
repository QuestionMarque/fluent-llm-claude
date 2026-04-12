"""Simple structured logger for execution tracing.

Extension hook: swap this for structlog or loguru when productizing.
"""
import datetime
from typing import Any


def _log(level: str, message: str, **context: Any) -> None:
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    ctx_str = " ".join(f"{k}={v!r}" for k, v in context.items())
    line = f"[{ts}] [{level.upper():5}] {message}"
    if ctx_str:
        line += f" | {ctx_str}"
    print(line)


def info(message: str, **context: Any) -> None:
    _log("info", message, **context)


def warning(message: str, **context: Any) -> None:
    _log("warn", message, **context)


def error(message: str, **context: Any) -> None:
    _log("error", message, **context)


def debug(message: str, **context: Any) -> None:
    _log("debug", message, **context)
