"""
ツール実行ターン向けの決定論的 EpisodicCue 生成。

LLM・プロンプト文字列・旧 cue_keys に依存しない。runtime / tool メタ /
canonical_arguments / LlmCommandResultDto / ActionResultEntry / 観測 structured のみを入力とする。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Iterable, Sequence

from ai_rpg_world.application.llm.contracts.dtos import (
    EMOTION_HINT_VALUES,
    ActionResultEntry,
    LlmCommandResultDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.contracts.episodic_memory import EpisodicCue, EpisodicCueSource

_EMOTION_HINT_SET = frozenset(EMOTION_HINT_VALUES)
_SAFE_SEGMENT_RE = re.compile(r"[^a-z0-9_]+")

# 1 episode あたりの cue 上限（索引肥大・暴走防止）
MAX_EPISODIC_CUES = 32
# tile_area は冗長になりやすいため個別上限（action/outcome より後ろで列挙し、ここで打ち切る）
MAX_TILE_AREA_CUES = 24
# value は索引キーとして短く保つ（canonical は axis:value のため value 側のみが対象）
MAX_CUE_VALUE_CHARS = 96


def build_episodic_cues_for_tool_turn(
    *,
    tool_name: str,
    canonical_arguments: Mapping[str, Any] | None,
    runtime_context: ToolRuntimeContextDto | None,
    command_result: LlmCommandResultDto | None,
    observation_structured: Mapping[str, Any] | None = None,
) -> tuple[EpisodicCue, ...]:
    """
    同一入力から常に同じ cue 列を返す（挿入順も固定）。

    None のコンテキストや未知フィールドは黙って無視する。
    """
    collected: list[EpisodicCue] = []

    # action / outcome / canonical はシグナルが強いため先に並べ、tile_area 大量時でも欠落しないようにする。
    tn = _optional_str(tool_name)
    if tn is not None:
        seg = _sanitize_tool_segment(tn)
        if seg is not None:
            collected.append(EpisodicCue(axis="action", value=seg, source=EpisodicCueSource.TOOL))

    args = canonical_arguments
    if args is not None:
        collected.extend(_cues_from_canonical_arguments(args))

    res = command_result
    if res is not None:
        oc = _outcome_cue_from_success_and_error(success=res.success, error_code=res.error_code)
        if oc is not None:
            collected.append(oc)

    collected.extend(
        _collect_situation_episodic_cues(
            runtime_context=runtime_context,
            observation_structured=observation_structured,
        )
    )

    validated = _validate_and_dedupe(collected)
    return tuple(validated)


def merge_ordered_episodic_cues(
    ordered_parts: Sequence[tuple[EpisodicCue, ...]],
) -> tuple[EpisodicCue, ...]:
    """
    複数の cue 列を先頭から順に連結し、canonical 単位で重複除去する。

    チャンク境界など、観測由来の局面 cue と複数 tool ターンの cue を束ねるときに使う。
    先に渡した列の cue が、同一 canonical では後続より優先される（挿入順維持）。
    """
    collected: list[EpisodicCue] = []
    for part in ordered_parts:
        collected.extend(part)
    return tuple(_validate_and_dedupe(collected))


def build_situation_episodic_cues(
    *,
    runtime_context: ToolRuntimeContextDto | None,
    observation_structured: Mapping[str, Any] | None = None,
    latest_action: ActionResultEntry | None = None,
) -> tuple[EpisodicCue, ...]:
    """
    受動想起用の「現在局面」に相当する cue 列を、保存時 `build_episodic_cues_for_tool_turn` と
    同じ軸・語彙・正規化で返す（挿入順も固定）。

    `ToolRuntimeContextDto` と直近観測 structured に加え、`latest_action` があれば
    直近ツール名・成否（§0.2）を action / outcome 軸で足し、チャンク保存側の cue と揃えて想起しやすくする。

    None の入力や未知フィールドは黙って無視する。
    """
    collected: list[EpisodicCue] = []
    if latest_action is not None:
        collected.extend(_cues_from_latest_action_entry(latest_action))
    collected.extend(
        _collect_situation_episodic_cues(
            runtime_context=runtime_context,
            observation_structured=observation_structured,
        )
    )
    validated = _validate_and_dedupe(collected)
    return tuple(validated)


def _collect_situation_episodic_cues(
    *,
    runtime_context: ToolRuntimeContextDto | None,
    observation_structured: Mapping[str, Any] | None,
) -> list[EpisodicCue]:
    """runtime と観測 structured から局面 cue を組み立てる（重複除去・件数上限は呼び出し側）。"""
    out: list[EpisodicCue] = []
    rt = runtime_context
    if rt is not None:
        out.extend(_cues_from_runtime_place(rt))

    obs = observation_structured
    if obs is not None:
        out.extend(_cues_from_observation_structured(obs))

    if rt is not None:
        out.extend(_cues_from_runtime_targets(rt.targets))
        out.extend(_cues_from_runtime_tile_areas(rt))

    return out


def _cues_from_latest_action_entry(entry: ActionResultEntry) -> list[EpisodicCue]:
    """IActionResultStore の最新行動から action / outcome cue を付与（tool ターンと同一正規化）。"""
    out: list[EpisodicCue] = []
    tn = _optional_str(entry.tool_name)
    if tn is not None:
        seg = _sanitize_tool_segment(tn)
        if seg is not None:
            out.append(EpisodicCue(axis="action", value=seg, source=EpisodicCueSource.TOOL))
    oc = _outcome_cue_from_success_and_error(success=entry.success, error_code=entry.error_code)
    if oc is not None:
        out.append(oc)
    return out


def _optional_str(raw: object | None) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    return s if s else None


def _sanitize_tool_segment(name: str) -> str | None:
    """tool 名を cue value として安全な単一段に落とす。"""
    lowered = name.strip().lower()
    if not lowered:
        return None
    cleaned = _SAFE_SEGMENT_RE.sub("_", lowered).strip("_")
    return _truncate_value(cleaned) if cleaned else None


def _sanitize_id_segment(prefix: str, raw_id: int) -> str:
    body = str(int(raw_id))
    seg = f"{prefix}_{body}" if prefix else body
    out = _truncate_value(seg)
    return out


def _truncate_value(value: str) -> str:
    if len(value) <= MAX_CUE_VALUE_CHARS:
        return value
    return value[:MAX_CUE_VALUE_CHARS]


def _normalize_error_code(code: str) -> str | None:
    s = code.strip().lower()
    if not s:
        return None
    cleaned = _SAFE_SEGMENT_RE.sub("_", s).strip("_")
    if not cleaned:
        return None
    return _truncate_value(cleaned)


def _outcome_cue_from_success_and_error(
    *, success: bool, error_code: str | None
) -> EpisodicCue | None:
    if success:
        value = "success"
    else:
        ec = error_code
        if isinstance(ec, str) and ec.strip():
            norm = _normalize_error_code(ec)
            value = f"failure_{norm}" if norm else "failure"
        else:
            value = "failure"
    safe = _truncate_value(value)
    if not safe:
        return None
    return EpisodicCue(axis="outcome", value=safe, source=EpisodicCueSource.TOOL)


def _strict_int(raw: Any) -> int | None:
    """bool は int のサブクラスだがゲーム id として誤解釈しない。"""
    return raw if type(raw) is int else None


def _cues_from_runtime_place(rt: ToolRuntimeContextDto) -> list[EpisodicCue]:
    out: list[EpisodicCue] = []
    src = EpisodicCueSource.RUNTIME_CONTEXT
    sid = _strict_int(rt.current_spot_id)
    if sid is not None:
        out.append(EpisodicCue(axis="place_spot", value=str(sid), source=src))
    sub = _strict_int(rt.current_sub_location_id)
    if sub is not None:
        out.append(EpisodicCue(axis="sub_loc", value=str(sub), source=src))
    return out


def _cues_from_runtime_tile_areas(rt: ToolRuntimeContextDto) -> list[EpisodicCue]:
    out: list[EpisodicCue] = []
    src = EpisodicCueSource.RUNTIME_CONTEXT
    areas = rt.current_area_ids
    if not isinstance(areas, tuple):
        return out
    sorted_ids = sorted({a for a in areas if type(a) is int})
    for aid in sorted_ids[:MAX_TILE_AREA_CUES]:
        out.append(EpisodicCue(axis="tile_area", value=str(aid), source=src))
    return out


def _kind_slug(kind: str) -> str:
    k = kind.strip().lower()
    if not k:
        return "target"
    cleaned = _SAFE_SEGMENT_RE.sub("_", k).strip("_")
    return cleaned if cleaned else "target"


def _cues_from_runtime_targets(targets: Mapping[str, ToolRuntimeTargetDto]) -> list[EpisodicCue]:
    out: list[EpisodicCue] = []
    src = EpisodicCueSource.RUNTIME_CONTEXT
    for label in sorted(targets.keys()):
        t = targets[label]
        if not isinstance(t, ToolRuntimeTargetDto):
            continue
        pid = _strict_int(t.player_id)
        if pid is not None:
            slug = _kind_slug(t.kind)
            val = _sanitize_id_segment(slug, pid)
            out.append(EpisodicCue(axis="entity", value=val, source=src))
        woid = _strict_int(t.world_object_id)
        if woid is not None:
            val = _sanitize_id_segment("world_object", woid)
            out.append(EpisodicCue(axis="object", value=val, source=src))
        iid = _strict_int(t.item_instance_id)
        if iid is not None:
            val = _sanitize_id_segment("item_instance", iid)
            out.append(EpisodicCue(axis="object", value=val, source=src))
        cid = _strict_int(t.chest_world_object_id)
        if cid is not None:
            val = _sanitize_id_segment("chest_world_object", cid)
            out.append(EpisodicCue(axis="object", value=val, source=src))
    return out


def _cues_from_canonical_arguments(args: Mapping[str, Any]) -> list[EpisodicCue]:
    out: list[EpisodicCue] = []
    hint = args.get("emotion_hint")
    if isinstance(hint, str):
        h = hint.strip().lower()
        if h in _EMOTION_HINT_SET:
            hv = _truncate_value(h)
            out.append(EpisodicCue(axis="emotion", value=hv, source=EpisodicCueSource.TOOL))
    woid = _strict_int(args.get("world_object_id"))
    if woid is not None:
        val = _sanitize_id_segment("world_object", woid)
        out.append(EpisodicCue(axis="object", value=val, source=EpisodicCueSource.TOOL))
    return out


def _coerce_non_bool_int(raw: Any) -> int | None:
    if type(raw) is int:
        return raw
    if isinstance(raw, float):
        if raw.is_integer():
            return int(raw)
        return None
    if isinstance(raw, str):
        s = raw.strip()
        if not s or not s.isdigit():
            return None
        try:
            return int(s)
        except ValueError:
            return None
    return None


def _coerce_actor_entity(raw: Any) -> str | None:
    x = _coerce_non_bool_int(raw)
    if x is not None:
        return _sanitize_id_segment("actor", x)
    if isinstance(raw, str):
        slug = _sanitize_tool_segment(raw)
        if slug is None:
            return None
        return _truncate_value(f"actor_{slug}")
    return None


def _cues_from_observation_structured(structured: Mapping[str, Any]) -> list[EpisodicCue]:
    out: list[EpisodicCue] = []
    src = EpisodicCueSource.OBSERVATION_STRUCTURED
    spot = structured.get("spot_id_value")
    si = _coerce_non_bool_int(spot)
    if si is not None:
        out.append(EpisodicCue(axis="place_spot", value=str(si), source=src))
    wov = structured.get("world_object_id_value")
    wi = _coerce_non_bool_int(wov)
    if wi is not None:
        val = _sanitize_id_segment("world_object", wi)
        out.append(EpisodicCue(axis="object", value=val, source=src))
    actor = structured.get("actor")
    av = _coerce_actor_entity(actor)
    if av is not None:
        out.append(EpisodicCue(axis="entity", value=av, source=src))
    return out


def _validate_and_dedupe(cues: Iterable[EpisodicCue]) -> list[EpisodicCue]:
    """canonical 単位で重複除去し、件数・値長を守る。"""
    seen: set[str] = set()
    ordered: list[EpisodicCue] = []
    for c in cues:
        if not isinstance(c, EpisodicCue):
            continue
        val = c.value
        if len(val) > MAX_CUE_VALUE_CHARS:
            continue
        key = c.to_canonical()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(c)
        if len(ordered) >= MAX_EPISODIC_CUES:
            break
    return ordered
