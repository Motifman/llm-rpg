"""対人行為に再使用間隔を置けることを保証する。

## なぜ要るか

実 run 008 で、インポスターが tick 4 と tick 6 で連続殺害して tick 7 に
終わった。**歩ける速さで殺し続けられる。** クルーは死体を見つける前に数を
減らされ、通報も会議も起きなかった。

本家 (Among Us) には殺害の間隔がある。

## 「キルのクールダウン」を作らない

engine が知っているのは「宣言された対人行為」までで、そのうちどれが殺しか
は知らない。知らせると、殺しのある世界とない世界で engine が分岐を持つ。
どの行為に間隔を置くかはシナリオが決める。

    { "action_name": "strike_down", "cooldown_ticks": 5 }

## 成功したときだけ起点が動く

空振りで待たされると、**前提条件を確かめる行動そのものが罰になる**。
「暗くないので襲えなかった」で 5 tick 封じられると、条件を試せなくなる。

## 行から消さない

「暗い場所のみ」と同じく、いま満たしていない条件もヒントとして書く。
消すと、いつ解禁されるか分からず毎 tick 試して無駄手になる (#860)。
自分の待ち時間は自分が知っている事実なので、出しても漏れない。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from ai_rpg_world.application.world_graph.interaction_cooldown_store import (
    InteractionCooldownStore,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI, _SENA, _KUZE = PlayerId(1), PlayerId(2), PlayerId(3)

#: station_drill が宣言している間隔。
_DECLARED_COOLDOWN = 5


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


def _armed_killer_world(tmp_path: Path, *, damage: int = 10, cooldown: int = 5):
    """刃物を持ったインポスターと、暗い通路に立つ相手が居る世界。

    ``damage`` を小さくするのは、**一撃で倒れると 2 回目を試せない**ため。
    間隔そのものを見たいので、相手が立っていられるようにする。
    """
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    for interaction in raw["player_interactions"]:
        if interaction["action_name"] == "strike_down":
            interaction["cooldown_ticks"] = cooldown
            interaction["effects"][0]["parameters"]["damage"] = damage
    path = tmp_path / "cooldown.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    runtime = create_world_runtime(path)
    _move(runtime, _KUZE, "storage")
    runtime.do_interact(_KUZE, "supply_shelf", "find_cutter")
    for player_id in (_SENA, _KUZE):
        _move(runtime, player_id, "corridor")
    return runtime


class TestTheSecondUseHasToWait:
    """一度使うと、間隔が明けるまで使えない。"""

    def test_using_it_twice_in_a_row_is_refused(self, tmp_path) -> None:
        """続けて使うと拒否される。"""
        runtime = _armed_killer_world(tmp_path)
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        with pytest.raises(InteractionNotAllowedException):
            runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

    def test_the_refusal_says_how_long(self, tmp_path) -> None:
        """あと何 tick かを伝える。

        伝えないと、毎 tick 試して無駄手になる。
        """
        runtime = _armed_killer_world(tmp_path, cooldown=3)
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        with pytest.raises(InteractionNotAllowedException) as caught:
            runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        assert "3" in str(caught.value)

    def test_it_becomes_usable_again(self, tmp_path) -> None:
        """間隔が明ければ使える。

        塞ぎっぱなしだと、一度襲った時点でインポスターが無力になる。
        """
        runtime = _armed_killer_world(tmp_path, cooldown=3)
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")
        for _ in range(3):
            runtime.advance_tick()

        assert runtime.do_interact_with_player(_KUZE, _SENA, "strike_down") is not None

    def test_a_failed_attempt_does_not_start_the_wait(self, tmp_path) -> None:
        """失敗した試みでは起点が動かない。

        **前提条件を確かめる行動が罰になってはいけない。** 明るい場所で
        襲おうとして断られただけで 5 tick 封じられると、条件を試せなくなる。
        """
        runtime = _armed_killer_world(tmp_path)
        _move(runtime, _KUZE, "hall")
        _move(runtime, _SENA, "hall")

        with pytest.raises(InteractionNotAllowedException):
            runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        # 暗い通路へ戻れば、待たされずに使える。
        for player_id in (_SENA, _KUZE):
            _move(runtime, player_id, "corridor")

        assert runtime.do_interact_with_player(_KUZE, _SENA, "strike_down") is not None


class TestActionsWithoutTheDeclaration:
    """宣言していない行為は今までどおり。"""

    def test_a_zero_cooldown_never_blocks(self, tmp_path) -> None:
        """`cooldown_ticks` が 0 の行為は連続で使える。

        **既存シナリオへの影響がゼロであること**をここで担保する。宣言を
        書いていないシナリオは 0 として読まれるので、これがそのまま
        「今までどおり動く」の保証になる。
        """
        runtime = _armed_killer_world(tmp_path, cooldown=0)

        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        assert runtime.do_interact_with_player(_KUZE, _SENA, "strike_down") is not None


class TestTheRowSaysHowLong:
    """行に残り tick が出る。"""

    def test_the_hint_shows_the_remaining_ticks(self, tmp_path) -> None:
        """待っている間、行に「あと N tick」が出る。

        行から消すと、いつ解禁されるか分からず毎 tick 試すことになる。
        「暗い場所のみ」と同じく、**満たしていない条件も書く**のが既存の設計。
        """
        runtime = _armed_killer_world(tmp_path, cooldown=4)
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        row = next(
            line
            for line in runtime.build_observation(_KUZE).splitlines()
            if "セナ" in line and "襲う" in line
        )

        assert "あと 4 tick" in row

    def test_the_hint_disappears_once_it_is_usable(self, tmp_path) -> None:
        """明けたら消える。

        残り続けると、使えるのに使えないと読める。
        """
        runtime = _armed_killer_world(tmp_path, cooldown=2)
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")
        for _ in range(2):
            runtime.advance_tick()

        row = next(
            line
            for line in runtime.build_observation(_KUZE).splitlines()
            if "セナ" in line and "襲う" in line
        )

        assert "tick" not in row


class TestTheDeclarationIsChecked:
    """書き方の間違いを読み込み時に落とす。"""

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(-1, id="negative"),
            pytest.param(True, id="a_boolean"),
            pytest.param("5", id="a_string"),
        ],
    )
    def test_a_malformed_value_is_rejected(self, tmp_path, value) -> None:
        """負の値・真偽値・文字列は拒否する。

        真偽値を弾くのは、`true` と書いて 1 tick になると**書いた人の意図と
        結果が食い違う**ため。
        """
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))
        for interaction in raw["player_interactions"]:
            if interaction["action_name"] == "strike_down":
                interaction["cooldown_ticks"] = value
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        with pytest.raises(ScenarioLoadError):
            ScenarioLoader().load_from_file(path)

    def test_zero_is_allowed(self, tmp_path) -> None:
        """0 は正当な宣言 (制限しない)。"""
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))
        for interaction in raw["player_interactions"]:
            interaction["cooldown_ticks"] = 0
        path = tmp_path / "zero.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        scenario = ScenarioLoader().load_from_file(path)

        assert all(i.cooldown_ticks == 0 for i in scenario.player_interactions)

    def test_the_drill_declares_one(self) -> None:
        """station_drill が実際に宣言している。

        tmp_path の書き換えだけで通ると、**本物のシナリオに入れ忘れていても
        緑になる**。
        """
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))
        declared = {
            i["action_name"]: i.get("cooldown_ticks", 0)
            for i in raw["player_interactions"]
        }

        assert declared["strike_down"] == _DECLARED_COOLDOWN


class TestTheStoreItself:
    """store 単体の決まり。"""

    def test_the_first_use_never_waits(self) -> None:
        """一度も使っていなければ待たない。

        「使ったことがない」と「待っている」を同じ扱いにすると、開始直後に
        誰も動けなくなる。
        """
        store = InteractionCooldownStore()

        assert (
            store.remaining_ticks(
                _KUZE, "strike_down", cooldown_ticks=5, current_tick=0
            )
            == 0
        )

    def test_a_tick_going_backwards_does_not_wait_forever(self) -> None:
        """現在 tick が記録より前に戻っていたら待たせない。

        snapshot の取り違えなどで起きうる。負の残りを返して**永遠に待たせる**
        より、使える側に倒して行動として観測できるようにする。
        """
        store = InteractionCooldownStore()
        store.record_success(_KUZE, "strike_down", 100)

        assert (
            store.remaining_ticks(
                _KUZE, "strike_down", cooldown_ticks=5, current_tick=10
            )
            == 0
        )

    def test_restoring_replaces_instead_of_merging(self) -> None:
        """復元は差し替えで、追記ではない。

        追記だと、復元前に走った tick の記録が混ざって**再開後だけ間隔が
        伸びる**。
        """
        store = InteractionCooldownStore()
        store.record_success(_KUZE, "strike_down", 50)

        store.replace_all([(int(_MORI), "strike_down", 3)])

        assert store.last_success_tick(_KUZE, "strike_down") is None
        assert store.last_success_tick(_MORI, "strike_down") == 3


class TestItSurvivesASnapshot:
    """再開しても間隔が消えない。"""

    def test_the_codec_round_trips(self, tmp_path) -> None:
        """保存して復元すると、待ち時間が残る。

        **落とすと、snapshot を挟んだ run でだけ連続殺害が復活する。**
        挟まない run と結果が変わり、再現性のある実験にならない。
        """
        from ai_rpg_world.application.being.world_subsystems import (
            InteractionCooldownSubsystemCodec,
        )

        runtime = _armed_killer_world(tmp_path, cooldown=5)
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        codec = InteractionCooldownSubsystemCodec()
        saved = codec.capture(runtime)

        restored = _armed_killer_world(tmp_path, cooldown=5)
        codec.restore(restored, saved)

        with pytest.raises(InteractionNotAllowedException):
            restored.do_interact_with_player(_KUZE, _SENA, "strike_down")
