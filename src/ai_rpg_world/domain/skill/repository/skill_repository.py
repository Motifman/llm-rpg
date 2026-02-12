from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.skill.aggregate.skill_deck_progress_aggregate import SkillDeckProgressAggregate
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import SkillDeckProgressId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec


class SkillLoadoutRepository(Repository[SkillLoadoutAggregate, SkillLoadoutId]):
    """スキルデッキ構成集約のリポジトリインターフェース"""

    def find_by_owner_id(self, owner_id: int) -> SkillLoadoutAggregate | None:
        """所有者IDに紐付くロードアウトを検索する"""
        raise NotImplementedError


class SkillDeckProgressRepository(Repository[SkillDeckProgressAggregate, SkillDeckProgressId]):
    """スキルデッキ進化進行集約のリポジトリインターフェース"""

    def find_by_owner_id(self, owner_id: int) -> SkillDeckProgressAggregate | None:
        """所有者IDに紐付く進行状況を検索する"""
        raise NotImplementedError


class SkillSpecRepository(Repository[SkillSpec, SkillId]):
    """スキル定義（マスタ）リポジトリインターフェース"""

    pass

