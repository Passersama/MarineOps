"""Business vocabulary and rules, independent of Qt and SQLite."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class Status(StrEnum):
    WAITING = "Waiting"
    ON_BOARD = "On Board"
    DONE = "Done"


class AppError(Exception):
    """An expected error safe for the UI to explain."""

    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def business_date(utc_time: str, timezone_name: str) -> str:
    try:
        zone = ZoneInfo(timezone_name)
        moment = datetime.fromisoformat(utc_time.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            raise ValueError("timestamp must include a UTC offset")
        return moment.astimezone(zone).strftime("%Y%m%d")
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise AppError("INVALID_TIMEZONE", f"Invalid business time zone: {timezone_name}") from exc


def normalized_name(value: str) -> str:
    return " ".join(value.split()).casefold()


@dataclass(frozen=True, slots=True)
class Command:
    command_id: str
    operation: str
    payload: dict


@dataclass(frozen=True, slots=True)
class Receipt:
    command_id: str
    operation: str
    result: dict
    revision: int

