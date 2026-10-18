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
from typing import Any

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
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
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
