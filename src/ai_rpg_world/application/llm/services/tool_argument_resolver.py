"""LLM の UI 向けラベル引数を canonical args に解決する。"""

from typing import TYPE_CHECKING, Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
from ai_rpg_world.application.llm.contracts.interfaces import IToolArgumentResolver
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.services._argument_resolvers import (
    CombatSkillArgumentResolver,
    GuildShopTradeArgumentResolver,
    MovementArgumentResolver,
    QuestArgumentResolver,
    WorldArgumentResolver,
)
from ai_rpg_world.application.llm.services.quest_objective_target_resolver import (
    QuestObjectiveTargetResolver,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_NO_OP

if TYPE_CHECKING:
    from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
    from ai_rpg_world.domain.monster.repository.monster_repository import MonsterTemplateRepository
    from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
    from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository

__all__ = [
    "DefaultToolArgumentResolver",
    "ToolArgumentResolutionException",
]


class DefaultToolArgumentResolver(IToolArgumentResolver):
    """ツール名ごとに UI ラベルを既存アプリケーション層の引数へ解決する。"""

    def __init__(
        self,
        *,
        monster_template_repository: Optional["MonsterTemplateRepository"] = None,
        spot_repository: Optional["SpotRepository"] = None,
        item_spec_repository: Optional["ItemSpecRepository"] = None,
        player_profile_repository: Optional["PlayerProfileRepository"] = None,
    ) -> None:
        objective_resolver = QuestObjectiveTargetResolver(
            monster_template_repository=monster_template_repository,
            spot_repository=spot_repository,
            item_spec_repository=item_spec_repository,
            player_profile_repository=player_profile_repository,
        )
        self._resolvers = [
            MovementArgumentResolver(),
            WorldArgumentResolver(),
            CombatSkillArgumentResolver(),
            QuestArgumentResolver(objective_resolver),
            GuildShopTradeArgumentResolver(),
        ]

    def resolve(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        if not isinstance(tool_name, str):
            raise TypeError("tool_name must be str")
        if arguments is not None and not isinstance(arguments, dict):
            raise TypeError("arguments must be dict or None")
        if not isinstance(runtime_context, ToolRuntimeContextDto):
            raise TypeError("runtime_context must be ToolRuntimeContextDto")

        args = arguments or {}

        if tool_name == TOOL_NAME_NO_OP:
            return {}

        for resolver in self._resolvers:
            result = resolver.resolve_args(tool_name, args, runtime_context)
            if result is not None:
                return result

        return dict(args)
