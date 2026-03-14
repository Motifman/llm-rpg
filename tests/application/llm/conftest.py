"""
LLM テスト用共通フィクスチャ・ヘルパー。

ToolCommandMapper は Phase 3 で handler_map のみ受け取る形に変更された。
_create_tool_command_mapper でサービス群から handler map を組み立て、ToolCommandMapper を返す。
"""

from typing import Any, Optional
from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.tool_command_mapper import ToolCommandMapper
from ai_rpg_world.application.llm.wiring import _build_tool_handler_map
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)


def _create_tool_command_mapper(
    movement_service: Any,
    pursuit_service: Optional[Any] = None,
    speech_service: Optional[Any] = None,
    interaction_service: Optional[Any] = None,
    harvest_service: Optional[Any] = None,
    attention_service: Optional[Any] = None,
    conversation_service: Optional[Any] = None,
    place_object_service: Optional[Any] = None,
    drop_item_service: Optional[Any] = None,
    chest_service: Optional[Any] = None,
    skill_tool_service: Optional[Any] = None,
    quest_service: Optional[Any] = None,
    guild_service: Optional[Any] = None,
    shop_service: Optional[Any] = None,
    trade_service: Optional[Any] = None,
    post_service: Optional[Any] = None,
    reply_service: Optional[Any] = None,
    user_command_service: Optional[Any] = None,
    item_repository: Optional[Any] = None,
    monster_repository: Optional[Any] = None,
    physical_map_repository: Optional[Any] = None,
    player_status_repository: Optional[Any] = None,
    memory_query_executor: Optional[Any] = None,
    subagent_runner: Optional[Any] = None,
    todo_store: Optional[Any] = None,
    working_memory_store: Optional[Any] = None,
) -> ToolCommandMapper:
    """
    テスト用: サービス群から handler map を組み立て、ToolCommandMapper を返す。
    テストで使う param 名（pursuit_service, quest_service 等）を wiring の名前にマッピングする。
    """
    if physical_map_repository is None:
        physical_map_repository = MagicMock(spec=PhysicalMapRepository)
    if player_status_repository is None:
        player_status_repository = MagicMock(spec=PlayerStatusRepository)
    handler_map = _build_tool_handler_map(
        movement_service=movement_service,
        pursuit_command_service=pursuit_service,
        speech_service=speech_service,
        interaction_service=interaction_service,
        harvest_service=harvest_service,
        attention_service=attention_service,
        conversation_service=conversation_service,
        place_object_service=place_object_service,
        drop_item_service=drop_item_service,
        chest_service=chest_service,
        skill_tool_service=skill_tool_service,
        quest_command_service=quest_service,
        guild_command_service=guild_service,
        shop_command_service=shop_service,
        trade_command_service=trade_service,
        post_service=post_service,
        reply_service=reply_service,
        user_command_service=user_command_service,
        item_repository=item_repository,
        monster_repository=monster_repository,
        physical_map_repository=physical_map_repository,
        player_status_repository=player_status_repository,
        memory_query_executor=memory_query_executor,
        subagent_runner=subagent_runner,
        todo_store=todo_store,
        working_memory_store=working_memory_store,
    )
    return ToolCommandMapper(handler_map=handler_map)
