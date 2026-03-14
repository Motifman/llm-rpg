"""
LLM エージェント用ワイヤリング（方針 B）。

観測 → schedule_turn → tick → run_scheduled_turns および
プロンプト組み立て・ツール実行・結果記録までを一括で組み立てる。

本モジュールは**ライブラリ**として提供する。ゲームの組み立て（WorldSimulationApplicationService や
EventHandlerComposition のインスタンス化）は**呼び出し元（外部）**で行い、本関数の返り値を渡す。

【ブートストラップ契約（呼び出し元が守ること）】
1. create_llm_agent_wiring(...) を呼び、返り値 (observation_registry, llm_turn_trigger) を取得する。
2. observation_registry を EventHandlerComposition の observation_registry 引数に渡す。
3. llm_turn_trigger を WorldSimulationApplicationService の llm_turn_trigger 引数に渡す。

【オプション: 意図的ドロップ（world_drop_item）】
- LLM に world_drop_item ツールを有効化する: drop_item_service に PlayerDropItemApplicationService を渡す。
  （DropItemApplicationService + PlayerDropItemApplicationService を PlayerInventoryRepository / PlayerStatusRepository /
   UnitOfWork で組み立てて作成する。）
- ドロップしたアイテムをマップ上に GROUND_ITEM として配置する: composition_builder 内で
  ItemDroppedFromInventoryDropHandler と IntentionalDropEventHandlerRegistry を組み立て、
  EventHandlerComposition の intentional_drop_registry 引数に渡す。
  （inventory_overflow_registry と同様に、player_status_repository と physical_map_repository をハンドラに渡す。）
"""

import os
from typing import Any, Callable, Dict, NamedTuple, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto

from ai_rpg_world.application.llm.wiring._llm_client_factory import (
    create_llm_client_from_env,
    create_subagent_invoke_text,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    IEpisodeMemoryStore,
    ILLMClient,
    ILLMPlayerResolver,
    ILongTermMemoryStore,
    ILlmTurnTrigger,
    IReflectionRunner,
    IReflectionStatePort,
    ISlidingWindowMemory,
)
from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.services.agent_orchestrator import LlmAgentOrchestrator
from ai_rpg_world.application.llm.services.available_tools_provider import (
    DefaultAvailableToolsProvider,
)
from ai_rpg_world.application.llm.services.context_format_strategy import (
    SectionBasedContextFormatStrategy,
)
from ai_rpg_world.application.llm.services.current_state_formatter import (
    DefaultCurrentStateFormatter,
)
from ai_rpg_world.application.llm.services.game_tool_registry import (
    DefaultGameToolRegistry,
)
from ai_rpg_world.application.llm.services.in_memory_todo_store import (
    InMemoryTodoStore,
)
from ai_rpg_world.application.llm.services.in_memory_working_memory_store import (
    InMemoryWorkingMemoryStore,
)
from ai_rpg_world.application.llm.services.handle_store import InMemoryHandleStore
from ai_rpg_world.application.llm.services.memory_query_executor import (
    MemoryQueryExecutor,
)
from ai_rpg_world.application.llm.services.subagent_runner import SubagentRunner
from ai_rpg_world.application.llm.services.llm_agent_turn_runner import (
    LlmAgentTurnRunner,
)
from ai_rpg_world.application.llm.services.memory_extractor import (
    RuleBasedMemoryExtractor,
)
from ai_rpg_world.application.llm.services.predictive_memory_retriever import (
    DefaultPredictiveMemoryRetriever,
)
from ai_rpg_world.application.llm.services.reflection_runner import (
    DefaultReflectionRunner,
)
from ai_rpg_world.application.llm.services.reflection_service import (
    RuleBasedReflectionService,
)
from ai_rpg_world.application.llm.services.llm_player_resolver import (
    ProfileBasedLlmPlayerResolver,
)
from ai_rpg_world.application.llm.services.llm_turn_trigger import DefaultLlmTurnTrigger
from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder
from ai_rpg_world.application.llm.services.recent_events_formatter import (
    DefaultRecentEventsFormatter,
)
from ai_rpg_world.application.llm.services.system_prompt_builder import (
    DefaultSystemPromptBuilder,
)
from ai_rpg_world.application.llm.services.sliding_window_memory import (
    DefaultSlidingWindowMemory,
)
from ai_rpg_world.application.llm.services.executors.guild_executor import (
    GuildToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.memory_executor import (
    MemoryToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.movement_executor import (
    MovementToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.quest_executor import (
    QuestToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.shop_executor import (
    ShopToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.speech_executor import (
    SpeechToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.sns_executor import (
    SnsToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.todo_executor import (
    TodoToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.trade_executor import (
    TradeToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.world_executor import (
    WorldToolExecutor,
)
from ai_rpg_world.application.llm.services.tool_command_mapper import (
    ToolCommandMapper,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_NO_OP
from ai_rpg_world.application.llm.services.tool_argument_resolver import (
    DefaultToolArgumentResolver,
)
from ai_rpg_world.application.world.contracts.queries import (
    GetPlayerCurrentStateQuery,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.application.llm.services.tool_definitions import (
    register_default_tools,
)
from ai_rpg_world.application.llm.services.ui_context_builder import (
    DefaultLlmUiContextBuilder,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
    IObservationFormatter,
)
from ai_rpg_world.application.observation.handlers.observation_event_handler import (
    ObservationEventHandler,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
    create_observation_recipient_resolver,
)
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.domain.world.service.world_time_config_service import (
    WorldTimeConfigService,
)
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.infrastructure.events.observation_event_handler_registry import (
    ObservationEventHandlerRegistry,
)
from ai_rpg_world.infrastructure.llm._memory_store_factory import (
    create_episode_memory_store,
    create_long_term_memory_store,
    create_reflection_state_port,
)

_ENV_LLM_VIEW_DISTANCE = "LLM_VIEW_DISTANCE"
_DEFAULT_LLM_VIEW_DISTANCE = 5


class _MemoryStackResult(NamedTuple):
    """_build_memory_stack の返り値。episode / long_term / reflection / working / todo / handle の構築結果。"""

    episode_memory_store: IEpisodeMemoryStore
    long_term_memory_store: ILongTermMemoryStore
    reflection_state_port: Optional[IReflectionStatePort]
    working_memory_store: InMemoryWorkingMemoryStore
    todo_store: InMemoryTodoStore
    handle_store: InMemoryHandleStore


class _ReflectionStackResult(NamedTuple):
    """_build_reflection_stack の返り値。reflection_service と reflection_runner の構築結果。"""

    reflection_service: RuleBasedReflectionService
    reflection_runner: Optional[IReflectionRunner]


def _build_reflection_stack(
    *,
    episode_memory_store: IEpisodeMemoryStore,
    long_term_memory_store: ILongTermMemoryStore,
    reflection_state_port: Optional[IReflectionStatePort],
    player_status_repository: PlayerStatusRepository,
    llm_player_resolver: ILLMPlayerResolver,
    world_time_config_service: Optional[WorldTimeConfigService] = None,
) -> _ReflectionStackResult:
    """
    RuleBasedReflectionService と DefaultReflectionRunner を構築する。

    world_time_config_service が WorldTimeConfigService のインスタンスの場合のみ
    reflection_runner を作成し、それ以外の場合は None を返す。
    """
    reflection_service = RuleBasedReflectionService(
        episode_store=episode_memory_store,
        long_term_store=long_term_memory_store,
    )
    reflection_runner: Optional[IReflectionRunner] = None
    if world_time_config_service is not None and isinstance(
        world_time_config_service, WorldTimeConfigService
    ):
        reflection_runner = DefaultReflectionRunner(
            reflection_service=reflection_service,
            player_status_repository=player_status_repository,
            llm_player_resolver=llm_player_resolver,
            world_time_config=world_time_config_service,
            state_port=reflection_state_port,
        )
    return _ReflectionStackResult(
        reflection_service=reflection_service,
        reflection_runner=reflection_runner,
    )


class _ToolStackResult(NamedTuple):
    """_build_tool_stack の返り値。available_tools_provider, tool_command_mapper, tool_argument_resolver の構築結果。"""

    available_tools_provider: DefaultAvailableToolsProvider
    tool_command_mapper: ToolCommandMapper
    tool_argument_resolver: DefaultToolArgumentResolver


def _build_tool_handler_map(
    *,
    movement_service: Any,
    pursuit_command_service: Optional[Any],
    speech_service: Optional[Any],
    interaction_service: Optional[Any],
    harvest_service: Optional[Any],
    attention_service: Optional[Any],
    conversation_service: Optional[Any],
    place_object_service: Optional[Any],
    drop_item_service: Optional[Any],
    chest_service: Optional[Any],
    skill_tool_service: Optional[Any],
    quest_command_service: Optional[Any],
    guild_command_service: Optional[Any],
    shop_command_service: Optional[Any],
    trade_command_service: Optional[Any],
    post_service: Optional[Any],
    reply_service: Optional[Any],
    user_command_service: Optional[Any],
    item_repository: Optional[Any],
    monster_repository: Optional[Any],
    physical_map_repository: PhysicalMapRepository,
    player_status_repository: PlayerStatusRepository,
    memory_query_executor: Optional[MemoryQueryExecutor],
    subagent_runner: Optional[SubagentRunner],
    todo_store: Optional[InMemoryTodoStore],
    working_memory_store: Optional[InMemoryWorkingMemoryStore],
) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
    """
    Executor 群を組み立て、tool_name → handler の辞書を返す。
    movement_service は必須。各 service が None の場合は対応するハンドラは登録されない。
    """
    move_to_destination = getattr(movement_service, "move_to_destination", None)
    if not callable(move_to_destination):
        raise TypeError("movement_service must have a callable move_to_destination")
    if pursuit_command_service is not None:
        if not callable(getattr(pursuit_command_service, "start_pursuit", None)):
            raise TypeError("pursuit_command_service must have a callable start_pursuit")
        if not callable(getattr(pursuit_command_service, "cancel_pursuit", None)):
            raise TypeError("pursuit_command_service must have a callable cancel_pursuit")
    if speech_service is not None and not callable(
        getattr(speech_service, "speak", None)
    ):
        raise TypeError("speech_service must have a callable speak")

    handler_map: Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]] = {
        TOOL_NAME_NO_OP: lambda pid, a: LlmCommandResultDto(
            success=True, message="何もしませんでした。", was_no_op=True
        ),
    }
    handler_map.update(
        GuildToolExecutor(guild_service=guild_command_service).get_handlers()
    )
    handler_map.update(
        MovementToolExecutor(
            movement_service=movement_service,
            pursuit_service=pursuit_command_service,
        ).get_handlers()
    )
    handler_map.update(
        SpeechToolExecutor(speech_service=speech_service).get_handlers()
    )
    handler_map.update(
        MemoryToolExecutor(
            memory_query_executor=memory_query_executor,
            subagent_runner=subagent_runner,
            working_memory_store=working_memory_store,
        ).get_handlers()
    )
    handler_map.update(TodoToolExecutor(todo_store).get_handlers())
    handler_map.update(
        QuestToolExecutor(quest_service=quest_command_service).get_handlers()
    )
    handler_map.update(
        ShopToolExecutor(shop_service=shop_command_service).get_handlers()
    )
    handler_map.update(
        TradeToolExecutor(trade_service=trade_command_service).get_handlers()
    )
    handler_map.update(
        SnsToolExecutor(
            post_service=post_service,
            reply_service=reply_service,
            user_command_service=user_command_service,
        ).get_handlers()
    )
    handler_map.update(
        WorldToolExecutor(
            interaction_service=interaction_service,
            harvest_service=harvest_service,
            attention_service=attention_service,
            conversation_service=conversation_service,
            place_object_service=place_object_service,
            drop_item_service=drop_item_service,
            chest_service=chest_service,
            skill_tool_service=skill_tool_service,
            item_repository=item_repository,
            monster_repository=monster_repository,
            physical_map_repository=physical_map_repository,
            player_status_repository=player_status_repository,
        ).get_handlers()
    )
    return handler_map


def _build_tool_stack(
    *,
    game_tool_registry: DefaultGameToolRegistry,
    memory_query_executor: MemoryQueryExecutor,
    subagent_runner: SubagentRunner,
    working_memory_store: InMemoryWorkingMemoryStore,
    todo_store: InMemoryTodoStore,
    movement_service: Any,
    pursuit_command_service: Optional[Any],
    speech_service: Optional[Any],
    interaction_service: Optional[Any],
    harvest_service: Optional[Any],
    attention_service: Optional[Any],
    conversation_service: Optional[Any],
    place_object_service: Optional[Any],
    drop_item_service: Optional[Any],
    chest_service: Optional[Any],
    skill_tool_service: Optional[Any],
    quest_command_service: Optional[Any],
    guild_command_service: Optional[Any],
    shop_command_service: Optional[Any],
    trade_command_service: Optional[Any],
    post_service: Optional[Any],
    reply_service: Optional[Any],
    user_command_service: Optional[Any],
    item_repository: Optional[Any],
    monster_repository: Optional[Any],
    physical_map_repository: PhysicalMapRepository,
    player_status_repository: PlayerStatusRepository,
    monster_template_repository: Optional[Any],
    spot_repository: Optional[Any],
    item_spec_repository: Optional[Any],
    player_profile_repository: PlayerProfileRepository,
) -> _ToolStackResult:
    """
    register_default_tools, available_tools_provider, tool_command_mapper, tool_argument_resolver を構築する。
    """
    register_default_tools(
        game_tool_registry,
        speech_enabled=speech_service is not None,
        interaction_enabled=interaction_service is not None,
        harvest_enabled=harvest_service is not None,
        attention_enabled=attention_service is not None,
        conversation_enabled=conversation_service is not None,
        place_enabled=place_object_service is not None,
        drop_enabled=drop_item_service is not None,
        chest_enabled=chest_service is not None,
        pursuit_enabled=pursuit_command_service is not None,
        combat_enabled=skill_tool_service is not None,
        quest_enabled=quest_command_service is not None,
        guild_enabled=guild_command_service is not None,
        shop_enabled=shop_command_service is not None,
        trade_enabled=trade_command_service is not None,
        sns_enabled=(
            post_service is not None
            or reply_service is not None
            or user_command_service is not None
        ),
        inspect_item_enabled=item_repository is not None,
        inspect_target_enabled=(
            monster_repository is not None
            and physical_map_repository is not None
            and player_status_repository is not None
        ),
        memory_query_enabled=True,
        subagent_enabled=True,
        todo_enabled=True,
        working_memory_enabled=True,
    )
    available_tools_provider = DefaultAvailableToolsProvider(game_tool_registry)
    handler_map = _build_tool_handler_map(
        movement_service=movement_service,
        pursuit_command_service=pursuit_command_service,
        speech_service=speech_service,
        interaction_service=interaction_service,
        harvest_service=harvest_service,
        attention_service=attention_service,
        conversation_service=conversation_service,
        place_object_service=place_object_service,
        drop_item_service=drop_item_service,
        chest_service=chest_service,
        skill_tool_service=skill_tool_service,
        quest_command_service=quest_command_service,
        guild_command_service=guild_command_service,
        shop_command_service=shop_command_service,
        trade_command_service=trade_command_service,
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
    tool_command_mapper = ToolCommandMapper(handler_map=handler_map)
    tool_argument_resolver = DefaultToolArgumentResolver(
        monster_template_repository=monster_template_repository,
        spot_repository=spot_repository,
        item_spec_repository=item_spec_repository,
        player_profile_repository=player_profile_repository,
    )
    return _ToolStackResult(
        available_tools_provider=available_tools_provider,
        tool_command_mapper=tool_command_mapper,
        tool_argument_resolver=tool_argument_resolver,
    )


def _build_observation_stack(
    *,
    player_status_repository: PlayerStatusRepository,
    physical_map_repository: PhysicalMapRepository,
    player_profile_repository: PlayerProfileRepository,
    quest_repository: Optional[Any],
    guild_repository: Optional[Any],
    shop_repository: Optional[Any],
    trade_repository: Optional[Any],
    monster_repository: Optional[Any],
    hit_box_repository: Optional[Any],
    skill_loadout_repository: Optional[Any],
    skill_deck_progress_repository: Optional[Any],
    sns_user_repository: Optional[Any],
    buffer: "IObservationContextBuffer",
    unit_of_work_factory: UnitOfWorkFactory,
    llm_turn_trigger: ILlmTurnTrigger,
    llm_player_resolver: ILLMPlayerResolver,
    movement_service: Any,
    game_time_provider: Optional[Any],
    world_time_config_service: Optional[Any],
    observation_formatter: Optional[IObservationFormatter],
    spot_repository: Optional[Any],
    item_spec_repository: Optional[Any],
    item_repository: Optional[Any],
    skill_spec_repository: Optional[Any],
) -> ObservationEventHandlerRegistry:
    """
    observation_resolver, formatter, handler, registry を構築する。
    observation_formatter が None の場合は ObservationFormatter を遅延 import で生成する。
    """
    observation_resolver = create_observation_recipient_resolver(
        player_status_repository=player_status_repository,
        physical_map_repository=physical_map_repository,
        quest_repository=quest_repository,
        guild_repository=guild_repository,
        shop_repository=shop_repository,
        trade_repository=trade_repository,
        monster_repository=monster_repository,
        hit_box_repository=hit_box_repository,
        skill_loadout_repository=skill_loadout_repository,
        skill_deck_progress_repository=skill_deck_progress_repository,
        sns_user_repository=sns_user_repository,
    )
    formatter = observation_formatter
    if formatter is None:
        from ai_rpg_world.application.observation.services.observation_formatter import (
            ObservationFormatter,
        )
        formatter = ObservationFormatter(
            spot_repository=spot_repository,
            player_profile_repository=player_profile_repository,
            item_spec_repository=item_spec_repository,
            item_repository=item_repository,
            shop_repository=shop_repository,
            guild_repository=guild_repository,
            monster_repository=monster_repository,
            skill_spec_repository=skill_spec_repository,
            sns_user_repository=sns_user_repository,
        )
    observation_handler = ObservationEventHandler(
        resolver=observation_resolver,
        formatter=formatter,
        buffer=buffer,
        unit_of_work_factory=unit_of_work_factory,
        player_status_repository=player_status_repository,
        turn_trigger=llm_turn_trigger,
        llm_player_resolver=llm_player_resolver,
        movement_service=movement_service,
        game_time_provider=game_time_provider,
        world_time_config=world_time_config_service,
    )
    return ObservationEventHandlerRegistry(
        observation_handler=observation_handler,
    )


def _build_prompt_stack(
    *,
    buffer: "IObservationContextBuffer",
    sliding_window: ISlidingWindowMemory,
    action_result_store: IActionResultStore,
    world_query_service: Any,
    player_profile_repository: PlayerProfileRepository,
    current_state_formatter: "DefaultCurrentStateFormatter",
    recent_events_formatter: "DefaultRecentEventsFormatter",
    context_format_strategy: "SectionBasedContextFormatStrategy",
    system_prompt_builder: "DefaultSystemPromptBuilder",
    available_tools_provider: "DefaultAvailableToolsProvider",
    ui_context_builder: "DefaultLlmUiContextBuilder",
    episode_memory_store: IEpisodeMemoryStore,
    long_term_memory_store: ILongTermMemoryStore,
    tile_map_view_distance: int,
) -> DefaultPromptBuilder:
    """
    predictive_retriever と prompt_builder を構築する。
    """
    predictive_retriever = DefaultPredictiveMemoryRetriever(
        episode_store=episode_memory_store,
        long_term_store=long_term_memory_store,
    )
    return DefaultPromptBuilder(
        observation_buffer=buffer,
        sliding_window_memory=sliding_window,
        action_result_store=action_result_store,
        world_query_service=world_query_service,
        player_profile_repository=player_profile_repository,
        current_state_formatter=current_state_formatter,
        recent_events_formatter=recent_events_formatter,
        context_format_strategy=context_format_strategy,
        system_prompt_builder=system_prompt_builder,
        available_tools_provider=available_tools_provider,
        ui_context_builder=ui_context_builder,
        predictive_memory_retriever=predictive_retriever,
        tile_map_view_distance=tile_map_view_distance,
    )


def _build_memory_stack(
    *,
    memory_db_path: Optional[str] = None,
    episode_memory_store: Optional[IEpisodeMemoryStore] = None,
    long_term_memory_store: Optional[ILongTermMemoryStore] = None,
    reflection_state_port: Optional[IReflectionStatePort] = None,
) -> _MemoryStackResult:
    """
    episode / long_term / reflection / working / todo / handle を構築する。

    memory_db_path または環境変数 LLM_MEMORY_DB_PATH により永続化の有無が決まる。
    引数で渡された store/port がある場合はそのまま使用し、None の場合のみファクトリで生成する。
    """
    if episode_memory_store is None:
        episode_memory_store = create_episode_memory_store(memory_db_path=memory_db_path)
    if long_term_memory_store is None:
        long_term_memory_store = create_long_term_memory_store(
            memory_db_path=memory_db_path
        )
    working_memory_store = InMemoryWorkingMemoryStore()
    todo_store = InMemoryTodoStore()
    handle_store = InMemoryHandleStore()
    if reflection_state_port is None:
        reflection_state_port = create_reflection_state_port(
            memory_db_path=memory_db_path
        )
    return _MemoryStackResult(
        episode_memory_store=episode_memory_store,
        long_term_memory_store=long_term_memory_store,
        reflection_state_port=reflection_state_port,
        working_memory_store=working_memory_store,
        todo_store=todo_store,
        handle_store=handle_store,
    )


class LlmAgentWiringResult:
    """create_llm_agent_wiring の返り値。unpacking で (registry, trigger) も取得可能。"""

    def __init__(
        self,
        observation_registry: "ObservationEventHandlerRegistry",
        llm_turn_trigger: ILlmTurnTrigger,
        reflection_runner: Optional[IReflectionRunner] = None,
    ) -> None:
        self.observation_registry = observation_registry
        self.llm_turn_trigger = llm_turn_trigger
        self.reflection_runner = reflection_runner

    def __iter__(self) -> Any:
        yield self.observation_registry
        yield self.llm_turn_trigger


def create_llm_agent_wiring(
    *,
    player_status_repository: PlayerStatusRepository,
    physical_map_repository: PhysicalMapRepository,
    world_query_service: Any,
    movement_service: Any,
    pursuit_command_service: Optional[Any] = None,
    speech_service: Optional[Any] = None,
    interaction_service: Optional[Any] = None,
    harvest_service: Optional[Any] = None,
    attention_service: Optional[Any] = None,
    conversation_service: Optional[Any] = None,
    place_object_service: Optional[Any] = None,
    drop_item_service: Optional[Any] = None,
    chest_service: Optional[Any] = None,
    skill_tool_service: Optional[Any] = None,
    player_profile_repository: PlayerProfileRepository,
    unit_of_work_factory: UnitOfWorkFactory,
    observation_buffer: Optional[IObservationContextBuffer] = None,
    observation_formatter: Optional[IObservationFormatter] = None,
    spot_repository: Optional[Any] = None,
    item_spec_repository: Optional[Any] = None,
    monster_template_repository: Optional[Any] = None,
    item_repository: Optional[Any] = None,
    quest_repository: Optional[Any] = None,
    shop_repository: Optional[Any] = None,
    trade_repository: Optional[Any] = None,
    guild_repository: Optional[Any] = None,
    monster_repository: Optional[Any] = None,
    hit_box_repository: Optional[Any] = None,
    skill_loadout_repository: Optional[Any] = None,
    skill_deck_progress_repository: Optional[Any] = None,
    skill_spec_repository: Optional[Any] = None,
    sns_user_repository: Optional[Any] = None,
    quest_command_service: Optional[Any] = None,
    guild_command_service: Optional[Any] = None,
    shop_command_service: Optional[Any] = None,
    trade_command_service: Optional[Any] = None,
    post_service: Optional[Any] = None,
    reply_service: Optional[Any] = None,
    user_command_service: Optional[Any] = None,
    llm_client: Optional[ILLMClient] = None,
    game_time_provider: Optional[Any] = None,
    world_time_config_service: Optional[Any] = None,
    memory_db_path: Optional[str] = None,
    episode_memory_store: Optional[IEpisodeMemoryStore] = None,
    long_term_memory_store: Optional[Any] = None,
    reflection_state_port: Optional[Any] = None,
    action_result_store: Optional[IActionResultStore] = None,
    sliding_window_memory: Optional[ISlidingWindowMemory] = None,
    llm_player_resolver: Optional[ILLMPlayerResolver] = None,
    max_turns: int = 5,
    llm_view_distance: Optional[int] = None,
) -> "LlmAgentWiringResult":
    """
    LLM エージェント用の観測ハンドラ登録用 Registry と LlmTurnTrigger を組み立てて返す。
    """
    if player_status_repository is None:
        raise TypeError("player_status_repository must not be None")
    if physical_map_repository is None:
        raise TypeError("physical_map_repository must not be None")
    if world_query_service is None:
        raise TypeError("world_query_service must not be None")
    if movement_service is None:
        raise TypeError("movement_service must not be None")
    if player_profile_repository is None:
        raise TypeError("player_profile_repository must not be None")
    if unit_of_work_factory is None:
        raise TypeError("unit_of_work_factory must not be None")

    buffer = observation_buffer if observation_buffer is not None else DefaultObservationContextBuffer()
    current_state_formatter = DefaultCurrentStateFormatter()

    sliding_window = (
        sliding_window_memory
        if sliding_window_memory is not None
        else DefaultSlidingWindowMemory()
    )
    action_result_store = (
        action_result_store
        if action_result_store is not None
        else DefaultActionResultStore()
    )
    ui_context_builder = DefaultLlmUiContextBuilder()
    recent_events_formatter = DefaultRecentEventsFormatter()
    context_format_strategy = SectionBasedContextFormatStrategy()
    system_prompt_builder = DefaultSystemPromptBuilder()
    game_tool_registry = DefaultGameToolRegistry()

    if llm_view_distance is not None:
        effective_view_distance = llm_view_distance
    else:
        raw = (os.environ.get(_ENV_LLM_VIEW_DISTANCE) or "").strip()
        if raw:
            try:
                effective_view_distance = int(raw)
                if effective_view_distance < 0:
                    effective_view_distance = _DEFAULT_LLM_VIEW_DISTANCE
            except ValueError:
                effective_view_distance = _DEFAULT_LLM_VIEW_DISTANCE
        else:
            effective_view_distance = _DEFAULT_LLM_VIEW_DISTANCE

    memory_stack = _build_memory_stack(
        memory_db_path=memory_db_path,
        episode_memory_store=episode_memory_store,
        long_term_memory_store=long_term_memory_store,
        reflection_state_port=reflection_state_port,
    )
    episode_memory_store = memory_stack.episode_memory_store
    long_term_memory_store = memory_stack.long_term_memory_store
    reflection_state_port = memory_stack.reflection_state_port
    working_memory_store = memory_stack.working_memory_store
    todo_store = memory_stack.todo_store
    handle_store = memory_stack.handle_store

    def _state_provider(pid: PlayerId) -> str:
        dto = world_query_service.get_player_current_state(
            GetPlayerCurrentStateQuery(
                player_id=pid.value,
                view_distance=effective_view_distance,
            )
        )
        if dto is None:
            return "（情報なし）"
        return current_state_formatter.format(dto)

    memory_query_executor = MemoryQueryExecutor(
        episode_store=episode_memory_store,
        long_term_store=long_term_memory_store,
        sliding_window=sliding_window,
        action_result_store=action_result_store,
        working_memory_store=working_memory_store,
        state_provider=_state_provider,
        recent_events_formatter=recent_events_formatter,
        handle_store=handle_store,
    )
    client = llm_client if llm_client is not None else create_llm_client_from_env()
    subagent_invoke_text = create_subagent_invoke_text(client)
    subagent_runner = SubagentRunner(
        memory_query_executor=memory_query_executor,
        invoke_text=subagent_invoke_text,
        handle_store=handle_store,
    )

    tool_stack = _build_tool_stack(
        game_tool_registry=game_tool_registry,
        memory_query_executor=memory_query_executor,
        subagent_runner=subagent_runner,
        working_memory_store=working_memory_store,
        todo_store=todo_store,
        movement_service=movement_service,
        pursuit_command_service=pursuit_command_service,
        speech_service=speech_service,
        interaction_service=interaction_service,
        harvest_service=harvest_service,
        attention_service=attention_service,
        conversation_service=conversation_service,
        place_object_service=place_object_service,
        drop_item_service=drop_item_service,
        chest_service=chest_service,
        skill_tool_service=skill_tool_service,
        quest_command_service=quest_command_service,
        guild_command_service=guild_command_service,
        shop_command_service=shop_command_service,
        trade_command_service=trade_command_service,
        post_service=post_service,
        reply_service=reply_service,
        user_command_service=user_command_service,
        item_repository=item_repository,
        monster_repository=monster_repository,
        physical_map_repository=physical_map_repository,
        player_status_repository=player_status_repository,
        monster_template_repository=monster_template_repository,
        spot_repository=spot_repository,
        item_spec_repository=item_spec_repository,
        player_profile_repository=player_profile_repository,
    )
    available_tools_provider = tool_stack.available_tools_provider
    tool_command_mapper = tool_stack.tool_command_mapper
    tool_argument_resolver = tool_stack.tool_argument_resolver

    memory_extractor = RuleBasedMemoryExtractor()
    if llm_player_resolver is None:
        llm_player_resolver = ProfileBasedLlmPlayerResolver(
            player_profile_repository=player_profile_repository,
        )
    reflection_service, reflection_runner = _build_reflection_stack(
        episode_memory_store=episode_memory_store,
        long_term_memory_store=long_term_memory_store,
        reflection_state_port=reflection_state_port,
        player_status_repository=player_status_repository,
        llm_player_resolver=llm_player_resolver,
        world_time_config_service=world_time_config_service,
    )
    prompt_builder = _build_prompt_stack(
        buffer=buffer,
        sliding_window=sliding_window,
        action_result_store=action_result_store,
        world_query_service=world_query_service,
        player_profile_repository=player_profile_repository,
        current_state_formatter=current_state_formatter,
        recent_events_formatter=recent_events_formatter,
        context_format_strategy=context_format_strategy,
        system_prompt_builder=system_prompt_builder,
        available_tools_provider=available_tools_provider,
        ui_context_builder=ui_context_builder,
        episode_memory_store=episode_memory_store,
        long_term_memory_store=long_term_memory_store,
        tile_map_view_distance=effective_view_distance,
    )
    orchestrator = LlmAgentOrchestrator(
        prompt_builder=prompt_builder,
        llm_client=client,
        tool_command_mapper=tool_command_mapper,
        action_result_store=action_result_store,
        tool_argument_resolver=tool_argument_resolver,
        memory_extractor=memory_extractor,
        episode_memory_store=episode_memory_store,
        handle_store=handle_store,
    )
    turn_runner = LlmAgentTurnRunner(
        observation_buffer=buffer,
        world_query_service=world_query_service,
        movement_service=movement_service,
        action_result_store=action_result_store,
        orchestrator=orchestrator,
    )
    llm_turn_trigger = DefaultLlmTurnTrigger(turn_runner=turn_runner, max_turns=max_turns)

    observation_registry = _build_observation_stack(
        player_status_repository=player_status_repository,
        physical_map_repository=physical_map_repository,
        player_profile_repository=player_profile_repository,
        quest_repository=quest_repository,
        guild_repository=guild_repository,
        shop_repository=shop_repository,
        trade_repository=trade_repository,
        monster_repository=monster_repository,
        hit_box_repository=hit_box_repository,
        skill_loadout_repository=skill_loadout_repository,
        skill_deck_progress_repository=skill_deck_progress_repository,
        sns_user_repository=sns_user_repository,
        buffer=buffer,
        unit_of_work_factory=unit_of_work_factory,
        llm_turn_trigger=llm_turn_trigger,
        llm_player_resolver=llm_player_resolver,
        movement_service=movement_service,
        game_time_provider=game_time_provider,
        world_time_config_service=world_time_config_service,
        observation_formatter=observation_formatter,
        spot_repository=spot_repository,
        item_spec_repository=item_spec_repository,
        item_repository=item_repository,
        skill_spec_repository=skill_spec_repository,
    )
    return LlmAgentWiringResult(
        observation_registry=observation_registry,
        llm_turn_trigger=llm_turn_trigger,
        reflection_runner=reflection_runner,
    )


__all__ = ["create_llm_agent_wiring", "LlmAgentWiringResult"]
