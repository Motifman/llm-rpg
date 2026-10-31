"""``BeingSnapshot`` と JSON 互換の dict の変換。ファイルと SQLite が同じ形で保存する (design_decisions D1469-1)。"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.domain.being.exception.being_exceptions import BeingSnapshotIncompleteException
from ai_rpg_world.domain.being.value_object.being_snapshot import BeingSnapshot


def snapshot_to_dict(snapshot: BeingSnapshot) -> dict[str, Any]:
    """``BeingSnapshot`` を JSON 互換 dict に変換する。ファイルと SQLite の両方がこの形で保存する。"""
    if not isinstance(snapshot, BeingSnapshot):
        raise TypeError(f"snapshot must be BeingSnapshot, got {type(snapshot).__name__}")
    persona = snapshot.persona
    return {
        "being_id_value": snapshot.being_id_value,
        "persona": {
            "name": persona.name,
            "first_person": persona.first_person,
            "speech": persona.speech,
            "traits": list(persona.traits),
            "values": list(persona.values),
            "fears": list(persona.fears),
            "background": persona.background,
        },
        "attachment_world_id": snapshot.attachment_world_id,
        "attachment_player_id": snapshot.attachment_player_id,
        "snapshot_version": snapshot.snapshot_version,
        "memory_payload_json": snapshot.memory_payload_json,
    }


def _list_of(data: dict[str, Any], key: str) -> tuple[Any, ...]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise BeingSnapshotIncompleteException(f"{key} must be list, got {type(value).__name__}")
    return tuple(value)


def _persona_from(data: dict[str, Any]) -> Persona:
    """``persona`` が無い古い snapshot は、``identity_name`` と ``identity_first_person`` から名前と一人称だけを読む。

    後から足したキーが無いときと同じく、ほかの人柄は決まっていないものとして読む (design_decisions D1469-1)。
    """
    raw = data.get("persona")
    if raw is None:
        return Persona(name=data["identity_name"], first_person=data["identity_first_person"])
    if not isinstance(raw, dict):
        raise BeingSnapshotIncompleteException(f"persona must be dict, got {type(raw).__name__}")
    return Persona(
        name=raw["name"],
        first_person=raw.get("first_person"),
        speech=raw.get("speech"),
        traits=_list_of(raw, "traits"),
        values=_list_of(raw, "values"),
        fears=_list_of(raw, "fears"),
        background=raw.get("background"),
    )


def dict_to_snapshot(data: dict[str, Any]) -> BeingSnapshot:
    """JSON 由来 dict から ``BeingSnapshot`` を再構築する。

    ``snapshot_version`` が無い行は最古の版 (1) として読む。古い snapshot の ``declared_memory_kinds`` は、
    読み捨てた件数を数えるためだけに ``legacy_declared_memory_kinds`` へ移す。
    """
    if not isinstance(data, dict):
        raise BeingSnapshotIncompleteException(f"data must be dict, got {type(data).__name__}")
    return BeingSnapshot(
        being_id_value=data["being_id_value"],
        persona=_persona_from(data),
        attachment_world_id=data.get("attachment_world_id"),
        attachment_player_id=data.get("attachment_player_id"),
        snapshot_version=data.get("snapshot_version", 1),
        memory_payload_json=data.get("memory_payload_json"),
        legacy_declared_memory_kinds=_list_of(data, "declared_memory_kinds"),
    )


__all__ = ["dict_to_snapshot", "snapshot_to_dict"]
