"""chunk を構成する action 群から prediction_context_id を集める (U1)。

同期経路 (``EpisodicChunkCoordinator``) と非同期経路の両方が
``PREDICTION_OUTCOME`` の trace に載せるため、ここに集約する。

想起の信用割り当て (外れのずれの書き添えと、的中の回数) を確定した予期から返して
いた受け取る側は #1631 で消した。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def prediction_context_ids_from_actions(actions: Iterable[Any]) -> list[str]:
    """chunk を構成する action 群から prediction_context_id を重複排除して集める。

    id 機構が OFF (= 発行された id が 1 つも無い) のときは
    空リストを返す。
    """
    ids: list[str] = []
    try:
        for action in actions:
            pid = getattr(action, "prediction_context_id", None)
            if pid and pid not in ids:
                ids.append(pid)
    except Exception:
        return []
    return ids


__all__ = ["prediction_context_ids_from_actions"]
