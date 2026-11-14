"""いくつもの memento の変換で使う JSON の部品が、型の違う値を通さないことを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    exact_fields,
    json_bool,
    json_int,
    json_str,
    keyed_items,
)
from ai_rpg_world.game_world.infrastructure.persistence.stored_memento_exception import (
    StoredMementoUnreadableException,
)


def test_json_int_refuses_true() -> None:
    """json_int は true を 1 として読まずに StoredMementoUnreadableException で止まる。"""
    with pytest.raises(StoredMementoUnreadableException):
        json_int(True)


def test_json_bool_refuses_one() -> None:
    """json_bool は 1 を true として読まずに止まる。"""
    with pytest.raises(StoredMementoUnreadableException):
        json_bool(1)


def test_json_str_refuses_a_number() -> None:
    """json_str は数を文字列として読まずに止まる。"""
    with pytest.raises(StoredMementoUnreadableException):
        json_str(3)


def test_exact_fields_refuses_keys_of_mixed_types_as_unknown() -> None:
    """数と文字列の知らないキーが混ざった object も、並べ替えで別の例外にならずに StoredMementoUnreadableException で止まる。"""
    with pytest.raises(StoredMementoUnreadableException, match="unknown"):
        exact_fields({1: "a", "speed": 2, "now": 0}, ("now",))


def test_keyed_items_reads_an_object_as_keys_and_values() -> None:
    """keyed_items は object のキーと値を、それぞれ渡した関数で読んだ対応表にする。"""
    items = keyed_items({"actor": 1, "target": 2}, str.upper, json_int)

    assert items == {"ACTOR": 1, "TARGET": 2}


def test_keyed_items_refuses_a_list() -> None:
    """keyed_items はキーと値の組の列を object として読まずに止まる。"""
    with pytest.raises(StoredMementoUnreadableException, match="expected an object"):
        keyed_items([["actor", 1]], str, json_int)


def test_keyed_items_refuses_keys_read_as_the_same_key() -> None:
    """2 つのキーが同じキーとして読まれると、後の値で上書きせずに止まる。"""
    with pytest.raises(StoredMementoUnreadableException, match="same key"):
        keyed_items({"actor": 1, "ACTOR": 2}, str.lower, json_int)
