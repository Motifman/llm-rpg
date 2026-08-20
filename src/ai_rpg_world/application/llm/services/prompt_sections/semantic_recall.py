"""semantic memory の受動想起 section 組み立て。"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, List, Optional

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.episodic_cue_rules import build_situation_episodic_cues
from ai_rpg_world.application.llm.services.recall_need_cues import recall_cues_for_needs
from ai_rpg_world.application.llm.services.semantic_passive_recall_service import (
    format_semantic_recall_section,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

from ai_rpg_world.application.llm.services.prompt_sections.episodic_recall import (
    _gather_additional_freetexts_for_recall,
)

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder


def _gather_semantic_topic_words_for_recall(current_state_dto: Any | None) -> list[str]:
    """現在状態 DTO から semantic relevance 用の日本語 topic 語を抽出する。

    ID ではなく、prompt に出る名前・状態語だけを使う。戻り値は
    ``build_situation_episodic_cues`` の検索入力側 topic cue になり、episode
    保存側の cue には混ぜない。
    """
    out: list[str] = []

    def add(raw: Any | None) -> None:
        if not isinstance(raw, str):
            return
        text = raw.strip()
        if text:
            out.append(text)

    if current_state_dto is None:
        return out

    add(getattr(current_state_dto, "current_spot_name", None))
    for area_name in getattr(current_state_dto, "area_names", None) or ():
        add(area_name)

    for obj in getattr(current_state_dto, "visible_objects", None) or ():
        add(getattr(obj, "display_name", None))

    for item in getattr(current_state_dto, "inventory_items", None) or ():
        add(getattr(item, "display_name", None))

    snap = getattr(current_state_dto, "spot_graph_snapshot", None)
    if snap is None:
        return out

    add(getattr(snap, "current_spot_name", None))
    for obj in getattr(snap, "objects", None) or ():
        add(getattr(obj, "name", None))
    for item in getattr(snap, "inventory_items", None) or ():
        add(getattr(item, "name", None))
    for item in getattr(snap, "ground_items", None) or ():
        add(getattr(item, "name", None))
    for entity in getattr(snap, "nearby_entities", None) or ():
        add(getattr(entity, "display_name", None))
    for monster in getattr(snap, "monsters_at_spot", None) or ():
        add(getattr(monster, "display_name", None))

    # 強く出ている欲求から検索語を足す。
    #
    # 以前はここで need_lines を**文字列として読み直していた**
    # (``line.startswith("空腹") and ("高い" in line or "危険" in line)``)。判定に
    # 要る値は AgentNeed が持っているのに、自分たちが組み立てた表示文から読み直して
    # いたので、tier の言い回しを変えると想起の手がかりが黙って消えた (系統2)。
    out.extend(recall_cues_for_needs(getattr(snap, "need_states", None) or ()))

    return out


def run_semantic_passive_recall(
    builder: "DefaultPromptBuilder",
    *,
    player_id: PlayerId,
    being_id: BeingId,
    observations: List[ObservationEntry],
    action_results: List[Any],
    ui_context: Any,
    current_state_dto: Optional[Any] = None,
) -> tuple[str, tuple[str, ...]]:
    """Phase 1c: semantic memory の状況連想 top-K を §「【関連する学び】」用に整形する。

    service 未注入 または top_k=0 なら空文字 (= section ごと省略)。
    situation_cues は episodic 受動想起と同じ build_situation_episodic_cues
    を使う (関連 episodes と関連 semantic facts を同じ「いま」基準で集める)。

    戻り値は (整形テキスト, belief entry_id 群)。後者は U1 の
    prediction_context_id に「その build で in-context だった belief」
    として紐づけるため。
    """
    if builder._semantic_passive_recall is None or builder._semantic_passive_top_k <= 0:
        return "", ()

    observation_structured = None
    observation_prose: Optional[str] = None
    if observations:
        observation_structured = observations[0].output.structured
        observation_prose = observations[0].output.prose
    latest_action = action_results[0] if action_results else None
    additional_freetexts = _gather_additional_freetexts_for_recall(
        observations, action_results
    )
    encounter_tick = builder._resolve_encounter_tick()
    situation_cues = build_situation_episodic_cues(
        runtime_context=ui_context.tool_runtime_context,
        observation_structured=observation_structured,
        latest_action=latest_action,
        observation_prose=observation_prose,
        noun_matcher=builder._noun_matcher,
        additional_freetexts=additional_freetexts,
        semantic_topic_words=_gather_semantic_topic_words_for_recall(current_state_dto),
        include_topic_cues=True,
        encounter_memory=builder._encounter_memory_for_recall,
        encounter_player_id=player_id,
        encounter_current_tick=encounter_tick,
        encounter_recent_window_ticks=builder._encounter_recent_window_ticks,
    )
    now = datetime.now(timezone.utc)
    try:
        candidates = builder._semantic_passive_recall.retrieve(
            being_id=being_id,
            situation_cues=situation_cues,
            top_k=builder._semantic_passive_top_k,
            now=now,
        )
    except Exception as e:
        # semantic ランキング失敗で prompt build を止めない
        builder._logger.warning(
            "Semantic passive recall failed for player_id=%s: %s",
            player_id.value,
            e,
            exc_info=True,
        )
        candidates = []

    emit_semantic_passive_recall_trace(
        builder,
        player_id=player_id,
        situation_cues=situation_cues,
        candidates=candidates,
    )

    belief_ids = tuple(c.entry.entry_id for c in candidates)
    return format_semantic_recall_section(candidates), belief_ids


def emit_semantic_passive_recall_trace(
    builder: "DefaultPromptBuilder",
    *,
    player_id: PlayerId,
    situation_cues: tuple,
    candidates: list,
) -> None:
    """``SEMANTIC_PASSIVE_RECALL`` を 1 件 emit する (失敗は握りつぶす)。

    Phase 1c 計測点: どの semantic entry が top-K に入り、それぞれの
    score 内訳 (recency / importance / relevance) を後追いできるようにする。
    """
    recorder = builder._resolve_trace_recorder()
    if recorder is None:
        return
    tick: Optional[int] = None
    if builder._current_tick_provider is not None:
        try:
            tick = builder._current_tick_provider()
        except Exception:
            tick = None
    try:
        cue_keys = [c.to_canonical() for c in situation_cues]
    except Exception:
        cue_keys = []
    cand_payload: list[dict] = []
    for cand in candidates:
        try:
            cand_payload.append(cand.to_trace_payload())
        except Exception:
            continue
    try:
        recorder.record(
            TraceEventKind.SEMANTIC_PASSIVE_RECALL,
            tick=tick,
            player_id=int(player_id.value),
            situation_cues=cue_keys,
            top_k=int(builder._semantic_passive_top_k),
            candidate_count=len(cand_payload),
            candidates=cand_payload,
        )
    except Exception:
        builder._logger.debug(
            "trace recorder.record raised for SEMANTIC_PASSIVE_RECALL; skipping",
            exc_info=True,
        )
