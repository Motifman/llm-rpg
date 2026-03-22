"""
LLM ツール定義のカテゴリ別カタログ。

各モジュールが get_*_specs() で (ToolDefinitionDto, IAvailabilityResolver) のリストを返し、
register_default_tools がそれらを集約してレジストリへ登録する。
"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import (
    IAvailabilityResolver,
    IGameToolRegistry,
)
from ai_rpg_world.application.llm.services.tool_catalog.combat import get_combat_specs
from ai_rpg_world.application.llm.services.tool_catalog.guild import get_guild_specs
from ai_rpg_world.application.llm.services.tool_catalog.memory import get_memory_specs
from ai_rpg_world.application.llm.services.tool_catalog.movement import get_movement_specs
from ai_rpg_world.application.llm.services.tool_catalog.pursuit import get_pursuit_specs
from ai_rpg_world.application.llm.services.tool_catalog.quest import get_quest_specs
from ai_rpg_world.application.llm.services.tool_catalog.shop import get_shop_specs
from ai_rpg_world.application.llm.services.tool_catalog.sns import (
    get_sns_specs,
    get_sns_virtual_page_specs,
)
from ai_rpg_world.application.llm.services.tool_catalog.speech import get_speech_specs
from ai_rpg_world.application.llm.services.tool_catalog.trade import (
    get_trade_specs,
    get_trade_virtual_page_specs,
)
from ai_rpg_world.application.llm.services.tool_catalog.world import get_world_specs


def _register_specs(
    registry: IGameToolRegistry,
    specs: List[Tuple[ToolDefinitionDto, IAvailabilityResolver]],
) -> None:
    """(definition, resolver) のリストをレジストリに登録する。"""
    for definition, resolver in specs:
        registry.register(definition, resolver)


def register_default_tools(
    registry: IGameToolRegistry,
    *,
    speech_enabled: bool = False,
    interaction_enabled: bool = False,
    harvest_enabled: bool = False,
    attention_enabled: bool = False,
    conversation_enabled: bool = False,
    place_enabled: bool = False,
    drop_enabled: bool = False,
    chest_enabled: bool = False,
    pursuit_enabled: bool = False,
    combat_enabled: bool = False,
    quest_enabled: bool = False,
    guild_enabled: bool = False,
    shop_enabled: bool = False,
    trade_enabled: bool = False,
    sns_enabled: bool = False,
    sns_virtual_pages_enabled: bool = False,
    trade_virtual_pages_enabled: bool = False,
    inspect_item_enabled: bool = False,
    inspect_target_enabled: bool = False,
    memory_query_enabled: bool = False,
    subagent_enabled: bool = False,
    todo_enabled: bool = False,
    working_memory_enabled: bool = False,
) -> None:
    """標準ツール群を登録し、依存サービスがあるカテゴリだけ追加する。

    Trade は trade_enabled のとき登録し、一覧の露出は取引所モードと各 resolver で制御する。
    """
    if not isinstance(registry, IGameToolRegistry):
        raise TypeError("registry must be IGameToolRegistry")

    _register_specs(registry, get_movement_specs())

    if pursuit_enabled:
        _register_specs(registry, get_pursuit_specs())
    if speech_enabled:
        _register_specs(registry, get_speech_specs())
    _register_specs(
        registry,
        get_world_specs(
            interaction_enabled=interaction_enabled,
            harvest_enabled=harvest_enabled,
            attention_enabled=attention_enabled,
            conversation_enabled=conversation_enabled,
            place_enabled=place_enabled,
            drop_enabled=drop_enabled,
            chest_enabled=chest_enabled,
            inspect_item_enabled=inspect_item_enabled,
            inspect_target_enabled=inspect_target_enabled,
        ),
    )
    if combat_enabled:
        _register_specs(registry, get_combat_specs())
    if quest_enabled:
        _register_specs(registry, get_quest_specs())
    if guild_enabled:
        _register_specs(registry, get_guild_specs())
    if shop_enabled:
        _register_specs(registry, get_shop_specs())
    if trade_enabled:
        _register_specs(registry, get_trade_specs())
    if trade_enabled and trade_virtual_pages_enabled:
        _register_specs(registry, get_trade_virtual_page_specs())
    if sns_enabled:
        _register_specs(registry, get_sns_specs())
    if sns_enabled and sns_virtual_pages_enabled:
        _register_specs(registry, get_sns_virtual_page_specs())
    _register_specs(
        registry,
        get_memory_specs(
            memory_query_enabled=memory_query_enabled,
            subagent_enabled=subagent_enabled,
            todo_enabled=todo_enabled,
            working_memory_enabled=working_memory_enabled,
        ),
    )


__all__ = ["register_default_tools"]
