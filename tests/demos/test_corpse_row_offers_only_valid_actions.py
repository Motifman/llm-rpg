"""死体の行に、その相手に使えない行動が出ないことを保証する。

## 実 run で見つかった歪み

    - "セナ" (倒れて動かない) 〔手ぶら〕 [背後から襲う (strike_down…), 持ち物を奪う, tend_to_player]
    - "クゼ" (死亡している) 〔手ぶら〕 [背後から襲う (strike_down…), 持ち物を奪う, tend_to_player]

倒れている相手に「背後から襲う」、**追放された人に「介抱して起こす」**まで
並んでいた。行動候補そのものが世界の説明になっている以上、質感の話ではなく
事実の誤りになる。

## 原因は非対称だったこと

「倒れた相手を要求する行動」は立っている相手から隠していたのに、**逆が
無かった**。宣言から要求を導いて対称に見る。

- `TARGET_PLAYER_IS_INCAPACITATED` を持つ → 倒れた相手を要求する
- 持たない → 立っている相手を要求する

倒れた相手を殴れるようにしたいシナリオは、その条件を宣言すれば出せる。

## 退場が確定した相手には何も出さない

engine の普遍則 (`validate_actionable_target`) が実行時に必ず弾くので、
出すと「選べるのに必ず失敗する手」になる (#860 で潰した形)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI = PlayerId(1)
_SENA = PlayerId(2)
_KUZE = PlayerId(3)   # keeper


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


@pytest.fixture()
def runtime_with_tending(tmp_path):
    """手当てを残した station_drill。

    本体の station_drill は `grace_ticks: 0` の世界なので、手当てを
    `disabled_tools` で落としてある。**手当ての表示を確かめるテストは、
    手当てのある世界で回さないと意味が無い。** シナリオの宣言に
    引きずられて「出ないこと」を確かめてしまう。
    """
    import json

    raw = json.loads(_SCENARIO.read_text(encoding="utf-8"))
    raw["disabled_tools"] = [
        name for name in raw.get("disabled_tools", []) if name != "tend_to_player"
    ]
    path = tmp_path / "with_tending.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(path)


def _row(runtime, viewer: PlayerId = _MORI, name: str = "セナ") -> str:
    for line in runtime.build_observation(viewer).splitlines():
        if name in line and '"' in line:
            return line
    return ""


def _down(runtime, player_id: PlayerId) -> None:
    status = runtime._player_status_repo.find_by_id(player_id)
    status.apply_damage(status.hp.value)
    runtime._player_status_repo.save(status)


class TestStandingTarget:
    """立っている相手には、生きた相手向けの行動だけ出る。"""

    def test_attacking_is_offered(self, runtime) -> None:
        """襲うは出る。

        見る側はクゼ (keeper) にする。**自分にできない行為は自分の一覧に
        出ない**ようになったので、crew の視点では確かめられない。ここで
        見たいのは「立っている相手には生きた相手向けの行動が出る」ことで、
        誰が襲えるかではない。
        """
        assert "strike_down" in _row(runtime, viewer=_KUZE)

    def test_looting_is_not_offered(self, runtime) -> None:
        """倒れた相手向けの行動は出ない (従来どおり)。"""
        assert "loot_from_downed" not in _row(runtime)

    def test_tending_is_not_offered(self, runtime) -> None:
        """手当ても出ない。"""
        assert "tend_to_player" not in _row(runtime)


class TestDownedTarget:
    """倒れている相手には、倒れた相手向けの行動だけ出る。"""

    def test_attacking_is_no_longer_offered(self, runtime) -> None:
        """**襲うが消える。** ここが今回の主眼。

        倒れた相手を殴る行動を出したいシナリオは、その action に
        `TARGET_PLAYER_IS_INCAPACITATED` を宣言すれば出せる。
        """
        _down(runtime, _SENA)

        assert "strike_down" not in _row(runtime)

    def test_looting_is_offered(self, runtime) -> None:
        """漁るは出る。"""
        _down(runtime, _SENA)

        assert "loot_from_downed" in _row(runtime)

    def test_tending_is_offered(self, runtime_with_tending) -> None:
        """手当ても出る。"""
        _down(runtime_with_tending, _SENA)

        assert "tend_to_player" in _row(runtime_with_tending)


class TestEliminatedTarget:
    """退場が確定した相手には、何も出ない。"""

    def _eliminate(self, runtime, outcome) -> None:
        _down(runtime, _SENA)
        runtime._player_outcome_registry.set_outcome(_SENA, outcome)

    @pytest.mark.parametrize(
        "outcome", [PlayerOutcomeEnum.DEAD, PlayerOutcomeEnum.EJECTED]
    )
    def test_no_action_is_offered(self, runtime, outcome) -> None:
        """死亡でも追放でも、行動候補が空になる。"""
        self._eliminate(runtime, outcome)

        row = _row(runtime)
        assert row, "行そのものは出る (死体は見える)"
        for action in ("strike_down", "loot_from_downed", "tend_to_player"):
            assert action not in row, row

    def test_the_row_itself_still_shows(self, runtime) -> None:
        """行は消さない。

        **死体はその場に見えている。** 行ごと消すと、通報する相手が
        prompt から消える。出さないのは行動候補だけ。
        """
        self._eliminate(runtime, PlayerOutcomeEnum.DEAD)

        assert "セナ" in _row(runtime)


class TestNoEngineIdentifierIsBare:
    """engine の tool も日本語のラベルつきで出る。"""

    def test_tend_has_a_display_label(self, runtime_with_tending) -> None:
        """`tend_to_player` が生の識別子のまま並ばない。

        シナリオ宣言の interaction は日本語つきで出るのに、engine の tool
        だけ裸だった。#892 の「engine の語彙をプロンプトに出さない」に揃える。
        """
        _down(runtime_with_tending, _SENA)

        assert "介抱して起こす" in _row(runtime_with_tending)
