"""クエスト目標の target_name -> target_id 解決。"""

from typing import TYPE_CHECKING, Optional

from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
    safe_int,
)
from ai_rpg_world.domain.player.exception.player_exceptions import PlayerNameValidationException
from ai_rpg_world.domain.player.value_object.player_name import PlayerName

if TYPE_CHECKING:
    from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
    from ai_rpg_world.domain.monster.repository.monster_repository import MonsterTemplateRepository
    from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
    from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository

_ALLOWED_QUEST_OBJECTIVE_TYPES = frozenset({
    "kill_monster", "obtain_item", "reach_spot", "kill_player",
})


class QuestObjectiveTargetResolver:
    """クエスト目標の target_name を target_id に解決する。"""

    def __init__(
        self,
        *,
        monster_template_repository: Optional["MonsterTemplateRepository"] = None,
        spot_repository: Optional["SpotRepository"] = None,
        item_spec_repository: Optional["ItemSpecRepository"] = None,
        player_profile_repository: Optional["PlayerProfileRepository"] = None,
    ) -> None:
        self._monster_template_repository = monster_template_repository
        self._spot_repository = spot_repository
        self._item_spec_repository = item_spec_repository
        self._player_profile_repository = player_profile_repository

    def resolve_target_id(
        self,
        objective_type: str,
        target_name: Optional[str],
        target_id: Optional[int],
    ) -> int:
        """目標タイプと target_name または target_id から target_id を返す。"""
        ot_stripped = (objective_type or "").strip()
        if not ot_stripped:
            raise ToolArgumentResolutionException(
                "objective_type が指定されていません。",
                "INVALID_OBJECTIVES",
            )

        # 許可外の目標タイプは target_id のみサポート（target_name 解決不可）
        if ot_stripped not in _ALLOWED_QUEST_OBJECTIVE_TYPES:
            if target_id is not None:
                return safe_int(target_id, "target_id", min_val=0)
            raise ToolArgumentResolutionException(
                "プレイヤー発行可能な目標は kill_monster, obtain_item, reach_spot, kill_player です。",
                "INVALID_OBJECTIVE_TYPE",
            )

        tid_val: Optional[int] = None
        has_target_name = isinstance(target_name, str) and bool(target_name.strip())

        if has_target_name:
            name = target_name.strip()
            if ot_stripped == "kill_monster":
                if self._monster_template_repository is None:
                    raise ToolArgumentResolutionException(
                        "target_name による解決はモンスターリポジトリが設定されていないため利用できません。target_id を指定してください。",
                        "RESOLVER_NOT_CONFIGURED",
                    )
                template = self._monster_template_repository.find_by_name(name)
                if template is None:
                    raise ToolArgumentResolutionException(
                        "指定したモンスター名が見つかりません。名前を確認してください。",
                        "MONSTER_TEMPLATE_NOT_FOUND",
                    )
                tid_val = template.template_id.value
            elif ot_stripped == "reach_spot":
                if self._spot_repository is None:
                    raise ToolArgumentResolutionException(
                        "target_name による解決はスポットリポジトリが設定されていないため利用できません。target_id を指定してください。",
                        "RESOLVER_NOT_CONFIGURED",
                    )
                spot = self._spot_repository.find_by_name(name)
                if spot is None:
                    raise ToolArgumentResolutionException(
                        "指定したスポット名が見つかりません。名前を確認してください。",
                        "SPOT_NOT_FOUND",
                    )
                tid_val = spot.spot_id.value
            elif ot_stripped == "obtain_item":
                if self._item_spec_repository is None:
                    raise ToolArgumentResolutionException(
                        "target_name による解決はアイテムリポジトリが設定されていないため利用できません。target_id を指定してください。",
                        "RESOLVER_NOT_CONFIGURED",
                    )
                item_spec = self._item_spec_repository.find_by_name(name)
                if item_spec is None:
                    raise ToolArgumentResolutionException(
                        "指定したアイテム名が見つかりません。名前を確認してください。",
                        "ITEM_SPEC_NOT_FOUND",
                    )
                tid_val = item_spec.item_spec_id.value
            elif ot_stripped == "kill_player":
                if self._player_profile_repository is None:
                    raise ToolArgumentResolutionException(
                        "target_name による解決はプレイヤーリポジトリが設定されていないため利用できません。target_id を指定してください。",
                        "RESOLVER_NOT_CONFIGURED",
                    )
                try:
                    player_name = PlayerName(name)
                except PlayerNameValidationException:
                    raise ToolArgumentResolutionException(
                        "指定したプレイヤー名が見つかりません。名前を確認してください。",
                        "PLAYER_PROFILE_NOT_FOUND",
                    ) from None
                profile = self._player_profile_repository.find_by_name(player_name)
                if profile is None:
                    raise ToolArgumentResolutionException(
                        "指定したプレイヤー名が見つかりません。名前を確認してください。",
                        "PLAYER_PROFILE_NOT_FOUND",
                    )
                tid_val = profile.player_id.value

        if tid_val is None and target_id is not None:
            tid_val = safe_int(target_id, "target_id", min_val=0)

        if tid_val is None:
            raise ToolArgumentResolutionException(
                "target_name または target_id を指定してください。",
                "INVALID_OBJECTIVES",
            )

        return tid_val
