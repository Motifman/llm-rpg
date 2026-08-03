"""手番を記録した state key は、作家が何と名付けても prompt に出ない。

## 名前で守っていた

``SpotObject.visible_state`` に、隠す key の名前が 1 つ直書きされていた。

    _REACTIVE_LAST_HARVEST_TICK_STATE_KEY = "last_harvest_tick"

流木や木の実は ``last_harvest_tick`` という名前を選んだので守られていた。
**別の名前を選んだ物体は守られていない。**

## もう漏れている

survival_island_v2 / v2_short / v3_coop / v4_coop の焚き火跡が、実際に
こう出ている。

    - "焚き火跡" (lit=false, last_lit_tick=-100) — 石を組んだ焚き火跡。

``last_lit_tick`` と名付けただけで守りを外れた。``signal_fire_pit`` の
``lit_at_tick`` も同じ。``-100`` は「ずっと昔」を表す番兵値で、読んだ
エージェントには意味の無い数字が並ぶだけになる。

``tick`` は世界の中に無い語 (#892)。世界の中の人が「手番」を数えている
はずがない。

## 名前ではなく仕組みで守る

守るべきは「``last_harvest_tick`` という綴り」ではなく「**手番を記録する
効果が書いた key**」。名前は作家の自由で、engine が当てにいくものではない。

読み込み時に、物体の interaction から ``RECORD_OBJECT_STATE_TICK`` が書く
``state_key`` を集めて ``hidden_state_keys`` に足す。**書けば自動で伏せ
られる**ので、作家も engine も名前を覚えなくてよい。

JSON に ``hidden_state_keys`` を書かせる案は採らない。書き忘れが即漏洩に
なる。``spot_object.py`` のコメントに「per-object 設定に頼ると設定漏れで
漏れる (既知回帰)」とあり、**同じ失敗を一度している**。

## engine の名前なら直書きしてよい

``stock`` / ``stock_tick`` 等の備蓄プール key は消さない。あれは engine 自身が
書き込む key で、名前は engine の語彙。

    engine が自分で作る名前はハードコードしてよい。
    シナリオが決める名前をハードコードしてはいけない。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_REPO = Path(__file__).resolve().parents[2]
_SCENARIO_DIR = _REPO / "data" / "scenarios"
_ISLAND = _SCENARIO_DIR / "survival_island_v2.json"

#: 出荷シナリオと、テスト用の作例の両方を見張る。作例のほうが
#: ``target_object`` に自分自身を明示する書き方をしていて、出荷シナリオだけ
#: 見ていると**実際に多い書き方のほうを取りこぼす**。
_ALL_SCENARIOS = sorted(_SCENARIO_DIR.glob("*.json")) + sorted(
    (_REPO / "tests" / "fixtures" / "scenarios").glob("*.json")
)


def _recorded_tick_keys(scenario_path: Path) -> dict[str, set[str]]:
    """物体ごとに「手番を記録する効果が書く key」を宣言から集める。

    テストが engine の実装を写さないよう、**シナリオ JSON だけ**から読む。
    """
    data = json.loads(scenario_path.read_text(encoding="utf-8"))
    by_object: dict[str, set[str]] = {}
    for spot in data.get("spots", []):
        for obj in (spot.get("interior") or {}).get("objects", []):
            for interaction in obj.get("interactions", []):
                for effect in interaction.get("effects", []):
                    if effect.get("effect_type") != "RECORD_OBJECT_STATE_TICK":
                        continue
                    params = effect.get("parameters") or {}
                    state_key = params.get("state_key")
                    if not state_key:
                        continue
                    owner = params.get("target_object") or obj["id"]
                    by_object.setdefault(owner, set()).add(state_key)
    return by_object


def _spot_of_object(scenario_path: Path, object_id: str) -> str:
    data = json.loads(scenario_path.read_text(encoding="utf-8"))
    for spot in data.get("spots", []):
        for obj in (spot.get("interior") or {}).get("objects", []):
            if obj["id"] == object_id:
                return spot["id"]
    raise AssertionError(f"物体が見つからない: {object_id}")


def _object_row(observation: str, object_name: str) -> str:
    """物体の行だけを取り出す。

    部屋の説明文にも同じ語が出る (「石を組んだ焚き火跡があり」)。行を絞らずに
    観測全文を見ると、**説明文のおかげで通るだけのテスト**になる。
    """
    return next(
        line.strip()
        for line in observation.splitlines()
        if line.strip().startswith(f'- "{object_name}"')
    )


def _observation_at(runtime, spot: str, player_id: PlayerId = PlayerId(1)) -> str:
    graph = runtime._spot_graph_repo.find_graph()
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)
    return runtime.build_observation(player_id)


class TestTheFirePitNoLongerShowsItsBookkeeping:
    """名前を変えただけで漏れていた焚き火跡が、もう漏らさない。"""

    def test_the_fire_pit_does_not_show_its_recorded_tick(self) -> None:
        """焚き火跡の行に ``last_lit_tick`` が出ない。

        ``last_harvest_tick`` だけを直書きで隠していたので、``last_lit_tick``
        と名付けたこの物体は守られていなかった。
        """
        runtime = create_world_runtime(_ISLAND)

        text = _observation_at(runtime, _spot_of_object(_ISLAND, "fire_pit"))

        assert "焚き火跡" in text
        assert "last_lit_tick" not in text

    def test_the_signal_fire_does_not_show_its_recorded_tick(self) -> None:
        """狼煙台の行に ``lit_at_tick`` が出ない。

        こちらは JSON の初期 state に宣言が無く、火を灯して初めて書かれる。
        **宣言から導出するだけでは足りず**、書き込む側も伏せる必要がある。
        """
        runtime = create_world_runtime(_ISLAND)

        text = _observation_at(runtime, _spot_of_object(_ISLAND, "signal_fire_pit"))

        assert "lit_at_tick" not in text

    def test_the_driftwood_is_still_protected(self) -> None:
        """もともと守られていた流木の山も、引き続き漏らさない。

        直書きの定数を消すので、**それに守られていたものが漏れ出さないか**を
        一緒に見る。
        """
        runtime = create_world_runtime(_ISLAND)

        text = _observation_at(runtime, _spot_of_object(_ISLAND, "driftwood_pile"))

        assert "流木の山" in text
        assert "last_harvest_tick" not in text


class TestTheRowStillSaysSomethingUseful:
    """伏せた結果、行が無言にならない。"""

    def test_the_object_still_describes_itself(self) -> None:
        """内部の記録を伏せても、物体の説明と操作は残る。

        **「行ごと消す」でも上のテストは全部通る**ので、残る側を必ず見る。
        state を隠しすぎて何も読めない行になっては本末転倒。
        """
        runtime = create_world_runtime(_ISLAND)

        text = _observation_at(runtime, _spot_of_object(_ISLAND, "fire_pit"))
        row = _object_row(text, "焚き火跡")

        assert "石を組んだ焚き火跡" in row
        assert "build_fire" in row


class TestEveryScenarioKeepsItsRecordedTicksToItself:
    """同梱シナリオを総当たりして、記録した手番が prompt に出ないことを見張る。

    ``tick`` という文字列を探す形にはしない。**それでは名前を当てる守りに
    逆戻り**する。シナリオの宣言から key を集めて、その key を探す。
    """

    @pytest.mark.parametrize(
        "scenario_path", _ALL_SCENARIOS, ids=lambda p: p.stem
    )
    def test_no_recorded_tick_key_reaches_any_prompt(self, scenario_path) -> None:
        """どの物体の行にも、手番を記録する key が現れない。

        シナリオを足せば自動で対象になるので、この見張りを忘れても落ちる。
        """
        by_object = _recorded_tick_keys(scenario_path)
        if not by_object:
            pytest.skip("手番を記録する物体が無い")

        runtime = create_world_runtime(scenario_path)
        for object_id, keys in by_object.items():
            spot = _spot_of_object(scenario_path, object_id)
            text = _observation_at(runtime, spot)
            for key in keys:
                assert f"{key}=" not in text, (object_id, key)


class TestEachLayerHoldsOnItsOwn:
    """2 段の守りを、1 段ずつ確かめる。

    観測から見ると 2 段が重なっているので、**どちらか片方を壊しても観測は
    無事**になる。それでは片方が壊れたことに気付けないので、段ごとに見る。
    """

    def test_the_loader_marks_a_self_recorded_key_as_hidden(self) -> None:
        """読み込んだ時点で、自分に記録する key が伏せる集合に入っている。

        ``target_object`` に**自分自身を明示する**書き方 (``herb_planter`` が
        ``target_object: herb_planter`` と書く形) でも拾う。「指定があれば
        他所行き」と決めつけると、実際に多いほうの書き方が漏れる。
        """
        scenario = _REPO / "tests" / "fixtures" / "scenarios" / (
            "herbal_tea_greenhouse_demo.json"
        )
        runtime = create_world_runtime(scenario)

        interior = runtime._spot_interior_repo.find_by_spot_id(
            SpotId.create(runtime.id_mapper.get_int("spot", "greenhouse"))
        )
        planter = next(
            obj
            for obj in interior.objects
            if runtime.id_mapper.get_str("object", int(obj.object_id))
            == "herb_planter"
        )

        assert "last_harvest_tick" in planter.hidden_state_keys

    def test_the_effect_hides_a_key_it_writes_into_another_object(self) -> None:
        """別の物体に手番を書き込むと、書かれた側の伏せる集合に入る。

        読み込み時の導出は自分に書く宣言しか拾えない。**別の物体を指す経路は
        ここでしか守れない。**
        """
        from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
        from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
            InteractionEffectTypeEnum,
        )
        from ai_rpg_world.domain.world_graph.enum.spot_object_type import (
            SpotObjectTypeEnum,
        )
        from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
        from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
            WorldGraphEffectService,
        )
        from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
            InteractionEffect,
        )
        from ai_rpg_world.domain.world_graph.value_object.spot_object_id import (
            SpotObjectId,
        )
        from ai_rpg_world.domain.common.value_object import WorldTick

        def _object(object_id: int, name: str) -> SpotObject:
            return SpotObject(
                object_id=SpotObjectId.create(object_id),
                name=name,
                description="",
                object_type=SpotObjectTypeEnum.OTHER,
                state={},
                interactions=(),
            )

        lever, furnace = _object(1, "レバー"), _object(2, "炉")
        interior = SpotInterior(
            sub_locations=(),
            objects=(lever, furnace),
            ground_items=(),
            discoverable_items=(),
        )
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.RECORD_OBJECT_STATE_TICK,
            parameters={"state_key": "started_at_tick", "object_id": 2},
        )

        result = WorldGraphEffectService().apply_effects(
            interior=interior,
            acting_object=lever,
            effects=[effect],
            world_flags=frozenset(),
            current_tick=WorldTick(9),
        )

        written = next(
            obj
            for obj in result.new_interior.objects
            if int(obj.object_id) == 2
        )
        assert written.state["started_at_tick"] == 9
        assert "started_at_tick" in written.hidden_state_keys
        assert written.visible_state() == {}


class TestTheEngineOwnedNamesStayHardcoded:
    """engine 自身が書き込む key の直書きは残す。"""

    def test_the_stock_pool_keys_are_still_excluded_by_name(self) -> None:
        """備蓄プールの key は、宣言が無くても名前で除外され続ける。

        あれは engine が書き込む key で、名前は engine の語彙。シナリオが
        決めた名前を当てにいくのとは別の話で、混同すると今度は ``stock=0``
        が漏れる。生値のまま出ると、lazy 再生を計算しないので「0 なのに
        採れる」矛盾が見える。
        """
        from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
        from ai_rpg_world.domain.world_graph.enum.spot_object_type import (
            SpotObjectTypeEnum,
        )
        from ai_rpg_world.domain.world_graph.value_object.spot_object_id import (
            SpotObjectId,
        )

        obj = SpotObject(
            object_id=SpotObjectId.create(1),
            name="木の実の茂み",
            description="",
            object_type=SpotObjectTypeEnum.OTHER,
            state={"stock": 0, "stock_tick": 12, "ripe": True},
            interactions=(),
        )

        assert obj.visible_state() == {"ripe": True}

    def test_a_name_alone_no_longer_hides_anything(self) -> None:
        """記録する宣言が無ければ、``last_harvest_tick`` でも伏せられない。

        名前による守りが残っていると、**導出のほうが壊れても流木だけは救われ
        続ける**ので、壊れたことに気付けない。守りは 1 か所に寄せる。

        この物体は手番を記録する操作を持たないので、``last_harvest_tick`` は
        ただの作家の自由 state として扱われる (``cursed=true`` と同じ)。
        """
        from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
        from ai_rpg_world.domain.world_graph.enum.spot_object_type import (
            SpotObjectTypeEnum,
        )
        from ai_rpg_world.domain.world_graph.value_object.spot_object_id import (
            SpotObjectId,
        )

        obj = SpotObject(
            object_id=SpotObjectId.create(1),
            name="名前だけ紛らわしい物",
            description="手番を記録する操作を持たない。",
            object_type=SpotObjectTypeEnum.OTHER,
            state={"last_harvest_tick": 7},
            interactions=(),
        )

        assert obj.visible_state() == {"last_harvest_tick": 7}
