"""5 memory store の VO ↔ JSON dict 変換ヘルパ。

Phase 4 Step 4-2b (Issue #470): ``BeingMemorySnapshotService`` が `BeingSnapshot`
の ``memory_payload_json`` に詰める JSON の **内部 schema を版管理する** ための
serializer 群。

各 ``_<vo>_to_dict`` / ``_dict_to_<vo>`` は 1:1 の VO ↔ dict 変換を提供する。
**datetime は ISO 8601 文字列、Enum は ``.value``** で表現する (= JSON 標準型のみ)。
これにより snapshot JSON は他言語 / 外部ツールでも読みやすい。

NOTE: sqlite store にも類似の serializer (``_episode_to_payload_dict`` 等) が
存在するが、本 PR ではあえて重複させている。理由:

- 本 codec は **snapshot schema の版管理を行う** (= 内部 schema を凍結したい)
- sqlite store の serializer は **その store の永続化形式に縛られる** (= 行
  carve up の都合で形が変わりうる)

将来両者を統合するなら sqlite 側を本 module に寄せる方向 (application 層に
serializer を集約) になるが、本 PR の scope 外 (= 4-2b の責務は snapshot
service の構築のみ)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # PR-G: codec が触る per-Being store の VO を型注釈のみ用途で前方参照。
    # 実体は dict_to_* の関数内で遅延 import する (= 本 module は
    # application/being/ 層、参照先 VO は application/llm/services/ 配下なので
    # 単純な top-level import でも 循環は起きないが、他の codec 群と書式を
    # 揃え + dataclass の構築コストを呼び出し時に閉じ込めるためこの形を取る)。
    from ai_rpg_world.application.llm.services.afterglow_store import (
        AfterglowEntry,
    )
    from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
        RecallSlotEntry,
    )

from ai_rpg_world.domain.memory.episodic.value_object.episode_action import (
    EpisodeAction,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import (
    EpisodeLocation,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import (
    EpisodeSource,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import (
    EpisodicCueSource,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import (
    EpisodicReinterpretationEntry,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_status import (
    EpisodicReinterpretationStatus,
)
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    MemoryLink,
    MemoryLinkType,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from ai_rpg_world.domain.memory.memo.value_object.memo_entry import MemoEntry
from ai_rpg_world.domain.memory.memo.value_object.memo_fulfillment_context import (
    MemoFulfillmentContext,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)


# ---- datetime helpers ---------------------------------------------------------

def _dt_to_iso(dt: datetime) -> str:
    """tz-aware は UTC に寄せて isoformat。naive は UTC とみなす。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


def _iso_to_dt(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


# ---- memo ---------------------------------------------------------------------

def memo_entry_to_dict(entry: MemoEntry) -> dict[str, Any]:
    ctx = entry.fulfillment_context
    return {
        "id": entry.id,
        "content": entry.content,
        "added_at": _dt_to_iso(entry.added_at),
        "completed": entry.completed,
        "added_at_tick": entry.added_at_tick,
        "completed_at": _dt_to_iso(entry.completed_at) if entry.completed_at else None,
        "fulfillment_context": _fulfillment_to_dict(ctx) if ctx else None,
    }


def dict_to_memo_entry(data: dict[str, Any]) -> MemoEntry:
    ctx_raw = data.get("fulfillment_context")
    completed_at = data.get("completed_at")
    return MemoEntry(
        id=str(data["id"]),
        content=str(data["content"]),
        added_at=_iso_to_dt(str(data["added_at"])),
        completed=bool(data.get("completed", False)),
        added_at_tick=data.get("added_at_tick"),
        completed_at=_iso_to_dt(str(completed_at)) if completed_at else None,
        fulfillment_context=_dict_to_fulfillment(ctx_raw) if ctx_raw else None,
    )


def _fulfillment_to_dict(ctx: MemoFulfillmentContext) -> dict[str, Any]:
    return {
        "completed_at": _dt_to_iso(ctx.completed_at),
        "completed_at_tick": ctx.completed_at_tick,
        "recent_observation_proses": list(ctx.recent_observation_proses),
        "recent_action_summaries": list(ctx.recent_action_summaries),
    }


def _dict_to_fulfillment(data: dict[str, Any]) -> MemoFulfillmentContext:
    return MemoFulfillmentContext(
        completed_at=_iso_to_dt(str(data["completed_at"])),
        completed_at_tick=data.get("completed_at_tick"),
        recent_observation_proses=tuple(
            str(x) for x in data.get("recent_observation_proses", ())
        ),
        recent_action_summaries=tuple(
            str(x) for x in data.get("recent_action_summaries", ())
        ),
    )


# ---- semantic -----------------------------------------------------------------

def semantic_entry_to_dict(entry: SemanticMemoryEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "player_id": entry.player_id,
        "text": entry.text,
        "evidence_episode_ids": list(entry.evidence_episode_ids),
        "confidence": entry.confidence,
        "created_at": _dt_to_iso(entry.created_at),
        "importance_score": entry.importance_score,
        "tags": list(entry.tags),
    }


def dict_to_semantic_entry(data: dict[str, Any]) -> SemanticMemoryEntry:
    return SemanticMemoryEntry(
        entry_id=str(data["entry_id"]),
        player_id=int(data["player_id"]),
        text=str(data["text"]),
        evidence_episode_ids=tuple(
            str(x) for x in data.get("evidence_episode_ids", ())
        ),
        confidence=float(data["confidence"]),
        created_at=_iso_to_dt(str(data["created_at"])),
        importance_score=int(data.get("importance_score", 5)),
        tags=tuple(str(x) for x in data.get("tags", ())),
    )


# ---- memory_link --------------------------------------------------------------

def memory_link_to_dict(link: MemoryLink) -> dict[str, Any]:
    return {
        "link_id": link.link_id,
        "player_id": link.player_id,
        "episode_id_a": link.episode_id_a,
        "episode_id_b": link.episode_id_b,
        "link_type": link.link_type.value,
        "strength": link.strength,
        "co_activation_count": link.co_activation_count,
        "created_at": _dt_to_iso(link.created_at),
        "last_activated_at": _dt_to_iso(link.last_activated_at),
        "decay_rate": link.decay_rate,
    }


def dict_to_memory_link(data: dict[str, Any]) -> MemoryLink:
    return MemoryLink(
        link_id=str(data["link_id"]),
        player_id=int(data["player_id"]),
        episode_id_a=str(data["episode_id_a"]),
        episode_id_b=str(data["episode_id_b"]),
        link_type=MemoryLinkType(str(data["link_type"])),
        strength=float(data["strength"]),
        co_activation_count=int(data["co_activation_count"]),
        created_at=_iso_to_dt(str(data["created_at"])),
        last_activated_at=_iso_to_dt(str(data["last_activated_at"])),
        decay_rate=float(data["decay_rate"]),
    )


# ---- recall_buffer ------------------------------------------------------------

def recall_observation_to_dict(obs: EpisodicRecallObservation) -> dict[str, Any]:
    return {
        "recall_id": obs.recall_id,
        "player_id": obs.player_id,
        "episode_id": obs.episode_id,
        "recalled_at": _dt_to_iso(obs.recalled_at),
        "source_axes": list(obs.source_axes),
        "current_state_snapshot": obs.current_state_snapshot,
        "recent_events_snapshot": obs.recent_events_snapshot,
        "persona_snapshot": obs.persona_snapshot,
        "situation_cues": list(obs.situation_cues),
        "turn_index": obs.turn_index,
        "prediction_context_id": obs.prediction_context_id,
    }


def dict_to_recall_observation(data: dict[str, Any]) -> EpisodicRecallObservation:
    return EpisodicRecallObservation(
        recall_id=str(data["recall_id"]),
        player_id=int(data["player_id"]),
        episode_id=str(data["episode_id"]),
        recalled_at=_iso_to_dt(str(data["recalled_at"])),
        source_axes=tuple(str(x) for x in data.get("source_axes", ())),
        current_state_snapshot=str(data.get("current_state_snapshot", "")),
        recent_events_snapshot=str(data.get("recent_events_snapshot", "")),
        persona_snapshot=str(data.get("persona_snapshot", "")),
        situation_cues=tuple(str(x) for x in data.get("situation_cues", ())),
        turn_index=int(data.get("turn_index", 0)),
        # U1: 旧 snapshot にはキー自体が無いので None に倒す (後方互換)。
        prediction_context_id=data.get("prediction_context_id"),
    )


# ---- reinterpretation_journal -------------------------------------------------

def reinterpretation_entry_to_dict(
    entry: EpisodicReinterpretationEntry,
) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "player_id": entry.player_id,
        "episode_id": entry.episode_id,
        "created_at": _dt_to_iso(entry.created_at),
        "turn_index": entry.turn_index,
        "current_interpretation": entry.current_interpretation,
        "current_recall_text": entry.current_recall_text,
        "source_recall_ids": list(entry.source_recall_ids),
        "status": entry.status.value,
        "superseded_at": _dt_to_iso(entry.superseded_at)
        if entry.superseded_at
        else None,
    }


def dict_to_reinterpretation_entry(
    data: dict[str, Any],
) -> EpisodicReinterpretationEntry:
    superseded = data.get("superseded_at")
    return EpisodicReinterpretationEntry(
        entry_id=str(data["entry_id"]),
        player_id=int(data["player_id"]),
        episode_id=str(data["episode_id"]),
        created_at=_iso_to_dt(str(data["created_at"])),
        turn_index=int(data["turn_index"]),
        current_interpretation=str(data["current_interpretation"]),
        current_recall_text=str(data["current_recall_text"]),
        source_recall_ids=tuple(str(x) for x in data.get("source_recall_ids", ())),
        status=EpisodicReinterpretationStatus(str(data["status"])),
        superseded_at=_iso_to_dt(str(superseded)) if superseded else None,
    )


# ---- episodic_episode ---------------------------------------------------------

def subjective_episode_to_dict(ep: SubjectiveEpisode) -> dict[str, Any]:
    loc = ep.location
    act = ep.action
    return {
        "episode_id": ep.episode_id,
        "player_id": ep.player_id,
        "occurred_at": _dt_to_iso(ep.occurred_at),
        "game_time_label": ep.game_time_label,
        "source": {"event_ids": list(ep.source.event_ids)},
        "location": {
            "spot_id": loc.spot_id,
            "tile_area_ids": list(loc.tile_area_ids),
            "sub_location_id": loc.sub_location_id,
            "x": loc.x,
            "y": loc.y,
            "z": loc.z,
        },
        "action": None
        if act is None
        else {
            "tool_name": act.tool_name,
            "canonical_arguments_text": act.canonical_arguments_text,
        },
        "who": list(ep.who),
        "what": ep.what,
        "why": ep.why,
        "observed": ep.observed,
        "expected": ep.expected,
        "outcome": ep.outcome,
        "prediction_error": ep.prediction_error,
        "felt": ep.felt,
        "interpreted": ep.interpreted,
        "cues": [
            {"axis": c.axis, "value": c.value, "source": c.source.value}
            for c in ep.cues
        ],
        "recall_text": ep.recall_text,
        "recall_count": ep.recall_count,
        "last_recalled_at": _dt_to_iso(ep.last_recalled_at)
        if ep.last_recalled_at
        else None,
    }


def dict_to_subjective_episode(data: dict[str, Any]) -> SubjectiveEpisode:
    loc_raw = data.get("location") or {}
    act_raw = data.get("action")
    src_raw = data.get("source") or {}
    last_recalled = data.get("last_recalled_at")
    return SubjectiveEpisode(
        episode_id=str(data["episode_id"]),
        player_id=int(data["player_id"]),
        occurred_at=_iso_to_dt(str(data["occurred_at"])),
        game_time_label=data.get("game_time_label"),
        source=EpisodeSource(
            event_ids=tuple(str(x) for x in src_raw.get("event_ids", ()))
        ),
        location=EpisodeLocation(
            spot_id=loc_raw.get("spot_id"),
            tile_area_ids=tuple(int(x) for x in loc_raw.get("tile_area_ids", ())),
            sub_location_id=loc_raw.get("sub_location_id"),
            x=loc_raw.get("x"),
            y=loc_raw.get("y"),
            z=loc_raw.get("z"),
        ),
        action=None
        if act_raw is None
        else EpisodeAction(
            tool_name=str(act_raw["tool_name"]),
            canonical_arguments_text=act_raw.get("canonical_arguments_text"),
        ),
        who=tuple(str(x) for x in data.get("who", ())),
        what=str(data["what"]),
        why=data.get("why"),
        observed=str(data["observed"]),
        expected=data.get("expected"),
        outcome=str(data["outcome"]),
        prediction_error=data.get("prediction_error"),
        felt=data.get("felt"),
        interpreted=data.get("interpreted"),
        cues=tuple(
            EpisodicCue(
                axis=str(c["axis"]),
                value=str(c["value"]),
                source=EpisodicCueSource(str(c["source"])),
            )
            for c in data.get("cues", ())
        ),
        recall_text=data.get("recall_text"),
        recall_count=int(data.get("recall_count", 0)),
        last_recalled_at=_iso_to_dt(str(last_recalled)) if last_recalled else None,
    )


# ── PR-G: Recall Layer (Slot / Afterglow / Habituation) codec ──
# 想起階層 (PR #580 / #588 / #526 段階 2) の per-Being 状態を snapshot に乗せる
# ための VO ↔ dict 変換。slot cooldown と habituation は (episode_id, tick) の
# ペアなので共通の codec を使う。


def recall_slot_entry_to_dict(entry: RecallSlotEntry) -> dict[str, Any]:
    """RecallSlotEntry → dict。"""
    return {
        "episode_id": entry.episode_id,
        "entered_tick": entry.entered_tick,
    }


def dict_to_recall_slot_entry(data: dict[str, Any]) -> RecallSlotEntry:
    """dict → RecallSlotEntry。"""
    from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
        RecallSlotEntry,
    )
    return RecallSlotEntry(
        episode_id=str(data["episode_id"]),
        entered_tick=int(data["entered_tick"]),
    )


def afterglow_entry_to_dict(entry: AfterglowEntry) -> dict[str, Any]:
    """AfterglowEntry → dict。``source`` は AfterglowSource.value (= 文字列)。"""
    return {
        "episode_id": entry.episode_id,
        "heading": entry.heading,
        "entered_tick": entry.entered_tick,
        "source": entry.source.value,
    }


def dict_to_afterglow_entry(data: dict[str, Any]) -> AfterglowEntry:
    """dict → AfterglowEntry。未知の source は AfterglowSource(...) が
    ValueError を投げる (= _decode_list で BeingMemoryPayloadFormatError に
    wrap される)。"""
    from ai_rpg_world.application.llm.services.afterglow_store import (
        AfterglowEntry,
        AfterglowSource,
    )
    return AfterglowEntry(
        episode_id=str(data["episode_id"]),
        heading=str(data["heading"]),
        entered_tick=int(data["entered_tick"]),
        source=AfterglowSource(str(data["source"])),
    )


def episode_tick_pair_to_dict(episode_id: str, tick: int) -> dict[str, Any]:
    """(episode_id, tick) → dict。cooldown / habituation で共有する shape。"""
    return {"episode_id": episode_id, "tick": int(tick)}


def dict_to_episode_tick_pair(data: dict[str, Any]) -> tuple[str, int]:
    """dict → (episode_id, tick)。"""
    return (str(data["episode_id"]), int(data["tick"]))
