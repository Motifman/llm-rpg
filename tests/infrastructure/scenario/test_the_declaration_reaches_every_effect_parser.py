"""属性の宣言が、効果を読むすべての入口へ届いていることを保証する。

## なぜこの試験が要るか

次の PR で「**変えられないと宣言した属性を書く効果**を起動時に落とす」検査を
入れる。その検査は効果をパースする側に置くので、**宣言がそこへ届いていない
入口が 1 つでもあると、その入口だけ検査が消える**。

消えても緑のまま進む。「宣言したつもりが効いていない」は、宣言しないより悪い。

## この PR は挙動を変えない

`parse_interaction_effect` は受け取った宣言を**まだ読まない**。ここで見るのは
**配線だけ**である。挙動が変わっていないことは、既存の全シナリオが従来どおり
読めることで示す。

## この試験が見ていないもの

**AST が見るのは literal だけ。** 呼び出し側が「早すぎる時点で組んだ空の
宣言」を変数で渡す形は、ここでは止まらない。それを止めているのはローダーの
読み順であって、実際に効いていることを確かめるのは次の PR の「入口ごとに
落ちる」試験である。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_SRC = Path(__file__).resolve().parents[3] / "src" / "ai_rpg_world"
_SCENARIO_DIR = _SRC / "infrastructure" / "scenario"
_SCENARIOS = Path(__file__).resolve().parents[3] / "data" / "scenarios"

#: 宣言を渡す引数の名前。
_ARG = "player_attribute_specs"


def _functions_that_need_the_declaration() -> frozenset:
    """宣言を引数に取る関数の名前を、**定義から導く**。

    手で並べた表にしない。表にすると、綴り違いの項目は**どの呼び出しにも
    一致しない**まま緑になり、項目を 1 つ落としてもやはり緑になる。実際に
    `#1223` で実在しないツール名を表に混ぜて検査を空振りさせ、この試験の
    最初の版でも「項目を落とす」変異が生き残った。

    定義から導けば、**新しい入口が引数を取った時点で自動的に対象になる**。
    """
    names = set()
    for path in sorted(_SCENARIO_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            declared = [a.arg for a in node.args.args + node.args.kwonlyargs]
            if _ARG in declared:
                names.add(node.name)
    return frozenset(names)


def _calls_in(path: Path) -> List[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)]


def _called_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _relevant_calls() -> List[tuple[Path, ast.Call]]:
    needs_arg = _functions_that_need_the_declaration()
    found: List[tuple[Path, ast.Call]] = []
    for path in sorted(_SCENARIO_DIR.glob("*.py")):
        for call in _calls_in(path):
            if _called_name(call) in needs_arg:
                found.append((path, call))
    return found


class TestEveryCallSitePassesTheDeclaration:
    """宣言を要る呼び出しが、全部それを渡している。"""

    def test_the_argument_is_passed_everywhere(self) -> None:
        """宣言を要る呼び出しに、`player_attribute_specs` が付いている。

        必須のキーワード引数なので渡し忘れは実行時に落ちるが、**落ちるのは
        その経路を通るシナリオを読んだときだけ**。宣言の無いシナリオしか
        試験していない入口は、渡し忘れても緑のまま通る。
        """
        missing = [
            f"{path.name}:{call.lineno} {_called_name(call)}"
            for path, call in _relevant_calls()
            if not any(kw.arg == _ARG for kw in call.keywords)
        ]

        assert missing == []

    def test_no_call_site_passes_an_empty_declaration(self) -> None:
        """空の宣言を literal で渡している呼び出しが無い。

        `PlayerAttributeSpecs.empty()` や `PlayerAttributeSpecs(by_name={})` を
        渡すと、引数は付いているのに**検査は何も見ない**。型では止まらない
        ので、書き方のほうを見る。

        **見えるのは literal だけ。** 変数に入れて渡す形は止まらない。
        """
        suspicious: List[str] = []
        for path, call in _relevant_calls():
            for kw in call.keywords:
                if kw.arg != _ARG:
                    continue
                source = ast.unparse(kw.value)
                if "empty()" in source or "by_name={}" in source:
                    suspicious.append(f"{path.name}:{call.lineno} {source}")

        assert suspicious == []

    def test_the_set_of_functions_is_derived_and_complete(self) -> None:
        """対象の関数が定義から導かれ、既知の入口を全部含む (**正の対照**)。

        手で並べた表を廃したので「実在しない項目」は原理的に入らないが、
        **導き方が壊れて 1 つも拾えなくなる**ことはある。既知の入口が
        含まれているかまで見る。
        """
        needs_arg = _functions_that_need_the_declaration()

        assert len(needs_arg) >= 8
        assert {
            "parse_interaction_effect",
            "parse_interaction_def",
            "parse_scenario_events",
            "parse_synchronized_action_groups",
            "parse_ongoing_conditions",
            "parse_item_interaction_registry",
            "parse_spots_and_graph",
            "parse_interior",
            "parse_spot_object",
            "parse_player_interactions",
        } <= needs_arg

    def test_the_scan_actually_finds_call_sites(self) -> None:
        """走査が実際に呼び出しを拾えている (**正の対照**)。

        これが無いと、上の 2 つは関数名が変わって **1 件も拾えなくなった**
        ときにも緑になる。表で守る検査は、表が空でも緑になる。
        """
        calls = _relevant_calls()
        names = {_called_name(call) for _, call in calls}

        assert len(calls) >= 10
        assert "parse_interaction_effect" in names
        assert "parse_interaction_def" in names


class TestTheWorldsThatDeclareNothingStillLoad:
    """宣言の無いシナリオが、いままでどおり読める (**正の対照**)。

    配線だけの PR なので、**読めなくなっていないこと**が挙動不変の根拠になる。
    """

    @pytest.mark.parametrize(
        "scenario_path",
        sorted(p for p in _SCENARIOS.glob("*.json")),
        ids=lambda p: p.stem,
    )
    def test_the_scenario_still_loads(self, scenario_path: Path) -> None:
        """同梱シナリオが、宣言の有無に関わらず読み込める。"""
        runtime = create_world_runtime(str(scenario_path))

        assert runtime.scenario is not None

    def test_a_scenario_without_the_section_has_no_specs(
        self, tmp_path: Path
    ) -> None:
        """宣言の節が無ければ、空の宣言として読まれる。

        **空で届くこと自体は正しい。** 空だと検査が何も落とさないので、
        既存シナリオの挙動が変わらない。
        """
        raw: Dict[str, Any] = json.loads(
            (_SCENARIOS / "station_drill.json").read_text(encoding="utf-8")
        )
        raw.pop("player_attributes", None)
        path = tmp_path / "no_attrs.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        runtime = create_world_runtime(str(path))

        assert runtime.scenario.player_attribute_specs.by_name == {}
