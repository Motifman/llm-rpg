"""廃坑の山村で物を手に入れたときの文が、その品の正式な名前で書かれていることを保証する。

Issue #1641。金庫の文が「鉄の鍵」と書いていたため、鍵を取った人も周りも「昇降機の起動鍵」という
名前を知る機会が無く、名前の違う懐探りが「持っていない」と断られ続けた。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "mine_village_v1.json"


def _messages_giving(item_spec: str) -> list[str]:
    raw = json.loads(_SCENARIO.read_text(encoding="utf-8"))
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            effects = node.get("effects")
            if isinstance(effects, list) and any(
                e.get("effect_type") == "GIVE_ITEM" and e.get("parameters", {}).get("item_spec") == item_spec
                for e in effects
            ):
                found.extend(
                    e["parameters"]["message"] for e in effects if e.get("effect_type") == "SHOW_MESSAGE"
                )
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(raw)
    return found


@pytest.mark.parametrize(
    ("item_spec", "name"),
    [("lift_key", "昇降機の起動鍵"), ("small_fuel_can", "燃料が少し残った缶")],
)
def test_the_message_names_the_item_given(item_spec: str, name: str) -> None:
    """金庫から鍵を、木箱から缶を取り出す文は、渡す品の正式な名前を含む。"""
    messages = _messages_giving(item_spec)

    assert messages
    assert all(name in m for m in messages), messages
