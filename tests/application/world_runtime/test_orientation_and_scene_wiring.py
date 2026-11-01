"""シナリオの runtime が、入るときの案内 (Orientation) と今見えている場面 (Scene) を詰めて渡し、
プロンプトをそこから組むことを保証する (design_decisions D1630、D1630-2)。"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.description_text import description_text, descriptions_text
from ai_rpg_world.application.llm.services.dynamic_argument_candidates import inject_dynamic_argument_candidate_table
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.being.contract import Scene
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_STATION_DRILL = Path(__file__).resolve().parents[3] / "data" / "scenarios" / "station_drill.json"


@pytest.fixture
def runtime(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.CRITICAL)
    return create_world_runtime(_STATION_DRILL)


class TestOrientation:
    """プレイヤーごとの案内と、システムプロンプトとの関係を保証する。"""

    def test_orientation_holds_persona_premise_and_briefing_in_order(self, runtime) -> None:
        """station_drill の案内は、世界の前提・概要の見出し・見取り図の 3 節・この世界の決まり・人柄の順に並ぶ。"""
        orientation = runtime.orientation_for(PlayerId(1))

        assert [d.heading for d in orientation.descriptions] == [
            "世界の前提",
            "このゲームについて",
            "この場所の造り",
            "点検の割り当て",
            "話し合いと投票の決まり",
            "この世界の決まり",
            "ペルソナ",
        ]

    def test_system_prompt_is_built_from_the_orientation(self, runtime) -> None:
        """システムプロンプトは、冒頭の一文、作法、案内をそのまま文にしたもの、課された目的の順に並ぶ。"""
        orientation = runtime.orientation_for(PlayerId(1))

        expected_head = (
            "あなたは【ペルソナ】に書かれた人物として行動するキャラクターである。\n\n"
            + runtime.conduct_text()
            + "\n\n"
            + descriptions_text(orientation.descriptions)
        )
        assert runtime.build_system_prompt(PlayerId(1)).startswith(expected_head + "\n\n【現在の目的】\n")

    def test_player_not_in_the_scenario_has_no_orientation(self, runtime) -> None:
        """シナリオに居ないプレイヤーの案内は None。"""
        assert runtime.orientation_for(PlayerId(99)) is None


class TestScene:
    """1 ターンのプロンプトに載る場面と、ユーザー文の末尾との関係を保証する。"""

    def test_scene_holds_surroundings_and_notices_apart(self, runtime) -> None:
        """場面の説明文は【現在地と周囲】で、知らせ (station_drill では【時間の経過】) は別の並びに入る。"""
        scene = runtime.build_full_prompt(PlayerId(1))["scene"]

        assert isinstance(scene, Scene)
        assert [d.heading for d in scene.descriptions] == ["現在地と周囲"]
        assert [d.heading for d in scene.notices] == ["時間の経過"]

    def test_active_ongoing_condition_is_a_notice_before_the_elapsed_time(self, runtime) -> None:
        """停電が起きると、場面の知らせに【進行中の異常】が【時間の経過】より前に入る。"""
        control_terminal = ItemSpecId.create(runtime.id_mapper.get_int("item_spec", "control_terminal"))
        runtime.do_interact_with_item(PlayerId(3), control_terminal, "cut_power")

        scene = runtime.build_full_prompt(PlayerId(1))["scene"]

        assert [d.heading for d in scene.notices] == ["進行中の異常", "時間の経過"]

    def test_candidate_table_is_placed_right_after_the_surroundings(self, runtime) -> None:
        """出すツールが決まって候補表を差し込むと、場面でも【現在地と周囲】の直後に入る。"""
        tool_names = {d.name for d in runtime.get_tool_definitions(player_id=PlayerId(1))}

        prompt = inject_dynamic_argument_candidate_table(runtime.build_full_prompt(PlayerId(1)), tool_names)

        assert [d.heading for d in prompt["scene"].descriptions] == ["現在地と周囲", "現在選べる対象引数"]
        assert [d.heading for d in prompt["scene"].notices] == ["時間の経過"]

    def test_candidate_table_outside_the_scene_leaves_the_scene_alone(self, runtime) -> None:
        """reason_first の行動の段のように場面の外へ候補表を置くときは、場面に候補表を入れない。"""
        tool_names = {d.name for d in runtime.get_tool_definitions(player_id=PlayerId(1))}
        prompt = runtime.build_full_prompt(PlayerId(1))

        injected = inject_dynamic_argument_candidate_table(prompt, tool_names, in_scene=False)

        assert injected["scene"] == prompt["scene"]
        assert "【現在選べる対象引数】" in injected["messages"][-1]["content"]

    def test_user_message_shows_the_scene_in_the_same_order(self, runtime) -> None:
        """場面の説明文と知らせは、文にした形のまま、この順でユーザー文に現れる。"""
        tool_names = {d.name for d in runtime.get_tool_definitions(player_id=PlayerId(1))}
        prompt = inject_dynamic_argument_candidate_table(runtime.build_full_prompt(PlayerId(1)), tool_names)
        user = prompt["messages"][-1]["content"]

        scene = prompt["scene"]
        positions = [user.index(description_text(d)) for d in (*scene.descriptions, *scene.notices)]

        assert positions == sorted(positions)
