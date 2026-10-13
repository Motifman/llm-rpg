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
    from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
        BeliefEvidence,
    )

from ai_rpg_world.being.domain.acquaintance import Acquaintance, HowKnown
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex, IndexRevision
from ai_rpg_world.being.domain.memo_book import (
    Memo,
    MemoCertainty,
    MemoKind,
    MemoProvenance,
    MemoSource,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.common.exception import DomainException
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
        "being_id": entry.being_id.value,
        "text": entry.text,
        "evidence_episode_ids": list(entry.evidence_episode_ids),
        "confidence": entry.confidence,
        "created_at": _dt_to_iso(entry.created_at),
        "importance_score": entry.importance_score,
        "tags": list(entry.tags),
        # U3a (belief journal 化)。
        "belief_id": entry.belief_id,
        "status": entry.status,
        "supersedes": entry.supersedes,
        "support_evidence_ids": list(entry.support_evidence_ids),
        "contradict_evidence_ids": list(entry.contradict_evidence_ids),
        # P3b: CONFIRMATION 支持の内数。siblings (support/contradict) が
        # snapshot round-trip される以上、これも round-trip しないと resume 後に
        # 0 に戻り、以後の strengthen/contradict で CONFIRMATION 支持を通常支持
        # として過大評価してしまう (confidence の再膨張)。
        "confirmation_support_count": entry.confirmation_support_count,
        # P10: HEARSAY 支持の内数。confirmation 同様 sibling が round-trip される
        # 以上これも往復しないと resume 後に 0 に戻り、以後の strengthen/contradict
        # で伝聞支持を直接体験として過大評価する (confidence の再膨張)。
        "hearsay_support_count": entry.hearsay_support_count,
        "last_observed_turn": entry.last_observed_turn,
    }


def dict_to_semantic_entry(
    data: dict[str, Any],
    *,
    fallback_being_id: BeingId | None = None,
) -> SemanticMemoryEntry:
    # U3a: 旧 snapshot (belief journal キー無し) は default に倒す。
    # belief_id は空文字→ SemanticMemoryEntry.__post_init__ が entry_id に
    # フォールバックする。
    raw_being_id = data.get("being_id")
    if raw_being_id is not None:
        parsed = BeingId(str(raw_being_id))
        if fallback_being_id is not None and parsed != fallback_being_id:
            raise ValueError(
                "semantic entry being_id does not match snapshot being"
            )
        being_id = parsed
    elif fallback_being_id is not None:
        being_id = fallback_being_id
    else:
        raise ValueError("being_id is required to decode SemanticMemoryEntry")
    supersedes = data.get("supersedes")
    return SemanticMemoryEntry(
        entry_id=str(data["entry_id"]),
        player_id=int(data["player_id"]),
        being_id=being_id,
        text=str(data["text"]),
        evidence_episode_ids=tuple(
            str(x) for x in data.get("evidence_episode_ids", ())
        ),
        confidence=float(data["confidence"]),
        created_at=_iso_to_dt(str(data["created_at"])),
        importance_score=int(data.get("importance_score", 5)),
        tags=tuple(str(x) for x in data.get("tags", ())),
        belief_id=str(data.get("belief_id") or ""),
        status=str(data.get("status", "active")),
        supersedes=str(supersedes) if supersedes else None,
        support_evidence_ids=tuple(
            str(x) for x in data.get("support_evidence_ids", ())
        ),
        contradict_evidence_ids=tuple(
            str(x) for x in data.get("contradict_evidence_ids", ())
        ),
        # P3b: 旧 snapshot (このキー無し) は 0 に倒す (VO 既定と一致)。
        confirmation_support_count=int(data.get("confirmation_support_count", 0)),
        # P10: 旧 snapshot (このキー無し) は 0 に倒す (VO 既定と一致)。
        hearsay_support_count=int(data.get("hearsay_support_count", 0)),
        # #1452: キーが無ければ観測のターン数が分からない信念として戻す。
        last_observed_turn=(
            int(data["last_observed_turn"])
            if data.get("last_observed_turn") is not None
            else None
        ),
    )


# ---- memory_link --------------------------------------------------------------

def memory_link_to_dict(link: MemoryLink) -> dict[str, Any]:
    return {
        "link_id": link.link_id,
        "player_id": link.player_id,
        "being_id": link.being_id.value,
        "episode_id_a": link.episode_id_a,
        "episode_id_b": link.episode_id_b,
        "link_type": link.link_type.value,
        "strength": link.strength,
        "co_activation_count": link.co_activation_count,
        "created_at": _dt_to_iso(link.created_at),
        "last_activated_at": _dt_to_iso(link.last_activated_at),
        "decay_rate": link.decay_rate,
    }


def dict_to_memory_link(
    data: dict[str, Any],
    *,
    fallback_being_id: BeingId | None = None,
) -> MemoryLink:
    raw_being_id = data.get("being_id")
    if raw_being_id is not None:
        parsed = BeingId(str(raw_being_id))
        if fallback_being_id is not None and parsed != fallback_being_id:
            raise ValueError(
                "memory link being_id does not match snapshot being"
            )
        being_id = parsed
    elif fallback_being_id is not None:
        being_id = fallback_being_id
    else:
        raise ValueError("being_id is required to decode MemoryLink")
    return MemoryLink(
        link_id=str(data["link_id"]),
        player_id=int(data["player_id"]),
        being_id=being_id,
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
    )


# ---- reinterpretation_journal -------------------------------------------------

def reinterpretation_entry_to_dict(
    entry: EpisodicReinterpretationEntry,
) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "player_id": entry.player_id,
        "being_id": entry.being_id.value,
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
    *,
    fallback_being_id: BeingId | None = None,
) -> EpisodicReinterpretationEntry:
    raw_being_id = data.get("being_id")
    if raw_being_id is not None:
        parsed = BeingId(str(raw_being_id))
        if fallback_being_id is not None and parsed != fallback_being_id:
            raise ValueError(
                "reinterpretation entry being_id does not match snapshot being"
            )
        being_id = parsed
    elif fallback_being_id is not None:
        being_id = fallback_being_id
    else:
        raise ValueError("being_id is required to decode EpisodicReinterpretationEntry")
    superseded = data.get("superseded_at")
    return EpisodicReinterpretationEntry(
        entry_id=str(data["entry_id"]),
        player_id=int(data["player_id"]),
        being_id=being_id,
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
        "being_id": ep.being_id.value,
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
        # PR-M (約束清算の共在ゲート誤棄却の修正): co_present (= chunk 時点で
        # 同席していた他プレイヤー名。エンジン由来の確定事実) を snapshot に
        # 乗せ、長走実験の終了 → 再開で共在情報が静かに失われないようにする。
        "co_present": list(ep.co_present),
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
        # U6 (予測誤差統一設計 / salience): 常に "low"/"high" のどちらかを
        # 持つ必須フィールド。旧 snapshot には無いので decode 側は
        # data.get("salience", "low") で後方互換する。
        "salience": ep.salience,
    }


def dict_to_subjective_episode(
    data: dict[str, Any],
    *,
    fallback_being_id: BeingId | None = None,
) -> SubjectiveEpisode:
    loc_raw = data.get("location") or {}
    act_raw = data.get("action")
    src_raw = data.get("source") or {}
    last_recalled = data.get("last_recalled_at")
    raw_being_id = data.get("being_id")
    if raw_being_id is not None:
        parsed = BeingId(str(raw_being_id))
        if fallback_being_id is not None and parsed != fallback_being_id:
            raise ValueError(
                "subjective episode being_id does not match snapshot being"
            )
        being_id = parsed
    elif fallback_being_id is not None:
        being_id = fallback_being_id
    else:
        raise ValueError("being_id is required to decode SubjectiveEpisode")
    return SubjectiveEpisode(
        episode_id=str(data["episode_id"]),
        player_id=int(data["player_id"]),
        being_id=being_id,
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
        # PR-M: co_present キーが無い旧 snapshot は空タプルにフォールバック
        # (co_present 導入前に保存された episode を壊さない後方互換)。
        co_present=tuple(str(x) for x in data.get("co_present", ())),
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
        # U6: 旧 snapshot (salience キー無し) は "low" に倒す。
        salience=str(data.get("salience", "low")),
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


def episode_hit_count_pair_to_dict(episode_id: str, hit_count: int) -> dict[str, Any]:
    """U9b (予測誤差統一設計 部品5・想起の信用割り当て): (episode_id, hit_count)

    → dict。``episode_tick_pair_to_dict`` と構造は同じだが、hit_count を
    tick フィールド名で表現すると意味を誤読しやすいので専用 key にする。"""
    return {"episode_id": episode_id, "hit_count": int(hit_count)}


def dict_to_episode_hit_count_pair(data: dict[str, Any]) -> tuple[str, int]:
    """dict → (episode_id, hit_count)。"""
    return (str(data["episode_id"]), int(data["hit_count"]))


# ---- belief_evidence (U2: 証拠台帳統一設計) ------------------------------------


def belief_evidence_to_dict(evidence: BeliefEvidence) -> dict[str, Any]:
    return {
        "evidence_id": evidence.evidence_id,
        "source_kind": evidence.source_kind.value,
        "episode_ids": list(evidence.episode_ids),
        "cue_signature": evidence.cue_signature,
        "text": evidence.text,
        "salience": evidence.salience,
        "occurred_at": _dt_to_iso(evidence.occurred_at),
        "observed_turn": evidence.observed_turn,
        "tick": evidence.tick,
        # U4 (予測誤差統一設計 部品3): in-context だった belief_id 群。
        "in_context_belief_ids": list(evidence.in_context_belief_ids),
        # P9 (伝聞): HEARSAY evidence の話者。HEARSAY 以外は None。
        "source_speaker": evidence.source_speaker,
        "what_happened": list(evidence.what_happened),
    }


def dict_to_belief_evidence(data: dict[str, Any]) -> BeliefEvidence:
    """dict → BeliefEvidence。

    未知の source_kind は ``BeliefEvidenceSourceKind(...)`` が ValueError を
    投げる。それ以外の不変条件違反 (salience 不正値など) は BeliefEvidence VO
    が **ドメイン例外** ``BeliefEvidenceValidationException`` を投げるが、
    これは組み込み例外を継承しないため、呼び出し元 ``_decode_list`` の
    ``except (KeyError, ValueError, TypeError)`` に捕まらず契約
    (一律 ``BeingMemoryPayloadFormatError`` に wrap する) を静かに破る。
    そこで本 codec 側でドメイン例外を捕えて ``ValueError`` に翻訳し、
    generic な ``_decode_list`` を semantic ドメイン例外に結合させずに
    既存の except 契約へ自然に収める (U2 レビュー MEDIUM 指摘対応)。
    """
    from ai_rpg_world.domain.memory.semantic.exception.semantic_exception import (
        BeliefEvidenceValidationException,
    )
    from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
        BeliefEvidence,
    )
    from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
        BeliefEvidenceSourceKind,
    )

    try:
        return BeliefEvidence(
            evidence_id=str(data["evidence_id"]),
            source_kind=BeliefEvidenceSourceKind(str(data["source_kind"])),
            episode_ids=tuple(str(x) for x in data.get("episode_ids", ())),
            cue_signature=str(data["cue_signature"]),
            text=str(data["text"]),
            salience=str(data["salience"]),
            occurred_at=_iso_to_dt(str(data["occurred_at"])),
            # #1452: いつ見たかを捏造しないので、キーが無い旧データは読まない。
            observed_turn=data["observed_turn"],
            tick=int(data["tick"]) if data.get("tick") is not None else None,
            # U4: 旧データ (U4 導入前) には無いキーなので .get で空タプルに倒す
            # (= 後方互換。attribution 機構 OFF 時の evidence とも同じ形になる)。
            in_context_belief_ids=tuple(
                str(x) for x in data.get("in_context_belief_ids", ())
            ),
            # P9: 旧データ (P9 導入前) には無いキーなので .get で None に倒す。
            source_speaker=(
                str(data["source_speaker"])
                if data.get("source_speaker") is not None
                else None
            ),
            # #1509: 旧データには無いキー。外れの理由を持たない材料として戻す。
            what_happened=_str_tuple(
                data.get("what_happened", []), name="what_happened"
            ),
        )
    except BeliefEvidenceValidationException as exc:
        raise ValueError(f"invalid BeliefEvidence payload: {exc}") from exc


def _str_tuple(value: Any, *, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{name} must be list[str], got {value!r}")
    return tuple(value)


def acquaintance_to_dict(acquaintance: Acquaintance) -> dict[str, Any]:
    return {
        "environment_name": acquaintance.environment_name,
        "name": acquaintance.name,
        "how_known": acquaintance.how_known.name,
        "known_since_turn": acquaintance.known_since_turn,
        "name_learned_turn": acquaintance.name_learned_turn,
        "relation_note": acquaintance.relation_note,
        "met_count": acquaintance.met_count,
        "first_met_turn": acquaintance.first_met_turn,
        "last_met_turn": acquaintance.last_met_turn,
    }


def dict_to_acquaintance(data: dict[str, Any]) -> Acquaintance:
    return Acquaintance(
        environment_name=data["environment_name"],
        name=data["name"],
        how_known=HowKnown[data["how_known"]],
        known_since_turn=data["known_since_turn"],
        name_learned_turn=data["name_learned_turn"],
        relation_note=data["relation_note"],
        met_count=data["met_count"],
        first_met_turn=data["first_met_turn"],
        last_met_turn=data["last_met_turn"],
    )


def _episode_index_to_dict(index: EpisodeIndex) -> dict[str, Any]:
    return {"summary": index.summary, "recall_when": index.recall_when}


def _dict_to_episode_index(data: dict[str, Any]) -> EpisodeIndex:
    return EpisodeIndex(summary=data["summary"], recall_when=data["recall_when"])


def being_episode_to_dict(episode: Episode) -> dict[str, Any]:
    return {
        "episode_id": episode.episode_id,
        "handle": episode.handle,
        "environment_name": episode.environment_name,
        "written_turn": episode.written_turn,
        "index": _episode_index_to_dict(episode.index),
        "body": episode.body,
        "recall_count": episode.recall_count,
        "last_recalled_turn": episode.last_recalled_turn,
        "index_history": [
            {
                "previous": _episode_index_to_dict(revision.previous),
                "revised_turn": revision.revised_turn,
            }
            for revision in episode.index_history
        ],
    }


def dict_to_being_episode(data: dict[str, Any]) -> Episode:
    """呼び名は ID から作り直さない。伸ばした呼び名が 6 文字に戻ると、前の呼び名が別の記録を指す。"""
    try:
        return Episode(
            episode_id=data["episode_id"],
            handle=data["handle"],
            environment_name=data["environment_name"],
            written_turn=data["written_turn"],
            index=_dict_to_episode_index(data["index"]),
            body=data["body"],
            recall_count=data["recall_count"],
            last_recalled_turn=data["last_recalled_turn"],
            index_history=tuple(
                IndexRevision(
                    previous=_dict_to_episode_index(revision["previous"]),
                    revised_turn=revision["revised_turn"],
                )
                for revision in data["index_history"]
            ),
        )
    except DomainException as exc:
        raise ValueError(f"invalid being episode payload: {exc}") from exc


def being_memo_to_dict(memo: Memo) -> dict[str, Any]:
    provenance = memo.provenance
    return {
        "memo_id": memo.memo_id,
        "handle": memo.handle,
        "kind": memo.kind.value,
        "text": memo.text,
        "provenance": None
        if provenance is None
        else {
            "source": provenance.source.value,
            "certainty": provenance.certainty.value,
            "source_from": provenance.source_from,
        },
        "written_turn": memo.written_turn,
        "edited_turn": memo.edited_turn,
        "environment_name": memo.environment_name,
    }


def dict_to_being_memo(data: dict[str, Any]) -> Memo:
    """呼び名は ID から作り直さない (エピソードと同じ理由)。"""
    try:
        provenance = data["provenance"]
        return Memo(
            memo_id=data["memo_id"],
            handle=data["handle"],
            kind=MemoKind(data["kind"]),
            text=data["text"],
            provenance=None
            if provenance is None
            else MemoProvenance(
                source=MemoSource(provenance["source"]),
                certainty=MemoCertainty(provenance["certainty"]),
                source_from=provenance["source_from"],
            ),
            written_turn=data["written_turn"],
            edited_turn=data["edited_turn"],
            environment_name=data["environment_name"],
        )
    except DomainException as exc:
        raise ValueError(f"invalid being memo payload: {exc}") from exc
