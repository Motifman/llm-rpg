"""Phase 4-E: クロスドメイン効果の visibility 分類とサマリ集計のテスト。

WorldGraphEffectService が各効果に EffectVisibility を解決し、
ACTOR_DIRECT / PUBLIC_OBSERVABLE / HIDDEN の 3 バケットに
AppliedEffectSummary を仕分けして返すことを検証する。
"""

from __future__ import annotations

from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.effect_visibility import EffectVisibility
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
    AppliedEffectKind,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


def _empty_interior() -> SpotInterior:
    return SpotInterior((), (), (), ())


def _interior_with_object(obj: SpotObject) -> SpotInterior:
    return SpotInterior((), (obj,), (), ())


def _player_status(state: dict | None = None) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(1),
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=100, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
        state=state,
    )


def _make_item(state: dict | None = None) -> ItemAggregate:
    spec = ItemSpec(
        item_spec_id=ItemSpecId(7),
        name="Lantern",
        item_type=ItemType.MATERIAL,
        rarity=Rarity.COMMON,
        description="A lantern.",
        max_stack_size=MaxStackSize(64),
    )
    return ItemAggregate.create(
        item_instance_id=ItemInstanceId(101),
        item_spec=spec,
        quantity=1,
        state=state,
    )


def _make_target_item(state: dict | None = None) -> ItemAggregate:
    spec = ItemSpec(
        item_spec_id=ItemSpecId(8),
        name="Box",
        item_type=ItemType.MATERIAL,
        rarity=Rarity.COMMON,
        description="A box.",
        max_stack_size=MaxStackSize(64),
    )
    return ItemAggregate.create(
        item_instance_id=ItemInstanceId(202),
        item_spec=spec,
        quantity=1,
        state=state,
    )


def _make_object() -> SpotObject:
    return SpotObject(
        object_id=SpotObjectId.create(1),
        name="燭台",
        description="蝋燭立て",
        object_type=SpotObjectTypeEnum.OTHER,
        state={},
        interactions=(),
    )


class TestActorDirectDefaults:
    """行為者本人の体験はデフォルトで ACTOR_DIRECT に分類される。"""

    def test_apply_damage_is_public_observable_by_default(self) -> None:
        """APPLY_DAMAGE は同スポットの他者から見える物理現象として PUBLIC_OBSERVABLE が既定。"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.APPLY_DAMAGE,
            parameters={"damage": 5, "message": "焼けた"},
        )
        result = svc.apply_effects(
            interior=_empty_interior(),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
        )
        assert len(result.public_observable_effects) == 1
        assert result.public_observable_effects[0].kind == AppliedEffectKind.DAMAGE
        assert (
            result.public_observable_effects[0].visibility
            == EffectVisibility.PUBLIC_OBSERVABLE
        )
        assert result.actor_direct_effects == ()
        assert result.hidden_effects == ()
        # DamageSpec にも visibility が伝播
        assert result.damage_specs[0].visibility == EffectVisibility.PUBLIC_OBSERVABLE

    def test_change_acting_item_state_is_actor_direct(self) -> None:
        """自分の使ったアイテム状態変化は ACTOR_DIRECT デフォルト。"""
        svc = WorldGraphEffectService()
        item = _make_item(state={"charges": 5})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_ITEM_INSTANCE_STATE,
            parameters={"state_updates": {"charges": 2}},
        )
        result = svc.apply_effects(
            interior=_empty_interior(),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
            acting_item_aggregate=item,
        )
        assert len(result.actor_direct_effects) == 1
        s = result.actor_direct_effects[0]
        assert s.kind == AppliedEffectKind.ACTING_ITEM_STATE_CHANGE
        delta_map = {d.key: (d.before, d.after) for d in s.state_delta}
        assert delta_map["charges"] == (5, 2)


class TestPublicObservableDefaults:
    """環境・接続・対象オブジェクトの物理変化はデフォルトで PUBLIC_OBSERVABLE。"""

    def test_change_object_state_is_public_observable(self) -> None:
        """CHANGE_OBJECT_STATE は同スポットの第三者観測対象。"""
        svc = WorldGraphEffectService()
        obj = _make_object()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_OBJECT_STATE,
            parameters={"state_updates": {"lit": True}, "object_id": 1},
        )
        result = svc.apply_effects(
            interior=_interior_with_object(obj),
            acting_object=obj,
            effects=[effect],
            world_flags=frozenset(),
        )
        assert len(result.public_observable_effects) == 1
        s = result.public_observable_effects[0]
        assert s.kind == AppliedEffectKind.SPOT_OBJECT_STATE_CHANGE
        assert s.visibility == EffectVisibility.PUBLIC_OBSERVABLE
        assert any(d.key == "lit" and d.after is True for d in s.state_delta)

    def test_change_target_item_state_is_public_observable(self) -> None:
        """使われた側のアイテム状態は第三者にも見える物理変化扱い。"""
        svc = WorldGraphEffectService()
        target = _make_target_item(state={"unlocked": False})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_TARGET_ITEM_INSTANCE_STATE,
            parameters={"state_updates": {"unlocked": True}},
        )
        result = svc.apply_effects(
            interior=_empty_interior(),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
            target_item_aggregate=target,
        )
        assert len(result.public_observable_effects) == 1
        s = result.public_observable_effects[0]
        assert s.kind == AppliedEffectKind.TARGET_ITEM_STATE_CHANGE


class TestHiddenDefaults:
    """内臓的・内部 bookkeeping 系はデフォルトで HIDDEN。"""

    def test_change_player_state_is_hidden(self) -> None:
        """プレイヤーの自由 state はデフォルト HIDDEN（毒・呪い等の内臓的状態）。"""
        svc = WorldGraphEffectService()
        status = _player_status()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_PLAYER_STATE,
            parameters={"state_updates": {"poisoned": True}},
        )
        result = svc.apply_effects(
            interior=_empty_interior(),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert len(result.hidden_effects) == 1
        s = result.hidden_effects[0]
        assert s.kind == AppliedEffectKind.ACTING_PLAYER_STATE_CHANGE
        assert s.visibility == EffectVisibility.HIDDEN
        assert any(d.key == "poisoned" and d.after is True for d in s.state_delta)
        assert result.actor_direct_effects == ()
        assert result.public_observable_effects == ()


class TestVisibilityFirstClassField:
    """visibility は InteractionEffect の first-class 属性として渡せる。"""

    def test_first_class_field_takes_precedence_over_parameters(self) -> None:
        """`InteractionEffect.visibility` が parameters['visibility'] より優先される。"""
        svc = WorldGraphEffectService()
        # parameters 側は HIDDEN を指定するが、first-class 側で ACTOR_DIRECT を強制
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.APPLY_DAMAGE,
            parameters={"damage": 2, "visibility": "HIDDEN"},
            visibility=EffectVisibility.ACTOR_DIRECT,
        )
        result = svc.apply_effects(
            interior=_empty_interior(),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
        )
        assert len(result.actor_direct_effects) == 1
        assert result.public_observable_effects == ()
        assert result.hidden_effects == ()


class TestVisibilityOverride:
    """シナリオ JSON が `visibility` を明示すれば既定を上書きできる。"""

    def test_player_state_can_be_lifted_to_actor_direct(self) -> None:
        """毒だけど本人は痛みで分かる、というケースを actor_direct で表現できる。

        first-class field `visibility` で上書きできることを確認する。
        """
        svc = WorldGraphEffectService()
        status = _player_status()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_PLAYER_STATE,
            parameters={"state_updates": {"buff_strength": 2}},
            visibility=EffectVisibility.ACTOR_DIRECT,
        )
        result = svc.apply_effects(
            interior=_empty_interior(),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert len(result.actor_direct_effects) == 1
        assert result.actor_direct_effects[0].visibility == EffectVisibility.ACTOR_DIRECT
        assert result.hidden_effects == ()

    def test_change_object_state_can_be_hidden(self) -> None:
        """物理変化を「気づかれない仕掛け」として HIDDEN に落とせる。"""
        svc = WorldGraphEffectService()
        obj = _make_object()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_OBJECT_STATE,
            parameters={"state_updates": {"trap_armed": True}, "object_id": 1},
            visibility=EffectVisibility.HIDDEN,
        )
        result = svc.apply_effects(
            interior=_interior_with_object(obj),
            acting_object=obj,
            effects=[effect],
            world_flags=frozenset(),
        )
        assert len(result.hidden_effects) == 1
        assert result.public_observable_effects == ()

    def test_unknown_visibility_falls_back_to_default(self) -> None:
        """parameters に未知の visibility 値が来たら既定値に落ちる（legacy 経路）。"""
        svc = WorldGraphEffectService()
        # parameters 経由は deprecated で warning ログが出るが、互換のため
        # まだ受け付ける。値が壊れていても効果適用自体は続行する。
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.APPLY_DAMAGE,
            parameters={"damage": 3, "visibility": "NOT_A_VISIBILITY"},
        )
        result = svc.apply_effects(
            interior=_empty_interior(),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
        )
        # APPLY_DAMAGE の既定は PUBLIC_OBSERVABLE
        assert len(result.public_observable_effects) == 1


class TestStateDeltaSemantics:
    """state delta が missing/None/sequential 更新を正しく扱うこと。"""

    def test_new_key_records_before_none(self) -> None:
        """before に存在しなかったキーは before=None で記録される。"""
        svc = WorldGraphEffectService()
        item = _make_item(state={})  # 空 state
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_ITEM_INSTANCE_STATE,
            parameters={"state_updates": {"charges": 3}},
        )
        result = svc.apply_effects(
            interior=_empty_interior(),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
            acting_item_aggregate=item,
        )
        deltas = result.actor_direct_effects[0].state_delta
        assert len(deltas) == 1
        assert deltas[0].key == "charges"
        assert deltas[0].before is None
        assert deltas[0].after == 3

    def test_explicit_none_to_value_is_recorded(self) -> None:
        """before に明示的に None が入っていた場合も差分として記録される。"""
        svc = WorldGraphEffectService()
        item = _make_item(state={"owner": None})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_ITEM_INSTANCE_STATE,
            parameters={"state_updates": {"owner": "alice"}},
        )
        result = svc.apply_effects(
            interior=_empty_interior(),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
            acting_item_aggregate=item,
        )
        deltas = result.actor_direct_effects[0].state_delta
        owner = next(d for d in deltas if d.key == "owner")
        assert owner.before is None
        assert owner.after == "alice"

    def test_sequential_mutations_capture_per_step_diff(self) -> None:
        """同じキーを連続更新したとき、各サマリは自分の before/after を持つ。"""
        svc = WorldGraphEffectService()
        item = _make_item(state={"charges": 5})
        e1 = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_ITEM_INSTANCE_STATE,
            parameters={"state_updates": {"charges": 3}},
        )
        e2 = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_ITEM_INSTANCE_STATE,
            parameters={"state_updates": {"charges": 1}},
        )
        result = svc.apply_effects(
            interior=_empty_interior(),
            acting_object=None,
            effects=[e1, e2],
            world_flags=frozenset(),
            acting_item_aggregate=item,
        )
        # 2 つの ACTING_ITEM_STATE_CHANGE summary が出るはず。
        item_summaries = [
            s
            for s in result.actor_direct_effects
            if s.kind == AppliedEffectKind.ACTING_ITEM_STATE_CHANGE
        ]
        assert len(item_summaries) == 2
        first = item_summaries[0].state_delta[0]
        second = item_summaries[1].state_delta[0]
        assert (first.before, first.after) == (5, 3)
        assert (second.before, second.after) == (3, 1)

    def test_no_op_update_yields_empty_delta(self) -> None:
        """同じ値で merge しても state_delta は空。サマリは出る (0件 update もイベントとして残す方針)。"""
        svc = WorldGraphEffectService()
        item = _make_item(state={"charges": 3})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_ITEM_INSTANCE_STATE,
            parameters={"state_updates": {"charges": 3}},
        )
        result = svc.apply_effects(
            interior=_empty_interior(),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
            acting_item_aggregate=item,
        )
        s = result.actor_direct_effects[0]
        assert s.kind == AppliedEffectKind.ACTING_ITEM_STATE_CHANGE
        assert s.state_delta == ()


class TestVisibilityBucketIsolation:
    """visibility 別バケットは互いに混ざらない。"""

    def test_actor_and_public_summaries_do_not_mix(self) -> None:
        """1 回の apply_effects で actor_direct と public_observable が同居しても分離される。"""
        svc = WorldGraphEffectService()
        status = _player_status()
        obj = _make_object()
        effect_actor = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.SATISFY_NEED,
            parameters={"need_type": "HUNGER", "amount": 5},
        )
        effect_public = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_OBJECT_STATE,
            parameters={"state_updates": {"opened": True}, "object_id": 1},
        )
        result = svc.apply_effects(
            interior=_interior_with_object(obj),
            acting_object=obj,
            effects=[effect_actor, effect_public],
            world_flags=frozenset(),
            acting_player_status=status,
        )
        kinds_actor = {s.kind for s in result.actor_direct_effects}
        kinds_public = {s.kind for s in result.public_observable_effects}
        assert AppliedEffectKind.SATISFY_NEED in kinds_actor
        assert AppliedEffectKind.SPOT_OBJECT_STATE_CHANGE in kinds_public
        assert AppliedEffectKind.SATISFY_NEED not in kinds_public
        assert AppliedEffectKind.SPOT_OBJECT_STATE_CHANGE not in kinds_actor
