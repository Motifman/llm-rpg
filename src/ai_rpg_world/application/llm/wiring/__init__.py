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

【SNS モード・タイムライン read ツール】
- `create_world_query_service(..., sns_mode_session=...)` と `create_llm_agent_wiring(..., sns_mode_session=...)`
  には**同一の** `SnsModeSessionService` インスタンスを渡す（`PlayerCurrentStateDto.is_sns_mode_active` と
  enter/logout のセッション状態を一致させるため）。
- 仮想 SNS 画面状態を `PlayerCurrentStateDto` と enter/logout で共有する場合は、同様に
  `sns_page_session` に**同一の** `SnsPageSessionService` を渡す。
- ホーム TL / ユーザー TL 系ツールを実行可能にするには `PostQueryService` を
  `create_llm_agent_wiring(..., post_query_service=...)` に渡す。WorldQueryService の組み立てには不要。

【取引所モード（Trade）】
- 取引所は SNS とは別のゲーム内アプリ。ツール登録は `register_default_tools(..., trade_enabled=True)` で
  行い、SNS 有効化とは独立している。
- セッション上は `SnsModeSessionService` がアクティブアプリスロット（SNS / 取引の相互排他）も担うため、
  取引の enter/exit を配線する場合も **WorldQuery と同一の** `sns_mode_session` を渡す。
- 仮想取引所ページツール（`trade_view_current_page` 等）を有効にするには `trade_page_query_service` と
  `trade_page_session` を `create_llm_agent_wiring(...)` に渡す（`WorldQueryService` 側と同一インスタンス）。
- Trade ReadModel を SQLite に置く場合は `TRADE_READMODEL_DB_PATH`（明示）または単一 DB 用の `GAME_DB_PATH` を設定し、
  `ai_rpg_world.application.trade.trade_read_model_wiring.create_trade_read_model_repository_for_app`
  （または `create_trade_query_service_for_app` / `create_trade_read_model_repositories_bundle_for_app`）で得たリポジトリを
  `TradeQueryService`・`TradePageQueryService`・`TradeEventHandler` 等に**同一インスタンスで**
  渡す（`.env.example` 参照）。

【エピソード記憶（MVP）】
- 既定はプロセス内の `InMemorySubjectiveEpisodeStore`。環境変数 `SUBJECTIVE_EPISODE_DB_PATH` に SQLite ファイルパスを
  指定すると永続化ストアを1つ生成し、`EpisodicChunkCoordinator`（チャンク境界で保存）経由で
  `LlmAgentOrchestrator` と `DefaultPromptBuilder` 内の `EpisodicPassiveRecallRetrievalService`（受動想起）に**同一インスタンス**を渡す。
  同じファイルに **MemoryLink** と **セマンティック昇格済みエントリ**のテーブルも作成され（マイグレーション namespace `episodic-memory-graph-v1`）、
  リンクストア・セマンティックストアは SQLite 実装が共有接続で使われる。未設定時はこれらのみインメモリ。
- チャンク草案は既定で `ChunkEpisodeDraftBuilder()`。テスト等では `chunk_episode_draft_builder=` で差し替え可能。
- テスト等でストアだけ差し替える場合は `episodic_episode_store=` を指定する（ストアと retrieval・coordinator で共有される）。
- 協調全体を差し替える場合は `episodic_chunk_coordinator=` を渡す（未指定時は上記ポートから組み立てる）。
- `LLM_CLIENT=litellm`（`LiteLLMClient`）時はチャンク保存で `interpreted` / `recall_text` を JSON 完了で付与し、失敗時はテンプレへフォールバックする。`episodic_chunk_subjective_completion=` で明示ポート差し替え可。Stub では未付与のまま。
- `create_spot_graph_wiring` も同方針で既定配線する（スポットグラフ専用のツール・画面組み立てのみが異なる）。

"""

import os
from typing import Any, Callable, Dict, NamedTuple, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    LlmCommandResultDto,
    ToolRuntimeContextDto,
)

from ai_rpg_world.application.llm.wiring._llm_client_factory import (
    create_llm_client_from_env,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    ILLMClient,
    ILLMPlayerResolver,
    ILlmTurnTrigger,
    IMemoStore,
    ISlidingWindowMemory,
)
from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.contracts.episodic_episode_store_port import (
    IEpisodicEpisodeStore,
)
from ai_rpg_world.application.llm.contracts.semantic_memory_store_port import (
    ISemanticMemoryStore,
)
from ai_rpg_world.application.llm.contracts.episodic_chunk_subjective_llm_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.application.llm.contracts.episodic_reinterpretation import (
    IEpisodicRecallBufferStore,
    IEpisodicReinterpretationCompletionPort,
    IEpisodicReinterpretationJournalStore,
)
from ai_rpg_world.application.llm.services.agent_orchestrator import LlmAgentOrchestrator
from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    MemoCompletionHintService,
)
from ai_rpg_world.application.trace import ITraceRecorder
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import (
    ChunkEpisodeDraftBuilder,
)
from ai_rpg_world.application.llm.services.episodic_chunk_coordinator import (
    EpisodicChunkCoordinator,
)
from ai_rpg_world.application.llm.services.episodic_reinterpretation_coordinator import (
    EpisodicReinterpretationCoordinator,
)
from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
    EpisodicChunkSubjectiveFieldsService,
)
from ai_rpg_world.application.llm.services.available_tools_provider import (
    DefaultAvailableToolsProvider,
)
from ai_rpg_world.application.llm.services.context_format_strategy import (
    SectionBasedContextFormatStrategy,
    build_section_format_strategy_from_env,
)
from ai_rpg_world.application.llm.wiring.feature_flags import (
    SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY,
    log_episodic_explore_related_state,
    log_semantic_llm_gist_state,
    log_semantic_passive_top_k_state,
    log_semantic_search_state,
    log_short_term_memory_kind_state,
    resolve_episodic_explore_related_enabled,
    resolve_semantic_llm_gist_enabled,
    resolve_semantic_passive_top_k,
    resolve_semantic_search_enabled,
    resolve_short_term_memory_kind,
)
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallRetrievalService,
)
from ai_rpg_world.application.llm.services.episodic_memory_link_application_service import (
    EpisodicMemoryLinkApplicationService,
)
from ai_rpg_world.application.llm.services.episodic_promotion_frontier import (
    EpisodicPromotionFrontier,
)
from ai_rpg_world.application.llm.services.episodic_semantic_cluster_promotion import (
    EpisodicSemanticClusterPromotionService,
)
from ai_rpg_world.application.llm.services.current_state_formatter import (
    DefaultCurrentStateFormatter,
)
from ai_rpg_world.application.llm.services.game_tool_registry import (
    DefaultGameToolRegistry,
)
from ai_rpg_world.application.llm.wiring._default_episodic_episode_store import (
    resolve_default_episodic_episode_store,
)
from ai_rpg_world.application.llm.wiring.episodic_memory_link_bundle import (
    build_episodic_memory_link_bundle,
    default_link_and_semantic_stores_for_episode_store,
)
from ai_rpg_world.application.llm.wiring._shared_builders import (
    build_episodic_coordinator_stack,
    build_episodic_memory_stack,
    build_game_time_label_provider,
    resolve_effective_view_distance,
)
from ai_rpg_world.application.llm.services.in_memory_todo_store import (
    InMemoryTodoStore,
)
from ai_rpg_world.application.llm.services.llm_agent_turn_runner import (
    LlmAgentTurnRunner,
)
from ai_rpg_world.application.llm.services.llm_player_resolver import (
    ProfileBasedLlmPlayerResolver,
)
from ai_rpg_world.application.llm.services.llm_turn_trigger import DefaultLlmTurnTrigger
from ai_rpg_world.application.llm.services.prompt_builder import (
    DEFAULT_RECENT_ACTIONS_LIMIT,
    DEFAULT_RECENT_OBSERVATIONS_LIMIT,
    DefaultPromptBuilder,
)
from ai_rpg_world.application.llm.services.recent_events_formatter import (
    DefaultRecentEventsFormatter,
)
from ai_rpg_world.application.llm.services.system_prompt_builder import (
    DefaultSystemPromptBuilder,
)
from ai_rpg_world.application.llm.contracts.persona import (
    AgentPersonaDto,
    PersonaPromptPolicy,
)
from ai_rpg_world.application.llm.services.persona_prompt_fragment_builder import (
    PersonaPromptFragmentBuilder,
)
from ai_rpg_world.application.llm.services.sliding_window_memory import (
    DefaultSlidingWindowMemory,
)
from ai_rpg_world.application.llm.services.executors.guild_executor import (
    GuildToolExecutor,
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
from ai_rpg_world.application.llm.services.executors.episodic_memory_explore_tool_executor import (
    EpisodicMemoryExploreToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.llm.services.tool_command_mapper import (
    ToolCommandMapper,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_NO_OP
from ai_rpg_world.application.llm.services.tool_argument_resolver import (
    DefaultToolArgumentResolver,
)
from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.application.world.contracts.interfaces import ICancelMovementPort
from ai_rpg_world.application.world.contracts.queries import (
    GetPlayerCurrentStateQuery,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.application.llm.services.tool_catalog import (
    register_default_tools,
    register_spot_graph_tools,
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
from ai_rpg_world.application.observation.services.movement_interruption_service import (
    MovementInterruptionService,
)
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.application.observation.services.observation_pipeline import (
    ObservationPipeline,
)
from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
    create_observation_recipient_resolver,
)
from ai_rpg_world.application.observation.services.observation_timestamp_resolver import (
    ObservationTimestampResolver,
)
from ai_rpg_world.application.observation.services.observation_turn_scheduler import (
    ObservationTurnScheduler,
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

_ENV_LLM_VIEW_DISTANCE = "LLM_VIEW_DISTANCE"
_DEFAULT_LLM_VIEW_DISTANCE = 5


class _RuntimeToolState(NamedTuple):
    """LLM ツール用の軽量状態。記憶系は持たず TODO のみ保持する。"""

    todo_store: InMemoryTodoStore



class _ToolStackResult(NamedTuple):
    """_build_tool_stack の返り値。available_tools_provider, tool_command_mapper, tool_argument_resolver の構築結果。"""

    available_tools_provider: DefaultAvailableToolsProvider
    tool_command_mapper: ToolCommandMapper
    tool_argument_resolver: DefaultToolArgumentResolver


def _build_tool_handler_map(
    *,
    include_tile_movement: bool = True,
    movement_service: Any = None,
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
    notification_command_service: Optional[Any],
    sns_mode_session: Optional[Any],
    sns_page_session: Optional[Any],
    sns_page_query_service: Optional[Any],
    trade_page_session: Optional[Any],
    trade_page_query_service: Optional[Any],
    reply_query_service: Optional[Any],
    notification_query_service: Optional[Any],
    item_repository: Optional[Any],
    monster_repository: Optional[Any],
    physical_map_repository: Optional[PhysicalMapRepository],
    player_status_repository: PlayerStatusRepository,
    todo_store: Optional[InMemoryTodoStore],
    sliding_window: Optional[ISlidingWindowMemory] = None,
    action_result_store: Optional[IActionResultStore] = None,
    current_tick_provider: Optional[Callable[[], Optional[int]]] = None,
    spot_graph_tool_executor: Optional[SpotGraphToolExecutor] = None,
    episodic_memory_explore_executor: Optional[EpisodicMemoryExploreToolExecutor] = None,
    semantic_memory_search_executor: Optional[Any] = None,
    trace_recorder: Optional["ITraceRecorder"] = None,
    speech_audience_resolver: Optional[Any] = None,
) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
    """
    Executor 群を組み立て、tool_name → handler の辞書を返す。
    include_tile_movement が True のとき movement_service は必須。
    各 service が None の場合は対応するハンドラは登録されない。
    """
    if include_tile_movement:
        move_to_destination = getattr(movement_service, "move_to_destination", None)
        if not callable(move_to_destination):
            raise TypeError("movement_service must have a callable move_to_destination")
        move_tile = getattr(movement_service, "move_tile", None)
        if not callable(move_tile):
            raise TypeError("movement_service must have a callable move_tile")
        cancel_movement = getattr(movement_service, "cancel_movement", None)
        if not callable(cancel_movement):
            raise TypeError("movement_service must have a callable cancel_movement")
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
    if include_tile_movement:
        handler_map.update(
            MovementToolExecutor(
                movement_service=movement_service,
                pursuit_service=pursuit_command_service,
            ).get_handlers()
        )
    handler_map.update(
        SpeechToolExecutor(
            speech_service=speech_service,
            audience_resolver=speech_audience_resolver,
        ).get_handlers()
    )
    handler_map.update(
        TodoToolExecutor(
            todo_store,
            sliding_window=sliding_window,
            action_result_store=action_result_store,
            current_tick_provider=current_tick_provider,
            trace_recorder=trace_recorder,
        ).get_handlers()
    )
    handler_map.update(
        QuestToolExecutor(quest_service=quest_command_service).get_handlers()
    )
    handler_map.update(
        ShopToolExecutor(shop_service=shop_command_service).get_handlers()
    )
    handler_map.update(
        TradeToolExecutor(
            trade_service=trade_command_service,
            sns_mode_session=sns_mode_session,
            trade_page_session=trade_page_session,
            trade_page_query_service=trade_page_query_service,
        ).get_handlers()
    )
    handler_map.update(
        SnsToolExecutor(
            post_service=post_service,
            reply_service=reply_service,
            user_command_service=user_command_service,
            notification_command_service=notification_command_service,
            sns_mode_session=sns_mode_session,
            sns_page_session=sns_page_session,
            sns_page_query_service=sns_page_query_service,
            reply_query_service=reply_query_service,
            notification_query_service=notification_query_service,
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
    if spot_graph_tool_executor is not None:
        handler_map.update(spot_graph_tool_executor.get_handlers())
    if episodic_memory_explore_executor is not None:
        handler_map.update(episodic_memory_explore_executor.get_handlers())
    if semantic_memory_search_executor is not None:
        handler_map.update(semantic_memory_search_executor.get_handlers())
    return handler_map


def _build_tool_stack(
    *,
    game_tool_registry: DefaultGameToolRegistry,
    todo_store: InMemoryTodoStore,
    include_tile_movement: bool = True,
    movement_service: Any = None,
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
    notification_command_service: Optional[Any],
    sns_mode_session: Optional[Any],
    sns_page_session: Optional[Any],
    post_query_service: Optional[Any],
    sns_page_query_service: Optional[Any],
    trade_page_session: Optional[Any],
    trade_page_query_service: Optional[Any],
    reply_query_service: Optional[Any],
    notification_query_service: Optional[Any],
    item_repository: Optional[Any],
    monster_repository: Optional[Any],
    physical_map_repository: Optional[PhysicalMapRepository],
    player_status_repository: PlayerStatusRepository,
    monster_template_repository: Optional[Any],
    spot_repository: Optional[Any],
    item_spec_repository: Optional[Any],
    player_profile_repository: PlayerProfileRepository,
    spot_graph_tool_executor: Optional[SpotGraphToolExecutor] = None,
    episodic_memory_explore_executor: Optional[EpisodicMemoryExploreToolExecutor] = None,
    episodic_explore_related_enabled: bool = False,
    semantic_memory_search_executor: Optional[Any] = None,
    semantic_search_enabled: bool = False,
    sliding_window: Optional[ISlidingWindowMemory] = None,
    action_result_store: Optional[IActionResultStore] = None,
    current_tick_provider: Optional[Callable[[], Optional[int]]] = None,
    trace_recorder: Optional["ITraceRecorder"] = None,
    speech_audience_resolver: Optional[Any] = None,
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
            or notification_command_service is not None
            or sns_mode_session is not None
            or post_query_service is not None
        ),
        sns_virtual_pages_enabled=sns_page_query_service is not None,
        trade_virtual_pages_enabled=trade_page_query_service is not None,
        inspect_item_enabled=item_repository is not None,
        inspect_target_enabled=(
            monster_repository is not None
            and physical_map_repository is not None
            and player_status_repository is not None
        ),
        todo_enabled=True,
        episodic_explore_related_enabled=episodic_explore_related_enabled,
        semantic_search_enabled=semantic_search_enabled,
        include_movement_tools=include_tile_movement,
    )
    if spot_graph_tool_executor is not None:
        register_spot_graph_tools(game_tool_registry)
    available_tools_provider = DefaultAvailableToolsProvider(game_tool_registry)
    handler_map = _build_tool_handler_map(
        include_tile_movement=include_tile_movement,
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
        notification_command_service=notification_command_service,
        sns_mode_session=sns_mode_session,
        sns_page_session=sns_page_session,
        sns_page_query_service=sns_page_query_service,
        trade_page_session=trade_page_session,
        trade_page_query_service=trade_page_query_service,
        reply_query_service=reply_query_service,
        notification_query_service=notification_query_service,
        item_repository=item_repository,
        monster_repository=monster_repository,
        physical_map_repository=physical_map_repository,
        player_status_repository=player_status_repository,
        todo_store=todo_store,
        sliding_window=sliding_window,
        action_result_store=action_result_store,
        current_tick_provider=current_tick_provider,
        spot_graph_tool_executor=spot_graph_tool_executor,
        episodic_memory_explore_executor=episodic_memory_explore_executor,
        semantic_memory_search_executor=semantic_memory_search_executor,
        trace_recorder=trace_recorder,
        speech_audience_resolver=speech_audience_resolver,
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
    physical_map_repository: Optional[PhysicalMapRepository],
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
    movement_service: Optional[ICancelMovementPort],
    game_time_provider: Optional[GameTimeProvider],
    world_time_config_service: Optional[WorldTimeConfigService],
    observation_formatter: Optional[IObservationFormatter],
    spot_repository: Optional[Any],
    item_spec_repository: Optional[Any],
    item_repository: Optional[Any],
    skill_spec_repository: Optional[Any],
    spot_graph_repository: Optional[Any] = None,
    observation_appender: Optional["ObservationAppender"] = None,
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
        spot_graph_repository=spot_graph_repository,
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
            spot_graph_repository=spot_graph_repository,
        )
    pipeline = ObservationPipeline(
        resolver=observation_resolver,
        formatter=formatter,
        player_status_repository=player_status_repository,
    )
    appender = observation_appender or ObservationAppender(buffer=buffer)
    timestamp_resolver = ObservationTimestampResolver(
        game_time_provider=game_time_provider,
        world_time_config=world_time_config_service,
    )
    movement_interruption = MovementInterruptionService(
        movement_service=movement_service,
        llm_player_resolver=llm_player_resolver,
    )
    turn_scheduler = ObservationTurnScheduler(
        turn_trigger=llm_turn_trigger,
        llm_player_resolver=llm_player_resolver,
    )
    observation_handler = ObservationEventHandler(
        pipeline=pipeline,
        appender=appender,
        timestamp_resolver=timestamp_resolver,
        movement_interruption=movement_interruption,
        turn_scheduler=turn_scheduler,
        unit_of_work_factory=unit_of_work_factory,
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
    tile_map_view_distance: int,
    tile_map_enabled: bool = True,
    persona_block_provider: Optional[Callable[[PlayerId], str]] = None,
    episodic_passive_recall: Optional[EpisodicPassiveRecallRetrievalService] = None,
    episodic_memory_link_service: Optional[EpisodicMemoryLinkApplicationService] = None,
    episodic_recall_buffer_store: Optional[IEpisodicRecallBufferStore] = None,
    episodic_reinterpretation_journal_store: Optional[IEpisodicReinterpretationJournalStore] = None,
    episodic_turn_index_provider: Optional[Callable[[PlayerId], int]] = None,
    semantic_passive_recall: Optional[Any] = None,
    semantic_passive_top_k: int = 0,
    memo_store: Optional["IMemoStore"] = None,
    current_tick_provider: Optional[Callable[[], Optional[int]]] = None,
) -> DefaultPromptBuilder:
    """
    predictive_retriever と prompt_builder を構築する。
    """
    from ai_rpg_world.application.llm.services.prompt_builder_config import (
        EpisodicRecallConfig,
        PromptBuilderCoreServices,
        PromptLimits,
        PromptSectionProviders,
    )

    core = PromptBuilderCoreServices(
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
    )
    sections = PromptSectionProviders(
        persona_block_provider=persona_block_provider,
        memo_store=memo_store,
    )
    episodic = EpisodicRecallConfig(
        passive_recall=episodic_passive_recall,
        memory_link_service=episodic_memory_link_service,
        recall_buffer_store=episodic_recall_buffer_store,
        reinterpretation_journal_store=episodic_reinterpretation_journal_store,
        turn_index_provider=episodic_turn_index_provider,
        semantic_passive_recall=semantic_passive_recall,
        semantic_passive_top_k=semantic_passive_top_k,
    )
    limits = PromptLimits(
        tile_map_view_distance=tile_map_view_distance,
        tile_map_enabled=tile_map_enabled,
    )
    return DefaultPromptBuilder(
        core,
        sections=sections,
        episodic=episodic,
        limits=limits,
        ui_context_builder=ui_context_builder,
        current_tick_provider=current_tick_provider,
    )


def _optional_episodic_chunk_subjective_fields_service(
    llm_client: ILLMClient,
    episodic_chunk_subjective_completion: Optional[IEpisodicChunkSubjectiveCompletionPort],
) -> Optional[EpisodicChunkSubjectiveFieldsService]:
    """
    LiteLLM 本番クライアント（または明示ポート）があるときだけ主観フィールド付与サービスを返す。
    """
    port: Optional[IEpisodicChunkSubjectiveCompletionPort] = episodic_chunk_subjective_completion
    if port is None:
        from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient

        if isinstance(llm_client, LiteLLMClient):
            port = llm_client
    if port is None:
        return None
    return EpisodicChunkSubjectiveFieldsService(port)


def _optional_semantic_gist_service(
    llm_client: ILLMClient,
    enabled: bool,
) -> Optional["SemanticGistService"]:
    """``SEMANTIC_LLM_GIST_ENABLED=1`` かつ LiteLLM クライアントあるときだけ
    ``SemanticGistService`` を返す。

    Phase 1b: gist 生成の LLM 化。OFF または非 LiteLLM の場合は None を返し、
    promotion service は既存の決定論 gist を使う。
    """
    if not enabled:
        return None
    from ai_rpg_world.application.llm.contracts.semantic_gist_completion_port import (
        ISemanticGistCompletionPort,
    )
    from ai_rpg_world.application.llm.services.semantic_gist_service import (
        SemanticGistService,
    )
    from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient

    if not isinstance(llm_client, LiteLLMClient):
        return None
    port: ISemanticGistCompletionPort = llm_client
    return SemanticGistService(port)


def _optional_episodic_reinterpretation_completion(
    llm_client: ILLMClient,
    explicit: Optional[IEpisodicReinterpretationCompletionPort],
) -> Optional[IEpisodicReinterpretationCompletionPort]:
    port: Optional[IEpisodicReinterpretationCompletionPort] = explicit
    if port is None:
        from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient

        if isinstance(llm_client, LiteLLMClient):
            port = llm_client
    return port


def _resolve_default_episodic_reinterpretation_stores(
    recall_buffer_store: Optional[IEpisodicRecallBufferStore],
    journal_store: Optional[IEpisodicReinterpretationJournalStore],
) -> tuple[IEpisodicRecallBufferStore, IEpisodicReinterpretationJournalStore]:
    if recall_buffer_store is not None and journal_store is not None:
        return recall_buffer_store, journal_store
    path = os.environ.get("SUBJECTIVE_EPISODE_DB_PATH", "").strip()
    if path:
        from ai_rpg_world.infrastructure.repository.sqlite_episodic_reinterpretation_store import (
            SqliteEpisodicReinterpretationStore,
        )

        sqlite_store = SqliteEpisodicReinterpretationStore.connect(path)
        return recall_buffer_store or sqlite_store, journal_store or sqlite_store
    from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
        InMemoryEpisodicRecallBufferStore,
        InMemoryEpisodicReinterpretationJournalStore,
    )

    return (
        recall_buffer_store or InMemoryEpisodicRecallBufferStore(),
        journal_store or InMemoryEpisodicReinterpretationJournalStore(),
    )


def _build_persona_block_provider(
    persona_store: Optional[Any],
    persona_prompt_policy: Optional[PersonaPromptPolicy],
) -> Optional[Callable[[PlayerId], str]]:
    if persona_store is None:
        return None
    fragment_builder = PersonaPromptFragmentBuilder(persona_prompt_policy)

    def _provider(player_id: PlayerId) -> str:
        persona = None
        if callable(persona_store):
            persona = persona_store(player_id)
        elif callable(getattr(persona_store, "get_persona", None)):
            persona = persona_store.get_persona(player_id)
        elif callable(getattr(persona_store, "find_by_id", None)):
            persona = persona_store.find_by_id(player_id)
        if persona is None:
            return ""
        if not isinstance(persona, AgentPersonaDto):
            raise TypeError("persona_store must return AgentPersonaDto or None")
        return fragment_builder.build(persona)

    return _provider


def _build_runtime_tool_state() -> _RuntimeToolState:
    return _RuntimeToolState(todo_store=InMemoryTodoStore())


def _build_short_term_memory(
    *,
    explicit: Optional[ISlidingWindowMemory],
    llm_client: ILLMClient,
    persona_resolver: Callable[[int], tuple[str, str]],
    kind: Optional[str] = None,
) -> ISlidingWindowMemory:
    """Phase 2: env で short term memory の実装を選択する。

    - 明示注入 (``sliding_window_memory=`` を渡された) → そのまま
    - ``kind`` (None なら env) が ``rolling_summary`` + LiteLLM client →
      ``RollingSummaryShortTermMemory`` (LLM 経路あり)
    - rolling_summary だが LLM 非対応 → ``RollingSummaryShortTermMemory``
      (LLM なし、template fallback only)
    - default (sliding_window) → ``DefaultSlidingWindowMemory``

    ``kind=None`` のとき env から ``SHORT_TERM_MEMORY_KIND`` を解決する。
    呼出側で事前解決済みの値を渡せるようにすることで、wiring 経路全体での
    env 読みを一箇所に集約しやすくする (テストでも env 差し込みが楽になる)。

    persona_resolver は LLM gist (Phase 1b) と共通の resolver を渡す前提。
    """
    if explicit is not None:
        return explicit
    resolved_kind = kind if kind is not None else resolve_short_term_memory_kind()
    log_short_term_memory_kind_state(resolved_kind)
    if resolved_kind != SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY:
        return DefaultSlidingWindowMemory()
    # rolling_summary kind
    from ai_rpg_world.application.llm.services.rolling_summary_short_term_memory import (
        RollingSummaryShortTermMemory,
    )
    from ai_rpg_world.application.llm.services.short_term_memory_summary_service import (
        ShortTermMemorySummaryService,
    )
    from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient

    summary_service: Optional[ShortTermMemorySummaryService] = None
    if isinstance(llm_client, LiteLLMClient):
        summary_service = ShortTermMemorySummaryService(llm_client)
    return RollingSummaryShortTermMemory(
        summary_service=summary_service,
        persona_resolver=persona_resolver,
    )


def _build_semantic_persona_resolver(
    *,
    player_profile_repository: Any,
    persona_block_provider: Optional[Callable[[PlayerId], str]],
) -> Callable[[int], tuple[str, str]]:
    """Phase 1b: semantic gist 用の persona_resolver。

    `player_id (int) -> (player_name, persona_block)` を返す callable を作る。
    player_profile_repository から player_name、persona_block_provider から
    persona_block を best-effort で取得。どちらも欠落しても fail せず空文字
    を返す (gist 生成は止めない)。
    """

    def _resolve(player_id_int: int) -> tuple[str, str]:
        pid = PlayerId(player_id_int)
        name = f"Player {player_id_int}"
        if player_profile_repository is not None:
            try:
                profile = player_profile_repository.find_by_id(pid)
                if profile is not None and getattr(profile, "name", None):
                    name = str(profile.name)
            except Exception:
                # repository が落ちても gist 生成を止めない
                pass
        persona_block = ""
        if persona_block_provider is not None:
            try:
                persona_block = persona_block_provider(pid) or ""
            except Exception:
                persona_block = ""
        return name, persona_block

    return _resolve


class LlmAgentWiringResult:
    """create_llm_agent_wiring の返り値。unpacking で (registry, trigger) も取得可能。"""

    def __init__(
        self,
        observation_registry: "ObservationEventHandlerRegistry",
        llm_turn_trigger: ILlmTurnTrigger,
        observation_buffer: Optional[IObservationContextBuffer] = None,
        observation_appender: Optional[ObservationAppender] = None,
        sns_mode_session: Optional[Any] = None,
        sns_page_session: Optional[Any] = None,
        trade_page_session: Optional[Any] = None,
        episodic_episode_store: Optional[IEpisodicEpisodeStore] = None,
        episodic_recall_buffer_store: Optional[IEpisodicRecallBufferStore] = None,
        episodic_reinterpretation_journal_store: Optional[
            IEpisodicReinterpretationJournalStore
        ] = None,
        semantic_memory_store: Optional[ISemanticMemoryStore] = None,
        event_publisher: Optional[Any] = None,
        monster_behavior_tick_service: Optional[Any] = None,
    ) -> None:
        self.observation_registry = observation_registry
        self.llm_turn_trigger = llm_turn_trigger
        self.event_publisher = event_publisher
        self.observation_buffer = observation_buffer
        if observation_appender is not None:
            self.observation_appender = observation_appender
        elif observation_buffer is not None:
            self.observation_appender = ObservationAppender(observation_buffer)
        else:
            self.observation_appender = None
        self.sns_mode_session = sns_mode_session
        self.sns_page_session = sns_page_session
        self.trade_page_session = trade_page_session
        self.episodic_episode_store = episodic_episode_store
        self.episodic_recall_buffer_store = episodic_recall_buffer_store
        self.episodic_reinterpretation_journal_store = episodic_reinterpretation_journal_store
        self.semantic_memory_store = semantic_memory_store
        # Phase 1 (PR #131): モンスター行動 tick サービス。presentation 側
        # tick driver が `tick(current_tick)` を呼び出して attack + wander を
        # 実行する。spot_graph_wiring 経由で構築された場合のみ非 None。
        self.monster_behavior_tick_service = monster_behavior_tick_service

    def __iter__(self) -> Any:
        yield self.observation_registry
        yield self.llm_turn_trigger


def create_llm_agent_wiring(
    *,
    player_status_repository: PlayerStatusRepository,
    physical_map_repository: Optional[PhysicalMapRepository] = None,
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
    repositories: Optional["GameRepositoriesConfig"] = None,
    quest_command_service: Optional[Any] = None,
    guild_command_service: Optional[Any] = None,
    shop_command_service: Optional[Any] = None,
    sns: Optional["SnsWiringConfig"] = None,
    trade: Optional["TradeWiringConfig"] = None,
    llm_client: Optional[ILLMClient] = None,
    game_time_provider: Optional[Any] = None,
    world_time_config_service: Optional[Any] = None,
    action_result_store: Optional[IActionResultStore] = None,
    sliding_window_memory: Optional[ISlidingWindowMemory] = None,
    llm_player_resolver: Optional[ILLMPlayerResolver] = None,
    max_turns: int = 5,
    llm_view_distance: Optional[int] = None,
    system_prompt_template: Optional[str] = None,
    persona_store: Optional[Any] = None,
    persona_prompt_policy: Optional[PersonaPromptPolicy] = None,
    episodic: Optional["EpisodicWiringConfig"] = None,
    trace_recorder: Optional["ITraceRecorder"] = None,
    speech_audience_resolver: Optional[Any] = None,
) -> "LlmAgentWiringResult":
    """
    LLM エージェント用の観測ハンドラ登録用 Registry と LlmTurnTrigger を組み立てて返す。

    既定では共有 in-memory エピソードストアと EpisodicChunkCoordinator により、
    チャンク境界での episode 保存とプロンプト上の受動想起が有効になる。

    Issue #227 後続 HIGH-4 Step 8a: episodic 関連 7 引数を ``EpisodicWiringConfig``
    にまとめた。caller は ``episodic=EpisodicWiringConfig(...)`` を渡す。default の
    None なら従来の自動配線が走る。
    """
    from ai_rpg_world.application.llm.wiring.wiring_configs import (
        EpisodicWiringConfig,
        GameRepositoriesConfig,
        SnsWiringConfig,
        TradeWiringConfig,
    )

    if episodic is None:
        episodic = EpisodicWiringConfig()
    # 個別変数に展開して以降のロジックを変えない (移行を最小差分にする)
    episodic_episode_store = episodic.episode_store
    episodic_recall_buffer_store = episodic.recall_buffer_store
    episodic_reinterpretation_journal_store = episodic.reinterpretation_journal_store
    episodic_reinterpretation_completion = episodic.reinterpretation_completion
    chunk_episode_draft_builder = episodic.chunk_episode_draft_builder
    episodic_chunk_coordinator = episodic.chunk_coordinator
    episodic_chunk_subjective_completion = episodic.chunk_subjective_completion

    if sns is None:
        sns = SnsWiringConfig()
    post_service = sns.post_service
    reply_service = sns.reply_service
    user_command_service = sns.user_command_service
    notification_command_service = sns.notification_command_service
    post_query_service = sns.post_query_service
    sns_page_query_service = sns.sns_page_query_service
    reply_query_service = sns.reply_query_service
    notification_query_service = sns.notification_query_service
    sns_mode_session = sns.mode_session
    sns_page_session = sns.page_session

    if trade is None:
        trade = TradeWiringConfig()
    trade_command_service = trade.command_service
    trade_page_session = trade.page_session
    trade_page_query_service = trade.page_query_service

    if repositories is None:
        repositories = GameRepositoriesConfig()
    item_repository = repositories.item_repository
    item_spec_repository = repositories.item_spec_repository
    monster_repository = repositories.monster_repository
    monster_template_repository = repositories.monster_template_repository
    quest_repository = repositories.quest_repository
    shop_repository = repositories.shop_repository
    trade_repository = repositories.trade_repository
    guild_repository = repositories.guild_repository
    hit_box_repository = repositories.hit_box_repository
    skill_loadout_repository = repositories.skill_loadout_repository
    skill_deck_progress_repository = repositories.skill_deck_progress_repository
    skill_spec_repository = repositories.skill_spec_repository
    sns_user_repository = repositories.sns_user_repository
    spot_repository = repositories.spot_repository
    spot_graph_repository = repositories.spot_graph_repository

    if player_status_repository is None:
        raise TypeError("player_status_repository must not be None")
    # physical_map_repository は spot_graph 専用ランタイムでは None で良い。
    # tile-map 依存のツール (inspect_target / drop_item の tile 配置等) は
    # 配下の executor 側で None ガードされている。
    if world_query_service is None:
        raise TypeError("world_query_service must not be None")
    if movement_service is None:
        raise TypeError("movement_service must not be None")
    if player_profile_repository is None:
        raise TypeError("player_profile_repository must not be None")
    if unit_of_work_factory is None:
        raise TypeError("unit_of_work_factory must not be None")

    buffer = (
        observation_buffer if observation_buffer is not None else DefaultObservationContextBuffer()
    )
    current_state_formatter = DefaultCurrentStateFormatter()

    # sliding_window は client / persona_resolver の構築後 (下の方) で組み立てる。
    # rolling_summary kind を選んだとき LLM port と persona_resolver が要るため。
    action_result_store = (
        action_result_store
        if action_result_store is not None
        else DefaultActionResultStore()
    )
    ui_context_builder = DefaultLlmUiContextBuilder()
    recent_events_formatter = DefaultRecentEventsFormatter()
    context_format_strategy = build_section_format_strategy_from_env()
    _resolved_episodic_explore_related_enabled = resolve_episodic_explore_related_enabled()
    log_episodic_explore_related_state(_resolved_episodic_explore_related_enabled)
    system_prompt_builder = (
        DefaultSystemPromptBuilder(template=system_prompt_template)
        if system_prompt_template is not None
        else DefaultSystemPromptBuilder()
    )
    game_tool_registry = DefaultGameToolRegistry()
    persona_block_provider = _build_persona_block_provider(
        persona_store, persona_prompt_policy
    )

    effective_view_distance = resolve_effective_view_distance(llm_view_distance)

    runtime_tool_state = _build_runtime_tool_state()
    todo_store = runtime_tool_state.todo_store

    def _current_tick_provider() -> Optional[int]:
        if game_time_provider is None:
            return None
        try:
            tick = game_time_provider.get_current_tick()
        except Exception:
            return None
        value = getattr(tick, "value", None)
        return value if isinstance(value, int) else None

    current_tick_provider: Optional[Callable[[], Optional[int]]] = (
        _current_tick_provider if game_time_provider is not None else None
    )

    client = llm_client if llm_client is not None else create_llm_client_from_env()
    _semantic_llm_gist_enabled = resolve_semantic_llm_gist_enabled()
    log_semantic_llm_gist_state(_semantic_llm_gist_enabled)
    _semantic_gist_service = _optional_semantic_gist_service(
        client, _semantic_llm_gist_enabled
    )
    _semantic_persona_resolver = _build_semantic_persona_resolver(
        player_profile_repository=player_profile_repository,
        persona_block_provider=persona_block_provider,
    )
    # Phase 2: short term memory の実装選択 (sliding_window | rolling_summary)。
    # persona_resolver / client が揃ったここで構築する。
    sliding_window = _build_short_term_memory(
        explicit=sliding_window_memory,
        llm_client=client,
        persona_resolver=_semantic_persona_resolver,
    )
    episodic_stack = build_episodic_memory_stack(
        episodic_episode_store,
        semantic_gist_service=_semantic_gist_service,
        semantic_persona_resolver=_semantic_persona_resolver,
    )
    shared_episode_store = episodic_stack.shared_episode_store
    semantic_memory_store = episodic_stack.semantic_memory_store
    # Phase 1c: semantic passive top-K の構築 (default OFF / top_k=0)。
    _semantic_passive_top_k = resolve_semantic_passive_top_k()
    log_semantic_passive_top_k_state(_semantic_passive_top_k)
    _semantic_passive_recall_service = None
    if _semantic_passive_top_k > 0:
        from ai_rpg_world.application.llm.services.semantic_passive_recall_service import (
            SemanticPassiveRecallService,
        )
        _semantic_passive_recall_service = SemanticPassiveRecallService(semantic_memory_store)
    # Phase 1d: memory_search_semantic tool (LLM 能動検索)。default OFF。
    _semantic_search_enabled = resolve_semantic_search_enabled()
    log_semantic_search_state(_semantic_search_enabled)
    _semantic_memory_search_executor = None
    if _semantic_search_enabled:
        from ai_rpg_world.application.llm.services.executors.semantic_memory_search_tool_executor import (
            SemanticMemorySearchToolExecutor,
        )
        _semantic_memory_search_executor = SemanticMemorySearchToolExecutor(
            semantic_store=semantic_memory_store
        )
    promotion_frontier = episodic_stack.promotion_frontier
    mem_bundle = episodic_stack.mem_bundle
    episodic_semantic_promotion = episodic_stack.episodic_semantic_promotion
    tool_stack = _build_tool_stack(
        game_tool_registry=game_tool_registry,
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
        notification_command_service=notification_command_service,
        sns_mode_session=sns_mode_session,
        sns_page_session=sns_page_session,
        post_query_service=post_query_service,
        sns_page_query_service=sns_page_query_service,
        trade_page_session=trade_page_session,
        trade_page_query_service=trade_page_query_service,
        reply_query_service=reply_query_service,
        notification_query_service=notification_query_service,
        item_repository=item_repository,
        monster_repository=monster_repository,
        physical_map_repository=physical_map_repository,
        player_status_repository=player_status_repository,
        monster_template_repository=monster_template_repository,
        spot_repository=spot_repository,
        item_spec_repository=item_spec_repository,
        player_profile_repository=player_profile_repository,
        episodic_memory_explore_executor=mem_bundle.memory_explore_executor(),
        episodic_explore_related_enabled=_resolved_episodic_explore_related_enabled,
        semantic_memory_search_executor=_semantic_memory_search_executor,
        semantic_search_enabled=_semantic_search_enabled,
        sliding_window=sliding_window,
        action_result_store=action_result_store,
        current_tick_provider=current_tick_provider,
        trace_recorder=trace_recorder,
        speech_audience_resolver=speech_audience_resolver,
    )
    available_tools_provider = tool_stack.available_tools_provider
    tool_command_mapper = tool_stack.tool_command_mapper
    tool_argument_resolver = tool_stack.tool_argument_resolver

    if llm_player_resolver is None:
        llm_player_resolver = ProfileBasedLlmPlayerResolver(
            player_profile_repository=player_profile_repository,
        )
    recall_buffer, reinterpretation_journal = _resolve_default_episodic_reinterpretation_stores(
        episodic_recall_buffer_store,
        episodic_reinterpretation_journal_store,
    )
    chunk_subjective_service = _optional_episodic_chunk_subjective_fields_service(
        client,
        episodic_chunk_subjective_completion,
    )
    reinterpretation_completion = _optional_episodic_reinterpretation_completion(
        client,
        episodic_reinterpretation_completion,
    )
    coord_stack = build_episodic_coordinator_stack(
        shared_episode_store=shared_episode_store,
        mem_bundle=mem_bundle,
        buffer=buffer,
        sliding_window=sliding_window,
        action_result_store=action_result_store,
        persona_block_provider=persona_block_provider,
        recall_buffer=recall_buffer,
        reinterpretation_journal=reinterpretation_journal,
        episodic_recall_buffer_store_override=episodic_recall_buffer_store,
        chunk_episode_draft_builder=chunk_episode_draft_builder,
        chunk_subjective_service=chunk_subjective_service,
        reinterpretation_completion=reinterpretation_completion,
        episodic_chunk_coordinator_override=episodic_chunk_coordinator,
    )
    reinterpretation_coord = coord_stack.reinterpretation_coord
    prompt_recall_buffer = coord_stack.prompt_recall_buffer
    episodic_coord = coord_stack.episodic_coord
    episodic_passive_recall = mem_bundle.passive_recall
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
        tile_map_view_distance=effective_view_distance,
        persona_block_provider=persona_block_provider,
        episodic_passive_recall=episodic_passive_recall,
        episodic_memory_link_service=mem_bundle.link_service,
        episodic_recall_buffer_store=prompt_recall_buffer,
        episodic_reinterpretation_journal_store=reinterpretation_journal,
        episodic_turn_index_provider=reinterpretation_coord.current_turn_index,
        semantic_passive_recall=_semantic_passive_recall_service,
        semantic_passive_top_k=_semantic_passive_top_k,
        memo_store=todo_store,
        current_tick_provider=current_tick_provider,
    )
    memo_completion_hint_service = MemoCompletionHintService(memo_store=todo_store)
    # Issue #227 後続レビュー (MEDIUM-6) fix: tile-map 経路にも
    # game_time_label_provider を渡す (これまで spot_graph 版だけが渡していて、
    # tile-map 版は action_result の時刻ラベルが付かない潜在バグだった)
    game_time_label_provider = build_game_time_label_provider(
        game_time_provider, world_time_config_service
    )
    orchestrator = LlmAgentOrchestrator(
        prompt_builder=prompt_builder,
        llm_client=client,
        tool_command_mapper=tool_command_mapper,
        action_result_store=action_result_store,
        tool_argument_resolver=tool_argument_resolver,
        episodic_chunk_coordinator=episodic_coord,
        episodic_reinterpretation_coordinator=reinterpretation_coord,
        episodic_semantic_promotion=episodic_semantic_promotion,
        game_time_label_provider=game_time_label_provider,
        memo_completion_hint_service=memo_completion_hint_service,
        trace_recorder=trace_recorder,
        tick_provider=current_tick_provider,
    )
    turn_runner = LlmAgentTurnRunner(
        observation_buffer=buffer,
        world_query_service=world_query_service,
        movement_service=movement_service,
        action_result_store=action_result_store,
        orchestrator=orchestrator,
    )
    llm_turn_trigger = DefaultLlmTurnTrigger(turn_runner=turn_runner, max_turns=max_turns)

    observation_appender = ObservationAppender(buffer)

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
        spot_graph_repository=spot_graph_repository,
        observation_appender=observation_appender,
    )
    return LlmAgentWiringResult(
        observation_registry=observation_registry,
        llm_turn_trigger=llm_turn_trigger,
        observation_buffer=buffer,
        observation_appender=observation_appender,
        sns_mode_session=sns_mode_session,
        sns_page_session=sns_page_session,
        trade_page_session=trade_page_session,
        episodic_episode_store=shared_episode_store,
        episodic_recall_buffer_store=recall_buffer,
        episodic_reinterpretation_journal_store=reinterpretation_journal,
        semantic_memory_store=semantic_memory_store,
    )


from ai_rpg_world.application.llm.wiring.spot_graph_wiring import create_spot_graph_wiring

__all__ = ["create_llm_agent_wiring", "create_spot_graph_wiring", "LlmAgentWiringResult"]
