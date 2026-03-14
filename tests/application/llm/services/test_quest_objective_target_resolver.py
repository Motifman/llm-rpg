"""QuestObjectiveTargetResolver のテスト。"""

import pytest

from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.services.quest_objective_target_resolver import (
    QuestObjectiveTargetResolver,
)
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.infrastructure.repository.in_memory_monster_template_repository import (
    InMemoryMonsterTemplateRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import InMemorySpotRepository
from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import (
    InMemoryItemSpecRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
    InMemoryPlayerProfileRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore


def _make_resolver_with_repos() -> QuestObjectiveTargetResolver:
    """target_name 解決用のリポジトリ付き Resolver を構築"""
    monster_repo = InMemoryMonsterTemplateRepository()
    monster_repo.save(
        MonsterTemplate(
            template_id=MonsterTemplateId(10),
            name="ゴブリン",
            base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
            reward_info=RewardInfo(0, 0),
            respawn_info=RespawnInfo(1, True),
            race=Race.BEAST,
            faction=MonsterFactionEnum.ENEMY,
            description="ゴブリン",
            skill_ids=[],
        )
    )

    data_store = InMemoryDataStore()
    data_store.clear_all()
    spot_repo = InMemorySpotRepository(data_store=data_store)
    spot_repo.save(Spot(SpotId(20), "北の森", "暗い森", SpotCategoryEnum.OTHER))

    item_repo = InMemoryItemSpecRepository()

    profile_repo = InMemoryPlayerProfileRepository(data_store=data_store)
    profile_repo.save(
        PlayerProfileAggregate.create(
            player_id=PlayerId(30),
            name=PlayerName("Alice"),
        )
    )

    return QuestObjectiveTargetResolver(
        monster_template_repository=monster_repo,
        spot_repository=spot_repo,
        item_spec_repository=item_repo,
        player_profile_repository=profile_repo,
    )


class TestQuestObjectiveTargetResolverKillMonster:
    """kill_monster の resolve_target_id テスト"""

    def test_resolves_target_name_to_template_id(self):
        resolver = _make_resolver_with_repos()
        result = resolver.resolve_target_id(
            objective_type="kill_monster",
            target_name="ゴブリン",
            target_id=None,
        )
        assert result == 10

    def test_resolves_target_id_when_provided(self):
        resolver = _make_resolver_with_repos()
        result = resolver.resolve_target_id(
            objective_type="kill_monster",
            target_name=None,
            target_id=101,
        )
        assert result == 101

    def test_target_name_priority_over_target_id(self):
        resolver = _make_resolver_with_repos()
        result = resolver.resolve_target_id(
            objective_type="kill_monster",
            target_name="ゴブリン",
            target_id=999,
        )
        assert result == 10

    def test_raises_when_monster_not_found(self):
        resolver = _make_resolver_with_repos()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve_target_id(
                objective_type="kill_monster",
                target_name="ドラゴン",
                target_id=None,
            )
        assert exc_info.value.error_code == "MONSTER_TEMPLATE_NOT_FOUND"

    def test_raises_resolver_not_configured_when_repo_none(self):
        resolver = QuestObjectiveTargetResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve_target_id(
                objective_type="kill_monster",
                target_name="ゴブリン",
                target_id=None,
            )
        assert exc_info.value.error_code == "RESOLVER_NOT_CONFIGURED"


class TestQuestObjectiveTargetResolverObtainItem:
    """obtain_item の resolve_target_id テスト"""

    def test_resolves_target_name_to_item_spec_id(self):
        resolver = _make_resolver_with_repos()
        result = resolver.resolve_target_id(
            objective_type="obtain_item",
            target_name="鉄の剣",
            target_id=None,
        )
        assert result == 1

    def test_raises_when_item_not_found(self):
        resolver = _make_resolver_with_repos()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve_target_id(
                objective_type="obtain_item",
                target_name="存在しないアイテム",
                target_id=None,
            )
        assert exc_info.value.error_code == "ITEM_SPEC_NOT_FOUND"


class TestQuestObjectiveTargetResolverReachSpot:
    """reach_spot の resolve_target_id テスト"""

    def test_resolves_target_name_to_spot_id(self):
        resolver = _make_resolver_with_repos()
        result = resolver.resolve_target_id(
            objective_type="reach_spot",
            target_name="北の森",
            target_id=None,
        )
        assert result == 20

    def test_raises_when_spot_not_found(self):
        resolver = _make_resolver_with_repos()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve_target_id(
                objective_type="reach_spot",
                target_name="存在しない場所",
                target_id=None,
            )
        assert exc_info.value.error_code == "SPOT_NOT_FOUND"


class TestQuestObjectiveTargetResolverKillPlayer:
    """kill_player の resolve_target_id テスト"""

    def test_resolves_target_name_to_player_id(self):
        resolver = _make_resolver_with_repos()
        result = resolver.resolve_target_id(
            objective_type="kill_player",
            target_name="Alice",
            target_id=None,
        )
        assert result == 30

    def test_raises_when_player_not_found(self):
        resolver = _make_resolver_with_repos()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve_target_id(
                objective_type="kill_player",
                target_name="存在しない人",
                target_id=None,
            )
        assert exc_info.value.error_code == "PLAYER_PROFILE_NOT_FOUND"


class TestQuestObjectiveTargetResolverNonAllowedTypes:
    """許可外の目標タイプ（talk_to_npc 等）のテスト"""

    def test_accepts_target_id_for_talk_to_npc(self):
        resolver = _make_resolver_with_repos()
        result = resolver.resolve_target_id(
            objective_type="talk_to_npc",
            target_name=None,
            target_id=5,
        )
        assert result == 5

    def test_raises_when_target_name_only_and_type_not_allowed(self):
        resolver = _make_resolver_with_repos()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve_target_id(
                objective_type="talk_to_npc",
                target_name="老人",
                target_id=None,
            )
        assert exc_info.value.error_code == "INVALID_OBJECTIVE_TYPE"
        assert "kill_monster" in str(exc_info.value)


class TestQuestObjectiveTargetResolverValidation:
    """入力検証のテスト"""

    def test_raises_when_objective_type_empty(self):
        resolver = _make_resolver_with_repos()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve_target_id(
                objective_type="",
                target_name=None,
                target_id=1,
            )
        assert exc_info.value.error_code == "INVALID_OBJECTIVES"

    def test_raises_when_objective_type_whitespace_only(self):
        resolver = _make_resolver_with_repos()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve_target_id(
                objective_type="   ",
                target_name=None,
                target_id=1,
            )
        assert exc_info.value.error_code == "INVALID_OBJECTIVES"

    def test_raises_when_neither_target_name_nor_target_id(self):
        resolver = _make_resolver_with_repos()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve_target_id(
                objective_type="kill_monster",
                target_name=None,
                target_id=None,
            )
        assert exc_info.value.error_code == "INVALID_OBJECTIVES"
        assert "target_name または target_id" in str(exc_info.value)

    def test_accepts_target_id_for_allowed_type_without_target_name(self):
        resolver = _make_resolver_with_repos()
        result = resolver.resolve_target_id(
            objective_type="kill_monster",
            target_name=None,
            target_id=100,
        )
        assert result == 100
