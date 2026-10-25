"""現在状態の契約に、実行経路を退役させたタイル用情報が戻らないことを保証する。"""

from dataclasses import fields

import pytest

from ai_rpg_world.application.world.contracts import dtos


@pytest.mark.parametrize(
    "dto_type",
    [dtos.PlayerCurrentStateDto, dtos.PlayerWorldStateDto, dtos.PlayerRuntimeContextDto],
)
def test_current_state_contract_has_no_legacy_tile_fields(dto_type: type) -> None:
    """現在状態と部品DTOは、座標・視界・タイル移動・会話・採取・スキル操作の旧項目を公開しない。"""
    removed = set(
        "current_spot_name current_spot_description x y z current_player_count "
        "current_player_ids connected_spot_ids connected_spot_names weather_type "
        "weather_intensity current_terrain_type visible_objects view_distance "
        "available_moves total_available_moves attention_level area_names area_id "
        "area_name available_location_areas current_location_description is_busy "
        "busy_until_tick has_active_path visible_tile_map chest_items active_conversation "
        "active_harvest usable_skills equipable_skill_candidates skill_equip_slots "
        "pending_skill_proposals awakened_action attention_level_options "
        "can_destroy_placeable actionable_objects notable_objects".split()
    )
    assert not {field.name for field in fields(dto_type)} & removed


def test_retired_tile_contract_types_are_absent() -> None:
    """現在状態専用だった視界・移動候補・会話・採取・スキル操作のDTO型を再公開しない。"""
    removed = (
        "VisibleObjectDto VisibleTileMapDto AvailableMoveDto AvailableLocationAreaDto "
        "ChestItemDto ConversationChoiceDto ActiveConversationDto ActiveHarvestDto "
        "UsableSkillDto EquipableSkillCandidateDto SkillEquipSlotDto PendingSkillProposalDto "
        "AwakenedActionDto AttentionLevelOptionDto"
    ).split()
    assert not set(vars(dtos)) & set(removed)


def test_retired_visibility_resolver_is_not_exported() -> None:
    """未登録だったタイル視界用の囁き判定器は、実装とパッケージの公開口に残らない。"""
    from ai_rpg_world.application.llm import services
    from ai_rpg_world.application.llm.services import availability_resolvers

    name = "WhisperAvailabilityResolver"
    assert not hasattr(availability_resolvers, name)
    assert not hasattr(services, name)
