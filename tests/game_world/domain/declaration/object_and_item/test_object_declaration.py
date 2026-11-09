from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ChoiceName,
    ChoiceStateKind,
    ChoiceValue,
    CountStateKind,
    CountValue,
    FlagStateKind,
    FlagValue,
    NoRefill,
    NothingWritten,
    ObjectAppearance,
    ObjectDeclaration,
    ObjectStateKeyDeclaration,
    StateValue,
    StockStateKind,
    StockValue,
    TextBody,
    WrittenText,
    WrittenTextStateKind,
)
from ai_rpg_world.game_world.domain.exception.object_and_item_exception import (
    StateKeyDuplicatedException,
    StateKeyOwnerMismatchException,
    StateValueMismatchesKindException,
)
from ai_rpg_world.game_world.domain.value_object import (
    Count,
    DescriptionText,
    DisplayName,
    ObjectId,
    PersonId,
    SpotId,
    StateKeyId,
    Ticks,
    WorldTick,
)

_LEVER = ObjectId("lift_lever")
_POSITIONS = ChoiceStateKind(choices=(ChoiceName("up"), ChoiceName("down")))
_STOCK = StockStateKind(capacity=Count(3), refills_every=Ticks(10))
_WRITTEN = WrittenText(body=TextBody("北の扉は罠"), author=PersonId("aki"), written_at=WorldTick(4))


def _key(key: str, kind: object, initial: StateValue, object_id: ObjectId = _LEVER) -> ObjectStateKeyDeclaration:
    return ObjectStateKeyDeclaration(object_id=object_id, key=StateKeyId(key), kind=kind, initial=initial)  # type: ignore[arg-type]


def _object(state_keys: tuple[ObjectStateKeyDeclaration, ...], object_id: ObjectId = _LEVER) -> ObjectDeclaration:
    return ObjectDeclaration(
        object_id=object_id,
        spot_id=SpotId("lift_landing"),
        name=DisplayName("レバー"),
        description=DescriptionText("昇降機を動かすレバー"),
        appearance=ObjectAppearance(seen_in_dark=False, hidden_until_revealed=False),
        state_keys=state_keys,
    )


class TestObjectStateKeyInitial:
    """ObjectStateKeyDeclaration が、状態の種類に合う initial のときだけ作れることを保証する。"""

    @pytest.mark.parametrize(
        ("kind", "initial"),
        [
            (FlagStateKind(), FlagValue(raised=False)),
            (CountStateKind(), CountValue(count=Count(0))),
            (_POSITIONS, ChoiceValue(choice=ChoiceName("down"))),
            (_STOCK, StockValue(amount=Count(3))),
            (_STOCK, StockValue(amount=Count(0))),
            (WrittenTextStateKind(), NothingWritten()),
        ],
    )
    def test_initial_matching_kind_is_kept(self, kind: object, initial: StateValue) -> None:
        """種類に合う initial は、そのまま持つ (在庫は上限ちょうどと 0 も合う)。"""
        declaration = _key("position", kind, initial)

        assert declaration.initial == initial

    @pytest.mark.parametrize(
        ("kind", "initial"),
        [
            (CountStateKind(), FlagValue(raised=True)),
            (FlagStateKind(), CountValue(count=Count(1))),
            (FlagStateKind(), StockValue(amount=Count(1))),
            (CountStateKind(), StockValue(amount=Count(1))),
            (StockStateKind(capacity=Count(3), refills_every=NoRefill()), CountValue(count=Count(1))),
            (_POSITIONS, FlagValue(raised=True)),
            (WrittenTextStateKind(), FlagValue(raised=False)),
            (FlagStateKind(), NothingWritten()),
        ],
    )
    def test_initial_of_another_kind_raises_domain_exception(self, kind: object, initial: StateValue) -> None:
        """別の種類の値 (数の鍵に旗の値など) を initial に持つと StateValueMismatchesKindException を投げる。"""
        with pytest.raises(StateValueMismatchesKindException):
            _key("position", kind, initial)

    def test_choice_not_in_declared_choices_raises_domain_exception(self) -> None:
        """選択の鍵の initial が、宣言した選択肢に無い名前だと StateValueMismatchesKindException を投げる。"""
        with pytest.raises(StateValueMismatchesKindException):
            _key("position", _POSITIONS, ChoiceValue(choice=ChoiceName("middle")))

    def test_stock_over_capacity_raises_domain_exception(self) -> None:
        """在庫の鍵の initial が上限を超えると StateValueMismatchesKindException を投げる。"""
        with pytest.raises(StateValueMismatchesKindException):
            _key("ore", _STOCK, StockValue(amount=Count(4)))

    def test_written_text_as_initial_raises_domain_exception(self) -> None:
        """書いた文の鍵は、最初から書かれた文 (WrittenText) を initial に持つと StateValueMismatchesKindException を投げる。"""
        with pytest.raises(StateValueMismatchesKindException):
            _key("note", WrittenTextStateKind(), _WRITTEN)


class TestObjectDeclarationStateKeys:
    """ObjectDeclaration が、自分の物の、重ならない状態の宣言だけを持つことを保証する。"""

    def test_state_keys_keep_the_declared_order(self) -> None:
        """宣言した状態の鍵を、宣言した順のまま持つ。"""
        keys = (
            _key("position", _POSITIONS, ChoiceValue(choice=ChoiceName("down"))),
            _key("pulled", CountStateKind(), CountValue(count=Count(0))),
        )

        assert _object(keys).state_keys == keys

    def test_object_without_state_keys_is_allowed(self) -> None:
        """状態の鍵が 1 つも無い物も作れる。"""
        assert _object(()).state_keys == ()

    def test_same_state_key_twice_raises_domain_exception(self) -> None:
        """1 つの物に同じ StateKeyId が 2 つあると、種類が違っても StateKeyDuplicatedException を投げる。"""
        keys = (
            _key("position", _POSITIONS, ChoiceValue(choice=ChoiceName("down"))),
            _key("position", FlagStateKind(), FlagValue(raised=False)),
        )

        with pytest.raises(StateKeyDuplicatedException):
            _object(keys)

    def test_same_state_key_on_different_objects_is_allowed(self) -> None:
        """同じ StateKeyId を別々の物が持つのは重なりにならない。"""
        door = ObjectId("north_door")

        _object((_key("open", FlagStateKind(), FlagValue(raised=False)),))
        declaration = _object((_key("open", FlagStateKind(), FlagValue(raised=False), object_id=door),), object_id=door)

        assert declaration.state_keys[0].key == StateKeyId("open")

    def test_state_key_of_another_object_raises_domain_exception(self) -> None:
        """object_id がその物と違う状態の宣言を持つと StateKeyOwnerMismatchException を投げる。"""
        keys = (_key("open", FlagStateKind(), FlagValue(raised=False), object_id=ObjectId("north_door")),)

        with pytest.raises(StateKeyOwnerMismatchException):
            _object(keys)


class TestObjectAppearance:
    """ObjectAppearance が、暗がりでも見えるかと、現れるまで隠れているかを別々に持つことを保証する。"""

    def test_appearance_keeps_both_flags(self) -> None:
        """2 つの欄を、宣言したとおり別々に持つ。"""
        appearance = ObjectAppearance(seen_in_dark=True, hidden_until_revealed=False)

        assert (appearance.seen_in_dark, appearance.hidden_until_revealed) == (True, False)
