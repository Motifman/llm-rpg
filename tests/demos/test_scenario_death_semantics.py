"""死の扱いをシナリオが選べることを保証する。

## なぜ engine 固定ではいけないか

無人島のような世界では「倒れた仲間に駆けつけて助け起こす」が成立してほしい。
秘匿役職の世界では、殺しは静かに起き、死は確定し、死体だけが残ってほしい。
**同じ engine に両方が要る。**

実 run (station_drill 001-005) で、engine 固定の挙動が秘匿役職を壊していた。

- 倒れた瞬間に**全員へ**「遠くで誰かが倒れた気配がした」が届く
  → 死体を見つける意味も通報する意味も無くなる
- 被害者に匿名の通知を出した直後、**加害者名が届く**
  → 匿名にした意味が消える
- 30 tick の猶予が切れるまで生存扱い
  → 同数の判定に届かず、短い run では決着しない

## 過去の判断は捨てず、条件付きにする

- #848「倒れているだけの相手は蘇生できるので生存として数える」
- #873「会議は救命猶予より必ず短い」

どちらも**蘇生のある世界での判断**として残る。`grace_ticks=0` の世界では
救命の余地そのものが無いので、意味を持たない。当時の判断が誤っていたのでは
なく、秘匿役職を想定していなかっただけ。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"
_DRILL = _SCENARIOS / "station_drill.json"
_WITHOUT_DECLARATION = _SCENARIOS / "survival_island_v4_coop.json"

_MORI, _SENA, _KUZE, _AOI = (PlayerId(i) for i in (1, 2, 3, 4))


def _move(runtime, player_id, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


@pytest.fixture()
def killed():
    """暗い通路でセナが襲われた直後の世界を返す。"""
    runtime = create_world_runtime(_DRILL)
    _move(runtime, _KUZE, "storage")
    runtime.do_interact(_KUZE, "supply_shelf", "find_cutter")
    for pid, spot in ((_SENA, "corridor"), (_KUZE, "corridor"),
                      (_MORI, "hall"), (_AOI, "hall")):
        _move(runtime, pid, spot)
    before = {
        int(p): len(runtime._obs_buffer.get_observations(p))
        for p in (_MORI, _SENA, _AOI)
    }
    runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")
    return runtime, before


def _new_prose(runtime, before, player_id) -> list[str]:
    return [
        e.output.prose
        for e in runtime._obs_buffer.get_observations(player_id)[int(before[int(player_id)]):]
    ]


class TestTheKillIsHidden:
    """殺しがその場に居ない者へ届かない。"""

    def test_players_elsewhere_learn_nothing(self, killed) -> None:
        """別の部屋に居る者に、倒れたことが届かない。

        **これが無いと隠密殺人が成立しない。** 倒れた瞬間に全員が知るなら、
        死体を見つける意味も通報する意味も無い。
        """
        runtime, before = killed

        for pid in (_MORI, _AOI):
            for prose in _new_prose(runtime, before, pid):
                assert "倒れた" not in prose, prose

    def test_the_victim_is_not_told_who_did_it(self, killed) -> None:
        """被害者に加害者の名前が届かない。

        engine の既定は「本人視点では当然分かる」。シナリオが匿名の通知を
        宣言している世界では、直後に名前が届くと**匿名にした意味が消える**。
        """
        runtime, before = killed

        for prose in _new_prose(runtime, before, _SENA):
            assert "クゼ" not in prose, prose

    def test_the_victim_still_learns_they_went_down(self, killed) -> None:
        """倒れたこと自体は本人に届く。

        消しすぎると、本人が何が起きたか分からないまま退場する。
        """
        runtime, before = killed

        assert any("倒れて" in p for p in _new_prose(runtime, before, _SENA))


class TestDeathIsImmediate:
    """猶予 0 の世界では、倒れた時点で退場が確定する。"""

    def test_the_outcome_is_settled_on_the_next_tick(self, killed) -> None:
        """次の tick で DEAD になる。

        既定の 30 tick のままだと、同数の判定に届かず短い run で決着しない。
        """
        runtime, _ = killed

        runtime.advance_tick()

        assert runtime._player_outcome_registry.get_outcome(_SENA) is (
            PlayerOutcomeEnum.DEAD
        )

    def test_the_body_can_no_longer_be_revived(self, killed) -> None:
        """確定したあとは手当てできない。

        `grace_ticks: 0` は「蘇生の無い世界」の宣言でもある。普遍則
        (#911) が退場済みを弾くので、行動側に何も書かずに成立する。
        """
        runtime, _ = killed
        runtime.advance_tick()
        _move(runtime, _MORI, "corridor")

        row = next(
            (l for l in runtime.build_observation(_MORI).splitlines()
             if "セナ" in l and '"' in l),
            "",
        )
        assert row
        assert "tend_to_player" not in row


class TestScenariosWithoutTheDeclaration:
    """宣言の無いシナリオの挙動は変わらない。"""

    def test_the_default_is_the_previous_behaviour(self) -> None:
        """既定は従来どおり (蘇生できる / 気配が届く / 加害者が分かる)。"""
        scenario = create_world_runtime(_WITHOUT_DECLARATION).scenario

        assert scenario.death_semantics.grace_ticks is None
        assert scenario.death_semantics.announce_globally is True
        assert scenario.death_semantics.victim_learns_killer is True


class TestValidation:
    """書き間違いを読み込み時に落とす。"""

    def _scenario(self, tmp_path, death):
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))
        raw["death"] = death
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        return path

    def test_a_negative_grace_is_rejected(self, tmp_path) -> None:
        """負の猶予は拒否する。0 は許す (即死の世界)。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioLoadError,
            ScenarioLoader,
        )

        with pytest.raises(ScenarioLoadError):
            ScenarioLoader().load_from_file(self._scenario(tmp_path, {"grace_ticks": -1}))

    def test_zero_is_allowed(self, tmp_path) -> None:
        """0 は正当な宣言。

        「書き忘れ」と区別するため、既定は None で持っている。0 を弾くと
        即死の世界が書けない。
        """
        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

        result = ScenarioLoader().load_from_file(
            self._scenario(tmp_path, {"grace_ticks": 0})
        )

        assert result.death_semantics.grace_ticks == 0

    def test_a_non_boolean_flag_is_rejected(self, tmp_path) -> None:
        """真偽値でない値は拒否する。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioLoadError,
            ScenarioLoader,
        )

        with pytest.raises(ScenarioLoadError):
            ScenarioLoader().load_from_file(
                self._scenario(tmp_path, {"announce_globally": "no"})
            )
