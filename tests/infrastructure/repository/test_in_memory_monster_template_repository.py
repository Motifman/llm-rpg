"""InMemoryMonsterTemplateRepository のテスト（正常・境界・例外ケース）"""

import pytest
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterTemplateValidationException
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.infrastructure.repository.in_memory_monster_template_repository import (
    InMemoryMonsterTemplateRepository,
)


def _make_template(template_id: int, name: str) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId(template_id),
        name=name,
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        reward_info=RewardInfo(0, 0),
        respawn_info=RespawnInfo(1, True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.ENEMY,
        description=f"{name} description",
        skill_ids=[],
    )


class TestInMemoryMonsterTemplateRepository:
    """InMemoryMonsterTemplateRepository のテスト"""

    @pytest.fixture
    def repo(self):
        return InMemoryMonsterTemplateRepository()

    def test_find_by_id_returns_none_when_empty(self, repo):
        """登録がないとき find_by_id は None"""
        assert repo.find_by_id(MonsterTemplateId(1)) is None

    def test_save_and_find_by_id(self, repo):
        """save で登録したテンプレートを find_by_id で取得できる"""
        template = _make_template(1, "Slime")
        repo.save(template)
        result = repo.find_by_id(MonsterTemplateId(1))
        assert result is not None
        assert result.template_id.value == 1
        assert result.name == "Slime"

    def test_find_by_name_returns_template_when_exists(self, repo):
        """find_by_name で登録済みの名前からテンプレートを取得できる"""
        template = _make_template(1, "ゴブリン")
        repo.save(template)
        result = repo.find_by_name("ゴブリン")
        assert result is not None
        assert result.template_id.value == 1
        assert result.name == "ゴブリン"

    def test_find_by_name_returns_none_when_not_exists(self, repo):
        """存在しない名前で find_by_name は None"""
        template = _make_template(1, "Slime")
        repo.save(template)
        assert repo.find_by_name("Goblin") is None
        assert repo.find_by_name("") is None
        assert repo.find_by_name("   ") is None

    def test_find_by_name_strips_whitespace(self, repo):
        """find_by_name は名前の前後の空白を無視する（内部的には保存時と同じキーで検索）"""
        template = _make_template(1, "Goblin")
        repo.save(template)
        result = repo.find_by_name("  Goblin  ")
        assert result is not None
        assert result.name == "Goblin"

    def test_find_by_name_empty_repo_returns_none(self, repo):
        """空のリポジトリで find_by_name は None"""
        assert repo.find_by_name("Slime") is None

    def test_find_by_ids_returns_matching_templates(self, repo):
        """find_by_ids は存在するテンプレートのみ返す"""
        repo.save(_make_template(1, "A"))
        repo.save(_make_template(2, "B"))
        result = repo.find_by_ids([MonsterTemplateId(1), MonsterTemplateId(999), MonsterTemplateId(2)])
        assert len(result) == 2
        assert {t.template_id.value for t in result} == {1, 2}

    def test_find_by_ids_empty_list(self, repo):
        """find_by_ids に空リストを渡すと空リスト"""
        assert repo.find_by_ids([]) == []

    def test_find_all_returns_all_templates(self, repo):
        """find_all は登録済みの全テンプレートを返す"""
        assert repo.find_all() == []
        repo.save(_make_template(1, "Slime"))
        repo.save(_make_template(2, "Goblin"))
        all_templates = repo.find_all()
        assert len(all_templates) == 2
        assert {t.name for t in all_templates} == {"Slime", "Goblin"}

    def test_delete_removes_template(self, repo):
        """delete で削除し、find_by_id と find_by_name が None になる"""
        template = _make_template(1, "Gone")
        repo.save(template)
        assert repo.find_by_id(MonsterTemplateId(1)) is not None
        assert repo.find_by_name("Gone") is not None
        deleted = repo.delete(MonsterTemplateId(1))
        assert deleted is True
        assert repo.find_by_id(MonsterTemplateId(1)) is None
        assert repo.find_by_name("Gone") is None

    def test_delete_non_existing_returns_false(self, repo):
        """存在しないテンプレートの delete は False"""
        assert repo.delete(MonsterTemplateId(999)) is False

    def test_save_overwrites_existing_and_find_by_name_returns_latest(self, repo):
        """同一 template_id で save すると上書きされ、find_by_name は最新を返す"""
        repo.save(_make_template(1, "Old"))
        repo.save(_make_template(1, "New"))
        found = repo.find_by_id(MonsterTemplateId(1))
        assert found.name == "New"
        assert repo.find_by_name("New") is not None
        assert repo.find_by_name("Old") is None

    def test_find_by_name_none_input_returns_none(self, repo):
        """None を渡すと find_by_name は None を返す（型チェック前の防御）"""
        repo.save(_make_template(1, "Slime"))
        assert repo.find_by_name(None) is None
