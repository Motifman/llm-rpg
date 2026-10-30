"""
LLM ツール定義のカテゴリ別カタログ。

各モジュールが get_*_specs() で (ToolDefinitionDto, IAvailabilityResolver) のリストを返し、
register_default_tools がそれらを集約してレジストリへ登録する。
"""

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import (
    IAvailabilityResolver,
    IGameToolRegistry,
)
from ai_rpg_world.application.llm.services.tool_catalog.guild import get_guild_specs
from ai_rpg_world.application.llm.services.tool_catalog.memory import get_memory_specs
from ai_rpg_world.application.llm.services.tool_catalog.quest import get_quest_specs
from ai_rpg_world.application.llm.services.tool_catalog.shop import get_shop_specs
from ai_rpg_world.application.llm.services.tool_catalog.sns import (
    get_sns_specs,
    get_sns_virtual_page_specs,
)
from ai_rpg_world.application.llm.services.tool_catalog.speech import get_speech_specs
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import get_spot_graph_specs
from ai_rpg_world.application.llm.services.tool_catalog.trade import (
    get_trade_specs,
    get_trade_virtual_page_specs,
)


def _register_specs(
    registry: IGameToolRegistry,
    specs: list[tuple[ToolDefinitionDto, IAvailabilityResolver]],
) -> None:
    """(definition, resolver) のリストをレジストリに登録する。"""
    for definition, resolver in specs:
        registry.register(definition, resolver)


def register_spot_graph_tools(registry: IGameToolRegistry) -> None:
    """スポットグラフ用ツール（spot_graph_*）をレジストリに登録する。"""
    _register_specs(registry, get_spot_graph_specs())


def register_default_tools(
    registry: IGameToolRegistry,
    *,
    speech_enabled: bool = False,
    quest_enabled: bool = False,
    guild_enabled: bool = False,
    shop_enabled: bool = False,
    trade_enabled: bool = False,
    sns_enabled: bool = False,
    sns_virtual_pages_enabled: bool = False,
    trade_virtual_pages_enabled: bool = False,
) -> None:
    """標準ツール群を登録し、依存サービスがあるカテゴリだけ追加する。

    取引所（Trade）カタログは `trade_enabled` のみで登録され、`sns_enabled` には依存しない。
    プロダクト設定で SNS と取引の両方を有効にした場合は、SNS 系と取引系が**別カタログとして**並ぶ
    （取引は SNS の下位機能ではない）。利用可能ツールの切り替えは `PlayerCurrentStateDto` の
    アクティブアプリ（none / sns / trade）と各 resolver が担う。
    """
    if not isinstance(registry, IGameToolRegistry):
        raise TypeError("registry must be IGameToolRegistry")

    if speech_enabled:
        _register_specs(registry, get_speech_specs())
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
    _register_specs(registry, get_memory_specs())


__all__ = ["register_default_tools", "register_spot_graph_tools"]
