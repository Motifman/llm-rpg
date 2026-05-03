"""1 回のツール結果から決定論的に SubjectiveEpisode 草案を組み立てる。

LLM・オーケストレータへの配線は行わない。
`episodic_cue_rules` が未マージの環境では `episodic_cues=` で注入するか、
モジュール不在時は cue を空として組み立てる（後から統合できる）。
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ai_rpg_world.application.llm.contracts.dtos import (
    EMOTION_HINT_VALUES,
    LlmCommandResultDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.contracts.episodic_memory import (
    EpisodicCue,
    EpisodeAction,
    EpisodeLocation,
    EpisodeSource,
    SubjectiveEpisode,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry

_EMOTION_HINT_SET = frozenset(EMOTION_HINT_VALUES)
_SAFE_SEGMENT_RE = re.compile(r"[^a-z0-9_]+")
_EPISODE_ID_NAMESPACE = uuid.UUID("018fc4d2-a6b1-7c3f-8120-ac5ed1e942b0")


def _strip_nonempty(label: str, raw: str) -> str:
    s = raw.strip()
    if not s:
        raise ValueError(f"{label} must be a non-empty str after strip")
    return s


def _optional_strip(label: str, raw: str | None) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{label} must be str or None")
    stripped = raw.strip()
    return stripped if stripped else None


def _slug_kind(kind: str) -> str:
    k = kind.strip().lower()
    cleaned = _SAFE_SEGMENT_RE.sub("_", k).strip("_")
    return cleaned if cleaned else "target"


def _actor_from_structured(raw: Any) -> str | None:
    if isinstance(raw, bool):  # bool is int subclass
        return None
    if isinstance(raw, int):
        return f"entity:actor:{raw}"
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        cleaned = _SAFE_SEGMENT_RE.sub("_", s.lower()).strip("_")
        if not cleaned:
            return None
        return f"entity:actor:{cleaned}"
    return None


def _collect_who(
    runtime_context: ToolRuntimeContextDto,
    observation: ObservationEntry | None,
) -> tuple[str, ...]:
    markers: list[str] = []

    targets = runtime_context.targets
    for label in sorted(targets.keys()):
        t = targets[label]
        if not isinstance(t, ToolRuntimeTargetDto):
            continue
        pid = t.player_id
        if isinstance(pid, int):
            markers.append(f"entity:{_slug_kind(t.kind)}:{pid}")
        woid = t.world_object_id
        if isinstance(woid, int):
            markers.append(f"object:world_object:{woid}")
        iid = t.item_instance_id
        if isinstance(iid, int):
            markers.append(f"object:item_instance:{iid}")
        cw = t.chest_world_object_id
        if isinstance(cw, int):
            markers.append(f"object:chest_world_object:{cw}")

    structured = observation.output.structured if observation else {}
    obs_actor = structured.get("actor") if isinstance(structured, dict) else None
    aa = _actor_from_structured(obs_actor)
    if aa is not None:
        markers.append(aa)

    seen: dict[str, None] = {}
    ordered_unique: list[str] = []
    for m in markers:
        if m not in seen:
            seen[m] = None
            ordered_unique.append(m)
    return tuple(ordered_unique)


def _canonical_arguments_text(canonical_arguments: Mapping[str, Any] | None) -> str | None:
    if not canonical_arguments:
        return None
    try:
        return json.dumps(dict(canonical_arguments), sort_keys=True, ensure_ascii=False, default=str)
    except TypeError:
        return str(canonical_arguments)


def _location_from_runtime(rt: ToolRuntimeContextDto) -> EpisodeLocation:
    areas = rt.current_area_ids
    normalized_areas: tuple[int, ...]
    if areas is None:
        normalized_areas = ()
    else:
        normalized_areas = tuple(int(a) for a in areas)

    def _nint(v: Any) -> int | None:
        if v is None:
            return None
        if isinstance(v, int):
            return v
        return None

    return EpisodeLocation(
        spot_id=_nint(rt.current_spot_id),
        tile_area_ids=normalized_areas,
        sub_location_id=_nint(rt.current_sub_location_id),
        x=_nint(rt.current_x),
        y=_nint(rt.current_y),
        z=_nint(rt.current_z),
    )


def _compose_observed(
    command_result: LlmCommandResultDto,
    result_summary: str,
    observation: ObservationEntry | None,
) -> str:
    """知覚本文は結果要約・DTO メッセージ・任意の観測 prose のみから組み立てる。"""
    rs = command_result.message.strip()
    summary = result_summary.strip()
    if summary and rs and summary != rs:
        core = f"{summary}\n{rs}"
    elif summary:
        core = summary
    elif rs:
        core = rs
    else:
        raise ValueError("result_summary か command_result.message のいずれかに非空白が必要です")
    obs_prose_stripped = observation.output.prose.strip() if observation else ""
    if obs_prose_stripped:
        return f"{core}\n{obs_prose_stripped}"
    return core


def _outcome_label(command_result: LlmCommandResultDto, result_summary: str) -> str:
    summary = result_summary.strip()
    if command_result.success:
        return f"成功: {summary}" if summary else "成功"
    ec = command_result.error_code
    suffix = summary if summary else command_result.message.strip()
    ec_part = f" code={ec}" if isinstance(ec, str) and ec.strip() else ""
    return f"失敗{ec_part}: {suffix}" if suffix else f"失敗{ec_part}"


def _prediction_error_template(
    expected: str | None, command_result: LlmCommandResultDto, result_summary: str
) -> str | None:
    if expected is None:
        return None
    summary = result_summary.strip() or command_result.message.strip()
    if summary == expected:
        return None
    return (
        "事前予想と結果要約が一致しない。"
        f" 予想: {expected}"
        f" / 結果: {summary}"
    )


def _recall_text(tool_name: str, command_result: LlmCommandResultDto, action_summary: str, result_summary: str) -> str:
    outcome_word = "成功" if command_result.success else "失敗"
    act = action_summary.strip()
    rs = result_summary.strip()
    if act:
        return f"{tool_name}: {act} は{outcome_word}（要約: {rs}）。"
    return f"{tool_name}: {outcome_word}（要約: {rs}）。"


def _default_episodic_cues(
    *,
    tool_name: str,
    canonical_arguments: Mapping[str, Any] | None,
    runtime_context: ToolRuntimeContextDto,
    command_result: LlmCommandResultDto,
    recent_observation: ObservationEntry | None,
) -> tuple[EpisodicCue, ...]:
    """`episodic_cue_rules` が import できれば決定論的 cue を載せる。それ以外は空（cue-rules 未マージと整合）。"""
    try:
        from ai_rpg_world.application.llm.services.episodic_cue_rules import (
            build_episodic_cues_for_tool_turn,
        )
    except ImportError:
        return ()

    structured = (
        recent_observation.output.structured
        if recent_observation is not None and isinstance(recent_observation.output.structured, dict)
        else None
    )
    return build_episodic_cues_for_tool_turn(
        tool_name=tool_name,
        canonical_arguments=canonical_arguments,
        runtime_context=runtime_context,
        command_result=command_result,
        observation_structured=structured,
    )


class ActionEpisodeDraftBuilder:
    """LLM を介さず 1 tool 結果から SubjectiveEpisode を組み立てる。"""

    def build(
        self,
        *,
        player_id: int,
        occurred_at: datetime | None,
        tool_name: str,
        canonical_arguments: Mapping[str, Any] | None,
        runtime_context: ToolRuntimeContextDto,
        command_result: LlmCommandResultDto,
        action_summary: str,
        result_summary: str,
        recent_observation: ObservationEntry | None = None,
        episodic_cues: tuple[EpisodicCue, ...] | None = None,
    ) -> SubjectiveEpisode:
        if not isinstance(player_id, int):
            raise TypeError("player_id must be int")

        ot = (
            occurred_at
            if occurred_at is not None
            else (recent_observation.occurred_at if recent_observation is not None else None)
        )
        if ot is None or not isinstance(ot, datetime):
            raise ValueError("occurred_at を渡すか、recent_observation.occurred_at が利用できること")

        tn = _strip_nonempty("tool_name", tool_name)
        act_sum = action_summary.strip()
        res_sum_raw = result_summary.strip()
        if not res_sum_raw and not command_result.message.strip():
            raise ValueError("result_summary と command_result.message の両方が空では構築できません")

        if not isinstance(runtime_context, ToolRuntimeContextDto):
            raise TypeError("runtime_context must be ToolRuntimeContextDto")
        if not isinstance(command_result, LlmCommandResultDto):
            raise TypeError("command_result must be LlmCommandResultDto")

        fingerprint = "|".join(
            (
                str(player_id),
                ot.replace(microsecond=0).isoformat(),
                tn,
                command_result.message,
                str(command_result.success),
                command_result.error_code or "",
                res_sum_raw,
            )
        )
        episode_id = str(uuid.uuid5(_EPISODE_ID_NAMESPACE, fingerprint))

        args = canonical_arguments or {}
        intention_raw = args.get("intention")
        expected_raw = args.get("expected_result")
        why = _optional_strip("why", intention_raw if isinstance(intention_raw, str) else None)
        expected = _optional_strip("expected", expected_raw if isinstance(expected_raw, str) else None)

        felt_raw = args.get("emotion_hint")
        felt: str | None = None
        if isinstance(felt_raw, str):
            el = felt_raw.strip().lower()
            if el in _EMOTION_HINT_SET:
                felt = el

        observed = _compose_observed(command_result, result_summary, recent_observation)
        rs_for_deriv = result_summary if res_sum_raw else command_result.message
        outcome = _outcome_label(command_result, rs_for_deriv)
        prediction_error = _prediction_error_template(expected, command_result, result_summary)

        if episodic_cues is not None:
            cues_resolved = episodic_cues
        else:
            cues_resolved = _default_episodic_cues(
                tool_name=tn,
                canonical_arguments=canonical_arguments,
                runtime_context=runtime_context,
                command_result=command_result,
                recent_observation=recent_observation,
            )

        action = EpisodeAction(tool_name=tn, canonical_arguments_text=_canonical_arguments_text(canonical_arguments))
        gt_val = recent_observation.game_time_label if recent_observation else None
        gametime = None
        if isinstance(gt_val, str):
            gst = gt_val.strip()
            gametime = gst if gst else None

        rs_for_what = res_sum_raw or command_result.message.strip()
        what_parts: list[str] = []
        if act_sum:
            what_parts.append(act_sum)
        what_parts.append(f"tool={tn}")
        if rs_for_what:
            what_parts.append(rs_for_what)
        what = " — ".join(what_parts)

        recall_rs = rs_for_deriv.strip() if rs_for_deriv else command_result.message.strip()

        return SubjectiveEpisode(
            episode_id=episode_id,
            player_id=player_id,
            occurred_at=ot,
            game_time_label=gametime,
            source=EpisodeSource(event_ids=(f"action_episode_draft:{episode_id}",)),
            location=_location_from_runtime(runtime_context),
            action=action,
            who=_collect_who(runtime_context, recent_observation),
            what=what,
            why=why,
            observed=observed,
            expected=expected,
            outcome=outcome,
            prediction_error=prediction_error,
            felt=felt,
            interpreted=None,
            intended_next=None,
            cues=cues_resolved,
            recall_text=_recall_text(tn, command_result, action_summary, recall_rs),
        )
