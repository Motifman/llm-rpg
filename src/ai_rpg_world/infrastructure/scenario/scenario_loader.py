"""シナリオ定義 JSON → ドメインオブジェクト変換。

scenario_format_version "1.0" に対応。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_rpg_world.infrastructure.scenario.declaration_site import declaring
from ai_rpg_world.infrastructure.scenario.load_error import (
    SUPPORTED_FORMAT_VERSIONS,
    ScenarioLoadError,
)
from ai_rpg_world.infrastructure.scenario.models import (
    AreaDef,
    DistantCueAppearEventDef,
    DistantCueDef,
    DistantCueSourceDef,
    InitialItemSpec,
    ItemSpecDefinition,
    OngoingConditionDef,
    PlayerSpawnConfig,
    ScenarioDayNightConfig,
    ScenarioLoadResult,
    ScenarioLootEntry,
    ScenarioLootTableDefinition,
    ScenarioMerchantDefinition,
    ScenarioMerchantPriceEntry,
    ScenarioMetadata,
    ScenarioMonsterPlacement,
    ScenarioMonsterSpawnCondition,
    ScenarioMonsterTemplate,
    ScenarioNeedsConfig,
    ScenarioWeatherConfig,
)
from ai_rpg_world.infrastructure.scenario.parse_actors import (
    parse_monsters_block,
    parse_mutually_known_roles,
    parse_players,
    parse_role_personas,
)
from ai_rpg_world.infrastructure.scenario.parse_economy import (
    parse_item_interaction_registry,
    parse_item_specs,
    parse_loot_tables,
    parse_market,
    parse_merchants,
    parse_needs_config,
    parse_player_attribute_specs,
)
from ai_rpg_world.infrastructure.scenario.parse_helpers import (
    parse_departed_agents_enabled,
    remote_recorded_tick_state_keys,
)
from ai_rpg_world.infrastructure.scenario.parse_interactions import (
    parse_player_interactions,
)
from ai_rpg_world.infrastructure.scenario.parse_map import (
    parse_areas,
    parse_connections,
    parse_distant_cues,
    parse_spots_and_graph,
)
from ai_rpg_world.infrastructure.scenario.parse_reactive_bindings import (
    parse_reactive_object_state_bindings,
    parse_reactive_passage_bindings,
)
from ai_rpg_world.infrastructure.scenario.parse_teams import parse_teams
from ai_rpg_world.infrastructure.scenario.parse_round_assignment import (
    apply_round_assignment,
)
from ai_rpg_world.infrastructure.scenario.parse_scenario_events import (
    parse_player_outcome_rules,
    parse_scenario_events,
)
from ai_rpg_world.infrastructure.scenario.parse_sync_groups import (
    parse_synchronized_action_groups,
    reject_unreachable_synchronized_action_names,
)
from ai_rpg_world.infrastructure.scenario.parse_world import (
    declared_world_flag_writers,
    parse_day_night_config,
    parse_death_semantics,
    parse_disabled_tools,
    parse_end_conditions,
    parse_meeting_enabled,
    parse_meeting_tuning,
    parse_metadata,
    parse_ongoing_conditions,
    parse_player_trade,
    parse_weather_config,
    pre_register_ids,
    validate_ongoing_condition_resolution_references,
)
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper
from ai_rpg_world.infrastructure.scenario.validate_features import (
    _DAY_NIGHT_FEATURE,
    _GAME_END_CONDITION_ALLOWED_SECTIONS,
    _INTERACTION_CONDITION_FEATURE_REQUIREMENTS,
    _MONSTER_SPAWN_CONDITION_FEATURE_REQUIREMENTS,
    _SCENARIO_EVENT_RECIPIENTS,
    _SCENARIO_EVENT_TRIGGERS,
    _WEATHER_FEATURE,
    SILENT_REACTIVE_OBJECT_BINDING_WARNING,
    validate_feature_consistency,
)

__all__ = [
    "AreaDef",
    "DistantCueAppearEventDef",
    "DistantCueDef",
    "DistantCueSourceDef",
    "InitialItemSpec",
    "ItemSpecDefinition",
    "OngoingConditionDef",
    "PlayerSpawnConfig",
    "SILENT_REACTIVE_OBJECT_BINDING_WARNING",
    "SUPPORTED_FORMAT_VERSIONS",
    "ScenarioDayNightConfig",
    "ScenarioLoadError",
    "ScenarioLoadResult",
    "ScenarioLoader",
    "ScenarioLootEntry",
    "ScenarioLootTableDefinition",
    "ScenarioMerchantDefinition",
    "ScenarioMerchantPriceEntry",
    "ScenarioMetadata",
    "ScenarioMonsterPlacement",
    "ScenarioMonsterSpawnCondition",
    "ScenarioMonsterTemplate",
    "ScenarioNeedsConfig",
    "ScenarioWeatherConfig",
    "_DAY_NIGHT_FEATURE",
    "_GAME_END_CONDITION_ALLOWED_SECTIONS",
    "_INTERACTION_CONDITION_FEATURE_REQUIREMENTS",
    "_MONSTER_SPAWN_CONDITION_FEATURE_REQUIREMENTS",
    "_SCENARIO_EVENT_RECIPIENTS",
    "_SCENARIO_EVENT_TRIGGERS",
    "_WEATHER_FEATURE",
]


class ScenarioLoader:
    """シナリオ定義 JSON を読み込んでドメインオブジェクト群に変換する。"""

    def load_from_file(
        self,
        path: Path,
        *,
        random_seed: int | None = None,
        round_number: int = 1,
    ) -> ScenarioLoadResult:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        with declaring(f"{path}:"):
            return self.load_from_dict(
                raw, random_seed=random_seed, round_number=round_number
            )

    def load_from_dict(
        self,
        raw: dict[str, Any],
        *,
        random_seed: int | None = None,
        round_number: int = 1,
    ) -> ScenarioLoadResult:
        version = raw.get("scenario_format_version")
        if version not in SUPPORTED_FORMAT_VERSIONS:
            raise ScenarioLoadError(
                f"Unsupported scenario_format_version: {version!r}. "
                f"Supported: {SUPPORTED_FORMAT_VERSIONS}"
            )
        if "outcome_resolution" in raw:
            raise ScenarioLoadError(
                "outcome_resolution は廃止されました。"
                "player_outcome_rules / game_end_conditions.end / needs を"
                "それぞれ宣言してください"
            )
        raw, round_assignments = apply_round_assignment(
            raw, random_seed=random_seed, round_number=round_number
        )
        mapper = ScenarioIdMapper()

        metadata = parse_metadata(raw["metadata"])
        # item_specs 内の interaction も他の spot / object を参照できる。
        # ItemSpecDefinition の解析より前に全 ID を登録し、宣言順に依存しない。
        pre_register_ids(raw, mapper)
        # **効果を読むより先に読む。** 「変えられないと宣言した属性を書く
        # 効果」を落とす検査が、効果をパースする側に要る。後ろに置くと、
        # 効果を読み終えたあとに宣言が届くので検査が空振りする。
        player_attribute_specs = parse_player_attribute_specs(
            raw.get("player_attributes")
        )
        item_defs = parse_item_specs(raw.get("item_specs", []), mapper)
        # PR #1: 動的 loot table を先にパース (effect parameter で
        # "loot_table" → id 解決するため、spots/effects のパース時点で
        # mapper に loot_table ns が登録済みである必要)。
        loot_tables = parse_loot_tables(raw.get("loot_tables", []), mapper)
        item_interaction_registry = parse_item_interaction_registry(
            raw.get("item_specs", []),
            mapper,
            player_attribute_specs=player_attribute_specs,
        )
        graph, interiors = parse_spots_and_graph(
            raw,
            mapper,
            remote_recorded_tick_keys=remote_recorded_tick_state_keys(
                raw.get("item_specs", []), mapper
            ),
            player_attribute_specs=player_attribute_specs,
        )
        areas = parse_areas(raw.get("areas", []), raw.get("spots", []))
        distant_cues = parse_distant_cues(
            raw.get("distant_cues", []),
            mapper,
            {area.area_id for area in areas},
        )
        parse_connections(raw.get("connections", []), graph, mapper)
        players = parse_players(
            raw.get("players", []),
            mapper,
            player_attribute_specs=player_attribute_specs,
        )
        # 商人は spot と item_spec の両方を参照するので、どちらの登録も
        # 終わったこの時点で解析する。
        merchants = parse_merchants(raw.get("merchants"), mapper)
        mutually_known_roles = parse_mutually_known_roles(
            raw.get("mutually_known_roles"), players
        )
        role_personas = parse_role_personas(raw.get("role_personas"), players)
        teams = parse_teams(raw.get("teams"), players, mapper)
        raw_end_conditions = raw.get("game_end_conditions", {})
        if teams and (raw_end_conditions.get("win") or raw_end_conditions.get("lose")):
            raise ScenarioLoadError(
                "teams を書いたシナリオでは game_end_conditions.win / lose を"
                "置けません。勝ちは teams[].win に、どのチームも勝たない終わりは"
                " game_end_conditions.end に書いてください"
            )
        win_conds = parse_end_conditions(
            raw_end_conditions.get("win", []), mapper, section="win"
        )
        lose_conds = parse_end_conditions(
            raw_end_conditions.get("lose", []), mapper, section="lose"
        )
        end_conds = parse_end_conditions(
            raw_end_conditions.get("end", []),
            mapper,
            section="team_end" if teams else "end",
        )
        initial_flags = tuple(raw.get("initial_flags", []))
        ongoing_conditions = parse_ongoing_conditions(
            raw.get("ongoing_conditions"),
            declared_flag_writers=declared_world_flag_writers(raw),
            mapper=mapper,
            player_attribute_specs=player_attribute_specs,
        )
        validate_ongoing_condition_resolution_references(
            raw,
            ongoing_conditions,
        )
        disabled_tools = parse_disabled_tools(raw.get("disabled_tools"))
        scenario_events = parse_scenario_events(
            raw.get("scenario_events", []),
            mapper,
            player_attribute_specs=player_attribute_specs,
        )
        player_outcome_rules = parse_player_outcome_rules(
            raw.get("player_outcome_rules", []), mapper,
        )
        needs_config = parse_needs_config(raw.get("needs"))
        weather_config = parse_weather_config(raw.get("environment", {}))
        day_night_config = parse_day_night_config(raw.get("environment", {}))
        monster_templates, monster_placements = parse_monsters_block(
            raw.get("monsters"), mapper,
        )
        reactive_bindings = parse_reactive_passage_bindings(
            raw.get("reactive_bindings", {}), mapper,
        )
        reactive_object_bindings = parse_reactive_object_state_bindings(
            raw.get("reactive_bindings", {}), mapper,
        )
        player_interactions = parse_player_interactions(
            raw.get("player_interactions", []),
            mapper,
            player_attribute_specs=player_attribute_specs,
        )
        sync_groups = parse_synchronized_action_groups(
            raw.get("synchronized_action_groups", []),
            mapper,
            player_attribute_specs=player_attribute_specs,
        )
        reject_unreachable_synchronized_action_names(sync_groups, raw)
        meeting_enabled = parse_meeting_enabled(raw)
        player_trade_enabled, player_trade_offer_expires = parse_player_trade(raw)
        public_sns_enabled = raw.get("public_sns_enabled", False)
        public_sns_push_budget_chars = raw.get("public_sns_push_budget_chars", 6000)
        if not isinstance(public_sns_enabled, bool):
            raise ScenarioLoadError("public_sns_enabled は真偽値が必要です")
        if isinstance(public_sns_push_budget_chars, bool) or not isinstance(public_sns_push_budget_chars, int) or not 512 <= public_sns_push_budget_chars <= 24000:
            raise ScenarioLoadError("public_sns_push_budget_chars は512以上24000以下の整数が必要です")
        market = parse_market(raw, mapper, merchants)
        departed_agents_enabled = parse_departed_agents_enabled(raw)
        death_semantics = parse_death_semantics(raw)
        meeting_tuning = parse_meeting_tuning(raw)

        result = ScenarioLoadResult(
            graph=graph,
            interiors=interiors,
            win_conditions=tuple(win_conds),
            lose_conditions=tuple(lose_conds),
            player_spawns=tuple(players),
            item_spec_definitions=tuple(item_defs),
            item_interaction_registry=item_interaction_registry,
            id_mapper=mapper,
            metadata=metadata,
            initial_flags=initial_flags,
            end_conditions=tuple(end_conds),
            disabled_tools=disabled_tools,
            mutually_known_roles=mutually_known_roles,
            role_personas=role_personas,
            ongoing_conditions=ongoing_conditions,
            scenario_events=scenario_events,
            player_outcome_rules=player_outcome_rules,
            needs_config=needs_config,
            player_attribute_specs=player_attribute_specs,
            weather_config=weather_config,
            day_night_config=day_night_config,
            reactive_passage_bindings=reactive_bindings,
            reactive_object_state_bindings=reactive_object_bindings,
            synchronized_action_groups=sync_groups,
            player_interactions=player_interactions,
            monster_templates=monster_templates,
            monster_placements=monster_placements,
            loot_tables=loot_tables,
            areas=areas,
            distant_cues=distant_cues,
            meeting_enabled=meeting_enabled,
            death_semantics=death_semantics,
            departed_agents_enabled=departed_agents_enabled,
            merchants=merchants,
            public_sns_enabled=public_sns_enabled,
            public_sns_push_budget_chars=public_sns_push_budget_chars,
            player_trade_enabled=player_trade_enabled,
            player_trade_offer_expires_in_ticks=player_trade_offer_expires,
            market=market,
            round_assignments=round_assignments,
            teams=teams,
            **meeting_tuning,
        )
        validate_feature_consistency(result, raw)
        return result
