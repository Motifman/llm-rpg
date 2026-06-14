"""Player growth + stats subsystem codec (Phase 9-2b)。

PlayerStatusAggregate の以下フィールドを JSON 化:
- ``_base_stats`` (BaseStats: max_hp / max_mp / attack / defense / speed /
  critical_rate / evasion_rate)
- ``_stat_growth_factor`` (StatGrowthFactor: 7 つの factor)
- ``_exp_table`` (ExpTable: base_exp / exponent / level_offset)
- ``_growth`` (Growth: level / total_exp + exp_table 参照)

scenario が「経験値で成長する」設計なら必須。scenario が固定の場合でも
base_stats は scenario 初期化時に決まるので、復元しないと dst run が
初期値に戻ってしまう。

すべて frozen dataclass の simple value object なので、フィールド単位で
JSON 化 / 再構築する。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

SUBSYSTEM_KEY = "player_growth"
SCHEMA_VERSION = 1


class PlayerGrowthSubsystemCodec(WorldSubsystemCodec):
    """各 player の base_stats / stat_growth_factor / exp_table / growth を JSON 化。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        repo = getattr(runtime, "_player_status_repo", None)
        if repo is None:
            raise RuntimeError(
                "runtime._player_status_repo not found; "
                "PlayerGrowthSubsystemCodec requires it"
            )
        entries: list[dict[str, Any]] = []
        for pid in runtime.get_player_ids():
            agg = repo.find_by_id(pid)
            if agg is None:
                continue
            bs = agg._base_stats
            gf = agg._stat_growth_factor
            et = agg._exp_table
            gr = agg._growth
            entries.append(
                {
                    "player_id": int(pid.value),
                    "base_stats": {
                        "max_hp": int(bs.max_hp),
                        "max_mp": int(bs.max_mp),
                        "attack": int(bs.attack),
                        "defense": int(bs.defense),
                        "speed": int(bs.speed),
                        "critical_rate": float(bs.critical_rate),
                        "evasion_rate": float(bs.evasion_rate),
                    },
                    "stat_growth_factor": {
                        "hp_factor": float(gf.hp_factor),
                        "mp_factor": float(gf.mp_factor),
                        "attack_factor": float(gf.attack_factor),
                        "defense_factor": float(gf.defense_factor),
                        "speed_factor": float(gf.speed_factor),
                        "critical_rate_factor": float(gf.critical_rate_factor),
                        "evasion_rate_factor": float(gf.evasion_rate_factor),
                    },
                    "exp_table": {
                        "base_exp": float(et.base_exp),
                        "exponent": float(et.exponent),
                        "level_offset": float(et.level_offset),
                    },
                    "growth": {
                        "level": int(gr.level),
                        "total_exp": int(gr.total_exp),
                    },
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
        from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
        from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
        from ai_rpg_world.domain.player.value_object.growth import Growth
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.player.value_object.stat_growth_factor import (
            StatGrowthFactor,
        )

        repo = getattr(runtime, "_player_status_repo", None)
        if repo is None:
            raise RuntimeError(
                "runtime._player_status_repo not found; "
                "PlayerGrowthSubsystemCodec requires it"
            )
        for entry in data.get("entries", []):
            pid = PlayerId(int(entry["player_id"]))
            agg = repo.find_by_id(pid)
            if agg is None:
                continue
            bs_d = entry["base_stats"]
            gf_d = entry["stat_growth_factor"]
            et_d = entry["exp_table"]
            gr_d = entry["growth"]

            new_base_stats = BaseStats(
                max_hp=int(bs_d["max_hp"]),
                max_mp=int(bs_d["max_mp"]),
                attack=int(bs_d["attack"]),
                defense=int(bs_d["defense"]),
                speed=int(bs_d["speed"]),
                critical_rate=float(bs_d["critical_rate"]),
                evasion_rate=float(bs_d["evasion_rate"]),
            )
            new_growth_factor = StatGrowthFactor(
                hp_factor=float(gf_d["hp_factor"]),
                mp_factor=float(gf_d["mp_factor"]),
                attack_factor=float(gf_d["attack_factor"]),
                defense_factor=float(gf_d["defense_factor"]),
                speed_factor=float(gf_d["speed_factor"]),
                critical_rate_factor=float(gf_d["critical_rate_factor"]),
                evasion_rate_factor=float(gf_d["evasion_rate_factor"]),
            )
            new_exp_table = ExpTable(
                base_exp=float(et_d["base_exp"]),
                exponent=float(et_d["exponent"]),
                level_offset=float(et_d["level_offset"]),
            )
            # Growth は exp_table を参照する VO なので順序が重要
            new_growth = Growth(
                level=int(gr_d["level"]),
                total_exp=int(gr_d["total_exp"]),
                exp_table=new_exp_table,
            )
            agg._base_stats = new_base_stats
            agg._stat_growth_factor = new_growth_factor
            agg._exp_table = new_exp_table
            agg._growth = new_growth
            if hasattr(agg, "_events"):
                agg._events.clear()
            repo.save(agg)


__all__ = [
    "PlayerGrowthSubsystemCodec",
    "SUBSYSTEM_KEY",
    "SCHEMA_VERSION",
]
