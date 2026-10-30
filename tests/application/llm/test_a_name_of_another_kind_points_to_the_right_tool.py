"""在るのに種類が違う名前を書いたとき、「無い」ではなく「種類が違う」と使うツールを添えて返す。

過去 83 run の interact 失敗 194 件のうち約 70 件が、敵・隣の場所・手持ちの品の名前を
対象に書いたものだった。従来は「候補にありません」と返していたので、当人は「大型カニは
いない」「川の上流は無い」と誤解し、同じ名前を別のツールで試す手を取れなかった。
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    InventoryToolRuntimeTargetDto,
    LlmCommandResultDto,
    MonsterToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    SpotGraphArgumentResolver,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.services.world_llm_turn.tool_dispatch import (
    adapt_executor_handler_with_resolver,
    build_interact_invalid_label_failure,
    build_travel_to_invalid_label_failure,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _context() -> ToolRuntimeContextDto:
    """物・敵・隣の場所・区画・人・手持ちの品・足元の品が 1 件ずつある場所。"""
    return ToolRuntimeContextDto(
        targets={
            "O1": ToolRuntimeTargetDto(
                label="O1",
                kind="spot_graph_object",
                display_name="貝の岩棚",
                world_object_id=11,
                available_interactions=("harvest",),
                interaction_labels=(("harvest", "貝を採る"),),
            ),
            "M1": MonsterToolRuntimeTargetDto(
                label="M1",
                kind="spot_graph_monster",
                display_name="大型カニ",
                world_object_id=31,
                monster_id=5,
            ),
            "S1": DestinationToolRuntimeTargetDto(
                label="S1",
                kind="spot_graph_destination",
                display_name="川の上流",
                spot_id=7,
            ),
            "SL1": ToolRuntimeTargetDto(
                label="SL1",
                kind="spot_graph_sub_location",
                display_name="焚き火跡",
                sub_location_id=2,
            ),
            "P1": PlayerToolRuntimeTargetDto(
                label="P1",
                kind="spot_graph_player",
                display_name="リン",
                player_id=2,
            ),
            "I1": InventoryToolRuntimeTargetDto(
                label="I1",
                kind="inventory_item",
                display_name="貝",
                item_instance_id=41,
            ),
            "G1": InventoryToolRuntimeTargetDto(
                label="G1",
                kind="ground_item",
                display_name="流木",
                real_item_instance_id=51,
            ),
        }
    )


def _fail(tool: str, args: dict[str, Any]) -> ToolArgumentResolutionException:
    with pytest.raises(ToolArgumentResolutionException) as caught:
        SpotGraphArgumentResolver().resolve_args(tool, {**args, "inner_thought": ""}, _context())
    return caught.value


class TestInteractIsToldWhichToolTheNameBelongsTo:
    def test_a_monster_name_points_to_attack(self) -> None:
        """敵の名前を interact の対象に書くと、種類違いとして attack を案内し、候補一覧も付く。"""
        exc = _fail("interact", {"target_label": "大型カニ", "action_name": "harvest"})

        assert exc.error_code == "INVALID_TARGET_KIND"
        assert "「大型カニ」はこの場所の敵で、対象の名前には使えません。" in str(exc)
        assert "attack" in str(exc)
        assert "有効な対象の名前: 貝の岩棚 / リン / 貝" in str(exc)

    def test_a_destination_name_points_to_travel_to(self) -> None:
        """隣の場所の名前を interact の対象に書くと、travel_to を案内する。"""
        exc = _fail("interact", {"target_label": "川の上流", "action_name": "harvest"})

        assert exc.error_code == "INVALID_TARGET_KIND"
        assert "隣の場所" in str(exc)
        assert "travel_to" in str(exc)

    def test_a_name_nowhere_in_the_world_is_still_not_found(self) -> None:
        """どの種別にも無い名前は従来どおり INVALID_TARGET_LABEL で、候補一覧が付く (正の対照)。"""
        exc = _fail("interact", {"target_label": "大樫の樹", "action_name": "harvest"})

        assert exc.error_code == "INVALID_TARGET_LABEL"
        assert "現在の候補にありません: 大樫の樹" in str(exc)
        assert "貝の岩棚" in str(exc)


class TestOnlyToolsOfThisWorldAreAdvised:
    def test_a_disabled_tool_is_not_advertised_but_the_kind_still_is(self) -> None:
        """シナリオが attack を無効化した世界では、敵だとは伝えるが attack は勧めない。"""
        resolver = SpotGraphArgumentResolver(tool_is_exposed=lambda tool: tool != "attack")

        with pytest.raises(ToolArgumentResolutionException) as caught:
            resolver.resolve_args(
                "interact", {"target_label": "大型カニ", "action_name": "harvest", "inner_thought": ""}, _context()
            )

        assert "この場所の敵" in str(caught.value)
        assert "attack" not in str(caught.value)

    def test_without_an_exposure_answer_every_tool_is_advised(self) -> None:
        """露出判断を注入しない最小配線では、従来どおり全ツールを在るものとして案内する (正の対照)。"""
        exc = _fail("interact", {"target_label": "大型カニ", "action_name": "harvest"})

        assert "attack" in str(exc)


class TestItemToolsAreToldWhichToolTheNameBelongsTo:
    def test_pickup_of_a_held_item_says_it_is_already_held(self) -> None:
        """手持ちの品を拾おうとすると、すでに持っていると伝える。"""
        exc = _fail("pickup_item", {"ground_item_label": "貝"})

        assert exc.error_code == "INVALID_TARGET_KIND"
        assert "「貝」は手持ちの品で、拾うものの名前には使えません。" in str(exc)
        assert "すでに持っている" in str(exc)

    def test_pickup_of_a_harvestable_object_points_to_interact(self) -> None:
        """採る物 (岩棚) を拾おうとすると、interact を案内する。"""
        exc = _fail("pickup_item", {"ground_item_label": "貝の岩棚"})

        assert exc.error_code == "INVALID_TARGET_KIND"
        assert "interact" in str(exc)

    def test_use_of_a_ground_item_points_to_pickup(self) -> None:
        """足元の品を使おうとすると、pickup_item を案内する。"""
        exc = _fail("use_item", {"item_label": "流木"})

        assert exc.error_code == "INVALID_TARGET_KIND"
        assert "足元の品" in str(exc)
        assert "pickup_item" in str(exc)

    def test_giving_to_an_item_name_points_out_it_is_not_a_person(self) -> None:
        """渡す相手に品の名前を書くと、その entry は種類違いで失敗し理由が残る。"""
        out = SpotGraphArgumentResolver().resolve_args(
            "give_item",
            {"gives": [{"item_label": "貝", "target_player_label": "流木"}], "inner_thought": ""},
            _context(),
        )

        entry = out["gives_resolved"][0]
        assert entry["error_code"] == "INVALID_TARGET_KIND"
        assert "「流木」は足元の品で、相手の名前には使えません。" in entry["message"]


class TestTravelToIsToldWhichToolTheNameBelongsTo:
    def test_a_sub_location_name_points_to_set_sub_location(self) -> None:
        """区画の名前を行き先に書くと、set_sub_location を案内する。"""
        exc = _fail("travel_to", {"destination_label": "焚き火跡"})

        assert exc.error_code == "INVALID_DESTINATION_KIND"
        assert "「焚き火跡」はこの場所の区画で、接続先名には使えません。" in str(exc)
        assert "set_sub_location" in str(exc)
        assert "有効な接続先: 川の上流" in str(exc)


class TestTheDispatchBuildersKeepTheExplanation:
    """interact と travel_to は専用の失敗組み立てを持つ。そこで文面を捨てないこと。"""

    def test_interact_builder_passes_the_wrong_kind_message_through(self) -> None:
        exc = _fail("interact", {"target_label": "大型カニ", "action_name": "harvest"})

        result = build_interact_invalid_label_failure(_context(), {"target_label": "大型カニ"}, exc)

        assert result.success is False
        assert result.error_code == "INVALID_TARGET_KIND"
        assert "attack" in result.message

    def test_travel_to_builder_passes_the_wrong_kind_message_through(self) -> None:
        exc = _fail("travel_to", {"destination_label": "焚き火跡"})

        result = build_travel_to_invalid_label_failure(_context(), {"destination_label": "焚き火跡"}, exc)

        assert result.error_code == "INVALID_DESTINATION_KIND"
        assert "set_sub_location" in result.message

    def test_interact_builder_still_owns_the_not_found_message(self) -> None:
        """どこにも無い名前の文面は従来どおり builder が組む (正の対照)。"""
        exc = _fail("interact", {"target_label": "大樫の樹", "action_name": "harvest"})

        result = build_interact_invalid_label_failure(_context(), {"target_label": "大樫の樹"}, exc)

        assert result.error_code == "INVALID_TARGET_LABEL"
        assert result.message.startswith("対象の名前が見つかりません: 大樫の樹")

    def test_the_explanation_reaches_the_agent_through_the_adapted_handler(self) -> None:
        """配線を通しても、当人に届く結果文に使うツールの案内が残る。"""

        def raw(_pid: int, _resolved: dict[str, Any], _ctx: Any) -> LlmCommandResultDto:
            raise AssertionError("resolver must fail before the executor runs")

        handler = adapt_executor_handler_with_resolver(
            raw,
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            SpotGraphArgumentResolver(),
            invalid_label_failure_builder=build_interact_invalid_label_failure,
        )
        result = handler(PlayerId(3), {"target_label": "川の上流", "action_name": "harvest"}, _context())

        assert result.success is False
        assert "travel_to" in result.message

        handler = adapt_executor_handler_with_resolver(
            raw,
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            SpotGraphArgumentResolver(),
            invalid_label_failure_builder=build_travel_to_invalid_label_failure,
        )
        result = handler(PlayerId(3), {"destination_label": "大型カニ"}, _context())

        assert "attack" in result.message
