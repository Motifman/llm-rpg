"""Helpers for storing Python objects as SQLite BLOB snapshots."""

from __future__ import annotations

import pickle
from typing import TypeVar

T = TypeVar("T")


def object_to_blob(value: T) -> bytes:
    return pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)


def blob_to_object(blob: bytes) -> T:
    return pickle.loads(blob)


__all__ = ["blob_to_object", "object_to_blob"]
