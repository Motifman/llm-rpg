"""JsonUnion・enum・順序つきの列の部品が、どの型か・どの名前かを書き分け、分からない JSON をはっきり止めることを保証する。"""

from __future__ import annotations

from enum import Enum

import pytest

from ai_rpg_world.game_world.domain.person.person_vitals import NotBusy
from ai_rpg_world.game_world.domain.value_object import WorldTick
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    JsonUnion,
    JsonUnionMember,
    enum_from_json,
    enum_to_json,
    json_int,
    ordered_items,
    world_tick_from_json,
)
from ai_rpg_world.game_world.infrastructure.persistence.stored_memento_exception import (
    MementoNotStorableException,
    StoredMementoUnreadableException,
)

_BUSY_UNTIL: JsonUnion[WorldTick | NotBusy] = JsonUnion(
    JsonUnionMember("world_tick", WorldTick, lambda tick: tick.value, world_tick_from_json),
    JsonUnionMember.fieldless("not_busy", NotBusy()),
)


class _Door(Enum):
    OPEN = "open"
    SHUT = "shut"
    CLOSED = "shut"


class TestJsonUnion:
    """JsonUnion が、型の印を 1 つだけのキーにして値を包み、印から型を選んで読むことを保証する。"""

    def test_value_is_wrapped_in_an_object_keyed_by_its_tag(self) -> None:
        """WorldTick(7) は、印 world_tick をキーに、7 を値にした object になる。"""
        assert _BUSY_UNTIL.to_json(WorldTick(7)) == {"world_tick": 7}

    def test_fieldless_member_is_written_as_an_empty_object(self) -> None:
        """中身の無い NotBusy は、印 not_busy に空の object を添えて書く。"""
        assert _BUSY_UNTIL.to_json(NotBusy()) == {"not_busy": {}}

    @pytest.mark.parametrize("value", [WorldTick(7), NotBusy()])
    def test_each_member_survives_a_round_trip(self, value: WorldTick | NotBusy) -> None:
        """どちらの型の値も、書いて読み戻すと同じ値になる。"""
        assert _BUSY_UNTIL.from_json(_BUSY_UNTIL.to_json(value)) == value

    def test_unknown_tag_is_refused(self) -> None:
        """知らない印の object は、その印の名前を添えて止まる。"""
        with pytest.raises(StoredMementoUnreadableException, match="sleeping"):
            _BUSY_UNTIL.from_json({"sleeping": {}})

    def test_object_without_a_tag_is_refused(self) -> None:
        """印の無い空の object は、どの型でもないとして止まる。"""
        with pytest.raises(StoredMementoUnreadableException, match="one of"):
            _BUSY_UNTIL.from_json({})

    def test_object_with_two_tags_is_refused(self) -> None:
        """印が 2 つある object は、どちらかを選ばずに止まる。"""
        with pytest.raises(StoredMementoUnreadableException, match="one of"):
            _BUSY_UNTIL.from_json({"world_tick": 3, "not_busy": {}})

    def test_bare_value_without_a_tag_is_refused(self) -> None:
        """印で包まずに 3 とだけ書かれた値は、tick として読まずに止まる。"""
        with pytest.raises(StoredMementoUnreadableException, match="one of"):
            _BUSY_UNTIL.from_json(3)

    def test_fieldless_member_with_a_field_is_refused(self) -> None:
        """中身の無い型の印に、知らないキーが書かれていると止まる。"""
        with pytest.raises(StoredMementoUnreadableException, match="since"):
            _BUSY_UNTIL.from_json({"not_busy": {"since": 3}})

    def test_value_of_a_type_not_in_the_union_is_not_stored(self) -> None:
        """対応表に無い型の値を書こうとすると、黙って捨てずに MementoNotStorableException で止まる。"""
        with pytest.raises(MementoNotStorableException, match="str"):
            _BUSY_UNTIL.to_json("soon")  # type: ignore[arg-type]

    def test_same_tag_listed_twice_is_refused(self) -> None:
        """同じ印を 2 つの型に使った JsonUnion は作れない。"""
        with pytest.raises(ValueError, match="world_tick"):
            JsonUnion(
                JsonUnionMember("world_tick", WorldTick, lambda tick: tick.value, world_tick_from_json),
                JsonUnionMember.fieldless("world_tick", NotBusy()),
            )

    def test_same_type_listed_twice_is_refused(self) -> None:
        """同じ型を 2 つの印で書く JsonUnion は作れない。"""
        with pytest.raises(ValueError, match="NotBusy"):
            JsonUnion(JsonUnionMember.fieldless("not_busy", NotBusy()), JsonUnionMember.fieldless("idle", NotBusy()))


class TestEnum:
    """enum を、値ではなくメンバーの名前で書いて読むことを保証する。"""

    def test_enum_is_written_by_its_member_name(self) -> None:
        """値が "open" のメンバー OPEN は、名前の "OPEN" と書く。"""
        assert enum_to_json(_Door.OPEN) == "OPEN"

    def test_enum_survives_a_round_trip(self) -> None:
        """書いた名前を読み戻すと、同じメンバーになる。"""
        assert enum_from_json(enum_to_json(_Door.SHUT), _Door) is _Door.SHUT

    def test_name_not_in_the_enum_is_refused(self) -> None:
        """enum に無い名前は、その名前を添えて止まる。"""
        with pytest.raises(StoredMementoUnreadableException, match="AJAR"):
            enum_from_json("AJAR", _Door)

    def test_value_instead_of_name_is_refused(self) -> None:
        """名前ではなく値の "open" が書かれていると、読み替えずに止まる。"""
        with pytest.raises(StoredMementoUnreadableException, match="open"):
            enum_from_json("open", _Door)

    def test_alias_name_is_refused(self) -> None:
        """別名の CLOSED は、書き戻すと SHUT になって行が変わるので、正規の名前でないとして止まる。"""
        with pytest.raises(StoredMementoUnreadableException, match="CLOSED"):
            enum_from_json("CLOSED", _Door)

    def test_non_string_is_refused(self) -> None:
        """文字列でない値は止まる。"""
        with pytest.raises(StoredMementoUnreadableException):
            enum_from_json(1, _Door)


class TestOrderedItems:
    """順序つきの列を、並びも重なりもそのまま読むことを保証する。"""

    def test_items_keep_their_order(self) -> None:
        """[3, 1, 2] は、並べ替えずに (3, 1, 2) として読む。"""
        assert ordered_items([3, 1, 2], json_int) == (3, 1, 2)

    def test_repeated_items_are_kept(self) -> None:
        """同じ値が 2 度並んでも畳まずに残す。重なりを断るかは memento と集約が決める。"""
        assert ordered_items([1, 1], json_int) == (1, 1)

    def test_non_list_is_refused(self) -> None:
        """列でない値は止まる。"""
        with pytest.raises(StoredMementoUnreadableException, match="list"):
            ordered_items({"a": 1}, json_int)

    def test_unreadable_item_is_refused(self) -> None:
        """列の中に読めない要素があると止まる。"""
        with pytest.raises(StoredMementoUnreadableException):
            ordered_items([1, "two"], json_int)
