"""Oneself が、自分の空腹と疲労を、それぞれの値と上限で段階にして身体の状態の行に書くことを保証する。"""

from __future__ import annotations

from ai_rpg_world.game_world.domain.perception.oneself import Oneself
from ai_rpg_world.game_world.domain.value_object import DisplayName, FatigueAmount, HitPoints, HungerAmount
from tests.game_world.support.world_design_for_tests import scene_texts


def test_hunger_and_fatigue_each_use_their_own_amount_and_limit() -> None:
    """空腹 45/200 は 22% で「少し」、疲労 70/100 は「高い」と、それぞれ自分の値と上限で書く。"""
    oneself = Oneself(
        belongings=(),
        hp=HitPoints(current=100, maximum=100),
        hunger=HungerAmount(45),
        hunger_limit=HungerAmount(200),
        fatigue=FatigueAmount(70),
        fatigue_limit=FatigueAmount(100),
        fatigue_felt=None,
    )

    assert oneself.lines(scene_texts())[-2:] == ["  空腹: 少し（45/200）", "  疲労: 高い（70/100）"]


def _tired(felt: DisplayName | None) -> Oneself:
    return Oneself(
        belongings=(),
        hp=HitPoints(current=100, maximum=100),
        hunger=HungerAmount(0),
        hunger_limit=HungerAmount(100),
        fatigue=FatigueAmount(100),
        fatigue_limit=FatigueAmount(100),
        fatigue_felt=felt,
    )


def test_felt_fatigue_follows_the_fatigue_line() -> None:
    """疲れの段階に一言「疲労が限界。体を使う行動ができない。」があると、疲労の行のすぐ下に「  → 」をつけて出る。"""
    lines = _tired(DisplayName("疲労が限界。体を使う行動ができない。")).lines(scene_texts())

    assert lines[-2:] == ["  疲労: 危険（100/100）", "  → 疲労が限界。体を使う行動ができない。"]


def test_no_felt_fatigue_adds_no_line() -> None:
    """疲れの段階に一言が無いと、疲労の行で終わる。"""
    assert _tired(None).lines(scene_texts())[-1] == "  疲労: 危険（100/100）"


def test_carrying_nothing_leaves_out_the_belongings_section() -> None:
    """何も持っていないとき、「所持アイテム:」の見出しを出さず、身体の状態から始まる。"""
    lines = _tired(None).lines(scene_texts())

    assert "所持アイテム:" not in lines
    assert lines[0] == "身体の状態:"
