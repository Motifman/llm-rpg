"""SQLite implementation of monster template read repository and writer."""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterTemplateRepository,
    MonsterTemplateWriter,
)
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_monster_template_state_codec import (
    build_monster_template,
)


class SqliteMonsterTemplateRepository(MonsterTemplateRepository):
    """Read monster templates from the game DB."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_connection(
        cls, connection: sqlite3.Connection
    ) -> "SqliteMonsterTemplateRepository":
        return cls(connection)

    def find_by_id(
        self, template_id: MonsterTemplateId
    ) -> Optional[MonsterTemplate]:
        cur = self._conn.execute(
            "SELECT * FROM game_monster_templates WHERE template_id = ?",
            (int(template_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._build_template_from_row(row)

    def find_by_ids(
        self, template_ids: List[MonsterTemplateId]
    ) -> List[MonsterTemplate]:
        return [x for template_id in template_ids for x in [self.find_by_id(template_id)] if x is not None]

    def find_by_name(self, name: str) -> Optional[MonsterTemplate]:
        if not name or not isinstance(name, str):
            return None
        key = name.strip()
        if not key:
            return None

        cur = self._conn.execute(
            "SELECT * FROM game_monster_templates WHERE name = ?",
            (key,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._build_template_from_row(row)

    def save(self, template: MonsterTemplate) -> MonsterTemplate:
        raise NotImplementedError(
            "SqliteMonsterTemplateRepository is read-only. Use SqliteMonsterTemplateWriter."
        )

    def delete(self, template_id: MonsterTemplateId) -> bool:
        raise NotImplementedError(
            "SqliteMonsterTemplateRepository is read-only. Use SqliteMonsterTemplateWriter."
        )

    def find_all(self) -> List[MonsterTemplate]:
        cur = self._conn.execute(
            "SELECT * FROM game_monster_templates ORDER BY template_id ASC"
        )
        return [self._build_template_from_row(row) for row in cur.fetchall()]

    def _build_template_from_row(self, row: sqlite3.Row) -> MonsterTemplate:
        template_id = int(row["template_id"])
        skill_rows = self._conn.execute(
            "SELECT skill_id FROM game_monster_template_skill_ids WHERE template_id = ? ORDER BY skill_index ASC",
            (template_id,),
        ).fetchall()
        phase_rows = self._conn.execute(
            "SELECT threshold FROM game_monster_template_phase_thresholds WHERE template_id = ? ORDER BY threshold_index ASC",
            (template_id,),
        ).fetchall()
        threat_rows = self._conn.execute(
            "SELECT race FROM game_monster_template_threat_races WHERE template_id = ? ORDER BY race_index ASC",
            (template_id,),
        ).fetchall()
        prey_rows = self._conn.execute(
            "SELECT race FROM game_monster_template_prey_races WHERE template_id = ? ORDER BY race_index ASC",
            (template_id,),
        ).fetchall()
        growth_rows = self._conn.execute(
            "SELECT * FROM game_monster_template_growth_stages WHERE template_id = ? ORDER BY stage_index ASC",
            (template_id,),
        ).fetchall()
        feed_rows = self._conn.execute(
            "SELECT item_spec_id FROM game_monster_template_preferred_feed_items WHERE template_id = ? ORDER BY item_index ASC",
            (template_id,),
        ).fetchall()
        respawn_weather_rows = self._conn.execute(
            "SELECT weather_type FROM game_monster_template_respawn_preferred_weather WHERE template_id = ? ORDER BY weather_index ASC",
            (template_id,),
        ).fetchall()
        respawn_trait_rows = self._conn.execute(
            "SELECT trait FROM game_monster_template_respawn_required_area_traits WHERE template_id = ? ORDER BY trait_index ASC",
            (template_id,),
        ).fetchall()
        return build_monster_template(
            row=row,
            skill_ids=[int(skill_row["skill_id"]) for skill_row in skill_rows],
            phase_thresholds=[float(phase_row["threshold"]) for phase_row in phase_rows],
            threat_races=[threat_row["race"] for threat_row in threat_rows],
            prey_races=[prey_row["race"] for prey_row in prey_rows],
            growth_stage_rows=list(growth_rows),
            preferred_feed_item_spec_ids=[int(feed_row["item_spec_id"]) for feed_row in feed_rows],
            respawn_preferred_weather=[weather_row["weather_type"] for weather_row in respawn_weather_rows],
            respawn_required_area_traits=[trait_row["trait"] for trait_row in respawn_trait_rows],
        )


class SqliteMonsterTemplateWriter(MonsterTemplateWriter):
    """MonsterTemplate 登録専用の SQLite writer。seed とテスト投入を担当する。"""

    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls, connection: sqlite3.Connection
    ) -> "SqliteMonsterTemplateWriter":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls, connection: sqlite3.Connection
    ) -> "SqliteMonsterTemplateWriter":
        return cls(connection, _commits_after_write=False)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def _assert_shared_transaction_active(self) -> None:
        if self._commits_after_write:
            return
        if not self._conn.in_transaction:
            raise RuntimeError(
                "for_shared_unit_of_work で生成した writer の書き込みは、"
                "アクティブなトランザクション内（with uow）で実行してください"
            )

    def replace_template(self, template: MonsterTemplate) -> None:
        self._assert_shared_transaction_active()
        self._conn.execute(
            """
            INSERT INTO game_monster_templates (
                template_id, name, description,
                base_max_hp, base_max_mp, base_attack, base_defense, base_speed,
                base_critical_rate, base_evasion_rate,
                reward_exp, reward_gold, reward_loot_table_id,
                respawn_interval_ticks, respawn_is_auto, respawn_time_band,
                race, faction, vision_range, flee_threshold, behavior_strategy_type,
                ecology_type, ambush_chase_range, territory_radius, active_time,
                hunger_increase_per_tick, hunger_decrease_on_prey_kill,
                hunger_starvation_threshold, starvation_ticks, max_age_ticks,
                forage_threshold, hunger_decrease_on_feed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(template_id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                base_max_hp = excluded.base_max_hp,
                base_max_mp = excluded.base_max_mp,
                base_attack = excluded.base_attack,
                base_defense = excluded.base_defense,
                base_speed = excluded.base_speed,
                base_critical_rate = excluded.base_critical_rate,
                base_evasion_rate = excluded.base_evasion_rate,
                reward_exp = excluded.reward_exp,
                reward_gold = excluded.reward_gold,
                reward_loot_table_id = excluded.reward_loot_table_id,
                respawn_interval_ticks = excluded.respawn_interval_ticks,
                respawn_is_auto = excluded.respawn_is_auto,
                respawn_time_band = excluded.respawn_time_band,
                race = excluded.race,
                faction = excluded.faction,
                vision_range = excluded.vision_range,
                flee_threshold = excluded.flee_threshold,
                behavior_strategy_type = excluded.behavior_strategy_type,
                ecology_type = excluded.ecology_type,
                ambush_chase_range = excluded.ambush_chase_range,
                territory_radius = excluded.territory_radius,
                active_time = excluded.active_time,
                hunger_increase_per_tick = excluded.hunger_increase_per_tick,
                hunger_decrease_on_prey_kill = excluded.hunger_decrease_on_prey_kill,
                hunger_starvation_threshold = excluded.hunger_starvation_threshold,
                starvation_ticks = excluded.starvation_ticks,
                max_age_ticks = excluded.max_age_ticks,
                forage_threshold = excluded.forage_threshold,
                hunger_decrease_on_feed = excluded.hunger_decrease_on_feed
            """,
            (
                int(template.template_id),
                template.name,
                template.description,
                template.base_stats.max_hp,
                template.base_stats.max_mp,
                template.base_stats.attack,
                template.base_stats.defense,
                template.base_stats.speed,
                template.base_stats.critical_rate,
                template.base_stats.evasion_rate,
                template.reward_info.exp,
                template.reward_info.gold,
                None if template.reward_info.loot_table_id is None else int(template.reward_info.loot_table_id),
                template.respawn_info.respawn_interval_ticks,
                int(template.respawn_info.is_auto_respawn),
                None
                if template.respawn_info.condition is None or template.respawn_info.condition.time_band is None
                else template.respawn_info.condition.time_band.value,
                template.race.value,
                template.faction.value,
                template.vision_range,
                template.flee_threshold,
                template.behavior_strategy_type,
                template.ecology_type.value,
                template.ambush_chase_range,
                template.territory_radius,
                template.active_time.value,
                template.hunger_increase_per_tick,
                template.hunger_decrease_on_prey_kill,
                template.hunger_starvation_threshold,
                template.starvation_ticks,
                template.max_age_ticks,
                template.forage_threshold,
                template.hunger_decrease_on_feed,
            ),
        )
        for table_name in (
            "game_monster_template_skill_ids",
            "game_monster_template_phase_thresholds",
            "game_monster_template_threat_races",
            "game_monster_template_prey_races",
            "game_monster_template_growth_stages",
            "game_monster_template_preferred_feed_items",
            "game_monster_template_respawn_preferred_weather",
            "game_monster_template_respawn_required_area_traits",
        ):
            self._conn.execute(f"DELETE FROM {table_name} WHERE template_id = ?", (int(template.template_id),))
        self._conn.executemany(
            "INSERT INTO game_monster_template_skill_ids (template_id, skill_index, skill_id) VALUES (?, ?, ?)",
            [(int(template.template_id), index, int(skill_id)) for index, skill_id in enumerate(template.skill_ids)],
        )
        self._conn.executemany(
            "INSERT INTO game_monster_template_phase_thresholds (template_id, threshold_index, threshold) VALUES (?, ?, ?)",
            [(int(template.template_id), index, value) for index, value in enumerate(template.phase_thresholds or [])],
        )
        self._conn.executemany(
            "INSERT INTO game_monster_template_threat_races (template_id, race_index, race) VALUES (?, ?, ?)",
            [(int(template.template_id), index, value) for index, value in enumerate(sorted(template.threat_races or []))],
        )
        self._conn.executemany(
            "INSERT INTO game_monster_template_prey_races (template_id, race_index, race) VALUES (?, ?, ?)",
            [(int(template.template_id), index, value) for index, value in enumerate(sorted(template.prey_races or []))],
        )
        self._conn.executemany(
            """
            INSERT INTO game_monster_template_growth_stages (
                template_id, stage_index, after_ticks, stats_multiplier, flee_bias_multiplier, allow_chase
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(template.template_id),
                    index,
                    stage.after_ticks,
                    stage.stats_multiplier,
                    stage.flee_bias_multiplier,
                    int(stage.allow_chase),
                )
                for index, stage in enumerate(template.growth_stages or [])
            ],
        )
        self._conn.executemany(
            "INSERT INTO game_monster_template_preferred_feed_items (template_id, item_index, item_spec_id) VALUES (?, ?, ?)",
            [
                (int(template.template_id), index, int(item_spec_id))
                for index, item_spec_id in enumerate(sorted(template.preferred_feed_item_spec_ids or [], key=int))
            ],
        )
        if template.respawn_info.condition is not None and template.respawn_info.condition.preferred_weather is not None:
            self._conn.executemany(
                "INSERT INTO game_monster_template_respawn_preferred_weather (template_id, weather_index, weather_type) VALUES (?, ?, ?)",
                [
                    (int(template.template_id), index, value.value)
                    for index, value in enumerate(sorted(template.respawn_info.condition.preferred_weather, key=lambda item: item.value))
                ],
            )
        if template.respawn_info.condition is not None and template.respawn_info.condition.required_area_traits is not None:
            self._conn.executemany(
                "INSERT INTO game_monster_template_respawn_required_area_traits (template_id, trait_index, trait) VALUES (?, ?, ?)",
                [
                    (int(template.template_id), index, value.value)
                    for index, value in enumerate(sorted(template.respawn_info.condition.required_area_traits, key=lambda item: item.value))
                ],
            )
        self._finalize_write()

    def delete_template(self, template_id: MonsterTemplateId) -> bool:
        self._assert_shared_transaction_active()
        cur = self._conn.execute(
            "DELETE FROM game_monster_template_skill_ids WHERE template_id = ?",
            (int(template_id),),
        )
        self._conn.execute("DELETE FROM game_monster_template_phase_thresholds WHERE template_id = ?", (int(template_id),))
        self._conn.execute("DELETE FROM game_monster_template_threat_races WHERE template_id = ?", (int(template_id),))
        self._conn.execute("DELETE FROM game_monster_template_prey_races WHERE template_id = ?", (int(template_id),))
        self._conn.execute("DELETE FROM game_monster_template_growth_stages WHERE template_id = ?", (int(template_id),))
        self._conn.execute("DELETE FROM game_monster_template_preferred_feed_items WHERE template_id = ?", (int(template_id),))
        self._conn.execute("DELETE FROM game_monster_template_respawn_preferred_weather WHERE template_id = ?", (int(template_id),))
        self._conn.execute("DELETE FROM game_monster_template_respawn_required_area_traits WHERE template_id = ?", (int(template_id),))
        cur = self._conn.execute(
            "DELETE FROM game_monster_templates WHERE template_id = ?",
            (int(template_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0


__all__ = ["SqliteMonsterTemplateRepository", "SqliteMonsterTemplateWriter"]
