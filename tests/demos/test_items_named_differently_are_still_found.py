"""廃坑の山村で懐を探るとき、品名が正式な名前と少し違っても相手の持ち物に当たり、当てられないときも「持っていない」と言い切らないことを保証する。

Issue #1641。mine_v1_008_r2 では「起動鍵」と書いた懐探りが 14 回「相手はそれを持っていない」と
断られ、鍵を持つミオが嘘つき扱いされた。設計は docs/design_decisions.md の D1641。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.common.exceptions import ApplicationException
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_graph.target_item_name_resolution import ItemNameRescueAnswer
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import InteractionNotAllowedException
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "mine_village_v1.json"
_HARU, _MIO, _GEN = PlayerId(1), PlayerId(2), PlayerId(3)
_REFUSED = (ApplicationException, InteractionNotAllowedException)


class _Recorder:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(self, kind: str, *, tick=None, player_id=None, **payload: Any) -> None:
        self.events.append({"kind": kind, "tick": tick, "player_id": player_id, **payload})

    def of(self, kind: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["kind"] == kind]


class _Rescue:
    def __init__(self, chosen: str | None, *, accepted: bool) -> None:
        self.chosen, self.accepted = chosen, accepted
        self.calls: list[str] = []

    def rescue(self, written: str, *, candidates: Mapping[str, str], action_name: str) -> ItemNameRescueAnswer:
        self.calls.append(written)
        return ItemNameRescueAnswer(
            chosen=self.chosen, accepted=self.accepted, confident_no_match=False,
            payload={"chosen": self.chosen, "accepted": self.accepted},
        )


@pytest.fixture()
def runtime():
    rt = create_world_runtime(_SCENARIO)
    for pid in (_MIO, _GEN):
        _place(rt, pid, "village_square")
    _give(rt, _MIO, "lift_key")
    return rt


def _place(rt, pid: PlayerId, spot: str) -> None:
    graph = rt._spot_graph_repo.find_graph()
    entity = EntityId.create(int(pid))
    graph.unplace_entity(entity)
    graph.place_entity(entity, SpotId.create(rt.id_mapper.get_int("spot", spot)))
    rt._spot_graph_repo.save(graph)


def _give(rt, pid: PlayerId, item: str) -> None:
    grant_item_specs_to_inventory(
        pid, (ItemSpecId(rt.id_mapper.get_int("item_spec", item)),),
        rt._item_repo, rt._item_spec_repo, rt._player_inventory_repo, overflow_sink=IGNORE_OVERFLOW,
    )


def _owns(rt, pid: PlayerId, item: str) -> bool:
    spec = rt.id_mapper.get_int("item_spec", item)
    owned = collect_owned_item_spec_ids_from_inventory(rt._player_inventory_repo.find_by_id(pid), rt._item_repo)
    return any(int(s.value) == spec for s in owned)


def _pickpocket(rt, item: str, target: PlayerId = _MIO) -> tuple[bool, str]:
    try:
        result = rt.do_interact_with_player(_GEN, target, "pickpocket", interaction_parameters={"item": item})
    except _REFUSED as exc:
        return False, str(exc)
    return True, "\n".join(result.messages)


class TestAPartOfTheName:
    """名前の一部で指したとき。"""

    def test_part_of_the_official_name_takes_that_item(self, runtime) -> None:
        """ミオが「昇降機の起動鍵」を持つとき、ゲンが「起動鍵」と書いて懐を探ると、その鍵がゲンに移る。"""
        done, message = _pickpocket(runtime, "起動鍵")

        assert done, message
        assert (_owns(runtime, _MIO, "lift_key"), _owns(runtime, _GEN, "lift_key")) == (False, True)

    def test_the_actor_is_told_which_item_the_name_was_read_as(self, runtime) -> None:
        """読み替えて奪えたときは、結果文の先頭で「起動鍵」を「昇降機の起動鍵」と解釈したと本人に伝える。"""
        _, message = _pickpocket(runtime, "起動鍵")

        assert message.startswith("「起動鍵」は「昇降機の起動鍵」と解釈した。")

    def test_the_rename_is_traced(self, runtime) -> None:
        """読み替えたときは、どの名前をどの品に当てたかが trace に 1 件残る。"""
        recorder = _Recorder()
        runtime.set_trace_recorder(recorder)

        _pickpocket(runtime, "起動鍵")

        [event] = recorder.of(TraceEventKind.ITEM_NAME_RESOLUTION)
        assert (event["player_id"], event["action_name"], event["target_player_id"]) == (int(_GEN), "pickpocket", int(_MIO))
        assert (event["written"], event["resolved_name"], event["method"], event["outcome"]) == (
            "起動鍵", "昇降機の起動鍵", "partial", "resolved",
        )

    def test_the_official_name_leaves_no_rename_trace(self, runtime) -> None:
        """正式な名前で奪ったときは、読み替えの trace を残さない。"""
        recorder = _Recorder()
        runtime.set_trace_recorder(recorder)

        done, _ = _pickpocket(runtime, "昇降機の起動鍵")

        assert done
        assert recorder.of(TraceEventKind.ITEM_NAME_RESOLUTION) == []

    def test_a_name_that_fits_two_items_takes_nothing(self, runtime) -> None:
        """「缶」が「燃料の缶」と「燃料が少し残った缶」の両方に当てはまるとき、どちらも奪わない。"""
        _give(runtime, _MIO, "fuel_can")
        _give(runtime, _MIO, "small_fuel_can")

        done, message = _pickpocket(runtime, "缶")

        assert not done
        assert "複数" in message
        assert (_owns(runtime, _GEN, "fuel_can"), _owns(runtime, _GEN, "small_fuel_can")) == (False, False)


class TestNothingFits:
    """名前が持ち物のどれにも当たらないとき。"""

    def test_without_a_judge_a_name_fitting_nothing_is_not_owned(self, runtime) -> None:
        """意味の判断が無い世界で、持ち物と重ならない「金槌」は今までどおり「相手はそれを持っていない。」と断られる。"""
        done, message = _pickpocket(runtime, "金槌")

        assert (done, message) == (False, "相手はそれを持っていない。")

    def test_an_unconfident_judgment_does_not_say_they_lack_it(self, runtime) -> None:
        """判断が確信を持てないとき、「鉄の鍵」は断られるが、「持っていない」とは言わず、名前が違うかもしれないと伝える。"""
        runtime.set_target_item_name_rescue(_Rescue("昇降機の起動鍵", accepted=False))

        done, message = _pickpocket(runtime, "鉄の鍵")

        assert not done
        assert "持っていない。" not in message.replace("持っていないとは限らない", "")
        assert "名前" in message
        assert not _owns(runtime, _GEN, "lift_key")

    def test_the_refusal_does_not_reveal_what_they_hold(self, runtime) -> None:
        """見分けられなかったという断りに、相手の持ち物の名前は出ない。"""
        runtime.set_target_item_name_rescue(_Rescue("昇降機の起動鍵", accepted=False))

        _, message = _pickpocket(runtime, "鉄の鍵")

        assert "昇降機の起動鍵" not in message

    def test_an_accepted_judgment_takes_the_chosen_item(self, runtime) -> None:
        """判断が確信をもって「鉄の鍵」を「昇降機の起動鍵」と選べば、その鍵がゲンに移る。"""
        runtime.set_target_item_name_rescue(_Rescue("昇降機の起動鍵", accepted=True))

        done, message = _pickpocket(runtime, "鉄の鍵")

        assert done, message
        assert _owns(runtime, _GEN, "lift_key")

    def test_an_earlier_precondition_still_speaks_first(self, runtime) -> None:
        """籠の中の相手には、名前が見分けられなかったことより先に「手が届かない」と返る。"""
        runtime.set_target_item_name_rescue(_Rescue("昇降機の起動鍵", accepted=False))
        _place(runtime, _MIO, "lift_landing")
        runtime.do_interact(_MIO, "lift", "board_lift")
        _place(runtime, _GEN, "lift_landing")

        done, message = _pickpocket(runtime, "鉄の鍵")

        assert (done, message) == (False, "籠の中の相手には手が届かない。")
