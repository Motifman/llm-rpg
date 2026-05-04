"""
スポットグラフ専用の LLM エージェント配線。

タイル移動ツールは登録せず、spot_graph_* ツールと SpotGraphCurrentStateFormatter を用いる。
その他の LLM 観測・ツール枠は create_llm_agent_wiring と別経路だが、エピソード記憶（共有
ストア・チャンク境界での保存・受動想起）は既定で**同じ方針**で配線する（インメモリまたは
`SUBJECTIVE_EPISODE_DB_PATH`）。
"""

from __future__ import annotations

import os
from typing import Any, Optional

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
from ai_rpg_world.application.llm.contracts.episodic_chunk_subjective_llm_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.application.llm.contracts.episodic_episode_store_port import (
    IEpisodicEpisodeStore,
)
from ai_rpg_world.application.llm.contracts.episodic_reinterpretation import (
    IEpisodicRecallBufferStore,
    IEpisodicReinterpretationCompletionPort,
    IEpisodicReinterpretationJournalStore,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    ILLMClient,
    ILLMPlayerResolver,
    ISlidingWindowMemory,
)
from ai_rpg_world.application.llm.contracts.persona import PersonaPromptPolicy
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import (
    ChunkEpisodeDraftBuilder,
)
from ai_rpg_world.application.llm.services.episodic_chunk_coordinator import (
    EpisodicChunkCoordinator,
)
from ai_rpg_world.application.llm.services.prompt_builder import (
    DEFAULT_RECENT_ACTIONS_LIMIT,
    DEFAULT_RECENT_OBSERVATIONS_LIMIT,
)
from ai_rpg_world.application.llm.services.episodic_promotion_frontier import (
    EpisodicPromotionFrontier,
)
from ai_rpg_world.application.llm.services.episodic_semantic_cluster_promotion import (
    EpisodicSemanticClusterPromotionService,
)
from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.llm.wiring._default_episodic_episode_store import (
    resolve_default_episodic_episode_store,
)
from ai_rpg_world.application.llm.services.spot_graph_current_state_formatter import (
    SpotGraphCurrentStateFormatter,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
    IObservationFormatter,
)
from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery
from ai_rpg_world.application.world.services.world_query_service import WorldQueryService
from ai_rpg_world.application.world_graph.spot_graph_augmenting_world_query import (
    SpotGraphAugmentingWorldQueryService,
)
from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
    SpotGraphCurrentStateBuilder,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
)
from ai_rpg_world.application.world_graph.spot_graph_no_op_movement_service import (
    SpotGraphNoOpMovementService,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import ISpotGraphRepository
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import ISpotInteriorRepository
from ai_rpg_world.application.llm.wiring.episodic_memory_link_bundle import (
    build_episodic_memory_link_bundle,
    default_link_and_semantic_stores_for_episode_store,
)


def create_spot_graph_wiring(
    *,
    player_status_repository: PlayerStatusRepository,
    physical_map_repository: PhysicalMapRepository,
    world_query_service: WorldQueryService,
    spot_graph_world_services: SpotGraphWorldServices,
    spot_graph_repository: ISpotGraphRepository,
    spot_interior_repository: ISpotInteriorRepository,
    player_inventory_repository: PlayerInventoryRepository,
    item_repository: ItemRepository,
    item_spec_repository: ItemSpecRepository,
    player_profile_repository: PlayerProfileRepository,
    unit_of_work_factory: UnitOfWorkFactory,
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
    observation_buffer: Optional[IObservationContextBuffer] = None,
    observation_formatter: Optional[IObservationFormatter] = None,
    spot_repository: Optional[Any] = None,
    monster_template_repository: Optional[Any] = None,
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
    notification_command_service: Optional[Any] = None,
    sns_mode_session: Optional[Any] = None,
    sns_page_session: Optional[Any] = None,
    post_query_service: Optional[Any] = None,
    sns_page_query_service: Optional[Any] = None,
    trade_page_session: Optional[Any] = None,
    trade_page_query_service: Optional[Any] = None,
    reply_query_service: Optional[Any] = None,
    notification_query_service: Optional[Any] = None,
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
    episodic_episode_store: Optional[IEpisodicEpisodeStore] = None,
    episodic_recall_buffer_store: Optional[IEpisodicRecallBufferStore] = None,
    episodic_reinterpretation_journal_store: Optional[
        IEpisodicReinterpretationJournalStore
    ] = None,
    episodic_reinterpretation_completion: Optional[
        IEpisodicReinterpretationCompletionPort
    ] = None,
    chunk_episode_draft_builder: Optional[ChunkEpisodeDraftBuilder] = None,
    episodic_chunk_coordinator: Optional[EpisodicChunkCoordinator] = None,
    episodic_chunk_subjective_completion: Optional[IEpisodicChunkSubjectiveCompletionPort] = None,
    event_publisher: Optional[Any] = None,
) -> "LlmAgentWiringResult":
    """スポットグラフ用に LLM 観測・ツール・プロンプトを組み立てる（タイル移動なし）。

    エピソード記憶は create_llm_agent_wiring と同様、既定で共有 in-memory ストアを
    オーケストレータと受動想起に渡す。上書きは `episodic_episode_store` /
    `chunk_episode_draft_builder` / `episodic_chunk_coordinator`。
    """
    # 遅延 import: wiring/__init__.py の循環を避ける
    from ai_rpg_world.application.llm.wiring import (
        LlmAgentWiringResult,
        _DEFAULT_LLM_VIEW_DISTANCE,
        _ENV_LLM_VIEW_DISTANCE,
        _build_observation_stack,
        _build_persona_block_provider,
        _build_prompt_stack,
        _build_runtime_tool_state,
        _build_tool_stack,
        _optional_episodic_chunk_subjective_fields_service,
        _optional_episodic_reinterpretation_completion,
        _resolve_default_episodic_reinterpretation_stores,
    )
    from ai_rpg_world.application.llm.services.episodic_reinterpretation_coordinator import (
        EpisodicReinterpretationCoordinator,
    )
    from ai_rpg_world.application.llm.wiring._llm_client_factory import (
        create_llm_client_from_env,
    )
    from ai_rpg_world.application.llm.services.action_result_store import (
        DefaultActionResultStore,
    )
    from ai_rpg_world.application.llm.services.agent_orchestrator import LlmAgentOrchestrator
    from ai_rpg_world.application.llm.services.context_format_strategy import (
        SectionBasedContextFormatStrategy,
    )
    from ai_rpg_world.application.llm.services.game_tool_registry import DefaultGameToolRegistry
    from ai_rpg_world.application.llm.services.in_memory_todo_store import InMemoryTodoStore
    from ai_rpg_world.application.llm.services.llm_player_resolver import ProfileBasedLlmPlayerResolver
    from ai_rpg_world.application.llm.services.llm_turn_trigger import DefaultLlmTurnTrigger
    from ai_rpg_world.application.llm.services.llm_agent_turn_runner import LlmAgentTurnRunner
    from ai_rpg_world.application.llm.services.recent_events_formatter import (
        DefaultRecentEventsFormatter,
    )
    from ai_rpg_world.application.llm.services.sliding_window_memory import DefaultSlidingWindowMemory
    from ai_rpg_world.application.llm.services.system_prompt_builder import DefaultSystemPromptBuilder
    from ai_rpg_world.application.llm.services.ui_context_builder import DefaultLlmUiContextBuilder
    from ai_rpg_world.application.observation.services.observation_context_buffer import (
        DefaultObservationContextBuffer,
    )
    from ai_rpg_world.application.observation.services.observation_appender import (
        ObservationAppender,
    )
    from ai_rpg_world.application.observation.services.observation_formatter import (
        ObservationFormatter,
    )

    if player_status_repository is None:
        raise TypeError("player_status_repository must not be None")
    if physical_map_repository is None:
        raise TypeError("physical_map_repository must not be None")
    if world_query_service is None:
        raise TypeError("world_query_service must not be None")
    if player_profile_repository is None:
        raise TypeError("player_profile_repository must not be None")
    if unit_of_work_factory is None:
        raise TypeError("unit_of_work_factory must not be None")

    buffer = (
        observation_buffer if observation_buffer is not None else DefaultObservationContextBuffer()
    )

    # --- EventPublisher: 渡されなければデフォルトで InMemoryEventPublisher を生成 ---
    if event_publisher is None:
        from ai_rpg_world.infrastructure.events.event_publisher_impl import InMemoryEventPublisher
        event_publisher = InMemoryEventPublisher()
    # ConsumableEffectHandler を登録（アイテム消費→HP/MP回復等）
    from ai_rpg_world.application.world.handlers.consumable_effect_handler import ConsumableEffectHandler
    from ai_rpg_world.infrastructure.events.consumable_effect_event_handler_registry import (
        ConsumableEffectEventHandlerRegistry,
    )
    consumable_handler = ConsumableEffectHandler(
        item_spec_repository=item_spec_repository,
        player_status_repository=player_status_repository,
    )
    ConsumableEffectEventHandlerRegistry(consumable_handler).register_handlers(event_publisher)

    # 光源アイテムを自動検出
    light_source_item_spec_ids = frozenset(
        rm.item_spec_id
        for rm in item_spec_repository.find_all()
        if getattr(rm, "is_light_source", False)
    )

    def _owned_item_spec_ids_provider(entity_id: int) -> frozenset:
        inv = player_inventory_repository.find_by_id(PlayerId(entity_id))
        if inv is None:
            return frozenset()
        return collect_owned_item_spec_ids_from_inventory(inv, item_repository)

    sg_builder = SpotGraphCurrentStateBuilder(
        spot_graph_repository=spot_graph_repository,
        spot_interior_repository=spot_interior_repository,
        player_status_repository=player_status_repository,
        light_source_item_spec_ids=light_source_item_spec_ids,
        owned_item_spec_ids_provider=_owned_item_spec_ids_provider,
    )
    augmented_world_query = SpotGraphAugmentingWorldQueryService(
        inner=world_query_service,
        spot_graph_builder=sg_builder,
    )
    current_state_formatter = SpotGraphCurrentStateFormatter()

    sliding_window = (
        sliding_window_memory if sliding_window_memory is not None else DefaultSlidingWindowMemory()
    )
    action_result_store = (
        action_result_store if action_result_store is not None else DefaultActionResultStore()
    )
    from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
        SpotGraphUiContextBuilder,
    )
    ui_context_builder = SpotGraphUiContextBuilder()
    recent_events_formatter = DefaultRecentEventsFormatter()
    context_format_strategy = SectionBasedContextFormatStrategy()
    system_prompt_builder = (
        DefaultSystemPromptBuilder(template=system_prompt_template)
        if system_prompt_template is not None
        else DefaultSystemPromptBuilder()
    )
    game_tool_registry = DefaultGameToolRegistry()
    persona_block_provider = _build_persona_block_provider(
        persona_store, persona_prompt_policy
    )

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

    runtime_tool_state = _build_runtime_tool_state()
    todo_store = runtime_tool_state.todo_store

    client = llm_client if llm_client is not None else create_llm_client_from_env()
    shared_episode_store = resolve_default_episodic_episode_store(episodic_episode_store)
    link_store, semantic_memory_store = default_link_and_semantic_stores_for_episode_store(
        shared_episode_store
    )
    promotion_frontier = EpisodicPromotionFrontier()
    mem_bundle = build_episodic_memory_link_bundle(
        shared_episode_store,
        link_store=link_store,
        promotion_frontier=promotion_frontier,
    )
    episodic_semantic_promotion = EpisodicSemanticClusterPromotionService(
        episode_store=shared_episode_store,
        link_store=mem_bundle.link_store,
        semantic_store=semantic_memory_store,
        promotion_frontier=promotion_frontier,
    )
    spot_graph_tool_executor = SpotGraphToolExecutor(
        spot_graph_world_services=spot_graph_world_services,
        player_inventory_repository=player_inventory_repository,
        item_repository=item_repository,
        event_publisher=event_publisher,
    )
    no_op_movement = SpotGraphNoOpMovementService()

    tool_stack = _build_tool_stack(
        game_tool_registry=game_tool_registry,
        todo_store=todo_store,
        include_tile_movement=False,
        movement_service=None,
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
        spot_graph_tool_executor=spot_graph_tool_executor,
        episodic_memory_explore_executor=mem_bundle.memory_explore_executor(),
        episodic_explore_related_enabled=True,
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
    chunk_builder = (
        chunk_episode_draft_builder
        if chunk_episode_draft_builder is not None
        else ChunkEpisodeDraftBuilder()
    )
    chunk_subjective_service = _optional_episodic_chunk_subjective_fields_service(
        client,
        episodic_chunk_subjective_completion,
    )
    reinterpretation_completion = _optional_episodic_reinterpretation_completion(
        client,
        episodic_reinterpretation_completion,
    )
    reinterpretation_coord = EpisodicReinterpretationCoordinator(
        episode_store=shared_episode_store,
        recall_buffer_store=recall_buffer,
        journal_store=reinterpretation_journal,
        completion=reinterpretation_completion,
    )
    prompt_recall_buffer = (
        recall_buffer
        if reinterpretation_completion is not None or episodic_recall_buffer_store is not None
        else None
    )
    episodic_coord = episodic_chunk_coordinator or EpisodicChunkCoordinator(
        observation_buffer=buffer,
        sliding_window_memory=sliding_window,
        action_result_store=action_result_store,
        episodic_episode_store=shared_episode_store,
        chunk_episode_draft_builder=chunk_builder,
        recent_observations_limit=DEFAULT_RECENT_OBSERVATIONS_LIMIT,
        recent_actions_limit=DEFAULT_RECENT_ACTIONS_LIMIT,
        chunk_subjective_fields_service=chunk_subjective_service,
        persona_block_provider=persona_block_provider
        if chunk_subjective_service is not None
        else None,
        episodic_memory_link_service=mem_bundle.link_service,
    )
    episodic_passive_recall = mem_bundle.passive_recall
    prompt_builder = _build_prompt_stack(
        buffer=buffer,
        sliding_window=sliding_window,
        action_result_store=action_result_store,
        world_query_service=augmented_world_query,
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
    )
    turn_runner = LlmAgentTurnRunner(
        observation_buffer=buffer,
        world_query_service=augmented_world_query,
        movement_service=no_op_movement,
        action_result_store=action_result_store,
        orchestrator=orchestrator,
    )
    llm_turn_trigger = DefaultLlmTurnTrigger(turn_runner=turn_runner, max_turns=max_turns)

    observation_appender = ObservationAppender(buffer)

    formatter = observation_formatter
    if formatter is None:
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

    # 観測パイプラインを EventPublisher に登録（スポットグラフイベントが観測として配信される）
    from ai_rpg_world.infrastructure.events.observation_event_handler_registry import (
        ObservationEventHandlerRegistry,
    )

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
        movement_service=no_op_movement,
        game_time_provider=game_time_provider,
        world_time_config_service=world_time_config_service,
        observation_formatter=formatter,
        spot_repository=spot_repository,
        item_spec_repository=item_spec_repository,
        item_repository=item_repository,
        skill_spec_repository=skill_spec_repository,
        spot_graph_repository=spot_graph_repository,
        observation_appender=observation_appender,
    )
    # 観測ハンドラを EventPublisher に登録
    ObservationEventHandlerRegistry(observation_registry).register_handlers(event_publisher)

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
        event_publisher=event_publisher,
    )


__all__ = ["create_spot_graph_wiring"]
