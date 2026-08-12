"""シナリオ条件評価用の乱数位置を保存・復元する codec。

確率条件は scenario event、reactive binding、player outcome rule が同じ
``random.Random`` を共有する。乱数位置を保存しないと、snapshot 再開後だけ
seed の先頭へ戻り、連続実行とは異なる出来事が発火する。
"""

from __future__ import annotations

import random
from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)


SUBSYSTEM_KEY = "scenario_predicate_rng"
SCHEMA_VERSION = 1


class ScenarioPredicateRngSubsystemCodec(WorldSubsystemCodec):
    """共有 ``random.Random`` の内部位置をJSON表現へ変換する。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        random_source = self._random_source(runtime)
        state_version, internal_state, gaussian_cache = random_source.getstate()
        return {
            "schema_version": SCHEMA_VERSION,
            "state_version": state_version,
            "internal_state": list(internal_state),
            "gaussian_cache": gaussian_cache,
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )

        state_version = data.get("state_version")
        internal_state = data.get("internal_state")
        gaussian_cache = data.get("gaussian_cache")
        if isinstance(state_version, bool) or not isinstance(state_version, int):
            raise ValueError(f"{SUBSYSTEM_KEY}.state_version must be int")
        if not isinstance(internal_state, list) or not internal_state:
            raise ValueError(f"{SUBSYSTEM_KEY}.internal_state must be non-empty list")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in internal_state):
            raise ValueError(f"{SUBSYSTEM_KEY}.internal_state must contain only int")
        if gaussian_cache is not None and (
            isinstance(gaussian_cache, bool)
            or not isinstance(gaussian_cache, (int, float))
        ):
            raise ValueError(
                f"{SUBSYSTEM_KEY}.gaussian_cache must be number or null"
            )

        restored_state = (state_version, tuple(internal_state), gaussian_cache)
        # 検証専用 instance に先に適用する。壊れた payload で本番の
        # 乱数位置を半端に変更しないため、対象は検証成功後にだけ更新する。
        validator = random.Random()
        try:
            validator.setstate(restored_state)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(f"{SUBSYSTEM_KEY} state is invalid: {exc}") from exc
        self._random_source(runtime).setstate(validator.getstate())

    @staticmethod
    def _random_source(runtime: Any) -> random.Random:
        random_source = getattr(runtime, "_scenario_predicate_random", None)
        if not isinstance(random_source, random.Random):
            raise RuntimeError(
                "runtime._scenario_predicate_random not found; "
                "ScenarioPredicateRngSubsystemCodec requires it"
            )
        return random_source


__all__ = [
    "ScenarioPredicateRngSubsystemCodec",
    "SUBSYSTEM_KEY",
    "SCHEMA_VERSION",
]
