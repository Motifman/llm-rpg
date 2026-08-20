"""変えられないと宣言した属性を書く効果を、起動時に落とす。

## なぜこの試験が要るか

#1219 で「その属性は変えられない」を宣言できるようにし、#1220 でそれを表示へ
出した。**ところが、書き換える効果はそのまま書けた。**

書けてしまう状態は、**宣言しないより悪い**。「変えられない」と読んで諦めた
行為が、別の宣言では成立する。世界の規則が場所によって違うことになる。

## 何を落とすか

本人の自由 state を書く効果は 2 つある (`acting_player_status.merge_state` の
呼び出し元を数えた)。

| effect | 書くもの |
|---|---|
| `CHANGE_PLAYER_STATE` | `parameters.state_updates` を merge |
| `RECORD_PLAYER_STATE_TICK` | `state[state_key] = 現在 tick` |

**`RECORD_PLAYER_STATE_TICK` を忘れない。** 書き込むのが tick の数値なので、
生業が数値で上書きされるという**分かりにくい壊れ方**をする。

## 何を落とさないか

- **`initial_state`** — 初期値は変更ではない。`mutable: false` は「途中で
  変わらない」であって「初めから無い」ではない
- **宣言の無い属性** — 従来どおり書ける。新しい規則を既定にしない
- **`mutable: true`** — 変えられると宣言してあるので書ける
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"
_TOWN = _SCENARIOS / "market_town_v3_board.json"

#: 市場町が宣言している、変えられない属性。
_UNCHANGEABLE = "trade"

_WRITE_IT = {
    "effect_type": "CHANGE_PLAYER_STATE",
    "parameters": {"state_updates": {_UNCHANGEABLE: "baker"}},
}
_STAMP_IT = {
    "effect_type": "RECORD_PLAYER_STATE_TICK",
    "parameters": {"state_key": _UNCHANGEABLE},
}


def _oven(raw: Dict[str, Any]) -> Dict[str, Any]:
    for spot in raw["spots"]:
        for obj in spot.get("interior", {}).get("objects", []):
            if obj["name"] == "石窯":
                return obj
    raise AssertionError("石窯がシナリオから消えています")


def _refused_for_the_attribute(error: Exception, where: str) -> bool:
    """**狙った理由で**落ちたか。

    入口ごとの検査は、その入口の名前がメッセージに出れば緑になってしまう。
    書き間違いなど**別の誤りで落ちても**同じ名前が出るので、属性の検査が
    働いたことまで見る。
    """
    message = str(error)
    return where in message and _UNCHANGEABLE in message and "mutable" in message


def _load(tmp_path: Path, mutate: Callable[[Dict[str, Any]], None]) -> Any:
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "town.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


class TestWritingWhatCannotChangeStopsTheWorld:
    """変えられない属性を書く効果は、起動時に落ちる。"""

    @pytest.mark.parametrize(
        "effect", [_WRITE_IT, _STAMP_IT], ids=["change", "record_tick"]
    )
    def test_both_writers_are_refused(
        self, tmp_path: Path, effect: Dict[str, Any]
    ) -> None:
        """本人 state を書く 2 つの効果が、どちらも落ちる。

        `RECORD_PLAYER_STATE_TICK` は書き込むのが tick の数値なので、
        **生業が数値で上書きされる**という分かりにくい壊れ方をする。
        """
        with pytest.raises(ScenarioLoadError) as caught:
            _load(tmp_path, lambda raw: _oven(raw)["interactions"][0]["effects"].append(effect))

        assert _UNCHANGEABLE in str(caught.value)

    def test_the_message_says_where_it_is_declared(self, tmp_path: Path) -> None:
        """落ちるときのメッセージが、シナリオ内のどこかを指す。

        属性名だけだと、同じ `action_name` が複数の spot にある世界で
        探す手間が残る。**断るときは行き先を教える** (#1203) を、起動時の
        失敗にも当てる。
        """
        with pytest.raises(ScenarioLoadError) as caught:
            _load(tmp_path, lambda raw: _oven(raw)["interactions"][0]["effects"].append(_WRITE_IT))

        message = str(caught.value)
        assert "bake_house" in message
        assert "stone_oven" in message
        assert "bake_bread" in message

    def test_the_message_keeps_the_original_reason(self, tmp_path: Path) -> None:
        """位置を足しても、元の理由が残っている。

        投げ直しで元の文を捨てると、**言い換えて意味が変わった失敗**になる。
        直し方 (`mutable` を true にするか、効果をやめる) まで残す。
        """
        with pytest.raises(ScenarioLoadError) as caught:
            _load(tmp_path, lambda raw: _oven(raw)["interactions"][0]["effects"].append(_WRITE_IT))

        message = str(caught.value)
        assert "CHANGE_PLAYER_STATE" in message
        assert "生業" in message
        assert "mutable" in message


class TestWhatIsStillAllowed:
    """落としてはいけないものを落としていない。"""

    def test_a_changeable_attribute_can_be_written(self, tmp_path: Path) -> None:
        """`mutable: true` の属性は書ける (**正の対照**)。

        これが無いと、上の検査は「効果を足すと必ず落ちる」でも緑になる。
        """
        def mutate(raw: Dict[str, Any]) -> None:
            raw["player_attributes"]["mood"] = {
                "display_name": "機嫌",
                "visibility": "public",
                "mutable": True,
            }
            _oven(raw)["interactions"][0]["effects"].append({
                "effect_type": "CHANGE_PLAYER_STATE",
                "parameters": {"state_updates": {"mood": "calm"}},
            })

        assert _load(tmp_path, mutate).scenario is not None

    def test_an_undeclared_attribute_can_be_written(self, tmp_path: Path) -> None:
        """宣言していない属性は、従来どおり書ける。

        **新しい規則を既定にしない。** 既定を変えると、過去の run と
        比べられなくなる。
        """
        def mutate(raw: Dict[str, Any]) -> None:
            _oven(raw)["interactions"][0]["effects"].append({
                "effect_type": "CHANGE_PLAYER_STATE",
                "parameters": {"state_updates": {"whatever": "x"}},
            })

        assert _load(tmp_path, mutate).scenario is not None

    def test_the_initial_state_may_hold_it(self, tmp_path: Path) -> None:
        """`initial_state` が変えられない属性を持っていても通る。

        **初期値は変更ではない。** `mutable: false` は「途中で変わらない」で
        あって「初めから無い」ではない。市場町はまさにこの形で生業を配って
        いる (**正の対照**)。
        """
        runtime = _load(tmp_path, lambda raw: None)

        assert all(
            _UNCHANGEABLE in spawn.initial_state
            for spawn in runtime.scenario.player_spawns
        )

    def test_a_condition_on_it_is_fine(self, tmp_path: Path) -> None:
        """その属性を**条件**にする宣言は通る。

        条件であって効果ではない。市場町の全作業がこの形なので、落ちたら
        シナリオが読めない (**正の対照**)。
        """
        def mutate(raw: Dict[str, Any]) -> None:
            _oven(raw)["interactions"][0]["preconditions"].append({
                "condition_type": "PLAYER_STATE_IS",
                "required_state": {_UNCHANGEABLE: "baker"},
                "failure_message": "焼き手にしか扱えない。",
            })

        assert _load(tmp_path, mutate).scenario is not None

    def test_every_shipped_scenario_still_loads(self) -> None:
        """同梱シナリオが全件読める (**正の対照**)。"""
        for path in sorted(_SCENARIOS.glob("*.json")):
            assert create_world_runtime(str(path)).scenario is not None


class TestEveryEntryPointRefusesIt:
    """効果を宣言できる入口すべてで落ちる。

    **1 つでも漏れると「変えられないと宣言したのに変わる」が残る。** 入口ごとに
    名指しで見ていないと、1 つ配線を忘れても他の入口の試験が緑にし続ける。
    """

    def test_an_object_interaction_is_refused(self, tmp_path: Path) -> None:
        """物体の操作で落ちる。"""
        with pytest.raises(ScenarioLoadError) as caught:
            _load(tmp_path, lambda raw: _oven(raw)["interactions"][0]["effects"].append(_WRITE_IT))

        assert _refused_for_the_attribute(caught.value, "stone_oven")

    def test_a_player_interaction_is_refused(self, tmp_path: Path) -> None:
        """対人 action で落ちる。"""
        def mutate(raw: Dict[str, Any]) -> None:
            raw["player_interactions"] = [{
                "action_name": "teach_baking",
                "display_label": "焼き方を教える",
                "effects": [dict(_WRITE_IT, target="TARGET_PLAYER")],
            }]

        with pytest.raises(ScenarioLoadError) as caught:
            _load(tmp_path, mutate)

        assert _refused_for_the_attribute(caught.value, "player_interactions")

    def test_an_item_interaction_is_refused(self, tmp_path: Path) -> None:
        """アイテムの操作で落ちる。"""
        def mutate(raw: Dict[str, Any]) -> None:
            bread = next(i for i in raw["item_specs"] if i["id"] == "bread")
            bread["interactions"] = [{
                "action_name": "study_the_loaf",
                "display_label": "パンを調べる",
                "effects": [_WRITE_IT],
            }]

        with pytest.raises(ScenarioLoadError) as caught:
            _load(tmp_path, mutate)

        assert _refused_for_the_attribute(caught.value, "bread")

    def test_a_scenario_event_is_refused(self, tmp_path: Path) -> None:
        """時限イベントで落ちる。

        イベントには spot も物体も無いので、**イベント id** が位置になる。
        """
        def mutate(raw: Dict[str, Any]) -> None:
            raw["scenario_events"] = [{
                "id": "the_calling",
                "conditions": [{"condition_type": "TICK_AT_LEAST", "tick": 10}],
                "effects": [_WRITE_IT],
            }]

        with pytest.raises(ScenarioLoadError) as caught:
            _load(tmp_path, mutate)

        assert _refused_for_the_attribute(caught.value, "the_calling")


class TestABugInTheCodeIsNotBlamedOnTheScenario:
    """コードのバグを、シナリオの誤りとして報告しない。"""

    def test_an_unexpected_error_keeps_its_type(self) -> None:
        """読み込み以外の例外は、位置を足されずそのまま抜ける。

        位置を足す処理が `Exception` を広く捕まえると、`KeyError` のような
        **コードのバグが「あなたのシナリオが間違っています」に化ける**。
        静かな失敗より厄介で、**嘘の診断が付いた騒がしい失敗**は読んだ人を
        シナリオの方へ何時間も歩かせる。
        """
        from ai_rpg_world.infrastructure.scenario.declaration_site import declaring

        with pytest.raises(KeyError):
            with declaring("spot 'x' の"):
                raise KeyError("コードのバグ")

    def test_a_load_error_keeps_its_type(self) -> None:
        """読み込みエラーの型は、投げ直しても変わらない。

        型が変わると、それを名指しで捕まえている既存の検査が黙って外れる。
        """
        from ai_rpg_world.infrastructure.scenario.declaration_site import declaring

        with pytest.raises(ScenarioLoadError) as caught:
            with declaring("spot 'x' の"):
                raise ScenarioLoadError("元の理由")

        assert type(caught.value) is ScenarioLoadError
        assert "元の理由" in str(caught.value)
        assert "spot 'x' の" in str(caught.value)
