"""シナリオが「この世界では出さないツール」を宣言できることを保証する。

## なぜ要るか

モンスターの居ない世界に ``attack`` が並び続けていた。対象候補が永久に
空なのに毎ターン選択肢に載るので、実 run 007 でインポスターが 3 手を
捨てている (「有効な攻撃対象名: ありません」×3)。

data/scenarios の 27 本中 **19 本にモンスターが 1 体も居ない**。特定の
シナリオの都合ではなく、7 割の世界で死んでいるツールだった。

同じ目で station_drill を見直すと、他にも 2 つ見つかった。``set_sub_location``
は 3 つの spot すべてで区画の宣言が空、``use_item`` は item_specs が 2 つとも
使用効果を持たない (ランタンは持っているだけで効く光源、カッターは前提条件
用の持ち物)。**どちらも対象が永久に存在しない。**

「選べるのに必ず失敗する手を並べない」は #860 で通した判断で、会議を
宣言しない世界から投票系を落とすのも同じ形。違いは**条件をどこに書くか**。

## engine に条件を書かなかった理由

「モンスターが居なければ attack を落とす」と engine に書くこともできた。
そうすると、ツールを 1 つ足すたびに engine へ「どんな世界で無意味か」を
書き足すことになる。**何を出さないかは世界ごとに違う**ので、シナリオが
決める形にした。

## プレフィックスキャッシュ

判定は run 中ずっと変わらないので、設計判断 #1 には触れない。フェーズに
よる出し分けと違い、同じ run の中で並びが揺れることが無い。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import (
    ToolExposureConfigurationError,
    create_world_runtime,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)

_SCENARIOS = Path(__file__).resolve().parents[3] / "data" / "scenarios"
_DRILL = _SCENARIOS / "station_drill.json"
#: モンスターの居る世界。ここでは attack が意味を持つ。
_WITH_MONSTERS = _SCENARIOS / "survival_island_v4_coop.json"


def _tool_names(path: Path, *, as_meeting_phase: bool | None = None) -> set[str]:
    runtime = create_world_runtime(path)
    if as_meeting_phase is None:
        return {d.name for d in runtime.get_tool_definitions(for_every_player=True)}
    return {
        d.name
        for d in runtime.get_tool_definitions(
            as_meeting_phase=as_meeting_phase,
            for_every_player=True,
        )
    }


def _rewritten(tmp_path: Path, disabled, *, source: Path = _DRILL) -> Path:
    raw = json.loads(source.read_text(encoding="utf-8"))
    if disabled is None:
        raw.pop("disabled_tools", None)
    else:
        raw["disabled_tools"] = disabled
    path = tmp_path / "rewritten.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


class TestTheDeclarationRemovesTheTool:
    """宣言したツールが LLM に出なくなる。"""

    def test_the_declared_tool_is_gone(self) -> None:
        """station_drill から attack が消える。"""
        assert "attack" not in _tool_names(_DRILL)

    def test_it_stays_gone_during_a_meeting(self) -> None:
        """会議中も消えたまま。

        フェーズで出し分ける仕組みと**別の軸**なので、片方だけに効いて
        いないかを確かめる。会議中にだけ戻ると、run を回すまで気付かない。
        """
        assert "attack" not in _tool_names(_DRILL, as_meeting_phase=True)
        assert "attack" not in _tool_names(_DRILL, as_meeting_phase=False)

    def test_other_tools_are_untouched(self) -> None:
        """宣言していないツールは今までどおり出る。

        消しすぎると世界が動かなくなる。
        """
        names = _tool_names(_DRILL)

        for expected in ("travel_to", "interact", "speak", "wait"):
            assert expected in names


class TestWorldsWithoutTheDeclaration:
    """宣言の無い世界の挙動は変わらない。"""

    def test_a_world_with_monsters_keeps_attack(self) -> None:
        """モンスターの居る世界では attack が残る。

        **engine 側で「モンスターが居なければ落とす」と決めていない**ので、
        宣言しなければ従来どおり出る。既存シナリオへの影響がゼロである
        ことがここで担保される。
        """
        assert "attack" in _tool_names(_WITH_MONSTERS)

    def test_an_absent_declaration_reads_as_empty(self, tmp_path) -> None:
        """宣言そのものが無ければ、何も落とさない。"""
        scenario = ScenarioLoader().load_from_file(
            _rewritten(tmp_path, None, source=_WITH_MONSTERS)
        )

        assert scenario.disabled_tools == ()


class TestAMisspelledNameStopsTheRun:
    """名前を間違えたら起動を止める。"""

    def test_an_unknown_tool_name_is_rejected(self, tmp_path) -> None:
        """実在しないツール名は起動時に落ちる。

        **黙って無視すると「無効化したつもりが出たまま」になる。** run を
        1 本流し終えてから、無駄手の山を見て初めて気付くことになる。
        """
        with pytest.raises(ToolExposureConfigurationError):
            create_world_runtime(
                _rewritten(tmp_path, ["tend_to_player", "attaack"])
            )

    def test_the_error_lists_what_can_be_written(self, tmp_path) -> None:
        """エラーが、書ける名前の一覧を示す。

        名前を間違えた人が次に要るのは正解の一覧で、「不正な名前です」
        だけでは同じ間違いを繰り返す。
        """
        with pytest.raises(ToolExposureConfigurationError) as caught:
            create_world_runtime(
                _rewritten(tmp_path, ["tend_to_player", "attaack"])
            )

        assert "travel_to" in str(caught.value)


class TestTheShapeIsCheckedAtLoad:
    """書き方の間違いは読み込み時に落とす。"""

    @pytest.mark.parametrize(
        "disabled",
        [
            pytest.param("attack", id="a_bare_string_instead_of_a_list"),
            pytest.param([""], id="an_empty_name"),
            pytest.param([123], id="a_non_string_name"),
            pytest.param(["attack", "attack"], id="a_duplicated_name"),
        ],
    )
    def test_a_malformed_declaration_is_rejected(self, tmp_path, disabled) -> None:
        """リストでない・空・文字列でない・重複は拒否する。

        重複を通さないのは、片方が消し忘れか書き換え漏れのことが多く、
        **どちらの意図か読めない**ため。
        """
        with pytest.raises(ScenarioLoadError):
            ScenarioLoader().load_from_file(_rewritten(tmp_path, disabled))


class TestTheDrillDeclaresIt:
    """station_drill が実際に宣言している。"""

    def test_the_scenario_file_disables_the_dead_tools(self) -> None:
        """シナリオ本体に宣言が書かれている。

        テストが tmp_path の書き換えだけで通ると、**本物のシナリオに
        入れ忘れていても緑になる**。

        3 つとも「この世界では対象が永久に存在しない」もの。

        - ``attack``: モンスターが 1 体も居ない
        - ``set_sub_location``: 3 つの spot すべてで区画の宣言が空
        - ``use_item``: item_specs が 2 つとも使用効果を持たない
          (ランタンは持っているだけで効く光源、カッターは前提条件用)
        """
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))
        declared = raw.get("disabled_tools", [])

        for name in ("attack", "set_sub_location", "use_item"):
            assert name in declared, name

    def test_the_world_still_has_nothing_for_those_tools(self) -> None:
        """宣言の根拠が、いまもシナリオに残っている。

        あとから区画やアイテムの使用効果を足したのに宣言を消し忘れると、
        **足した機能が黙って使えないまま**になる。宣言と世界の中身が
        食い違わないよう、根拠のほうを見張る。
        """
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))

        assert not raw.get("monsters")
        assert not [
            s for s in raw["spots"] if s.get("interior", {}).get("sub_locations")
        ]
        for spec in raw["item_specs"]:
            assert "effects" not in spec and "on_use" not in spec, spec["id"]
