"""P2: Experience trace と runtime 断片から決定論的に `EpisodicCue` を抽出する。

§3.2 の空間軸（place_spot / tile_area / sub_loc）と、行動・観測・オブジェクト系の
ルールベース索引のみを生成する。LLM 由来の自由記述 cue はここでは作らない。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionExperienceTrace,
    EpisodicCue,
    ObservationExperienceTrace,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.contracts.interfaces import ExperienceTraceUnion

MAX_EPISODIC_CUE_VALUE_LEN = 128
MAX_EPISODIC_CUES_PER_EPISODE = 48


def merge_episodic_cues(*bundles: Tuple[EpisodicCue, ...]) -> Tuple[EpisodicCue, ...]:
    """複数バンドルを一列にし、(axis, value) で重複除去（先勝ち）。"""
    seen: set[tuple[str, str]] = set()
    out: list[EpisodicCue] = []
    for bundle in bundles:
        for c in bundle:
            key = (c.axis.strip(), c.value.strip())
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
    return tuple(out)


def validate_episodic_cues(cues: Tuple[EpisodicCue, ...]) -> Tuple[EpisodicCue, ...]:
    """値長・件数上限を適用（超過分は落とす）。"""
    picked: list[EpisodicCue] = []
    for c in cues:
        if len(c.value) > MAX_EPISODIC_CUE_VALUE_LEN:
            continue
        picked.append(c)
        if len(picked) >= MAX_EPISODIC_CUES_PER_EPISODE:
            break
    return tuple(picked)


def _append_int_cue(
    out: list[EpisodicCue],
    axis: str,
    value: Optional[int],
) -> None:
    if value is None:
        return
    out.append(EpisodicCue(axis=axis, value=str(value), source="rule"))


def _append_str_cue(out: list[EpisodicCue], axis: str, value: Optional[str]) -> None:
    if value is None:
        return
    t = value.strip()
    if not t:
        return
    if len(t) > MAX_EPISODIC_CUE_VALUE_LEN:
        return
    out.append(EpisodicCue(axis=axis, value=t, source="rule"))


def _structured_int(structured: Dict[str, Any], key: str) -> Optional[int]:
    """structured の数値フィールドを int に正規化（JSON で文字列化されても拾う）。"""
    v = structured.get(key)
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        t = v.strip()
        if t.isdigit() or (t.startswith("-") and t[1:].isdigit()):
            return int(t)
    return None


def episodic_cues_from_action_trace(trace: ActionExperienceTrace) -> Tuple[EpisodicCue, ...]:
    """行動 trace から空間・ツール名（action 軸）を抽出。"""
    out: list[EpisodicCue] = []
    name = trace.tool_name.strip()
    if name:
        _append_str_cue(out, "action", name)
    _append_int_cue(out, "place_spot", trace.context_spot_id)
    if trace.context_tile_area_ids:
        for aid in trace.context_tile_area_ids:
            _append_int_cue(out, "tile_area", aid)
    _append_int_cue(out, "sub_loc", trace.context_sub_location_id)
    return tuple(out)


def episodic_cues_from_observation_trace(
    trace: ObservationExperienceTrace,
) -> Tuple[EpisodicCue, ...]:
    """観測 trace から空間・観測種別・structured 内の安定 id を抽出。"""
    out: list[EpisodicCue] = []
    _append_str_cue(out, "observation_kind", str(trace.observation_kind))
    _append_int_cue(out, "place_spot", trace.context_spot_id)
    st = trace.structured
    if isinstance(st, dict):
        sid = _structured_int(st, "spot_id_value")
        if sid is not None and trace.context_spot_id is None:
            _append_int_cue(out, "place_spot", sid)
        woid = _structured_int(st, "world_object_id_value")
        if woid is not None:
            _append_int_cue(out, "world_object", woid)
        mid = _structured_int(st, "monster_id_value")
        if mid is not None:
            _append_int_cue(out, "monster", mid)
    if trace.context_tile_area_ids:
        for aid in trace.context_tile_area_ids:
            _append_int_cue(out, "tile_area", aid)
    _append_int_cue(out, "sub_loc", trace.context_sub_location_id)
    return tuple(out)


def _cues_from_single_target(target: ToolRuntimeTargetDto) -> Tuple[EpisodicCue, ...]:
    out: list[EpisodicCue] = []
    _append_str_cue(out, "object_type", target.kind)
    interaction = target.interaction_type
    if isinstance(interaction, str) and interaction.strip():
        _append_str_cue(out, "object_category", interaction.strip())
    _append_int_cue(out, "world_object", target.world_object_id)
    _append_int_cue(out, "place_spot", target.spot_id)
    _append_int_cue(out, "tile_area", target.tile_location_area_id)
    _append_int_cue(out, "sub_loc", target.sub_location_id)
    return tuple(out)


def episodic_cues_from_tool_runtime_context(
    ctx: Optional[ToolRuntimeContextDto],
) -> Tuple[EpisodicCue, ...]:
    """ツール解決 targets と current_* から空間・対象 id を抽出。"""
    if ctx is None:
        return ()
    ctx_level: list[EpisodicCue] = []
    _append_int_cue(ctx_level, "place_spot", ctx.current_spot_id)
    _append_int_cue(ctx_level, "sub_loc", ctx.current_sub_location_id)
    if ctx.current_area_ids:
        for aid in ctx.current_area_ids:
            _append_int_cue(ctx_level, "tile_area", aid)
    bundles: list[Tuple[EpisodicCue, ...]] = [tuple(ctx_level)]
    for target in ctx.targets.values():
        bundles.append(_cues_from_single_target(target))
    return merge_episodic_cues(*bundles)


def episodic_cues_from_trace(trace: ExperienceTraceUnion) -> Tuple[EpisodicCue, ...]:
    if isinstance(trace, ActionExperienceTrace):
        return episodic_cues_from_action_trace(trace)
    if isinstance(trace, ObservationExperienceTrace):
        return episodic_cues_from_observation_trace(trace)
    raise TypeError("trace must be ActionExperienceTrace or ObservationExperienceTrace")


def episodic_cues_from_traces(
    traces: Tuple[ExperienceTraceUnion, ...],
    *,
    runtime: Optional[ToolRuntimeContextDto] = None,
) -> Tuple[EpisodicCue, ...]:
    """候補に含まれる全 trace（と任意の runtime 断片）から最終 cue 列を返す。"""
    parts: list[Tuple[EpisodicCue, ...]] = []
    if runtime is not None:
        parts.append(episodic_cues_from_tool_runtime_context(runtime))
    for t in traces:
        parts.append(episodic_cues_from_trace(t))
    return validate_episodic_cues(merge_episodic_cues(*parts))
