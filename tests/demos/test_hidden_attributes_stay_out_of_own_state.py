"""`player_attributes` で `visibility: hidden` と宣言した属性は、本人の「自分の状態」にも出ない。

互いの存在を知らずに始まる 2 チーム (廃坑の山村、#1508) では、`team=north` が
本人に出るだけで、対になる側がいそうだと分かる。所属のキーを本人に見せてよいかは
作者にしか分からないので、作者が宣言する (Issue #1546)。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_attribute_spec import (
    AttributeVisibility,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_TOWN = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "market_town_v3_board.json"

_LENA = PlayerId(1)


def _town_with_trade_visibility(tmp_path: Path, visibility: str) -> Any:
    raw: dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    raw["player_attributes"]["trade"]["visibility"] = visibility
    path = tmp_path / f"town_{visibility}.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


def _own_state_line(runtime: Any) -> str:
    lines = runtime.build_llm_context(_LENA).current_state_text.splitlines()
    return next((line for line in lines if line.startswith("自分の状態:")), "")


def _oven_line(runtime: Any) -> str:
    runtime.do_move(_LENA, "bake_house")
    for _ in range(2):
        runtime.advance_tick()
    lines = runtime.build_llm_context(_LENA).current_state_text.splitlines()
    return next(line for line in lines if '"石窯"' in line)


class TestHiddenAttributeDeclaration:
    """`visibility: hidden` の宣言が読め、本人の表示と物体の注記の両方から属性を外すことを保証する。"""

    def test_hidden_visibility_is_read_as_hidden(self, tmp_path: Path) -> None:
        """`visibility` に `hidden` と書くと、属性の宣言は `AttributeVisibility.HIDDEN` になる。"""
        runtime = _town_with_trade_visibility(tmp_path, "hidden")

        spec = runtime.scenario.player_attribute_specs.spec_of("trade")

        assert spec.visibility is AttributeVisibility.HIDDEN

    def test_public_attribute_still_shows_in_own_state(self, tmp_path: Path) -> None:
        """`public` と宣言した属性は、これまでどおり本人の「自分の状態」に `trade=picker` の形で出る。"""
        runtime = _town_with_trade_visibility(tmp_path, "public")

        assert "trade=picker" in _own_state_line(runtime)

    def test_hidden_attribute_is_left_out_of_own_state(self, tmp_path: Path) -> None:
        """`hidden` と宣言した属性のキーは、本人の現在の状況のどこにも `trade=` の形で出ない。"""
        runtime = _town_with_trade_visibility(tmp_path, "hidden")

        text = runtime.build_llm_context(_LENA).current_state_text

        assert "trade=" not in text

    def test_hidden_attribute_is_not_named_in_object_notes(self, tmp_path: Path) -> None:
        """`hidden` と宣言した属性の要求は、`secret` と同じく石窯の注記に呼び名で出ない。`public` なら「焼き手だけが扱える」と出る。"""
        public_line = _oven_line(_town_with_trade_visibility(tmp_path, "public"))
        hidden_line = _oven_line(_town_with_trade_visibility(tmp_path, "hidden"))

        assert "焼き手だけが扱える" in public_line
        assert "焼き手" not in hidden_line
