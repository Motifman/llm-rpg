"""Spot graph SQLite 永続化の例外定義。"""

from __future__ import annotations


class SpotGraphPersistenceError(ValueError):
    """スポットグラフ永続化の基底例外。"""


class SpotGraphSnapshotNotInitializedError(SpotGraphPersistenceError):
    """スポットグラフのスナップショットが未初期化。"""


class SpotGraphStateDecodeError(SpotGraphPersistenceError):
    """保存済み payload を復元できない。"""


class UnsupportedSpotGraphAggregateSchemaError(SpotGraphStateDecodeError):
    """SpotGraphAggregate の schema_version が非対応。"""


class UnsupportedSpotInteriorSchemaError(SpotGraphStateDecodeError):
    """SpotInterior の schema_version が非対応。"""


class SpotGraphConnectionRecordInvariantError(SpotGraphStateDecodeError):
    """接続レコードの双方向ペア情報が壊れている。"""


__all__ = [
    "SpotGraphConnectionRecordInvariantError",
    "SpotGraphPersistenceError",
    "SpotGraphSnapshotNotInitializedError",
    "SpotGraphStateDecodeError",
    "UnsupportedSpotGraphAggregateSchemaError",
    "UnsupportedSpotInteriorSchemaError",
]
