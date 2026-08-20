"""宣言に無い値を使う宣言を、起動時に落とす。

## なぜこの試験が要るか

`player_attributes` は取りうる値を書ける。ところが `values` を書いても、
**どこもそれを見ていなかった**。`"bakerr"` と書き間違えても世界は起動し、その
条件は**誰にも満たせないまま**残る。実行時にも落ちない — 単に一度も成立しない。

## 「永久に無理」の 2 種類を混ぜない

**世界の誰か 1 人でも満たせるか**で分かれる。落とすのは後者だけ。

| 形 | 扱い | なぜ |
|---|---|---|
| `{"trade": "baker"}` を摘み手が要求される | **正しい世界** | 焼き手なら満たせる。**満たせる人が居る** |
| `{"trade": "bakerr"}` (`values` に無い) | **落とす** | **誰も満たせない**。書き間違いしかありえない |

前者は職能の設計そのもので、#1220 の注記 (`焼き手だけが扱える`) が担当する。
**混ぜてはいけない。** 混ぜると、次に触る人が注記の側を「落とすべき」と読む。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"
_TOWN = _SCENARIOS / "market_town_v3_board.json"

#: 市場町が宣言している値のどれでもない、書き間違いの値。
_TYPO = "bakerr"
#: 宣言されている値。
_REAL = "baker"


def _oven(raw: Dict[str, Any]) -> Dict[str, Any]:
    for spot in raw["spots"]:
        for obj in spot.get("interior", {}).get("objects", []):
            if obj["name"] == "石窯":
                return obj
    raise AssertionError("石窯がシナリオから消えています")


def _load(tmp_path: Path, mutate: Callable[[Dict[str, Any]], None]) -> Any:
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "town.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


def _refused_for_the_value(error: Exception, where: str) -> bool:
    """**狙った理由で**落ちたか。

    箇所ごとの検査は、その箇所の名前がメッセージに出れば緑になってしまう。
    書き間違いなど別の誤りでも同じ名前が出るので、値の検査が働いたことまで
    見る。
    """
    message = str(error)
    return where in message and _TYPO in message and "書ける値" in message


def _use_typo_in_initial_state(raw: Dict[str, Any]) -> None:
    raw["players"][0]["initial_state"] = {"trade": _TYPO}


def _use_typo_in_effect(raw: Dict[str, Any]) -> None:
    _oven(raw)["interactions"][0]["effects"].append({
        "effect_type": "CHANGE_PLAYER_STATE",
        "parameters": {"state_updates": {"trade": _TYPO}},
    })


def _use_typo_in_precondition(raw: Dict[str, Any]) -> None:
    _oven(raw)["interactions"][0]["preconditions"][0] = {
        "condition_type": "PLAYER_STATE_IS",
        "required_state": {"trade": _TYPO},
        "failure_message": "焼き手にしか扱えない。",
    }


def _use_typo_in_target_precondition(raw: Dict[str, Any]) -> None:
    raw["player_interactions"] = [{
        "action_name": "hand_over_the_dough",
        "display_label": "生地を渡す",
        "preconditions": [{
            "condition_type": "TARGET_PLAYER_STATE_IS",
            "required_state": {"trade": _TYPO},
            "failure_message": "相手が焼き手でなければ意味がない。",
        }],
        "effects": [{
            "effect_type": "SHOW_MESSAGE",
            "target": "TARGET_PLAYER",
            "parameters": {"message": "生地を受け取った。"},
        }],
    }]


class TestAValueTheWorldDoesNotHaveStopsTheWorld:
    """宣言に無い値は、書かれた場所によらず落ちる。"""

    @pytest.mark.parametrize("mutate, where", [
        (_use_typo_in_initial_state, "initial_state"),
        (_use_typo_in_effect, "CHANGE_PLAYER_STATE"),
        (_use_typo_in_precondition, "PLAYER_STATE_IS"),
        (_use_typo_in_target_precondition, "TARGET_PLAYER_STATE_IS"),
    ], ids=["initial_state", "effect", "precondition", "target_precondition"])
    def test_the_typo_is_refused(
        self, tmp_path: Path, mutate: Callable[[Dict[str, Any]], None], where: str,
    ) -> None:
        """4 つの書き場所すべてで落ちる。

        1 つでも漏れると、**誰にも満たせない条件**や**誰も到達できない値**が
        黙って残る。実行時にも落ちないので、run を 1 本流して「なぜか一度も
        成立しない」として初めて気付くことになる。
        """
        with pytest.raises(ScenarioLoadError) as caught:
            _load(tmp_path, mutate)

        assert _refused_for_the_value(caught.value, where)

    def test_the_message_lists_what_can_be_written(self, tmp_path: Path) -> None:
        """メッセージが、書ける値を全部並べる。

        「不正です」だけでは、書いた人は次に何を書けばよいか分からない。
        **断るときは行き先を教える** (#1203) を起動時の失敗にも当てる。
        """
        with pytest.raises(ScenarioLoadError) as caught:
            _load(tmp_path, _use_typo_in_initial_state)

        message = str(caught.value)
        for value in ("picker", "baker", "reaper"):
            assert value in message

    def test_the_message_says_where_it_is_declared(self, tmp_path: Path) -> None:
        """前提条件のエラーに、どの操作かが入る。

        物体に操作が複数あると、物体までしか分からないと探す手間が残る。
        `preconditions` は `declaring()` の外にあって操作名が付いていなかった。
        """
        with pytest.raises(ScenarioLoadError) as caught:
            _load(tmp_path, _use_typo_in_precondition)

        message = str(caught.value)
        assert "bake_bread" in message
        assert "stone_oven" in message


class TestTheWorldThatIsMerelyHardStaysAllowed:
    """満たせる人が居る条件は、落とさない。"""

    def test_a_requirement_only_someone_else_can_meet_is_fine(
        self, tmp_path: Path
    ) -> None:
        """摘み手に焼き手を要求する条件は、**正しい世界**である。

        その人には永久に無理だが、**焼き手なら満たせる**。市場町の職能設計
        そのもので、ここを落とすと世界が成り立たない。表示で伝えるのは
        #1220 の注記の仕事。
        """
        runtime = _load(tmp_path, lambda raw: None)
        picker = runtime._player_status_repo.find_by_id(PlayerId(1))

        assert picker.state == {"trade": "picker"}
        assert any(
            spawn.initial_state.get("trade") == _REAL
            for spawn in runtime.scenario.player_spawns
        )

    def test_a_declared_value_is_accepted(self, tmp_path: Path) -> None:
        """宣言されている値なら通る (**正の対照**)。

        これが無いと、上の検査は「値を書くと必ず落ちる」でも緑になる。
        """
        def mutate(raw: Dict[str, Any]) -> None:
            _oven(raw)["interactions"][0]["preconditions"][0] = {
                "condition_type": "PLAYER_STATE_IS",
                "required_state": {"trade": _REAL},
                "failure_message": "焼き手にしか扱えない。",
            }

        assert _load(tmp_path, mutate).scenario is not None

    def test_an_attribute_without_declared_values_accepts_anything(
        self, tmp_path: Path
    ) -> None:
        """`values` を宣言していない属性は、どの値でも通る。

        数値や時刻のように**列挙のしようがない属性**がある。宣言していない
        ことを誤りにしない。
        """
        def mutate(raw: Dict[str, Any]) -> None:
            raw["player_attributes"]["mood"] = {
                "display_name": "機嫌",
                "visibility": "public",
                "mutable": True,
            }
            for spawn in raw["players"]:
                spawn.setdefault("initial_state", {})["mood"] = "なんでもよい"

        assert _load(tmp_path, mutate).scenario is not None

    def test_an_undeclared_attribute_accepts_anything(self, tmp_path: Path) -> None:
        """宣言の無い属性は、従来どおり何でも書ける。"""
        def mutate(raw: Dict[str, Any]) -> None:
            for spawn in raw["players"]:
                spawn.setdefault("initial_state", {})["whatever"] = "x"

        assert _load(tmp_path, mutate).scenario is not None

    def test_every_shipped_scenario_still_loads(self) -> None:
        """同梱シナリオが全件読める (**正の対照**)。"""
        for path in sorted(_SCENARIOS.glob("*.json")):
            assert create_world_runtime(str(path)).scenario is not None
