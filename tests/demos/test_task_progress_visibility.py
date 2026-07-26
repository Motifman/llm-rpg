"""作業の進み具合が現在状態から読めることを保証する。

## なぜ要るか

本家のタスクバーは、クルーにとって**勝ち筋が進んでいるかの唯一の指標**で、
インポスターが作業のふりをしても増えない。つまり「バーが止まっている」こと
自体が情報になる。

engine 側の事情としても要る。作業は別々の部屋に置かれるので、**他人が何を
終わらせたかは観測として届かない**。進みが見えないと、各エージェントは自分が
やったぶんしか知らないまま「まだ全然進んでいない」と誤認し続ける。

## 何を見せて、何を見せないか

見せるのは総数だけ。**誰が終わらせたかは見せない。** 見せると偽装が成立
しなくなる (作業のふりをしても「進んでいない」で即バレる)。どの作業が
残っているかも出さない。場所と紐づくので、消去法で「あそこに誰が居たか」が
割れる。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"
_BASE = _SCENARIOS / "darkened_station.json"
_WITHOUT_TASKS = _SCENARIOS / "survival_island_v4_coop.json"

_MORI = PlayerId(1)
_TASKS = ["task_radio", "task_fuel", "task_wiring", "task_scan"]


@pytest.fixture()
def runtime(tmp_path):
    """作業 4 個・3 個で勝ち、というシナリオを組んで返す。"""
    raw = json.loads(_BASE.read_text(encoding="utf-8"))
    raw["game_end_conditions"] = {
        "win": [{
            "type": "FLAGS_SET_AT_LEAST",
            "required_flags": _TASKS,
            "min_set_count": 3,
        }],
        "lose": [],
    }
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(path)


def _progress_line(runtime, player_id: PlayerId = _MORI) -> str:
    """現在状態から作業の行だけを取り出す。

    全文に対して assert すると、他の行の数字や語で偶然通ってしまう。
    """
    for line in runtime.build_observation(player_id).splitlines():
        if "作業の進み" in line:
            return line
    return ""


class TestTheProgressIsShown:
    """宣言のあるシナリオでは進みが出る。"""

    def test_it_starts_at_zero(self, runtime) -> None:
        """何も終わっていなければ 0。"""
        assert "0/4" in _progress_line(runtime)

    def test_it_counts_completed_tasks(self, runtime) -> None:
        """作業が終わるたびに増える。"""
        runtime._world_flag_state.add("task_radio")
        runtime._world_flag_state.add("task_fuel")

        assert "2/4" in _progress_line(runtime)

    def test_it_shows_how_many_more_are_needed(self, runtime) -> None:
        """あと何個で勝てるかが分かる。

        総数だけだと、3 個で勝てるのか 4 個なのかが読めない。締切と同じで、
        **あといくつかが分からないと配分を決められない**。
        """
        runtime._world_flag_state.add("task_radio")

        assert "あと 2" in _progress_line(runtime)

    def test_unrelated_flags_do_not_move_it(self, runtime) -> None:
        """関係の無いフラグでは進まない。

        照明や救難信号でも進むと、進捗が勝ち筋の指標でなくなる。
        """
        runtime._world_flag_state.add("lights_off")

        assert "0/4" in _progress_line(runtime)


class TestWhatIsNotShown:
    """見せてはいけないものを見せない。"""

    def test_it_does_not_name_who_completed_them(self, runtime) -> None:
        """誰が終わらせたかは出さない。

        出すと偽装が成立しない。作業のふりをしても「進んでいない」で
        即座に割れてしまう。
        """
        runtime._world_flag_state.add("task_radio")

        line = _progress_line(runtime)
        assert "モリ" not in line
        assert "クゼ" not in line

    def test_it_does_not_list_which_tasks_remain(self, runtime) -> None:
        """どの作業が残っているかも出さない。

        作業は場所と紐づくので、消去法で「あそこに誰が居たか」が割れる。
        """
        runtime._world_flag_state.add("task_radio")

        line = _progress_line(runtime)
        assert not any(name in line for name in _TASKS)


class TestScenariosWithoutTasks:
    """宣言の無いシナリオには何も足さない。"""

    def test_no_progress_line(self) -> None:
        """作業条件を書いていないシナリオでは行ごと出ない。

        比較実験の土台なので 1 行も足さない (#875 / #877 と同じ理由)。
        """
        other = create_world_runtime(_WITHOUT_TASKS)

        assert _progress_line(other) == ""

    def test_the_base_scenario_is_untouched(self) -> None:
        """darkened_station 自体もまだ作業を持たないので出ない。

        作業の配置は次の PR。ここで先に出ると、宣言していない進捗を
        見せることになる。
        """
        base = create_world_runtime(_BASE)

        assert _progress_line(base) == ""
