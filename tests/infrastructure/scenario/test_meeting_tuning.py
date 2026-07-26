"""会議の調整値をシナリオごとに変えられることを保証する。

## なぜ要るか

会議の tick 上限 20 は `darkened_station` のような 40 tick 級の run を
想定した値。**機構が一周するかを確かめるだけの短い run では、会議 1 回で
run の大半が消える。** 定数のままだと、確認のたびにコードを書き換えることに
なり、実験設定が JSON に残らない (CLAUDE.md の「実験に意味を持つ設定は
profile / scenario に集約する」に反する)。

## 1 以上の整数だけを通す

0 や負を許すと、会議が始まった瞬間に打ち切られたり、クールダウンが効かなく
なったりする。読み込み時に止めないと、run が終わるまで「なぜか会議が
成立しない」で悩むことになる。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_graph.game_phase_store import GamePhaseStore
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoadError

_BASE = (
    Path(__file__).resolve().parents[3] / "data" / "scenarios" / "darkened_station.json"
)

_MORI = PlayerId(1)
_KUZE = PlayerId(3)


def _scenario(tmp_path, meeting: dict) -> Path:
    raw = json.loads(_BASE.read_text(encoding="utf-8"))
    raw["meeting"] = meeting
    path = tmp_path / "tuned.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


class TestDefaults:
    """書かなければ既定のまま。"""

    def test_the_base_scenario_uses_the_defaults(self) -> None:
        """調整値を書いていないシナリオは既定値で動く。"""
        runtime = create_world_runtime(_BASE)

        store = runtime._game_phase_store
        assert store.meeting_tick_limit == GamePhaseStore.DEFAULT_MEETING_TICK_LIMIT
        assert store.emergency_buttons_per_player == 1


class TestOverridesTakeEffect:
    """書いた値が実際の挙動を変える。"""

    def test_a_short_meeting_actually_closes_early(self, tmp_path) -> None:
        """tick_limit を 4 にすると 4 tick で閉じる。

        **保持しているだけでは意味が無い。** 値が読まれていないと、短く
        したつもりの run で会議が 20 tick 走り続ける。挙動で確かめる。
        """
        runtime = create_world_runtime(_scenario(tmp_path, {"enabled": True, "tick_limit": 4}))
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        for _ in range(4):
            runtime.do_say(_MORI, "まだ結論は出ない")
            runtime.advance_tick()

        assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM

    def test_the_remaining_count_reflects_the_override(self, tmp_path) -> None:
        """現在状態の「残り」も調整値に従う。

        既定値のまま表示すると、実際は 4 tick で閉じるのに「残り 20」と
        読めてしまう。**締切として嘘をつく**ことになる。
        """
        runtime = create_world_runtime(_scenario(tmp_path, {"enabled": True, "tick_limit": 4}))
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        line = next(
            l for l in runtime.build_observation(_MORI).splitlines() if "話し合い" in l
        )
        assert "残り 4 tick" in line

    def test_more_emergency_buttons_can_be_granted(self, tmp_path) -> None:
        """緊急ボタンの回数を 2 にすると二度押せる。"""
        runtime = create_world_runtime(
            _scenario(tmp_path, {"enabled": True, "emergency_buttons_per_player": 2,
                                 "cooldown_ticks": 1})
        )
        assert runtime.call_emergency_meeting(_KUZE).success
        runtime.end_meeting(reason="vote_concluded")
        for _ in range(2):
            runtime.advance_tick()

        assert runtime.call_emergency_meeting(_KUZE).success


class TestValidation:
    """書き間違いを読み込み時に落とす。"""

    @pytest.mark.parametrize("value", [0, -1])
    def test_non_positive_values_are_rejected(self, tmp_path, value) -> None:
        """0 や負の値は拒否する。

        0 を許すと会議が始まった瞬間に打ち切られる。
        """
        with pytest.raises(ScenarioLoadError):
            create_world_runtime(
                _scenario(tmp_path, {"enabled": True, "tick_limit": value})
            )

    def test_non_integer_values_are_rejected(self, tmp_path) -> None:
        """整数以外は拒否する。"""
        with pytest.raises(ScenarioLoadError):
            create_world_runtime(
                _scenario(tmp_path, {"enabled": True, "silence_limit_ticks": "6"})
            )
