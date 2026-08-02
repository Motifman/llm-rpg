"""無効化したツールの名前が、プロンプトのどこにも残らないことを保証する。

## 宣言が半分しか効いていなかった

`disabled_tools` はツール定義の一覧からは消していたが、**プロンプト本文の
側にツール名を宣伝する箇所が別にあり**、そちらは無効化を見ていなかった。

    - "セナ" (倒れて動かない) [持ち物を奪う, 介抱して起こす (tend_to_player)]
    同じ場所にいるプレイヤー: (倒れていない相手には give_item で…)

行動候補として並べば、エージェントはそれを選ぶ。呼んだ先にツールは無い。
**無効化しないより悪い。**

#914 / #917 の死の観測で 2 回踏んだのと同じ形。「1 つの宣言が、複数の別々の
コードに手書きで反映されなければならない」。

## だからツール名を総当たりする

出す / 出さないの判断は `ToolExposure` に集めたが、集めただけでは
「参照し忘れた場所」を防げない。**ツール名を宣伝する場所が今後増えても
落ちる**形にする。1 つずつ無効化して、プロンプト全文に名前が出ないことを
確かめる。

新しくツールを足した人がこのテストを意識する必要は無い。名前は
`get_spot_graph_specs()` から取るので自動的に対象になる。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    get_spot_graph_specs,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI, _SENA, _KUZE, _AOI = (PlayerId(i) for i in (1, 2, 3, 4))

#: 全ツールを有効にしたとき、プロンプト本文に名前が出るツール。
#:
#: **これが正の対照。** 無効化テストは「消えること」しか見ないので、
#: そもそも出ていたのかを知らない。ここを固定しないと、宣伝箇所が 0 件でも
#: 総当たりが全部緑になる。実際 16 件中 13 件は名前がどこにも出ておらず、
#: 露出チェックを丸ごと消しても緑のままだった (claude の指摘)。
#:
#: 新しく宣伝文を書いた人は、この集合が増えて落ちる。そこで「露出判断を
#: 通すか、この集合に足すか」を選ぶことになる。
_ADVERTISED_TOOLS = {"give_item", "tend_to_player"}

_TOOL_NAMES = sorted(defn.name for defn, _ in get_spot_graph_specs())


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


def _world_with_only(tmp_path: Path, disabled: str) -> Path:
    """``disabled`` だけを無効化した station_drill を書き出す。

    本物の宣言 (attack など) は消す。**そのツール 1 つだけ**を無効化した
    状態で見たいので、他の宣言が混ざると何が効いたのか分からなくなる。
    """
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    raw["disabled_tools"] = [disabled]
    path = tmp_path / f"only_{disabled}.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def _observations_covering_the_interesting_states(runtime) -> list[str]:
    """死体・同席者・所持品が揃った状態の観測を、複数の視点ぶん返す。

    状態が偏ると、その状態でしか出ない宣伝文を見逃す。実際
    `tend_to_player` は**死体が無いと出ない**ので、最初に書いた総当たりは
    これを取り逃がしていた。
    """
    _move(runtime, _KUZE, "storage")
    runtime.do_interact(_KUZE, "supply_shelf", "find_cutter")
    # モリはランタンを持っているので、通路に居ると暗さが足りず襲えない。
    for player_id, spot in (
        (_SENA, "corridor"),
        (_KUZE, "corridor"),
        (_AOI, "corridor"),
        (_MORI, "hall"),
    ):
        _move(runtime, player_id, spot)
    runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

    return [runtime.build_observation(p) for p in (_AOI, _KUZE, _MORI)]


class TestNoDisabledToolIsAdvertisedAnywhere:
    """無効化したツールの名前が、プロンプト全文に出ない。"""

    @pytest.mark.parametrize("tool_name", _TOOL_NAMES)
    def test_the_name_is_absent_from_every_view(self, tmp_path, tool_name) -> None:
        """1 つずつ無効化して、どの視点の観測にも名前が出ない。"""
        runtime = create_world_runtime(_world_with_only(tmp_path, tool_name))

        for observation in _observations_covering_the_interesting_states(runtime):
            assert tool_name not in observation, observation

    def test_the_advertised_set_is_exactly_what_we_expect(self, tmp_path) -> None:
        """全ツールを有効にしたとき、名前が出るのは既知の集合ちょうど。

        **これが無いと、上の総当たりは自分が効いているかを知らないまま
        緑になる。** 宣伝箇所が 1 つも無くても全件通る。

        増えたとき: 誰かがツール名を含む文を書いた。露出判断を通すか、
        この集合に足すかを選ぶ。
        減ったとき: 宣伝が消えた。意図した削除ならこの集合を縮める。

        **限界: fixture が作る状態でしか見えない。** 変異で確かめたところ、
        「食料」カテゴリの表示文にツール名を混ぜても捕まらなかった
        (station_drill に食料が無く、その文字列が描画されない)。会議
        フェーズ・地面のアイテム・モンスター同席・区画のある spot も同様。
        現時点ではいずれも宣伝箇所が無いことを確認済みだが、そこに新しい文が
        生えたら取り逃がす。状態を増やすより、**そもそも本文にツール名を
        書かない**方針 (#892) のほうが効く。
        """
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))
        raw["disabled_tools"] = []
        path = tmp_path / "all_enabled.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        runtime = create_world_runtime(path)

        texts = _observations_covering_the_interesting_states(runtime)
        advertised = {n for n in _TOOL_NAMES if any(n in t for t in texts)}

        assert advertised == _ADVERTISED_TOOLS

    def test_no_remediation_text_names_a_tool(self) -> None:
        """失敗時の対処文が、ツール識別子を名指ししない。

        対処文はプロンプトに載るが、**呼び出し口が 77 か所あり**露出判断を
        渡せない。名指しをやめることで、どの世界でも嘘にならないようにする。

        実際 `GIVE_ITEM_TARGET_DOWN` が `tend_to_player` を勧めていて、
        蘇生の無い station_drill で到達する経路だった (codex の指摘)。
        """
        from ai_rpg_world.application.llm.remediation_mapping import (
            DEFAULT_REMEDIATION_BY_ERROR_CODE,
        )

        for code, text in DEFAULT_REMEDIATION_BY_ERROR_CODE.items():
            for name in _TOOL_NAMES:
                assert name not in text, (code, name, text)


class TestTheDrillNoLongerOffersTending:
    """station_drill から手当てが消えている。"""

    def test_the_corpse_row_does_not_offer_tending(self) -> None:
        """死体の行に「介抱して起こす」が出ない。

        `grace_ticks: 0` は「蘇生の無い世界」の宣言。倒れた同じ tick なら
        まだ手当てが通ってしまうので、engine の猶予判定に頼らずツールごと
        落とす。
        """
        runtime = create_world_runtime(_DRILL)

        for observation in _observations_covering_the_interesting_states(runtime):
            assert "tend_to_player" not in observation
            assert "介抱" not in observation

    def test_looting_the_body_is_still_offered(self) -> None:
        """持ち物を奪うほうは残る。

        消しすぎると死体から何もできなくなり、通報の手前で世界が薄くなる。
        """
        runtime = create_world_runtime(_DRILL)
        observations = _observations_covering_the_interesting_states(runtime)

        assert any("loot_from_downed" in o for o in observations)
