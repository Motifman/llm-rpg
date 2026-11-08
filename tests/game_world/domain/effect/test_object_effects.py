from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.action.acting_person import NoActingPerson
from ai_rpg_world.game_world.domain.action.action_arguments import TextArgumentValue
from ai_rpg_world.game_world.domain.action.trigger import HappeningFired
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import Actor, SubjectKind
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    CountStateKind,
    CountValue,
    FlagStateKind,
    FlagValue,
    NothingWritten,
    ObjectStateKeyDeclaration,
    StateKind,
    StateValue,
    StockStateKind,
    StockValue,
    TextBody,
    WrittenText,
    WrittenTextStateKind,
)
from ai_rpg_world.game_world.domain.declaration.object_and_item.object_declaration import (
    ObjectAppearance,
    ObjectDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.time_and_weather import NoDayNight
from ai_rpg_world.game_world.domain.effect.object_effects import (
    AddToObjectCountEffect,
    DepositGoldToObjectEffect,
    DepositItemToObjectEffect,
    RevealObjectEffect,
    SetObjectValueEffect,
    SubtractFromObjectCountEffect,
    TakeFromObjectStockEffect,
    WriteTextEffect,
)
from ai_rpg_world.game_world.domain.exception.effect_exception import (
    ArgumentIsNotTextException,
    TextHasNoAuthorException,
)
from ai_rpg_world.game_world.domain.exception.game_world_exception import (
    CountBelowZeroException,
    InsufficientGoldException,
)
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import (
    NotEnoughItemsOfSpecException,
    NotEnoughStockException,
)
from ai_rpg_world.game_world.domain.exception.trigger_exception import ArgumentNotInTriggerException
from ai_rpg_world.game_world.domain.objects_and_items import Item, ItemInstanceId, ObjectState
from ai_rpg_world.game_world.domain.value_object import (
    Count,
    DescriptionText,
    DisplayName,
    Gold,
    ObjectId,
    SpotId,
    StateKeyId,
    Ticks,
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from tests.game_world.domain.effect._builders import ALICE, WORLD, inventory, item_spec
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.declarations_for_tests import HappeningForTests
from tests.game_world.support.world_in_memory import WorldInMemory

_SHRINE = ObjectId("shrine")
_APPLE = item_spec("apple")
_APPLE_1 = ItemInstanceId("apple#1")
_MESSAGE = ArgumentName("message")


def _key(name: str, kind: StateKind, initial: StateValue) -> ObjectStateKeyDeclaration:
    return ObjectStateKeyDeclaration(object_id=_SHRINE, key=StateKeyId(name), kind=kind, initial=initial)


_LIT = _key("lit", FlagStateKind(), FlagValue(False))
_OFFERINGS = _key("offerings", CountStateKind(), CountValue(Count(2)))
_HOLY_WATER = _key("holy_water", StockStateKind(capacity=Count(5), refills_every=Ticks(100)), StockValue(Count(5)))
_PLAQUE = _key("plaque", WrittenTextStateKind(), NothingWritten())


def _shrine(*, hidden: bool = False) -> ObjectDeclaration:
    return ObjectDeclaration(
        object_id=_SHRINE,
        spot_id=SpotId("plaza"),
        name=DisplayName("祠"),
        description=DescriptionText("小さな祠"),
        appearance=ObjectAppearance(seen_in_dark=False, hidden_until_revealed=hidden),
        state_keys=(_LIT, _OFFERINGS, _HOLY_WATER, _PLAQUE),
    )


def _world(*, hidden: bool = False, apples: int = 0, gold: int = 0, ticks: int = 0) -> WorldInMemory:
    alice = inventory(ALICE)
    items = []
    for number in range(1, apples + 1):
        item = ItemInstanceId(f"apple#{number}")
        alice.receive(item, _APPLE.item_spec_id)
        items.append(Item.come_into_world(item, _APPLE, WorldTick(0)))
    alice.earn(Gold(gold))
    world = WorldInMemory(
        world=WORLD,
        people=(ALICE,),
        inventories=(alice,),
        items=tuple(items),
        object_states=(ObjectState.from_declaration(_shrine(hidden=hidden), WorldTick(0)),),
    )
    for _ in range(ticks):
        world.clock().advance(NoDayNight())
    return world


def _alice_acts(**arguments: TextArgumentValue | ItemInstanceId) -> ActionAttemptForTests:
    return ActionAttemptForTests(
        actor_id=ALICE, arguments={ArgumentName(name): value for name, value in arguments.items()}
    )


class _ArgumentsWithoutActor:
    def argument(self, name: ArgumentName) -> TextArgumentValue:
        return TextArgumentValue("助けて")

    def acting_person(self) -> NoActingPerson:
        return NoActingPerson()


def _value(world: WorldInMemory, key: ObjectStateKeyDeclaration) -> object:
    return world.object_states[_SHRINE].value_of(key, world.facts().now())


class TestObjectValueEffects:
    """物の値・数・在庫を書き換える効果が、鍵の持ち主の ObjectState に頼むことを保証する。"""

    def test_set_object_value_sets_key(self) -> None:
        """祠の「灯っている」を真にすると、祠の値が真になる。"""
        world = _world()

        SetObjectValueEffect(_LIT, FlagValue(True)).apply(world.facts(), world.aggregates(), _alice_acts())

        assert _value(world, _LIT) == FlagValue(True)

    def test_add_to_object_count_adds_amount(self) -> None:
        """供え物の数 2 に 3 を足すと 5 になる。"""
        world = _world()

        AddToObjectCountEffect(_OFFERINGS, Count(3)).apply(world.facts(), world.aggregates(), _alice_acts())

        assert _value(world, _OFFERINGS) == CountValue(Count(5))

    def test_subtract_from_object_count_below_zero_is_refused(self) -> None:
        """供え物の数 2 から 3 を引こうとすると、ObjectState が CountBelowZeroException で断り、数は 2 のまま。"""
        world = _world()

        with pytest.raises(CountBelowZeroException):
            SubtractFromObjectCountEffect(_OFFERINGS, Count(3)).apply(world.facts(), world.aggregates(), _alice_acts())

        assert _value(world, _OFFERINGS) == CountValue(Count(2))

    def test_take_from_object_stock_takes_amount(self) -> None:
        """聖水の在庫 5 から 2 を取ると 3 になる。"""
        world = _world()

        TakeFromObjectStockEffect(_HOLY_WATER, Count(2)).apply(world.facts(), world.aggregates(), _alice_acts())

        assert _value(world, _HOLY_WATER) == StockValue(Count(3))

    def test_take_from_object_stock_beyond_stock_is_refused(self) -> None:
        """聖水の在庫 5 から 6 を取ろうとすると、ObjectState が NotEnoughStockException で断る。"""
        world = _world()

        with pytest.raises(NotEnoughStockException):
            TakeFromObjectStockEffect(_HOLY_WATER, Count(6)).apply(world.facts(), world.aggregates(), _alice_acts())

    def test_reveal_object_reveals_hidden_object(self) -> None:
        """隠れていた祠を現すと、祠は現れている。"""
        world = _world(hidden=True)

        RevealObjectEffect(_shrine(hidden=True)).apply(world.facts(), world.aggregates(), _alice_acts())

        assert world.object_states[_SHRINE].is_revealed()


class TestWriteTextEffect:
    """WriteTextEffect が、行為の文の引数を、行った人の書いた文として今の tick に物へ残すことを保証する。"""

    def test_writes_argument_text_by_acting_person_now(self) -> None:
        """tick 4 に Alice が「助けて」を引数に書くと、札は本文「助けて」・書いた人 Alice・tick 4 の文になる。"""
        world = _world(ticks=4)

        WriteTextEffect(_PLAQUE, _MESSAGE).apply(
            world.facts(), world.aggregates(), _alice_acts(message=TextArgumentValue("助けて"))
        )

        assert _value(world, _PLAQUE) == WrittenText(body=TextBody("助けて"), author=ALICE, written_at=WorldTick(4))

    def test_item_argument_is_refused(self) -> None:
        """文を指すはずの引数に品物が入っていると、ArgumentIsNotTextException を投げ、札は書かれないまま。"""
        world = _world()

        with pytest.raises(ArgumentIsNotTextException):
            WriteTextEffect(_PLAQUE, _MESSAGE).apply(world.facts(), world.aggregates(), _alice_acts(message=_APPLE_1))

        assert _value(world, _PLAQUE) == NothingWritten()

    def test_trigger_without_arguments_is_refused(self) -> None:
        """引数を持たないきっかけ (出来事) では、ArgumentNotInTriggerException で断り、札は書かれない。"""
        world = _world()

        with pytest.raises(ArgumentNotInTriggerException):
            WriteTextEffect(_PLAQUE, _MESSAGE).apply(
                world.facts(), world.aggregates(), HappeningFired(HappeningForTests(HappeningId("wind")))
            )

        assert _value(world, _PLAQUE) == NothingWritten()

    def test_trigger_without_acting_person_is_refused(self) -> None:
        """引数を答えても行う人のいないきっかけでは、書いた人が決まらないので TextHasNoAuthorException で断る。"""
        world = _world()

        with pytest.raises(TextHasNoAuthorException):
            WriteTextEffect(_PLAQUE, _MESSAGE).apply(world.facts(), world.aggregates(), _ArgumentsWithoutActor())  # type: ignore[arg-type]

        assert _value(world, _PLAQUE) == NothingWritten()

    def test_requires_the_argument(self) -> None:
        """要るものは、読む引数の名前だけ。"""
        assert WriteTextEffect(_PLAQUE, _MESSAGE).requirements() == Requirements(
            subjects=frozenset(),
            uses_chance=False,
            uses_action_arguments=frozenset({_MESSAGE}),
            waits_for_flags=frozenset(),
            reads_world_stage=False,
            reads_day_phases=frozenset(),
            reads_weather=False,
            raises_flags=frozenset(),
            closes_group_decisions=frozenset(),
            may_hide_membership=False,
            reads_happenings=frozenset(),
        )


class TestDepositToObjectEffects:
    """物に預ける効果が、その人から品物や金を手放させ、物の数の鍵を増やすことを保証する。"""

    def test_deposit_item_gives_up_one_and_counts_it(self) -> None:
        """りんごを 2 つ持つ Alice が祠に 1 つ供えると、1 つが世界から消え、供え物の数は 3 になる。"""
        world = _world(apples=2)

        DepositItemToObjectEffect(Actor(), _APPLE, _OFFERINGS).apply(world.facts(), world.aggregates(), _alice_acts())

        assert world.inventories[ALICE].count_of(_APPLE.item_spec_id) == Count(1)
        assert len(world.items) == 1
        assert _value(world, _OFFERINGS) == CountValue(Count(3))

    def test_deposit_item_without_item_is_refused(self) -> None:
        """りんごを持たない Alice が供えようとすると、NotEnoughItemsOfSpecException で断り、供え物の数は 2 のまま。"""
        world = _world()

        with pytest.raises(NotEnoughItemsOfSpecException):
            DepositItemToObjectEffect(Actor(), _APPLE, _OFFERINGS).apply(
                world.facts(), world.aggregates(), _alice_acts()
            )

        assert _value(world, _OFFERINGS) == CountValue(Count(2))

    def test_deposit_gold_pays_and_counts_amount(self) -> None:
        """金 10 を持つ Alice が祠に 3 納めると、Alice の金は 7、供え物の数は 5 になる。"""
        world = _world(gold=10)

        DepositGoldToObjectEffect(Actor(), Gold(3), _OFFERINGS).apply(world.facts(), world.aggregates(), _alice_acts())

        assert world.inventories[ALICE].available_gold() == Gold(7)
        assert _value(world, _OFFERINGS) == CountValue(Count(5))

    def test_deposit_gold_beyond_purse_is_refused(self) -> None:
        """金 2 の Alice が 3 納めようとすると、InsufficientGoldException で断り、供え物の数は 2 のまま。"""
        world = _world(gold=2)

        with pytest.raises(InsufficientGoldException):
            DepositGoldToObjectEffect(Actor(), Gold(3), _OFFERINGS).apply(
                world.facts(), world.aggregates(), _alice_acts()
            )

        assert _value(world, _OFFERINGS) == CountValue(Count(2))

    def test_deposits_require_only_their_subject(self) -> None:
        """要るものは、預ける人の主語だけ。"""
        expected = Requirements(
            subjects=frozenset({SubjectKind.ACTOR}),
            uses_chance=False,
            uses_action_arguments=frozenset(),
            waits_for_flags=frozenset(),
            reads_world_stage=False,
            reads_day_phases=frozenset(),
            reads_weather=False,
            raises_flags=frozenset(),
            closes_group_decisions=frozenset(),
            may_hide_membership=False,
            reads_happenings=frozenset(),
        )

        assert DepositItemToObjectEffect(Actor(), _APPLE, _OFFERINGS).requirements() == expected
        assert DepositGoldToObjectEffect(Actor(), Gold(1), _OFFERINGS).requirements() == expected
