"""会議中であることが、プロンプトの現在状態から読めることを保証する。

会議と投票 (docs/memory_system/meeting_and_voting_design.md) の仕上げ。

## なぜ要るか

ここまで、会議が始まったことを知る手段は `GamePhaseChangedEvent` の観測
**1 回きり**だった。一方でツールセットは会議のあいだずっと切り替わって
いる。つまり **「なぜ移動できないのか」を説明する情報が、文脈から流れて
消える**。会議が長引くほど起きやすい。

「露出は変わったのに、その理由が現在状態から読めない」は、この engine で
繰り返し潰してきた形と同じ (使えない候補が並ぶ #860 / 宣言だけあって動かない
#840)。観測は流れるが、現在状態は毎ターン再構築されるので消えない。

## 残り時間を数字で出す

本家の会議には見えるタイマーがあり、それが議論の圧力を作っている。粗い
言い回し (「長引いている」) だと「もう投票すべきか」の判断材料が弱い。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_graph.game_phase_store import GamePhaseStore
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"
_FIXTURE_SCENARIOS = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "scenarios"
)
_WITH_MEETING = _FIXTURE_SCENARIOS / "darkened_station.json"
_WITHOUT_MEETING = _SCENARIOS / "survival_island_v4_coop.json"

_MORI = PlayerId(1)
_KUZE = PlayerId(3)


@pytest.fixture()
def runtime():
    return create_world_runtime(_WITH_MEETING)


def _current_state(runtime, player_id: PlayerId) -> str:
    return runtime.build_observation(player_id)


def _meeting_line(runtime, player_id: PlayerId) -> str:
    """現在状態から会議の行だけを取り出す。

    全文に対して assert すると、同室者一覧や地の文に偶然その語が含まれる
    だけで通ってしまう (「クゼ」は同席者としても出る)。行を特定する。
    """
    for line in _current_state(runtime, player_id).splitlines():
        if "話し合い" in line:
            return line
    return ""


class TestFreeRoamSaysNothing:
    """自由時間には何も足さない。"""

    def test_no_meeting_line_before_any_meeting(self, runtime) -> None:
        """会議が始まる前は、会議の行が出ない。"""
        assert "話し合い" not in _current_state(runtime, _MORI)

    def test_no_meeting_line_after_it_ends(self, runtime) -> None:
        """会議が終われば消える。

        残り続けると、自由時間に戻ったのに「まだ話し合い中」と読める。
        """
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")
        runtime.end_meeting(reason="vote_concluded")

        assert "話し合い" not in _current_state(runtime, _MORI)

    def test_scenarios_without_the_mechanism_are_untouched(self) -> None:
        """会議機構を宣言していないシナリオの現在状態は変わらない。

        比較実験の土台なので、1 行たりとも足さない (#875 と同じ理由)。
        """
        other = create_world_runtime(_WITHOUT_MEETING)

        assert "話し合い" not in _current_state(other, _MORI)


class TestDuringAMeeting:
    """会議中は状況が読める。"""

    def test_it_says_a_meeting_is_in_progress(self, runtime) -> None:
        """話し合いの最中だと分かる。

        **これが主眼**。ツールセットが切り替わった理由が、毎ターン
        現在状態から読める。
        """
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        assert "話し合い" in _current_state(runtime, _MORI)

    def test_the_remaining_ticks_are_shown(self, runtime) -> None:
        """打ち切りまでの残りが数字で出る。

        締切が見えないと「もう投票すべきか」を判断できない。
        """
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        assert (
            f"残り {GamePhaseStore.DEFAULT_MEETING_TICK_LIMIT} tick"
            in _meeting_line(runtime, _MORI)
        )

    def test_the_remaining_count_goes_down(self, runtime) -> None:
        """tick が進むと残りが減る。

        **固定文言を出しているだけだと上のテストは通る。** 実際に減って
        いることまで見ないと、締切として機能しているか分からない。
        """
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")
        first = _meeting_line(runtime, _MORI)
        runtime.advance_tick()
        runtime.advance_tick()
        second = _meeting_line(runtime, _MORI)

        assert first and second
        assert f"残り {GamePhaseStore.DEFAULT_MEETING_TICK_LIMIT} tick" in first
        assert f"残り {GamePhaseStore.DEFAULT_MEETING_TICK_LIMIT - 2} tick" in second

    def test_who_called_it_is_shown(self, runtime) -> None:
        """誰が呼んだのかが分かる。

        招集した人は議論の出発点になる。会議のあいだ何度も参照される情報
        なので、流れて消える観測ではなく現在状態に置く。
        """
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        # 全文で見ると同席者一覧の「クゼ」で通ってしまう。行で見る。
        assert "クゼ" in _meeting_line(runtime, _MORI)
