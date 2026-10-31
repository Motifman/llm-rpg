"""作業記憶 (WorkingMemory) が、区画を書き換わりにくい順に並べることを保証する (design_decisions D1630-2)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.being.contract import Description, Orientation, Scene
from ai_rpg_world.being.domain.working_memory import (
    Closing,
    MemoryTexts,
    Section,
    Steadiness,
    WorkingMemory,
)
from ai_rpg_world.domain.being.exception.being_exceptions import WorkingMemoryOrderException


def _section(steadiness: Steadiness, heading: str = "見出し") -> Section:
    return Section(heading=heading, lines=("文",), steadiness=steadiness)


def _compose(**overrides: object) -> WorkingMemory:
    values: dict[str, object] = {
        "orientation": Orientation([Description(heading="ペルソナ", text="あなたはハル。")]),
        "conduct": "【行動ルール】\n- 1 回に 1 つ",
        "imposed_goal": "外へ出る",
        "memory": MemoryTexts(
            known_people="- ミオ",
            backstory="[最新] 坑道に入った",
            recent_events="[0:00] 風が吹いた",
            episode_index="(まだ無い)",
            memo="やること:\n  (なし)",
        ),
        "scene": Scene(
            [Description(heading="現在地と周囲", text="北の竪坑口")],
            notices=[Description(heading="時間の経過", text="- 0 分")],
        ),
        "closing": Closing(instruction="行動を 1 つ選んでください。", warning="⚠ 同じ手を 3 回続けた。"),
    }
    values.update(overrides)
    return WorkingMemory.compose(**values)  # type: ignore[arg-type]


class TestOrder:
    """区画の並びが書き換わりにくい順でなければ作れないことを保証する。"""

    def test_steadier_sections_first_is_accepted(self) -> None:
        """書き換わりにくい区画から順に並べると作れる。同じ書き換わりにくさが続いてもよい。"""
        sections = (_section(Steadiness.FIXED), _section(Steadiness.ON_ENTRY), _section(Steadiness.ON_ENTRY))

        memory = WorkingMemory(system=sections, message=(_section(Steadiness.GROWING),), notices=(), closing=None)

        assert memory.system == sections

    @pytest.mark.parametrize("part", ["system", "message"])
    def test_less_steady_section_before_steadier_one_is_rejected(self, part: str) -> None:
        """システムプロンプトかメッセージのどちらかで、書き換わりやすい区画が先に来ると WorkingMemoryOrderException を投げる。"""
        parts: dict[str, object] = {"system": (), "message": (), "notices": (), "closing": None}
        parts[part] = (_section(Steadiness.EVERY_TURN), _section(Steadiness.GROWING))

        with pytest.raises(WorkingMemoryOrderException):
            WorkingMemory(**parts)  # type: ignore[arg-type]

    def test_notice_that_is_not_every_turn_is_rejected(self) -> None:
        """知らせは毎ターン置き換わるものなので、ほかの書き換わりにくさの区画を置くと拒む。"""
        with pytest.raises(WorkingMemoryOrderException):
            WorkingMemory(system=(), message=(), notices=(_section(Steadiness.ON_ENTRY),), closing=None)


class TestCompose:
    """環境の材料と Being の記憶の文から、今のプロンプトと同じ並びの区画を作ることを保証する。"""

    def test_system_holds_opening_orientation_and_conduct(self) -> None:
        """システムプロンプトは、冒頭の一文、案内の説明文、作法の文の順に並ぶ。"""
        memory = _compose()

        assert [(s.heading, s.steadiness) for s in memory.system] == [
            (None, Steadiness.FIXED),
            ("ペルソナ", Steadiness.ON_ENTRY),
            (None, Steadiness.ON_ENTRY),
        ]

    def test_message_holds_goal_memory_then_scene(self) -> None:
        """メッセージは、課された目的、知っている人、いきさつ、直近の出来事、目次、メモ、場面の説明文の順に並ぶ。"""
        memory = _compose()

        assert [s.heading for s in memory.message] == [
            "現在の目的",
            "知っている人",
            "ここまでのいきさつ",
            "直近の出来事",
            "思い出せる出来事",
            "メモ",
            "現在地と周囲",
        ]

    def test_notices_and_closing_follow_the_sections(self) -> None:
        """知らせは区画の後ろの並びに、締めの一文と繰り返しの警告は区画の外に置く。"""
        memory = _compose()

        assert [s.heading for s in memory.notices] == ["時間の経過"]
        assert memory.closing == Closing(instruction="行動を 1 つ選んでください。", warning="⚠ 同じ手を 3 回続けた。")

    def test_empty_goal_people_and_backstory_are_left_out(self) -> None:
        """目的、知っている人、いきさつ、目次、メモが空なら、その区画は見出しごと出さない。"""
        memory = _compose(imposed_goal="  ", memory=MemoryTexts(recent_events="[0:00] 風"))

        assert [s.heading for s in memory.message] == ["直近の出来事", "現在地と周囲"]

    def test_recent_events_always_appear_with_the_placeholder(self) -> None:
        """直近の出来事が空でも区画は出し、「（なし）」と書く。"""
        memory = _compose(memory=MemoryTexts())

        recent = next(s for s in memory.message if s.heading == "直近の出来事")
        assert recent.lines[-1] == "（なし）"


class TestWithScene:
    """場面だけを差し替えた作業記憶を作ることを保証する (design_decisions D1630-3)。"""

    def test_scene_sections_and_notices_are_replaced(self) -> None:
        """場面の区画と知らせは新しい場面のものになり、ほかの区画と締めはそのまま残る。"""
        memory = _compose()
        scene = Scene(
            [
                Description(heading="現在地と周囲", text="北の竪坑口"),
                Description(heading="現在選べる対象引数", text="- wait"),
            ],
            notices=[Description(heading="進行中の異常", text="- 停電")],
        )

        replaced = memory.with_scene(scene)

        assert [s.heading for s in replaced.message][-2:] == ["現在地と周囲", "現在選べる対象引数"]
        assert replaced.message[:-2] == memory.message[:-1]
        assert [s.heading for s in replaced.notices] == ["進行中の異常"]
        assert (replaced.system, replaced.closing) == (memory.system, memory.closing)

    def test_section_is_looked_up_by_heading(self) -> None:
        """メッセージの区画は見出しで引け、無い見出しは None。"""
        memory = _compose()

        assert memory.section("メモ") is not None
        assert memory.section("無い見出し") is None
