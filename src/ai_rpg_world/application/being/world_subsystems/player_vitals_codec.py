"""Player vitals (HP / MP / Stamina / Gold) subsystem codec (Phase 9-2)。

PlayerStatusAggregate の内部 ``_hp`` / ``_mp`` / ``_stamina`` / ``_gold`` を
直接 save / restore する。``is_down`` も含める (= 「死亡判定済」を保持)。

restore は ``PlayerStatusAggregate`` の private 属性を直接書き換えてから
``_player_status_repo.save(aggregate)`` で永続化する経路を取る (= setter
経路だと event 発火が起きる場合があるため)。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

SUBSYSTEM_KEY = "player_vitals"
SCHEMA_VERSION = 1


class PlayerVitalsSubsystemCodec(WorldSubsystemCodec):
    """各 player の vitals (HP / MP / Stamina / Gold / is_down) を JSON 化。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        repo = getattr(runtime, "_player_status_repo", None)
        if repo is None:
            raise RuntimeError(
                "runtime._player_status_repo not found; "
                "PlayerVitalsSubsystemCodec requires it"
            )
        entries: list[dict[str, Any]] = []
        for pid in runtime.get_player_ids():
            agg = repo.find_by_id(pid)
            if agg is None:
                continue
            # 内部 VO から value 抜き出し。``hp.max_hp`` 等の max は base_stats
            # 由来で scenario 初期化時に決まるが、growth で増えうるので一緒に
            # 保存する (= scenario 共通の base_stats とは独立な「現時点の値」)。
            entries.append(
                {
                    "player_id": int(pid.value),
                    "hp_value": int(agg._hp.value),
                    "hp_max": int(agg._hp.max_hp),
                    "mp_value": int(agg._mp.value),
                    "mp_max": int(agg._mp.max_mp),
                    "stamina_value": int(agg._stamina.value),
                    "stamina_max": int(agg._stamina.max_stamina),
                    "gold_value": int(agg._gold.value),
                    "is_down": bool(agg._is_down),
                }
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "entries": entries,
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )
        from ai_rpg_world.domain.player.value_object.gold import Gold
        from ai_rpg_world.domain.player.value_object.hp import Hp
        from ai_rpg_world.domain.player.value_object.mp import Mp
        from ai_rpg_world.domain.player.value_object.stamina import Stamina
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        repo = getattr(runtime, "_player_status_repo", None)
        if repo is None:
            raise RuntimeError(
                "runtime._player_status_repo not found; "
                "PlayerVitalsSubsystemCodec requires it"
            )
        for entry in data.get("entries", []):
            pid = PlayerId(int(entry["player_id"]))
            agg = repo.find_by_id(pid)
            if agg is None:
                # scenario の初期 spawn にいなかった player はスキップ
                # (= 通常起き得ないが、防御的にログだけにする)
                continue
            # 直接 private 属性を上書き (= constructor を通すと event 発行や
            # invariant チェックが入りうるので、snapshot restore は state を
            # 「すり替える」semantics で扱う)。
            agg._hp = Hp(
                value=int(entry["hp_value"]),
                max_hp=int(entry["hp_max"]),
            )
            agg._mp = Mp(
                value=int(entry["mp_value"]),
                max_mp=int(entry["mp_max"]),
            )
            agg._stamina = Stamina(
                value=int(entry["stamina_value"]),
                max_stamina=int(entry["stamina_max"]),
            )
            agg._gold = Gold(value=int(entry["gold_value"]))
            agg._is_down = bool(entry["is_down"])
            # restore 中の add_event を抑える: 内部 events 列をクリア
            # (= base AggregateRoot に events 蓄積がある場合)。
            if hasattr(agg, "_events"):
                agg._events.clear()
            repo.save(agg)


__all__ = ["PlayerVitalsSubsystemCodec", "SUBSYSTEM_KEY", "SCHEMA_VERSION"]
