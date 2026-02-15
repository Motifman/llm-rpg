"""
モンスターのスキル実行を統括するドメインサービス。

リポジトリに依存せず、渡された集約（モンスター・ロードアウト・物理マップ）に対して
MP消費・クールダウン開始・ヒットボックス生成パラメータ計算を行う。
呼び出し元（アプリケーション層）がリポジトリによる取得・永続化を担当する。
"""
from typing import List, TYPE_CHECKING

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.skill.service.skill_execution_service import SkillExecutionDomainService
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.combat.value_object.hit_box_spawn_param import HitBoxSpawnParam

if TYPE_CHECKING:
    from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
    from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate


class MonsterSkillExecutionDomainService:
    """
    モンスターがスキルを使用する際のドメインロジックを統括する。
    MP消費・use_skill（クールダウン開始）・ヒットボックス生成パラメータ計算を行う。
    """

    def __init__(self, skill_execution_service: SkillExecutionDomainService):
        self._skill_execution_service = skill_execution_service

    def execute(
        self,
        monster: "MonsterAggregate",
        loadout: SkillLoadoutAggregate,
        physical_map: "PhysicalMapAggregate",
        slot_index: int,
        current_tick: WorldTick,
    ) -> List[HitBoxSpawnParam]:
        """
        モンスターが指定スロットのスキルを使用し、ヒットボックス生成パラメータを返す。
        モンスターのMP消費とロードアウトのクールダウン開始を行う（集約を更新する）。

        Args:
            monster: スキルを使用するモンスター集約
            loadout: モンスターのスキルロードアウト集約
            physical_map: 対象の物理マップ集約
            slot_index: 使用するスキルのスロットインデックス
            current_tick: 現在のワールドティック

        Returns:
            HitBoxSpawnParam のリスト。呼び出し元が HitBoxFactory 等で HitBox を生成・保存する。

        Raises:
            DomainException: スロットにスキルがない、MP不足、クールダウン中、モンスターがマップ上にいない等
        """
        deck = loadout.get_current_deck(current_tick.value)
        skill_spec = deck.get_skill(slot_index)
        if not skill_spec:
            from ai_rpg_world.domain.skill.exception.skill_exceptions import SkillNotFoundInSlotException
            from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier
            raise SkillNotFoundInSlotException(
                f"slot has no skill: tier={deck.deck_tier.value}, slot={slot_index}"
            )

        monster.use_mp(skill_spec.mp_cost)
        loadout.use_skill(slot_index, current_tick.value, actor_id=loadout.owner_id)

        return self._skill_execution_service.execute_monster_skill(
            physical_map=physical_map,
            monster=monster,
            skill_spec=skill_spec,
            current_tick=current_tick,
        )
