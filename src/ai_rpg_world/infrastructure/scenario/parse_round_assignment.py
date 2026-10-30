"""``round_assignment``: 回ごとに、役と初期配置の枠を player に割り当てる (#1514)。

player の id と名前は動かさず、枠だけを並べ替える。Being は人物に結び付いた
まま、回ごとに役と配置だけが変わる。割り当ては読み込みの最初に生の JSON へ
書き込むので、その後の読み込みと検証は割り当て後の player に対して走る。
"""

from __future__ import annotations

import copy
import random
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError
from ai_rpg_world.infrastructure.scenario.parse_helpers import reject_unknown_keys

_SLOT_KEYS = ("spawn_spot", "initial_state")


@dataclass(frozen=True)
class RoundSlotAssignment:
    player_string_id: str
    group_index: int
    slot_index: int
    spawn_spot: str | None
    initial_state: Mapping[str, Any]


def apply_round_assignment(
    raw: Mapping[str, Any],
    *,
    random_seed: int | None,
    round_number: int,
) -> tuple[dict[str, Any], tuple[RoundSlotAssignment, ...]]:
    if isinstance(round_number, bool) or not isinstance(round_number, int) or round_number < 1:
        raise ScenarioLoadError(f"回の番号は正の整数にしてください: {round_number!r}")
    if "round_assignment" not in raw:
        return dict(raw), ()
    groups = _parse_groups(raw["round_assignment"], raw.get("players", []))
    if random_seed is None:
        raise ScenarioLoadError("round_assignment の割り当てを再現するには SCENARIO_RANDOM_SEED が要ります")
    rng = random.Random(f"round_assignment:{random_seed}:{round_number}")
    assigned_raw = dict(raw)
    players = [copy.deepcopy(p) for p in raw.get("players", [])]
    by_id: dict[str, dict[str, Any]] = {p["id"]: p for p in players if isinstance(p, dict) and "id" in p}
    assignments: list[RoundSlotAssignment] = []
    for group_index, (player_ids, slots) in enumerate(groups):
        order = rng.sample(range(len(slots)), len(slots))
        for player_id, slot_index in zip(player_ids, order):
            slot = slots[slot_index]
            player = by_id[player_id]
            if "spawn_spot" in slot:
                player["spawn_spot"] = slot["spawn_spot"]
            declared_state = player.get("initial_state", {})
            if isinstance(declared_state, Mapping):
                player["initial_state"] = {**declared_state, **slot.get("initial_state", {})}
            assignments.append(
                RoundSlotAssignment(
                    player_string_id=player_id,
                    group_index=group_index,
                    slot_index=slot_index,
                    spawn_spot=player.get("spawn_spot"),
                    initial_state=dict(player.get("initial_state", {})),
                )
            )
    assigned_raw["players"] = players
    return assigned_raw, tuple(assignments)


def _parse_groups(raw: Any, players_raw: Any) -> list[tuple[list[str], list[Mapping[str, Any]]]]:
    if not isinstance(raw, Mapping):
        raise ScenarioLoadError("round_assignment は object で書いてください")
    reject_unknown_keys(raw, ("groups",), where="round_assignment")
    groups_raw = raw.get("groups")
    if not isinstance(groups_raw, list) or not groups_raw:
        raise ScenarioLoadError("round_assignment.groups は 1 つ以上の group の配列で書いてください")
    if not isinstance(players_raw, list):
        raise ScenarioLoadError("round_assignment を使うには players を配列で書いてください")
    declared_ids = [p.get("id") for p in players_raw if isinstance(p, Mapping)]
    duplicated = sorted({i for i in declared_ids if isinstance(i, str) and declared_ids.count(i) > 1})
    if duplicated:
        raise ScenarioLoadError(f"round_assignment を使うには player の id を重複させないでください: {duplicated}")
    known_players = set(declared_ids)
    seen: set[str] = set()
    groups: list[tuple[list[str], list[Mapping[str, Any]]]] = []
    for index, group in enumerate(groups_raw):
        where = f"round_assignment.groups[{index}]"
        if not isinstance(group, Mapping):
            raise ScenarioLoadError(f"{where} は object で書いてください")
        reject_unknown_keys(group, ("players", "slots"), where=where)
        player_ids = group.get("players")
        slots = group.get("slots")
        if not isinstance(player_ids, list) or not all(isinstance(p, str) for p in player_ids):
            raise ScenarioLoadError(f"{where}.players は player id の配列で書いてください")
        if not isinstance(slots, list) or len(slots) != len(player_ids) or not slots:
            raise ScenarioLoadError(
                f"{where} の枠の数 ({len(slots) if isinstance(slots, list) else slots!r}) を"
                f" player の数 ({len(player_ids)}) と同じにしてください"
            )
        for player_id in player_ids:
            if player_id not in known_players:
                raise ScenarioLoadError(f"{where}.players に知らない player があります: {player_id}")
            if player_id in seen:
                raise ScenarioLoadError(f"round_assignment で player が 2 度割り当てられています: {player_id}")
            seen.add(player_id)
        for slot_index, slot in enumerate(slots):
            _validate_slot(slot, where=f"{where}.slots[{slot_index}]")
        groups.append((player_ids, slots))
    return groups


def _validate_slot(slot: Any, *, where: str) -> None:
    if not isinstance(slot, Mapping):
        raise ScenarioLoadError(f"{where} は object で書いてください")
    reject_unknown_keys(slot, _SLOT_KEYS, where=where)
    if not slot:
        raise ScenarioLoadError(f"{where} に spawn_spot か initial_state を書いてください")
    if "spawn_spot" in slot and not isinstance(slot["spawn_spot"], str):
        raise ScenarioLoadError(f"{where}.spawn_spot は場所の id で書いてください")
    if "initial_state" in slot:
        state = slot["initial_state"]
        if not isinstance(state, Mapping):
            raise ScenarioLoadError(f"{where}.initial_state は object で書いてください")
        for key, value in state.items():
            if not isinstance(key, str) or not isinstance(value, (str, int, float, bool, type(None))):
                raise ScenarioLoadError(
                    f"{where}.initial_state.{key} は文字列のキーと、文字列・数・真偽値・null の値で書いてください"
                )


__all__ = ["RoundSlotAssignment", "apply_round_assignment"]
