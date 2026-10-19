"""実体ごとの状態効果・前提条件を、使う側と使われる側の公開入口で検証する。"""

from __future__ import annotations

import logging

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum as Condition
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum as Effect
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import SpotInteractionService
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import WorldGraphEffectService
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect


def _item(instance_id: int, state: dict) -> ItemAggregate:
    spec = ItemSpec(
        item_spec_id=ItemSpecId(7),
        name="道具",
        item_type=ItemType.MATERIAL,
        rarity=Rarity.COMMON,
        description="状態を持つ道具",
        max_stack_size=MaxStackSize(64),
    )
    return ItemAggregate.create(
        item_instance_id=ItemInstanceId(instance_id),
        item_spec=spec,
        quantity=1,
        state=state,
    )


def _pair() -> dict[str, ItemAggregate]:
    return {
        "acting": _item(101, {"lit": False, "fuel": 5}),
        "target": _item(102, {"lit": False, "fuel": 9}),
    }


def _item_arguments(items: dict[str, ItemAggregate]) -> dict:
    return {f"{role}_item_aggregate": item for role, item in items.items()}


def _states(items: dict[str, ItemAggregate]) -> dict:
    return {role: dict(item.state) for role, item in items.items()}


def _apply(effect: InteractionEffect, items: dict[str, ItemAggregate], tick=None):
    return WorldGraphEffectService().apply_effects(
        interior=SpotInterior((), (), (), ()),
        acting_object=None,
        effects=[effect],
        world_flags=frozenset(),
        current_tick=tick,
        **_item_arguments(items),
    )


def _assert_flags(result, expected: tuple[bool, bool]) -> None:
    assert result.item_instance_state_changed is expected[0]
    assert result.target_item_instance_state_changed is expected[1]


def _interaction(*conditions: InteractionCondition) -> InteractionDef:
    return InteractionDef(
        action_name="use",
        display_label="使う",
        preconditions=conditions,
        effects=(),
    )


def _assert_warning(caplog, effect_type: Effect, cause: str) -> None:
    assert any(
        record.levelno >= logging.WARNING and effect_type.value in record.getMessage() and cause in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.parametrize(
    ("effect_type", "expected_states", "expected_flags"),
    [
        (
            Effect.CHANGE_ITEM_INSTANCE_STATE,
            {"acting": {"lit": True, "fuel": 5}, "target": {"lit": False, "fuel": 9}},
            (True, False),
        ),
        (
            Effect.CHANGE_TARGET_ITEM_INSTANCE_STATE,
            {"acting": {"lit": False, "fuel": 5}, "target": {"lit": True, "fuel": 9}},
            (False, True),
        ),
    ],
    ids=["acting", "target"],
)
def test_merges_only_selected_item_state(effect_type, expected_states, expected_flags):
    """選択側の指定キーだけ変え、未指定キーと反対側を残し、選択側だけ変更を通知する。"""
    items = _pair()
    result = _apply(
        InteractionEffect(effect_type=effect_type, parameters={"state_updates": {"lit": True}}),
        items,
    )
    assert _states(items) == expected_states
    _assert_flags(result, expected_flags)


@pytest.mark.parametrize(
    ("effect_type", "missing_role", "parameters"),
    [
        (Effect.CHANGE_ITEM_INSTANCE_STATE, "acting", {"state_updates": {"lit": True}}),
        (Effect.CHANGE_TARGET_ITEM_INSTANCE_STATE, "target", {"state_updates": {"lit": True}}),
        (Effect.RECORD_ITEM_INSTANCE_STATE_TICK, "acting", {"state_key": "used_at_tick"}),
        (Effect.RECORD_TARGET_ITEM_INSTANCE_STATE_TICK, "target", {"state_key": "used_at_tick"}),
    ],
)
def test_missing_item_warns_without_changing_other_item(effect_type, missing_role, parameters, caplog):
    """必要実体だけ欠落すると、その効果と不足実体を警告し、反対側へ代替適用しない。"""
    items = _pair()
    del items[missing_role]
    before = _states(items)
    with caplog.at_level(logging.WARNING):
        result = _apply(InteractionEffect(effect_type=effect_type, parameters=parameters), items, WorldTick(1))
    assert _states(items) == before
    _assert_flags(result, (False, False))
    _assert_warning(caplog, effect_type, f"{missing_role}_item_aggregate")


@pytest.mark.parametrize("effect_type", [Effect.CHANGE_ITEM_INSTANCE_STATE, Effect.CHANGE_TARGET_ITEM_INSTANCE_STATE])
def test_invalid_state_updates_warns_without_mutation(effect_type, caplog):
    """更新値が辞書でなければ原因を警告し、両実体の状態と両変更通知を変えない。"""
    items = _pair()
    before = _states(items)
    with caplog.at_level(logging.WARNING):
        result = _apply(
            InteractionEffect(effect_type=effect_type, parameters={"state_updates": "lit=true"}),
            items,
        )
    assert _states(items) == before
    _assert_flags(result, (False, False))
    _assert_warning(caplog, effect_type, "state_updates")


@pytest.mark.parametrize(
    ("role", "effect_type", "tick", "with_other", "expected_flags"),
    [
        ("acting", Effect.RECORD_ITEM_INSTANCE_STATE_TICK, 42, False, (True, False)),
        ("target", Effect.RECORD_TARGET_ITEM_INSTANCE_STATE_TICK, 99, False, (False, True)),
        ("acting", Effect.RECORD_ITEM_INSTANCE_STATE_TICK, 0, True, (True, False)),
        ("target", Effect.RECORD_TARGET_ITEM_INSTANCE_STATE_TICK, 0, True, (False, True)),
    ],
)
def test_records_tick_only_on_selected_item(role, effect_type, tick, with_other, expected_flags):
    """反対側なしでも現在時刻を記録し、両側があれば選択側だけを更新・通知する。"""
    items = {role: _item(101, {"lit": True})}
    if with_other:
        other_role = "target" if role == "acting" else "acting"
        items[other_role] = _item(102, {"untouched": "yes"})
    expected = {role: {"lit": True, "used_at_tick": tick}}
    if with_other:
        expected[other_role] = {"untouched": "yes"}
    result = _apply(
        InteractionEffect(effect_type=effect_type, parameters={"state_key": "used_at_tick"}),
        items,
        WorldTick(tick),
    )
    assert _states(items) == expected
    _assert_flags(result, expected_flags)


@pytest.mark.parametrize(
    "effect_type", [Effect.RECORD_ITEM_INSTANCE_STATE_TICK, Effect.RECORD_TARGET_ITEM_INSTANCE_STATE_TICK]
)
@pytest.mark.parametrize(
    ("parameters", "tick", "cause"),
    [({"state_key": "used_at_tick"}, None, "current_tick"), ({}, WorldTick(1), "state_key")],
    ids=["missing-tick", "missing-key"],
)
def test_invalid_tick_context_warns_without_mutation(effect_type, parameters, tick, cause, caplog):
    """時刻か書込先だけ欠落すると対応する原因を警告し、既存状態と両変更通知を保つ。"""
    items = _pair()
    before = _states(items)
    with caplog.at_level(logging.WARNING):
        result = _apply(InteractionEffect(effect_type=effect_type, parameters=parameters), items, tick)
    assert _states(items) == before
    _assert_flags(result, (False, False))
    _assert_warning(caplog, effect_type, cause)


@pytest.mark.parametrize(
    ("role", "condition_type", "failure_message"),
    [
        ("acting", Condition.ITEM_INSTANCE_STATE, "ランタンに火を点けてから使う必要がある"),
        ("target", Condition.TARGET_ITEM_INSTANCE_STATE, "この剣は錆びていない"),
    ],
)
@pytest.mark.parametrize(
    ("state", "required", "other_state", "expected"),
    [
        ({"lit": True, "fuel": 3}, {"lit": True}, None, True),
        ({"lit": True, "fuel": 3}, {"lit": True, "fuel": 3}, {"lit": False, "fuel": 5}, True),
        ({"lit": False, "fuel": 3}, {"lit": True, "fuel": 3}, {"lit": True, "fuel": 3}, False),
        ({"lit": True, "fuel": 5}, {"lit": True, "fuel": 3}, {"lit": True, "fuel": 3}, False),
    ],
    ids=["subset-without-other", "all-match", "first-key-differs", "last-key-differs"],
)
def test_required_state_matches_only_selected_instance(
    role, condition_type, failure_message, state, required, other_state, expected
):
    """反対側なしでも部分一致は成立し、複数キーでは選択側の全要求値と作者の拒否文を守る。"""
    items = {role: _item(101, state)}
    if other_state is not None:
        items["target" if role == "acting" else "acting"] = _item(102, other_state)
    before = _states(items)
    condition = InteractionCondition(
        condition_type=condition_type,
        required_state=required,
        failure_message=failure_message,
    )
    ok, message = SpotInteractionService().can_interact(
        _interaction(condition),
        None,
        frozenset(),
        frozenset(),
        **_item_arguments(items),
    )
    assert ok is expected
    assert message == (None if expected else failure_message)
    assert _states(items) == before


@pytest.mark.parametrize(
    ("condition_type", "missing_role", "reason_fragment"),
    [
        (Condition.ITEM_INSTANCE_STATE, "acting", "acting item"),
        (Condition.TARGET_ITEM_INSTANCE_STATE, "target", "target item"),
    ],
)
def test_missing_item_condition_refuses_with_reason(condition_type, missing_role, reason_fragment):
    """必要実体が欠けると、反対側が要求を満たしていても必要な実体を示して拒否する。"""
    other_role = "target" if missing_role == "acting" else "acting"
    items = {other_role: _item(101, {"lit": True})}
    before = _states(items)
    condition = InteractionCondition(condition_type=condition_type, required_state={"lit": True})
    ok, message = SpotInteractionService().can_interact(
        _interaction(condition),
        None,
        frozenset(),
        frozenset(),
        **_item_arguments(items),
    )
    assert ok is False
    assert reason_fragment in (message or "")
    assert _states(items) == before


@pytest.mark.parametrize(
    ("used", "rust", "expected", "message"),
    [
        (False, "high", True, None),
        (True, "high", False, "道具は使用済み"),
        (False, "low", False, "剣は修理済み"),
        (True, "low", False, "道具は使用済み"),
    ],
)
def test_each_item_condition_can_refuse_independently(used, rust, expected, message):
    """両側が一致するときだけ成立し、どちらの単独不一致でも作者の理由で拒否する。"""
    items = {"acting": _item(101, {"used": used}), "target": _item(102, {"rust": rust})}
    before = _states(items)
    interaction = _interaction(
        InteractionCondition(
            condition_type=Condition.ITEM_INSTANCE_STATE,
            required_state={"used": False},
            failure_message="道具は使用済み",
        ),
        InteractionCondition(
            condition_type=Condition.TARGET_ITEM_INSTANCE_STATE,
            required_state={"rust": "high"},
            failure_message="剣は修理済み",
        ),
    )
    ok, actual_message = SpotInteractionService().can_interact(
        interaction,
        None,
        frozenset(),
        frozenset(),
        **_item_arguments(items),
    )
    assert ok is expected
    assert actual_message == message
    assert _states(items) == before


def test_apply_effects_rejects_same_instance_for_acting_and_target():
    """同じ実体を両側へ渡すと、効果が空でも二重変更・二重保存を防ぐため即時拒否する。"""
    item = _item(101, {"x": 1})
    with pytest.raises(ValueError, match="must be distinct instances"):
        WorldGraphEffectService().apply_effects(
            interior=SpotInterior((), (), (), ()),
            acting_object=None,
            effects=[],
            world_flags=frozenset(),
            acting_item_aggregate=item,
            target_item_aggregate=item,
        )
    assert item.state == {"x": 1}


def test_can_interact_rejects_same_instance_for_acting_and_target():
    """同じ実体を両側へ渡すと、前提条件が空でも公開条件入口で即時拒否する。"""
    item = _item(101, {"x": 1})
    with pytest.raises(ValueError, match="must be distinct instances"):
        SpotInteractionService().can_interact(
            _interaction(),
            None,
            frozenset(),
            frozenset(),
            acting_item_aggregate=item,
            target_item_aggregate=item,
        )
    assert item.state == {"x": 1}


def test_both_aggregates_can_be_modified_in_one_apply():
    """一度の適用で道具を使用済み、剣を修理済みと現在時刻にし、両変更を通知する。"""
    items = {"acting": _item(101, {"used": False}), "target": _item(102, {"rust": "high"})}
    result = WorldGraphEffectService().apply_effects(
        interior=SpotInterior((), (), (), ()),
        acting_object=None,
        effects=[
            InteractionEffect(
                effect_type=Effect.CHANGE_ITEM_INSTANCE_STATE, parameters={"state_updates": {"used": True}}
            ),
            InteractionEffect(
                effect_type=Effect.CHANGE_TARGET_ITEM_INSTANCE_STATE, parameters={"state_updates": {"rust": "low"}}
            ),
            InteractionEffect(
                effect_type=Effect.RECORD_TARGET_ITEM_INSTANCE_STATE_TICK,
                parameters={"state_key": "last_repaired_tick"},
            ),
        ],
        world_flags=frozenset(),
        current_tick=WorldTick(7),
        **_item_arguments(items),
    )
    assert _states(items) == {"acting": {"used": True}, "target": {"rust": "low", "last_repaired_tick": 7}}
    _assert_flags(result, (True, True))
