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
"""

import os
from typing import Any, Optional, Tuple

_VALID_LLM_CLIENT_VALUES = frozenset({"stub", "litellm"})

from ai_rpg_world.application.llm.contracts.interfaces import (
    ILLMClient,
    ILlmTurnTrigger,
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
from ai_rpg_world.application.llm.services.tool_definitions import (
    register_default_tools,
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
    player_profile_repository: PlayerProfileRepository,
    unit_of_work_factory: UnitOfWorkFactory,
    observation_buffer: Optional[IObservationContextBuffer] = None,
    observation_formatter: Optional[IObservationFormatter] = None,
    spot_repository: Optional[Any] = None,
    item_spec_repository: Optional[Any] = None,
    item_repository: Optional[Any] = None,
    quest_repository: Optional[Any] = None,
    shop_repository: Optional[Any] = None,
    guild_repository: Optional[Any] = None,
    monster_repository: Optional[Any] = None,
    hit_box_repository: Optional[Any] = None,
    skill_loadout_repository: Optional[Any] = None,
    skill_deck_progress_repository: Optional[Any] = None,
    skill_spec_repository: Optional[Any] = None,
    llm_client: Optional[ILLMClient] = None,
    game_time_provider: Optional[Any] = None,
    world_time_config_service: Optional[Any] = None,
) -> Tuple[ObservationEventHandlerRegistry, ILlmTurnTrigger]:
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
        guild_repository: ギルド観測の配信先解決（全メンバー通知）・観測文の名前解決用（任意）。
        monster_repository: モンスター/会話NPC観測の配信先解決・観測文の名前解決用（任意）。
        hit_box_repository: 戦闘（HitBox）観測の配信先解決（owner 解決）用（任意）。
        skill_loadout_repository: スキル（Loadout）観測の配信先解決（owner 解決）用（任意）。
        skill_deck_progress_repository: スキル（DeckProgress）観測の配信先解決（owner 解決）用（任意）。
        skill_spec_repository: スキル名の観測文解決用（任意）。
        llm_client: 省略時は環境変数 LLM_CLIENT に従い作成（stub / litellm）
        game_time_provider: 省略時は観測にゲーム内時刻を付与しない。指定時は world_time_config_service も必要。
        world_time_config_service: 省略時は観測にゲーム内時刻を付与しない。ticks_per_day 等を提供する設定サービス。

    Returns:
        (ObservationEventHandlerRegistry, ILlmTurnTrigger)。
        呼び出し元は返り値の第1要素を EventHandlerComposition(observation_registry=...)、
        第2要素を WorldSimulationApplicationService(llm_turn_trigger=...) に渡すこと（ブートストラップ契約）。
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
    sliding_window = DefaultSlidingWindowMemory()
    action_result_store = DefaultActionResultStore()
    current_state_formatter = DefaultCurrentStateFormatter()
    recent_events_formatter = DefaultRecentEventsFormatter()
    context_format_strategy = SectionBasedContextFormatStrategy()
    system_prompt_builder = DefaultSystemPromptBuilder()
    game_tool_registry = DefaultGameToolRegistry()
    register_default_tools(game_tool_registry)
    available_tools_provider = DefaultAvailableToolsProvider(game_tool_registry)

    client = llm_client if llm_client is not None else _create_llm_client_from_env()
    tool_command_mapper = ToolCommandMapper(movement_service=movement_service)
    episode_memory_store = InMemoryEpisodeMemoryStore()
    long_term_memory_store = InMemoryLongTermMemoryStore()
    memory_extractor = RuleBasedMemoryExtractor()
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
        predictive_memory_retriever=predictive_retriever,
    )
    orchestrator = LlmAgentOrchestrator(
        prompt_builder=prompt_builder,
        llm_client=client,
        tool_command_mapper=tool_command_mapper,
        action_result_store=action_result_store,
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
    llm_player_resolver = ProfileBasedLlmPlayerResolver(
        player_profile_repository=player_profile_repository,
    )
    observation_resolver = create_observation_recipient_resolver(
        player_status_repository=player_status_repository,
        physical_map_repository=physical_map_repository,
        quest_repository=quest_repository,
        guild_repository=guild_repository,
        shop_repository=shop_repository,
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
        game_time_provider=game_time_provider,
        world_time_config=world_time_config_service,
    )
    observation_registry = ObservationEventHandlerRegistry(
        observation_handler=observation_handler,
    )
    return (observation_registry, llm_turn_trigger)
