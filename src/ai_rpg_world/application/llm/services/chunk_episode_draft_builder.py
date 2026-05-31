"""ChunkEncodingInput から LLM なしで SubjectiveEpisode のルール由来フィールドを埋める。

統一タイムラインのテキストは DefaultRecentEventsFormatter と同規則（観測・行動結果の一次情報を揃える）。
`interpreted` / `recall_text` は後続工程用に None のままとする。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    ChunkEncodingInput,
    chunk_encoding_episode_generation_allowed,
    format_unified_timeline_as_recent_events_bullets,
)
from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    LlmCommandResultDto,
)
from ai_rpg_world.application.llm.contracts.episodic_memory import (
    EpisodicCue,
    EpisodeAction,
    EpisodeLocation,
    EpisodeSource,
    SubjectiveEpisode,
)
from ai_rpg_world.application.llm.services.action_episode_draft_builder import (
    _actor_from_structured,
)
from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
    compute_template_interpreted,
    compute_template_recall,
)
from ai_rpg_world.application.llm.services.episodic_cue_rules import (
    _coerce_non_bool_int,
    build_episodic_cues_for_tool_turn,
    build_situation_episodic_cues,
    merge_ordered_episodic_cues,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry

_EPISODE_ID_NAMESPACE = uuid.UUID("018fc4d2-a6b1-7c3f-8120-ac5ed1e942b0")


def _as_utc(value: datetime) -> datetime:
    """naive datetime を UTC aware として扱う sort 正規化ヘルパ。

    Issue #311 後続: ドメインイベント / 観測の occurred_at に aware/naive が
    混在しても sort が落ちないようにする。``episodic_chunk_coordinator._as_utc``
    と同じ意図。
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _all_observation_entries(inp: ChunkEncodingInput) -> tuple[ObservationEntry, ...]:
    """プロンプトウィンドウ外の溢れ観測も、cue / who / 場所ヒントの材料に含める。"""
    return tuple(inp.observations) + tuple(inp.observation_overflow_from_window)


def _sorted_actions(action_results: tuple[ActionResultEntry, ...]) -> list[ActionResultEntry]:
    return sorted(action_results, key=lambda e: _as_utc(e.occurred_at))


def _event_ids_for_chunk(inp: ChunkEncodingInput) -> tuple[str, ...]:
    actions = _sorted_actions(inp.action_results)
    obs_all = sorted(
        _all_observation_entries(inp), key=lambda o: _as_utc(o.occurred_at)
    )
    ids: list[str] = []
    for idx, e in enumerate(actions):
        tn = e.tool_name if isinstance(e.tool_name, str) and e.tool_name.strip() else "_"
        fp = (
            e.argument_fingerprint.strip()
            if isinstance(e.argument_fingerprint, str) and e.argument_fingerprint.strip()
            else "_"
        )
        ids.append(
            f"action_result:{idx}:{e.occurred_at.isoformat()}:{tn}:{fp}:{e.success:d}"
        )
    for idx, o in enumerate(obs_all):
        cat = o.output.observation_category
        ids.append(f"observation:{idx}:{o.occurred_at.isoformat()}:{cat}")
    return tuple(ids)


def _episode_location_from_observations(entries: tuple[ObservationEntry, ...]) -> EpisodeLocation:
    """観測 structured の spot_id_value を優先する（複数あるときは最も occurred_at が新しいもの）。"""
    best_sid: int | None = None
    for o in sorted(entries, key=lambda x: _as_utc(x.occurred_at)):
        structured = o.output.structured if isinstance(o.output.structured, dict) else {}
        sid = _coerce_non_bool_int(structured.get("spot_id_value"))
        if sid is None:
            continue
        best_sid = sid
    if best_sid is None:
        return EpisodeLocation()
    return EpisodeLocation(spot_id=best_sid)


def _who_from_observations(entries: tuple[ObservationEntry, ...]) -> tuple[str, ...]:
    markers: list[str] = []
    for o in sorted(entries, key=lambda x: _as_utc(x.occurred_at)):
        structured = o.output.structured if isinstance(o.output.structured, dict) else {}
        aa = _actor_from_structured(structured.get("actor"))
        if aa is not None:
            markers.append(aa)
    seen: dict[str, None] = {}
    ordered: list[str] = []
    for m in markers:
        if m not in seen:
            seen[m] = None
            ordered.append(m)
    return tuple(ordered)


def _tool_name_segment(entry: ActionResultEntry) -> str:
    if isinstance(entry.tool_name, str) and entry.tool_name.strip():
        return entry.tool_name.strip()
    return "unknown_tool"


def _compose_action_tool_name_field(action_results: tuple[ActionResultEntry, ...]) -> str:
    """チャンク内の distinct tool 名を辞書順で連結（EpisodeAction.tool_name 用）。"""
    names = sorted({_tool_name_segment(e) for e in action_results})
    return ",".join(names)


def _compose_what(action_results: tuple[ActionResultEntry, ...]) -> str:
    parts: list[str] = []
    for e in _sorted_actions(action_results):
        tn = _tool_name_segment(e)
        asm = e.action_summary.strip() if e.action_summary.strip() else "(行動)"
        parts.append(f"{tn}: {asm}")
    return " — ".join(parts)


def _compose_outcome(action_results: tuple[ActionResultEntry, ...]) -> str:
    acts = _sorted_actions(action_results)
    n = len(acts)
    n_ok = sum(1 for a in acts if a.success)
    n_fail = n - n_ok
    last = acts[-1]
    rs = last.result_summary.strip() or last.action_summary.strip() or "(要約なし)"
    if n_fail == 0:
        return f"{n_ok}件成功（末尾要約: {rs}）"
    return f"{n_fail}件失敗を含む / {n_ok}成功（末尾要約: {rs}）"


def _canonical_args_fingerprint_text(action_results: tuple[ActionResultEntry, ...]) -> str | None:
    fps = [
        e.argument_fingerprint.strip()
        for e in _sorted_actions(action_results)
        if isinstance(e.argument_fingerprint, str) and e.argument_fingerprint.strip()
    ]
    if not fps:
        return None
    return "|".join(fps)


def _build_chunk_cues(inp: ChunkEncodingInput) -> tuple[EpisodicCue, ...]:
    parts: list[tuple[EpisodicCue, ...]] = []
    for o in sorted(_all_observation_entries(inp), key=lambda x: _as_utc(x.occurred_at)):
        st = o.output.structured if isinstance(o.output.structured, dict) else None
        parts.append(build_situation_episodic_cues(runtime_context=None, observation_structured=st))
    for e in _sorted_actions(inp.action_results):
        res = LlmCommandResultDto(
            success=e.success,
            message=e.result_summary,
            error_code=e.error_code,
            should_reschedule=e.should_reschedule,
        )
        parts.append(
            build_episodic_cues_for_tool_turn(
                tool_name=_tool_name_segment(e),
                canonical_arguments=None,
                runtime_context=None,
                command_result=res,
                observation_structured=None,
            )
        )
    return merge_ordered_episodic_cues(parts)


def _game_time_label_newest_in_window(inp: ChunkEncodingInput) -> str | None:
    """チャンクに含まれる観測（ウィンドウ内）のうち最も新しい game_time_label。"""
    best: str | None = None
    best_t = None
    for o in inp.observations:
        if not isinstance(o.game_time_label, str):
            continue
        gl = o.game_time_label.strip()
        if not gl:
            continue
        norm = _as_utc(o.occurred_at)
        if best_t is None or norm >= best_t:
            best_t = norm
            best = gl
    return best


class ChunkEpisodeDraftBuilder:
    """チャンク境界の ChunkEncodingInput から SubjectiveEpisode 草案を組み立てる。"""

    def build(self, inp: ChunkEncodingInput) -> SubjectiveEpisode:
        if not isinstance(inp, ChunkEncodingInput):
            raise TypeError("inp must be ChunkEncodingInput")
        if not chunk_encoding_episode_generation_allowed(inp):
            raise ValueError(
                "chunk でエピソード生成が許可されていません（ActionResultEntry が 1 件以上必要です）"
            )

        pid = inp.player_id.value
        observed = format_unified_timeline_as_recent_events_bullets(inp.unified_timeline)
        observed = observed.strip()
        if not observed:
            raise ValueError("統一タイムラインから observed を組み立てられません")

        acts = inp.action_results
        # Issue #311 後続: aware/naive 混在で max() が落ちないよう正規化キーで選ぶ
        occurred_at = max(acts, key=lambda e: _as_utc(e.occurred_at)).occurred_at
        obs_for_place_who = _all_observation_entries(inp)
        what = _compose_what(acts)
        # draft 時点で `recall_text` / `interpreted` をテンプレで埋めておく。
        #
        # 理由: LLM 補完サービス (EpisodicChunkSubjectiveFieldsService) を未配線の
        # 経路 (escape_game 等の MVP wiring) でも、recall 時の prompt に「何か」が
        # 載るようにする。第20回実験で `recall_text_snippet` が 0/21 件と全件空に
        # なり、せっかく recall が発火しても LLM に思い出を届けられていない問題が
        # 観測された (Issue #295 r2 trace)。LLM 補完が走るときは `merge_llm_subjective_fields`
        # が同じテンプレを fallback として持っており、上書きする。

        fingerprint = "|".join(
            (
                str(pid),
                occurred_at.isoformat(),
                observed,
                _compose_action_tool_name_field(acts),
                _compose_outcome(acts),
            )
        )
        episode_id = str(uuid.uuid5(_EPISODE_ID_NAMESPACE, fingerprint))

        return SubjectiveEpisode(
            episode_id=episode_id,
            player_id=pid,
            occurred_at=occurred_at,
            game_time_label=_game_time_label_newest_in_window(inp),
            source=EpisodeSource(event_ids=_event_ids_for_chunk(inp)),
            location=_episode_location_from_observations(obs_for_place_who),
            action=EpisodeAction(
                tool_name=_compose_action_tool_name_field(acts),
                canonical_arguments_text=_canonical_args_fingerprint_text(acts),
            ),
            who=_who_from_observations(obs_for_place_who),
            what=what,
            why=None,
            observed=observed,
            expected=None,
            outcome=_compose_outcome(acts),
            prediction_error=None,
            felt=None,
            interpreted=compute_template_interpreted(what),
            cues=_build_chunk_cues(inp),
            recall_text=compute_template_recall(observed, what),
            recall_count=0,
            last_recalled_at=None,
        )
