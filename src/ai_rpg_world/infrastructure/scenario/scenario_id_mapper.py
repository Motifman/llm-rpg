"""文字列 ID ↔ 数値 ID の双方向マッピング。

シナリオ JSON では人間が読みやすい文字列 ID を使い、
ドメインオブジェクト構築時に一貫した数値 ID へ変換する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


class ScenarioIdMappingError(Exception):
    """ID マッピング時のエラー。"""


@dataclass
class _Namespace:
    _next_id: int = 1
    _str_to_int: Dict[str, int] = field(default_factory=dict)
    _int_to_str: Dict[int, str] = field(default_factory=dict)

    def register(self, string_id: str) -> int:
        if string_id in self._str_to_int:
            return self._str_to_int[string_id]
        numeric = self._next_id
        self._next_id += 1
        self._str_to_int[string_id] = numeric
        self._int_to_str[numeric] = string_id
        return numeric

    def get_int(self, string_id: str) -> int:
        try:
            return self._str_to_int[string_id]
        except KeyError:
            raise ScenarioIdMappingError(
                f"Unknown string ID: {string_id!r}"
            ) from None

    def get_str(self, numeric_id: int) -> str:
        try:
            return self._int_to_str[numeric_id]
        except KeyError:
            raise ScenarioIdMappingError(
                f"Unknown numeric ID: {numeric_id}"
            ) from None

    def contains_str(self, string_id: str) -> bool:
        return string_id in self._str_to_int


class ScenarioIdMapper:
    """名前空間ごとに独立した文字列⇔数値 ID マッピングを管理する。"""

    _NAMESPACES = (
        "spot", "connection", "object", "sub_location", "item_spec", "player",
        # Phase B-2a: モンスター種別 ID。シナリオ JSON 内の文字列 ("wild_dog" 等)
        # を MonsterTemplateId(int) に対応付ける。
        "monster_template",
        # PR #1 動的 loot: LootTable の文字列 ID ("deep_fishing_loot" 等) を
        # LootTableId(int) に対応付ける。
        "loot_table",
    )

    def __init__(self) -> None:
        self._ns: Dict[str, _Namespace] = {n: _Namespace() for n in self._NAMESPACES}

    def register(self, namespace: str, string_id: str) -> int:
        return self._get_ns(namespace).register(string_id)

    def get_int(self, namespace: str, string_id: str) -> int:
        return self._get_ns(namespace).get_int(string_id)

    def get_str(self, namespace: str, numeric_id: int) -> str:
        return self._get_ns(namespace).get_str(numeric_id)

    def contains(self, namespace: str, string_id: str) -> bool:
        return self._get_ns(namespace).contains_str(string_id)

    def _get_ns(self, namespace: str) -> _Namespace:
        try:
            return self._ns[namespace]
        except KeyError:
            raise ScenarioIdMappingError(
                f"Unknown namespace: {namespace!r}. "
                f"Valid namespaces: {sorted(self._NAMESPACES)}"
            ) from None
