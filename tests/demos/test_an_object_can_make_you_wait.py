"""物体の操作にも、宣言した待ち時間が効く。

## 書けるのに効かない宣言だった

``cooldown_ticks`` は読み込み時に受け取られ、**人に対する操作** (襲う等) では
効いていた。**物体の操作では実行経路が誰も見ていなかった。**

出荷シナリオで物体に待ち時間を書いた例がゼロだったので、誰も踏んでいな
かった。妨害 (隔壁を降ろす) を書こうとして初めて出た。

    { "action_name": "seal_bulkhead", "cooldown_ticks": 20 }

と書いて、2 回続けて成功した。例外も警告も出ない。**作家の宣言が黙って
捨てられる**、#966 で読み込み時に落とすようにしたのと同じ形の失敗。

## 物体ごとに別々に数える

覚えておく単位は「行為の名前」だけでは足りない。survival_island_v2 には
``harvest`` / ``open_chest`` / ``drink_water`` がそれぞれ**別の物体に 2 つ**
宣言されている。名前だけで数えると、井戸を汲んだせいでポンプが使えなく
なる。

## 待っていることは行に書く

待ち時間が見えないと「選べるのに必ず失敗する手」になる (#860)。#964 で
人に対する行に足したのと同じものを、物体の行にも出す。単位は分で書く。
``tick`` は世界の中に無い語 (#892)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoadError

_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "scenarios"
    / "object_cooldown_demo.json"
)
#: 井戸は 6 手番おき。1 手番 5 分の既定なので 30 分。
_COOLDOWN_TICKS = 6
_A, _B = PlayerId(1), PlayerId(2)


@pytest.fixture()
def runtime():
    return create_world_runtime(_FIXTURE)


def _advance(runtime, ticks: int) -> None:
    for _ in range(ticks):
        runtime.advance_tick()


def _draw(runtime, obj: str = "stone_well", actor: PlayerId = _A):
    return runtime.do_interact(actor, obj, "draw_water")


def _scenario_variant(tmp_path: Path, mutate, filename: str) -> Path:
    raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / filename
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def _with_player_action(tmp_path: Path, action_name: str, filename: str) -> Path:
    """対人行為を 1 つ足したシナリオを書き出す。

    対人行為は「相手に効く効果」を 1 つ以上持つ必要がある。持たせずに書くと
    **別の検査で落ちて、接頭辞を弾いたと読み違える**。
    """

    def _mutate(raw: dict) -> None:
        raw["player_interactions"] = [
            {
                "action_name": action_name,
                "display_label": "揺り起こす",
                "effects": [
                    {
                        "effect_type": "APPLY_DAMAGE",
                        "target": "TARGET_PLAYER",
                        "parameters": {"damage": 0},
                    }
                ],
            }
        ]

    return _scenario_variant(tmp_path, _mutate, filename)


def _with_object_action(tmp_path: Path, action_name: str, filename: str) -> Path:
    def _mutate(raw: dict) -> None:
        raw["spots"][0]["interior"]["objects"][0]["interactions"].append(
            {
                "action_name": action_name,
                "display_label": "忍び込ませる",
                "effects": [
                    {
                        "effect_type": "SHOW_MESSAGE",
                        "parameters": {"message": "何も起きない。"},
                    }
                ],
            }
        )

    return _scenario_variant(tmp_path, _mutate, filename)


def _row(runtime, object_name: str, viewer: PlayerId = _A) -> str:
    """物体の行だけを取り出す。

    部屋の説明文にも同じ語が出るので、観測全文を見ると**説明文のおかげで
    通るだけのテスト**になる。
    """
    return next(
        line.strip()
        for line in runtime.build_observation(viewer).splitlines()
        if line.strip().startswith(f'- "{object_name}"')
    )


class TestTheWellMakesYouWait:
    """宣言した待ち時間のあいだ、同じ物体を続けて使えない。"""

    def test_drawing_twice_in_a_row_is_refused(self, runtime) -> None:
        """汲んだ直後にもう一度汲もうとすると弾かれる。

        **ここが黙って通っていた。** 宣言を書いても何も起きない状態は、
        書かないより悪い。作家は効いているつもりで組み立てる。
        """
        _draw(runtime)

        # 例外の種類と文面まで絞る。`Exception` だけだと AttributeError や
        # 保存失敗でも緑になり、**待ち時間で断ったことを確かめていない**
        # (codex の指摘)。
        with pytest.raises(InteractionNotAllowedException, match="あと 30 分"):
            _draw(runtime)

    def test_drawing_again_works_after_the_wait(self, runtime) -> None:
        """待ち時間が過ぎれば、また汲める。

        **「ずっと使えない」でも上のテストは通る**ので、使える側を一緒に見る。
        """
        _draw(runtime)
        _advance(runtime, _COOLDOWN_TICKS)

        result = _draw(runtime)

        assert "水を汲み上げた" in " ".join(result.messages)

    def test_an_object_without_the_declaration_is_never_limited(
        self, runtime
    ) -> None:
        """待ち時間を宣言していない操作は、何度でも続けられる。

        **全部の操作を待たせる実装でも上の 2 つは通る。** 宣言した物だけが
        待つことを見る。
        """
        for _ in range(3):
            runtime.do_interact(_A, "old_shelf", "rummage")


class TestEachObjectCountsItsOwnWait:
    """待ち時間は物体ごとに別々に数える。"""

    def test_another_object_with_the_same_action_still_works(
        self, runtime
    ) -> None:
        """井戸を汲んだ直後でも、手押しポンプの同名の操作は使える。

        覚える単位が行為の名前だけだと、**無関係な物体が巻き添え**になる。
        survival_island_v2 は harvest / open_chest / drink_water を別々の
        物体に 2 つずつ宣言していて、実際に起きる。
        """
        _draw(runtime, "stone_well")

        result = _draw(runtime, "hand_pump")

        assert "把手を押すと" in " ".join(result.messages)

    def test_another_action_on_the_same_object_still_works(
        self, runtime
    ) -> None:
        """同じ井戸でも、別の操作は待たされない。

        物体ごとにまとめて封じると、**覗くこともできなくなる**。
        """
        runtime.do_interact(_A, "yard_lantern", "light_lantern")
        _draw(runtime, "stone_well")

        result = runtime.do_interact(_A, "stone_well", "peer_inside")

        assert "底に水面が光っている" in " ".join(result.messages)

    def test_the_wait_belongs_to_the_person_who_used_it(self, runtime) -> None:
        """自分が汲んでも、相棒はまだ汲める。

        待ち時間は「その物体が使えない」ではなく「その人がその物体を続けて
        使えない」。人に対する操作と同じ数え方に揃える。
        """
        _draw(runtime, "stone_well", actor=_A)

        result = _draw(runtime, "stone_well", actor=_B)

        assert "水を汲み上げた" in " ".join(result.messages)


class TestFailingDoesNotStartTheWait:
    """空振りは待ち時間の起点にならない。"""

    def test_a_refused_attempt_leaves_the_action_usable(self, runtime) -> None:
        """前提条件で弾かれても、その操作はすぐ試せる。

        空振りで待たされると、**前提条件を試すことが罰**になる。「暗くて
        見えなかった」で封じられると、条件を確かめる行動が取れない。
        """
        with pytest.raises(
            InteractionNotAllowedException, match="暗くて底が見えない"
        ):
            runtime.do_interact(_A, "stone_well", "peer_inside")

        runtime.do_interact(_A, "yard_lantern", "light_lantern")
        result = runtime.do_interact(_A, "stone_well", "peer_inside")

        assert "底に水面が光っている" in " ".join(result.messages)


class TestAFailureAfterTheEffectsDoesNotStartTheWait:
    """効果を計算したあとで落ちた操作も、待ち時間の起点にならない。"""

    def test_a_failure_while_saving_leaves_the_action_usable(
        self, runtime
    ) -> None:
        """保存で落ちた操作のあと、同じ操作をすぐ試せる。

        前提条件の失敗だけを見ていると足りない。**効果計算より後の保存や配信で
        落ちた操作にも待ち時間が付いていた** (codex の指摘)。記録は適用と観測
        配信がすべて終わったあとに置く。
        """
        original = runtime._spot_interior_repo.save

        def _broken_save(*args, **kwargs):
            raise RuntimeError("保存が壊れている")

        runtime._spot_interior_repo.save = _broken_save
        with pytest.raises(RuntimeError):
            _draw(runtime)
        runtime._spot_interior_repo.save = original

        result = _draw(runtime)

        assert "水を汲み上げた" in " ".join(result.messages)


class TestTheReservedPrefixCannotBeClaimedByAScenario:
    """``object:`` で始まる行為名は読み込み時に落ちる。"""

    def test_a_player_action_named_with_the_prefix_is_refused(
        self, tmp_path
    ) -> None:
        """対人行為に予約接頭辞を付けると、読み込みが落ちる。

        接頭辞を片方に付けるだけでは**規約に頼った分離**にしかならない。対人
        行為を ``object:1:draw_water`` と名付けると、物体 1 の ``draw_water`` と
        同じキーになり、**待ち時間が静かに混ざる** (codex が実測)。

        snapshot のキー形式は変えないので、既存の保存データの移行が要らない。
        """
        scenario = _with_player_action(
            tmp_path, "object:1:draw_water", "reserved_player_action.json"
        )

        with pytest.raises(ScenarioLoadError, match="待ち時間の記録に使う接頭辞"):
            create_world_runtime(scenario)

    def test_an_object_action_named_with_the_prefix_is_refused(
        self, tmp_path
    ) -> None:
        """物体操作に予約接頭辞を付けても落ちる。

        検査は対人と物体が共通で通る 1 か所 (``_parse_interaction_def``) に
        置いてある。片方だけ守ると、もう片方から同じ衝突が入り込む。
        """
        scenario = _with_object_action(
            tmp_path, "object:9:sneak", "reserved_object_action.json"
        )

        with pytest.raises(ScenarioLoadError, match="待ち時間の記録に使う接頭辞"):
            create_world_runtime(scenario)

    def test_an_ordinary_player_action_name_is_accepted(self, tmp_path) -> None:
        """予約接頭辞で始まらない対人行為はそのまま通る。

        **「対人行為があると必ず落ちる」でも上のテストは通る。** 実際、最初は
        別の検査 (対人効果が無い) で落ちていたのを「接頭辞を弾いた」と読み違えて
        いた。落ちる理由まで揃える。
        """
        scenario = _with_player_action(
            tmp_path, "nudge_awake", "ordinary_player_action.json"
        )

        create_world_runtime(scenario)



class TestTheRowSaysHowLongToWait:
    """待っているあいだ、行にそう書く。"""

    def test_the_row_counts_in_minutes(self, runtime) -> None:
        """汲んだ直後の行に、残り時間が分で出る。

        ``tick`` は世界の中に無い語 (#892)。6 手番、1 手番 5 分なので 30 分。
        """
        _draw(runtime)

        row = _row(runtime, "石積みの井戸")

        assert "あと 30 分" in row
        assert "tick" not in row

    def test_no_wait_is_shown_before_the_first_use(self, runtime) -> None:
        """一度も使っていないうちは、待ち時間が出ない。

        **「常に出る」でも上のテストは通る**ので、出ない側を一緒に見る。
        """
        row = _row(runtime, "石積みの井戸")

        assert "あと" not in row

    def test_the_action_is_still_shown_while_waiting(self, runtime) -> None:
        """待っている間も、その操作は行から消えない。

        消すと、**自分の手段そのものを見失う** (#964 と同じ判断)。いつ使える
        ようになるかが書いてあれば、待つという次の手に繋がる。
        """
        _draw(runtime)

        row = _row(runtime, "石積みの井戸")

        assert "draw_water" in row
