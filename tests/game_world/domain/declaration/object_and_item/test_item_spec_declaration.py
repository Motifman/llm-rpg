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
    ItemSpecDeclaration,
    ItemStateKeyDeclaration,
    Lasts,
    LastsIndefinitely,
    LitWhen,
    NoRefill,
    NotALightSource,
    NothingWritten,
    StateValue,
    StockStateKind,
    StockValue,
    WrittenTextStateKind,
)
from ai_rpg_world.game_world.domain.exception.object_and_item_declaration_exception import (
    ItemStateKindNotAllowedException,
    LastingTicksBelowOneException,
    LightKeyNotDeclaredException,
    StateKeyDuplicatedException,
    StateKeyOwnerMismatchException,
    StateValueMismatchesKindException,
)
from ai_rpg_world.game_world.domain.value_object import (
    Count,
    DescriptionText,
    DisplayName,
    HandsNeeded,
    ItemSpecId,
    StateKeyId,
    Ticks,
)

_LANTERN = ItemSpecId("lantern")
_WICK = ChoiceStateKind(choices=(ChoiceName("unlit"), ChoiceName("lit")))


def _key(key: str, kind: object, initial: StateValue, item_spec_id: ItemSpecId = _LANTERN) -> ItemStateKeyDeclaration:
    return ItemStateKeyDeclaration(item_spec_id=item_spec_id, key=StateKeyId(key), kind=kind, initial=initial)  # type: ignore[arg-type]


_LIT_FLAG = _key("lit", FlagStateKind(), FlagValue(raised=False))


def _item(
    state_keys: tuple[ItemStateKeyDeclaration, ...] = (),
    lights_up: LitWhen | NotALightSource = NotALightSource(),
    item_spec_id: ItemSpecId = _LANTERN,
) -> ItemSpecDeclaration:
    return ItemSpecDeclaration(
        item_spec_id=item_spec_id,
        name=DisplayName("カンテラ"),
        description=DescriptionText("油で灯る手提げの明かり"),
        state_keys=state_keys,
        lights_up=lights_up,
        hands_needed=HandsNeeded(1),
        lasts=LastsIndefinitely(),
    )


class TestItemStateKeyKinds:
    """ItemStateKeyDeclaration が、旗・数・選択の種類だけを、種類に合う initial で持てることを保証する。"""

    @pytest.mark.parametrize(
        ("kind", "initial"),
        [
            (FlagStateKind(), FlagValue(raised=True)),
            (CountStateKind(), CountValue(count=Count(2))),
            (_WICK, ChoiceValue(choice=ChoiceName("unlit"))),
        ],
    )
    def test_flag_count_and_choice_kinds_are_allowed(self, kind: object, initial: StateValue) -> None:
        """旗・数・選択の鍵は、種類に合う initial で作れる。"""
        assert _key("lit", kind, initial).initial == initial

    @pytest.mark.parametrize(
        ("kind", "initial"),
        [
            (StockStateKind(capacity=Count(3), refills_every=NoRefill()), StockValue(amount=Count(3))),
            (WrittenTextStateKind(), NothingWritten()),
        ],
    )
    def test_stock_and_written_text_kinds_raise_domain_exception(self, kind: object, initial: StateValue) -> None:
        """在庫と書いた文の鍵は、品物には持てず ItemStateKindNotAllowedException を投げる。"""
        with pytest.raises(ItemStateKindNotAllowedException):
            _key("oil", kind, initial)

    def test_initial_of_another_kind_raises_domain_exception(self) -> None:
        """数の鍵に旗の値を initial に持つと StateValueMismatchesKindException を投げる。"""
        with pytest.raises(StateValueMismatchesKindException):
            _key("uses", CountStateKind(), FlagValue(raised=True))


class TestItemSpecDeclarationStateKeys:
    """ItemSpecDeclaration が、自分の品物の、重ならない状態の宣言だけを持つことを保証する。"""

    def test_same_state_key_twice_raises_domain_exception(self) -> None:
        """1 つの品物に同じ StateKeyId が 2 つあると StateKeyDuplicatedException を投げる。"""
        keys = (_LIT_FLAG, _key("lit", CountStateKind(), CountValue(count=Count(0))))

        with pytest.raises(StateKeyDuplicatedException):
            _item(keys)

    def test_state_key_of_another_item_raises_domain_exception(self) -> None:
        """item_spec_id がその品物と違う状態の宣言を持つと StateKeyOwnerMismatchException を投げる。"""
        keys = (_key("lit", FlagStateKind(), FlagValue(raised=False), item_spec_id=ItemSpecId("torch")),)

        with pytest.raises(StateKeyOwnerMismatchException):
            _item(keys)


class TestItemSpecDeclarationLightsUp:
    """ItemSpecDeclaration.lights_up が、その品物の状態の鍵と、その種類に合う値だけを指すことを保証する。"""

    def test_lit_when_on_declared_key_is_kept(self) -> None:
        """自分の状態の鍵と、その種類に合う値を指す LitWhen はそのまま持つ。"""
        lit_when = LitWhen(key=StateKeyId("wick"), value=ChoiceValue(choice=ChoiceName("lit")))

        item = _item((_key("wick", _WICK, ChoiceValue(choice=ChoiceName("unlit"))),), lights_up=lit_when)

        assert item.lights_up == lit_when

    def test_item_that_is_not_a_light_source_is_allowed(self) -> None:
        """明かりにならない品物は NotALightSource で作れる。"""
        assert _item().lights_up == NotALightSource()

    def test_lit_when_on_undeclared_key_raises_domain_exception(self) -> None:
        """LitWhen の鍵が、その品物の状態の宣言に無いと LightKeyNotDeclaredException を投げる。"""
        with pytest.raises(LightKeyNotDeclaredException):
            _item((_LIT_FLAG,), lights_up=LitWhen(key=StateKeyId("wick"), value=FlagValue(raised=True)))

    @pytest.mark.parametrize(
        "value",
        [CountValue(count=Count(1)), ChoiceValue(choice=ChoiceName("lit"))],
    )
    def test_lit_when_value_of_another_kind_raises_domain_exception(self, value: StateValue) -> None:
        """LitWhen の値が、指す鍵の種類に合わない (旗の鍵に数の値など) と StateValueMismatchesKindException を投げる。"""
        with pytest.raises(StateValueMismatchesKindException):
            _item((_LIT_FLAG,), lights_up=LitWhen(key=StateKeyId("lit"), value=value))

    def test_lit_when_choice_not_in_declared_choices_raises_domain_exception(self) -> None:
        """LitWhen の値が、選択の鍵の選択肢に無い名前だと StateValueMismatchesKindException を投げる。"""
        keys = (_key("wick", _WICK, ChoiceValue(choice=ChoiceName("unlit"))),)

        with pytest.raises(StateValueMismatchesKindException):
            _item(keys, lights_up=LitWhen(key=StateKeyId("wick"), value=ChoiceValue(choice=ChoiceName("burning"))))


class TestItemSpecDeclarationHandsNeeded:
    """ItemSpecDeclaration.hands_needed が、宣言した手の数を持つことを保証する。"""

    def test_declared_hands_needed_is_kept(self) -> None:
        """hands_needed に 2 を書いた品物 (つるはし) は HandsNeeded(2) を持つ。"""
        item = ItemSpecDeclaration(
            item_spec_id=ItemSpecId("pickaxe"),
            name=DisplayName("つるはし"),
            description=DescriptionText("両手で振る"),
            state_keys=(),
            lights_up=NotALightSource(),
            hands_needed=HandsNeeded(2),
            lasts=LastsIndefinitely(),
        )

        assert item.hands_needed == HandsNeeded(2)


class TestLasts:
    """Lasts が、世界に出てから消えるまでの時間を 1 tick 以上でだけ持てることを保証する。"""

    def test_zero_ticks_is_refused(self) -> None:
        """ticks に 0 を渡すと LastingTicksBelowOneException を投げる。"""
        with pytest.raises(LastingTicksBelowOneException):
            Lasts(ticks=Ticks(0), ended_text=DescriptionText("灯が燃え尽きた。"))

    def test_one_tick_is_accepted(self) -> None:
        """ticks に 1 を渡すと、その時間と ended_text を持つ Lasts になる。"""
        lasts = Lasts(ticks=Ticks(1), ended_text=DescriptionText("灯が燃え尽きた。"))

        assert (lasts.ticks, lasts.ended_text) == (Ticks(1), DescriptionText("灯が燃え尽きた。"))
