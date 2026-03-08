"""
LLM エージェント用ワイヤリング（方針 B）。

観測 → schedule_turn → tick → run_scheduled_turns および
プロンプト組み立て・ツール実行・結果記録までを一括で組み立てる。

本モジュールは**ライブラリ**として提供する。ゲームの組み立て（WorldSimulationApplicationService や
EventHandlerComposition のインスタンス化）は**呼び出し元（外部）**で行い、本関数の返り値を渡す。

【ブートストラップ契約（呼び出し元が守ること）】
1. create_llm_agent_wiring(...) を呼び、返り値 (observation_registry, llm_turn_trigger) を取得する。
2. observation_registry を EventHandlerComposition の observation_registry 引数に渡す。
   - register_for_profile(event_publisher, EventHandlerProfile.FULL) 時に観測ハンドラが登録される。
3. llm_turn_trigger を WorldSimulationApplicationService の llm_turn_trigger 引数に渡す。
   - tick() の末尾で run_scheduled_turns() が呼ばれ、スケジュール済み LLM プレイヤーのターンが実行される。
上記を満たすことで、観測イベント発生 → schedule_turn → tick → run_scheduled_turns の一連の流れが動作する。

LLM クライアント: 環境変数 LLM_CLIENT で "stub"（デフォルト）または "litellm" を指定。
開発では stub、本番では litellm を指定する。
"stub" / "litellm" 以外の値の場合は ValueError を送出する。

SQLite 記憶永続化: 環境変数 LLM_MEMORY_DB_PATH に DB ファイルパスを指定すると、
memory_db_path 引数なしでも episode / long-term / reflection state を SQLite に保存する。
起動経路（bootstrap）で本関数に memory_db_path を渡すか、LLM_MEMORY_DB_PATH を設定することで
restart 後の復元が可能になる。
"""

import os
from typing import Any, Optional, Tuple

_VALID_LLM_CLIENT_VALUES = frozenset({"stub", "litellm"})

from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    IEpisodeMemoryStore,
    ILLMClient,
    ILLMPlayerResolver,
    ILlmTurnTrigger,
    IReflectionRunner,
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
from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
    InMemoryEpisodeMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_long_term_memory_store import (
    InMemoryLongTermMemoryStore,
)
from ai_rpg_world.application.llm.services.llm_agent_turn_runner import (
    LlmAgentTurnRunner,
)
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
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
from ai_rpg_world.application.llm.services.tool_command_mapper import (
    ToolCommandMapper,
)
from ai_rpg_world.application.llm.services.tool_argument_resolver import (
    DefaultToolArgumentResolver,
)
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


_ENV_LLM_CLIENT = "LLM_CLIENT"
_DEFAULT_LLM_CLIENT = "stub"
_ENV_LLM_MEMORY_DB_PATH = "LLM_MEMORY_DB_PATH"


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


def _create_llm_client_from_env() -> ILLMClient:
    """環境変数 LLM_CLIENT に応じて ILLMClient 実装を返す。stub（デフォルト） or litellm。未知の値は ValueError。"""
    value = (os.environ.get(_ENV_LLM_CLIENT) or _DEFAULT_LLM_CLIENT).strip().lower()
    if value not in _VALID_LLM_CLIENT_VALUES:
        raise ValueError(
            f"LLM_CLIENT must be one of {sorted(_VALID_LLM_CLIENT_VALUES)}, got: {value!r}"
        )
    if value == "litellm":
        from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient
        return LiteLLMClient()
    return StubLlmClient()


def create_llm_agent_wiring(
    *,
    player_status_repository: PlayerStatusRepository,
    physical_map_repository: PhysicalMapRepository,
    world_query_service: Any,
    movement_service: Any,
    speech_service: Optional[Any] = None,
    interaction_service: Optional[Any] = None,
    harvest_service: Optional[Any] = None,
    attention_service: Optional[Any] = None,
    conversation_service: Optional[Any] = None,
    place_object_service: Optional[Any] = None,
    chest_service: Optional[Any] = None,
    skill_tool_service: Optional[Any] = None,
    player_profile_repository: PlayerProfileRepository,
    unit_of_work_factory: UnitOfWorkFactory,
    observation_buffer: Optional[IObservationContextBuffer] = None,
    observation_formatter: Optional[IObservationFormatter] = None,
    spot_repository: Optional[Any] = None,
    item_spec_repository: Optional[Any] = None,
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
    quest_command_service: Optional[Any] = None,
    guild_command_service: Optional[Any] = None,
    shop_command_service: Optional[Any] = None,
    trade_command_service: Optional[Any] = None,
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
) -> "LlmAgentWiringResult":
    """
    LLM エージェント用の観測ハンドラ登録用 Registry と LlmTurnTrigger を組み立てて返す。

    呼び出し元は:
    - 返り値の observation_registry を EventHandlerComposition の observation_registry に渡す
    - 返り値の llm_turn_trigger を WorldSimulationApplicationService の llm_turn_trigger に渡す

    Args:
        player_status_repository: 観測配信先解決・注意レベル取得用
        physical_map_repository: 観測配信先解決（WorldObjectId → PlayerId）用
        world_query_service: get_player_current_state を持つサービス
        movement_service: cancel_movement, move_to_destination を持つサービス
        player_profile_repository: プロンプト用プロフィール・LLM 判定（ProfileBased）用
        unit_of_work_factory: 観測ハンドラの別トランザクション用
        observation_buffer: 省略時は DefaultObservationContextBuffer を新規作成
        observation_formatter: 省略時は ObservationFormatter を新規作成。省略時は spot_repository / player_profile_repository / item_spec_repository / item_repository を渡すと名前解決に利用する。
        spot_repository: 観測文のスポット名解決用。省略時は「不明なスポット」となる。
        item_spec_repository: 観測文のアイテム名解決用（ResourceHarvested 等）。省略時は「何かのアイテム」となる。
        item_repository: 観測文のアイテム名解決用（チェスト・インベントリ系）。省略時は「何かのアイテム」となる。
        quest_repository: クエスト観測の配信先解決（承認・キャンセル等）用（任意）。
        shop_repository: ショップ観測の配信先解決（spot 解決）・観測文の名前解決用（任意）。
        trade_repository: 取引観測の配信先解決（TradeAccepted/TradeCancelled の seller/target 解決）用（任意）。
        guild_repository: ギルド観測の配信先解決（全メンバー通知）・観測文の名前解決用（任意）。
        monster_repository: モンスター/会話NPC観測の配信先解決・観測文の名前解決用（任意）。
        hit_box_repository: 戦闘（HitBox）観測の配信先解決（owner 解決）用（任意）。
        skill_loadout_repository: スキル（Loadout）観測の配信先解決（owner 解決）用（任意）。
        skill_deck_progress_repository: スキル（DeckProgress）観測の配信先解決（owner 解決）用（任意）。
        skill_spec_repository: スキル名の観測文解決用（任意）。
        llm_client: 省略時は環境変数 LLM_CLIENT に従い作成（stub / litellm）
        game_time_provider: 省略時は観測にゲーム内時刻を付与しない。指定時は world_time_config_service も必要。
        world_time_config_service: 省略時は観測にゲーム内時刻を付与しない。ticks_per_day 等を提供する設定サービス。
        memory_db_path: SQLite 記憶永続化の DB パス。指定時は episode / long-term / reflection state を SQLite に保存。省略時は環境変数 LLM_MEMORY_DB_PATH を参照し、それもなければ in-memory。
        episode_memory_store: テスト用注入。省略時は memory_db_path または in-memory で作成。
        long_term_memory_store: テスト用注入。省略時は memory_db_path または in-memory で作成。
        reflection_state_port: テスト用注入。省略時は memory_db_path 時のみ SqliteReflectionStatePort を作成。
        action_result_store: テスト用注入。省略時は DefaultActionResultStore を作成。
        sliding_window_memory: テスト用注入。省略時は DefaultSlidingWindowMemory を作成。
        llm_player_resolver: テスト用注入。省略時は ProfileBasedLlmPlayerResolver を作成。

    Returns:
        LlmAgentWiringResult。observation_registry, llm_turn_trigger, reflection_runner を持つ。
        既存の unpacking (registry, trigger) = create_llm_agent_wiring(...) も動作する。
        reflection_runner は world_time_config_service 指定時のみ設定され、
        WorldSimulationApplicationService(reflection_runner=...) に渡すと in-game day 境界で長期記憶が育つ。
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
    current_state_formatter = DefaultCurrentStateFormatter()
    ui_context_builder = DefaultLlmUiContextBuilder()
    recent_events_formatter = DefaultRecentEventsFormatter()
    context_format_strategy = SectionBasedContextFormatStrategy()
    system_prompt_builder = DefaultSystemPromptBuilder()
    game_tool_registry = DefaultGameToolRegistry()
    register_default_tools(
        game_tool_registry,
        speech_enabled=speech_service is not None,
        interaction_enabled=interaction_service is not None,
        harvest_enabled=harvest_service is not None,
        attention_enabled=attention_service is not None,
        conversation_enabled=conversation_service is not None,
        place_enabled=place_object_service is not None,
        chest_enabled=chest_service is not None,
        combat_enabled=skill_tool_service is not None,
        quest_enabled=quest_command_service is not None,
        guild_enabled=guild_command_service is not None,
        shop_enabled=shop_command_service is not None,
        trade_enabled=trade_command_service is not None,
    )
    available_tools_provider = DefaultAvailableToolsProvider(game_tool_registry)

    client = llm_client if llm_client is not None else _create_llm_client_from_env()
    tool_command_mapper = ToolCommandMapper(
        movement_service=movement_service,
        speech_service=speech_service,
        interaction_service=interaction_service,
        harvest_service=harvest_service,
        attention_service=attention_service,
        conversation_service=conversation_service,
        place_object_service=place_object_service,
        chest_service=chest_service,
        skill_tool_service=skill_tool_service,
        quest_service=quest_command_service,
        guild_service=guild_command_service,
        shop_service=shop_command_service,
        trade_service=trade_command_service,
    )
    tool_argument_resolver = DefaultToolArgumentResolver()

    # memory_db_path: 引数 > 環境変数 LLM_MEMORY_DB_PATH
    effective_memory_db_path = memory_db_path or (
        (os.environ.get(_ENV_LLM_MEMORY_DB_PATH) or "").strip() or None
    )

    if episode_memory_store is None:
        if effective_memory_db_path:
            from ai_rpg_world.infrastructure.llm.sqlite_episode_memory_store import (
                SqliteEpisodeMemoryStore,
            )
            episode_memory_store = SqliteEpisodeMemoryStore(effective_memory_db_path)
        else:
            episode_memory_store = InMemoryEpisodeMemoryStore()

    if long_term_memory_store is None:
        if effective_memory_db_path:
            from ai_rpg_world.infrastructure.llm.sqlite_long_term_memory_store import (
                SqliteLongTermMemoryStore,
            )
            long_term_memory_store = SqliteLongTermMemoryStore(effective_memory_db_path)
        else:
            long_term_memory_store = InMemoryLongTermMemoryStore()

    if reflection_state_port is None:
        if effective_memory_db_path:
            from ai_rpg_world.infrastructure.llm.sqlite_reflection_state_port import (
                SqliteReflectionStatePort,
            )
            reflection_state_port = SqliteReflectionStatePort(effective_memory_db_path)
        else:
            reflection_state_port = None
    memory_extractor = RuleBasedMemoryExtractor()
    if llm_player_resolver is None:
        llm_player_resolver = ProfileBasedLlmPlayerResolver(
            player_profile_repository=player_profile_repository,
        )
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
    predictive_retriever = DefaultPredictiveMemoryRetriever(
        episode_store=episode_memory_store,
        long_term_store=long_term_memory_store,
    )
    prompt_builder = DefaultPromptBuilder(
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
    )
    orchestrator = LlmAgentOrchestrator(
        prompt_builder=prompt_builder,
        llm_client=client,
        tool_command_mapper=tool_command_mapper,
        action_result_store=action_result_store,
        tool_argument_resolver=tool_argument_resolver,
        memory_extractor=memory_extractor,
        episode_memory_store=episode_memory_store,
    )
    turn_runner = LlmAgentTurnRunner(
        observation_buffer=buffer,
        world_query_service=world_query_service,
        movement_service=movement_service,
        action_result_store=action_result_store,
        orchestrator=orchestrator,
    )
    llm_turn_trigger = DefaultLlmTurnTrigger(turn_runner=turn_runner)
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
    observation_registry = ObservationEventHandlerRegistry(
        observation_handler=observation_handler,
    )
    return LlmAgentWiringResult(
        observation_registry=observation_registry,
        llm_turn_trigger=llm_turn_trigger,
        reflection_runner=reflection_runner,
    )
