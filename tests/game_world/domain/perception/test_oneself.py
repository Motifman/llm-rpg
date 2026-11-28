"""Oneself が、自分の空腹と疲労を段階にし、いましていることを終わる時刻つきで、身体の状態の行に書くことを保証する。"""

from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_and_clock_time import DayAndClockTime
from ai_rpg_world.game_world.domain.people import PersonRef, TextWithAssignedPeople, Unidentified
from ai_rpg_world.game_world.domain.perception.oneself import DoingNow, NotDoingAnything, Oneself
from ai_rpg_world.game_world.domain.person.shown_body import BodyChange
from ai_rpg_world.game_world.domain.value_object import DisplayName, FatigueAmount, HitPoints, HungerAmount
from tests.game_world.domain.perception._builders import ref
from tests.game_world.support.world_design_for_tests import clock_wording, scene_texts


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
        change=BodyChange(hp=0, hunger=0, fatigue=0),
        doing=NotDoingAnything(),
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
        change=BodyChange(hp=0, hunger=0, fatigue=0),
        doing=NotDoingAnything(),
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


def test_change_since_shown_is_written_with_its_sign_and_zero_is_left_out() -> None:
    """前回から HP +5・空腹 0・疲労 -2 のとき、HP は「、前回 +5」、疲労は「、前回 -2」を添え、変わらない空腹には何も添えない。"""
    oneself = Oneself(
        belongings=(),
        hp=HitPoints(current=60, maximum=100),
        hunger=HungerAmount(10),
        hunger_limit=HungerAmount(100),
        fatigue=FatigueAmount(30),
        fatigue_limit=FatigueAmount(100),
        fatigue_felt=None,
        change=BodyChange(hp=5, hunger=0, fatigue=-2),
        doing=NotDoingAnything(),
    )

    assert oneself.lines(scene_texts())[1:] == [
        "  HP: 消耗（60/100）、前回 +5",
        "  空腹: 問題なし（10/100）",
        "  疲労: 少し（30/100）、前回 -2",
    ]


def _doing(doing: DoingNow | NotDoingAnything) -> Oneself:
    return Oneself(
        belongings=(),
        hp=HitPoints(current=100, maximum=100),
        hunger=HungerAmount(0),
        hunger_limit=HungerAmount(100),
        fatigue=FatigueAmount(0),
        fatigue_limit=FatigueAmount(100),
        fatigue_felt=None,
        change=BodyChange(hp=0, hunger=0, fatigue=0),
        doing=doing,
    )


def test_what_the_person_is_doing_is_written_with_when_it_ends() -> None:
    """介抱している最中なら「  いましていること: 「{doing_target}」を介抱している (Day 1 深夜 1:00 ごろまで)」の行になり、相手は場面の人の穴に入る。"""
    bob = ref(2)
    holes: dict[str, PersonRef | Unidentified] = {"person_1": ref(3)}
    tending = DoingNow(
        text=TextWithAssignedPeople("「{target}」を介抱している", {"target": bob}),
        until=DayAndClockTime(day=1, hour=1, minute=0),
    )

    lines = _doing(tending).doing_lines(scene_texts(), clock_wording(), holes)

    assert lines == ["  いましていること: 「{doing_target}」を介抱している (Day 1 深夜 1:00 ごろまで)"]
    assert holes == {"person_1": ref(3), "doing_target": bob}


def test_world_without_day_and_night_writes_no_end_time() -> None:
    """昼夜の無い世界では時刻を書けないので、「ごろまで」を付けずに、していることだけを書く。"""
    searching = DoingNow(text=TextWithAssignedPeople("この場所を探している", {}), until=None)

    assert _doing(searching).doing_lines(scene_texts(), clock_wording(), {}) == [
        "  いましていること: この場所を探している"
    ]


def test_braces_in_what_the_person_is_doing_stay_as_letters() -> None:
    """していることの文に書かれた波かっこは、人の穴にせず、文字のまま場面の文に残る。"""
    lines = _doing(DoingNow(text=TextWithAssignedPeople("「{{鍵}}」を回している", {}), until=None)).doing_lines(
        scene_texts(), clock_wording(), {}
    )

    assert lines == ["  いましていること: 「{{鍵}}」を回している"]


def test_nothing_being_done_adds_no_line() -> None:
    """何もしていないときは、いましていることの行を出さない。"""
    assert _doing(NotDoingAnything()).doing_lines(scene_texts(), clock_wording(), {}) == []
