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

#: 名前がプロンプトに残ってよいツールと、その理由。
#:
#: 許可するのは「無効化した世界がそもそも成立しない」ものだけ。「消すのが
#: 面倒」を理由にここへ足すと、このテストは意味を失う。
_ALLOWED_TO_REMAIN = {
    # アイテム分類の説明文 (「近くのオブジェクトに interact して使う」) に
    # 出る。interact を無効化した世界では点検も探索も何もできず、シナリオ
    # として成立しない。行動候補ではなく説明文なので、選ばれることもない。
    "interact": "無効化した世界が成立しない。説明文であって行動候補ではない",
}

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
        if tool_name in _ALLOWED_TO_REMAIN:
            pytest.skip(_ALLOWED_TO_REMAIN[tool_name])

        runtime = create_world_runtime(_world_with_only(tmp_path, tool_name))

        for observation in _observations_covering_the_interesting_states(runtime):
            assert tool_name not in observation, observation

    def test_the_allowlist_only_holds_tools_that_exist(self) -> None:
        """許可リストに、実在しないツール名が残っていない。

        名前が変わったり消えたりしたあとも許可が残ると、**別のツールを
        黙って見逃す**わけではないが、理由の書かれた許可が意味を失う。
        """
        for name in _ALLOWED_TO_REMAIN:
            assert name in _TOOL_NAMES, name


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
