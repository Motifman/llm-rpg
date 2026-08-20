from __future__ import annotations

from typing import Any, List, Mapping, Optional

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.effect_target import EffectTarget
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionEffectValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.cross_domain_effect_spec import (
    DamageSpec,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.service.effect_application.object_target import (
    resolve_target_object,
)


def read_quantity(params: dict[str, Any]) -> int:
    """effect parameters から quantity を読む。default=1、負値は 0 にクランプ。

    Phase 2-A の数量セマンティクス。GIVE_ITEM / REMOVE_ITEM が 1 effect で
    複数 instance を扱えるようにするため。シナリオが quantity を書かない
    場合は既存挙動 (1 個) を維持する。
    """
    raw = params.get("quantity", 1)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return 1
    return max(0, n)


def item_spec_from_param(val: Any) -> ItemSpecId:
    if isinstance(val, ItemSpecId):
        return val
    return ItemSpecId.create(val)


def resolve_item_spec_for_transfer(
    effect_params: dict,
    interaction_parameters: Optional[dict],
    effect_type_name: str,
) -> ItemSpecId:
    """アイテム授受 effect が扱う品目を決める。

    ``item_spec_id_parameter`` が書かれていれば ``interaction_parameters``
    の該当キーから実行時に決め、無ければ定義に固定された
    ``item_spec_id`` を使う。倒れた相手の持ち物は prompt に見えている
    (PR #824) のので、奪う品目は LLM が名指しできる必要がある。定義に固定
    すると品目のぶんだけ action を並べることになり、設計 doc §3.2 で
    棄却した「同じ行為の複製」になる。

    実行時指定なのに参照キーが無い場合は例外にする。黙って 0 個付与に
    すると「奪ったのに何も手に入らない」が成功として返る。この経路まで
    来るのは ``TARGET_HAS_ITEM`` が先に弾くはずの状態なので、配線の
    壊れとして扱う。
    """
    key = effect_params.get("item_spec_id_parameter")
    if key is None:
        return item_spec_from_param(effect_params.get("item_spec_id"))
    raw = (interaction_parameters or {}).get(key)
    if raw is None:
        raise InteractionEffectValidationException(
            f"{effect_type_name} が参照する interaction_parameters[{key!r}] が"
            "ありません。対象品目を実行時に決める効果は、先に "
            "TARGET_HAS_ITEM 等で存在を確かめてください。"
        )
    return item_spec_from_param(raw)


def damage_bucket_for(
    effect: InteractionEffect,
    *,
    actor_bucket: List[DamageSpec],
    target_bucket: List[DamageSpec],
    target_player_status: Optional[PlayerStatusAggregate],
) -> List[DamageSpec]:
    """ダメージを行為者ぶんと対象ぶんのどちらに積むか決める。

    ``item_bucket_for`` と同じ約束。対象不在の ``TARGET_PLAYER`` を
    行為者へ倒すと「相手を刺したつもりが自分が傷ついた」になる。
    """
    if effect.target is not EffectTarget.TARGET_PLAYER:
        return actor_bucket
    if target_player_status is None:
        raise InteractionEffectValidationException(
            "target=TARGET_PLAYER の APPLY_DAMAGE が、対象プレイヤーの無い"
            "呼び出しに来ました。対人 interaction 以外で TARGET_PLAYER を"
            "指定しているか、対象の解決が漏れています。"
        )
    return target_bucket


def item_bucket_for(
    effect: InteractionEffect,
    *,
    actor_bucket: List[ItemSpecId],
    target_bucket: List[ItemSpecId],
    target_player_status: Optional[PlayerStatusAggregate],
) -> List[ItemSpecId]:
    """アイテム授受 effect を、行為者ぶんと対象ぶんのどちらに積むか決める。

    ``target=TARGET_PLAYER`` なのに対象プレイヤーが渡されていない呼び出し
    は、行為者バケットへフォールバックさせずに例外で止める。フォールバック
    すると「奪ったつもりで自分の持ち物が消える」という、成功として返る
    誤動作になる。
    """
    if effect.target is not EffectTarget.TARGET_PLAYER:
        return actor_bucket
    if target_player_status is None:
        raise InteractionEffectValidationException(
            f"target=TARGET_PLAYER の {effect.effect_type.value} が、対象"
            "プレイヤーの無い呼び出しに来ました。対人 interaction 以外で"
            "TARGET_PLAYER を指定しているか、対象の解決が漏れています。"
        )
    return target_bucket


def deposit_removal_details(
    *,
    interior: SpotInterior,
    acting_object: SpotObject | None,
    effect: InteractionEffect,
    interaction_parameters: Optional[dict],
    owned_item_spec_counts: Optional[Mapping[ItemSpecId, int]],
) -> tuple[ItemSpecId, str, SpotObject, int]:
    """預け入れ効果の対象と削除数を、副作用なしで一度だけ解決する。"""
    if owned_item_spec_counts is None:
        raise InteractionEffectValidationException(
            "DEPOSIT_ITEM_TO_OBJECT は行為者の所持数を必要とします"
        )
    params = effect.parameters
    sid = resolve_item_spec_for_transfer(
        params, interaction_parameters, "DEPOSIT_ITEM_TO_OBJECT"
    )
    state_key = params.get("state_key")
    if not isinstance(state_key, str) or not state_key:
        raise InteractionEffectValidationException(
            "DEPOSIT_ITEM_TO_OBJECT: state_key is required"
        )
    target = resolve_target_object(interior, acting_object, params)
    if target is None:
        raise InteractionEffectValidationException(
            "DEPOSIT_ITEM_TO_OBJECT: target object is not resolvable"
        )
    owned = max(0, int(owned_item_spec_counts.get(sid, 0)))
    raw_quantity = params.get("quantity")
    if raw_quantity == "all":
        deposited = owned
    else:
        try:
            requested = int(raw_quantity)
        except (TypeError, ValueError) as exc:
            raise InteractionEffectValidationException(
                "DEPOSIT_ITEM_TO_OBJECT: quantity must be a positive integer or 'all'"
            ) from exc
        if requested <= 0:
            raise InteractionEffectValidationException(
                "DEPOSIT_ITEM_TO_OBJECT: quantity must be a positive integer or 'all'"
            )
        deposited = min(owned, requested)
    return sid, state_key, target, deposited


def item_removals_for_effect(
    *,
    interior: SpotInterior,
    acting_object: SpotObject | None,
    effect: InteractionEffect,
    interaction_parameters: Optional[dict],
    owned_item_spec_counts: Optional[Mapping[ItemSpecId, int]],
    target_player_status: Optional[PlayerStatusAggregate],
) -> tuple[tuple[ItemSpecId, ...], tuple[ItemSpecId, ...]]:
    """単一効果の削除要求を、実際の適用と共用する正本から解決する。"""
    actor: List[ItemSpecId] = []
    target: List[ItemSpecId] = []
    effect_type = effect.effect_type
    params = effect.parameters
    if effect_type == InteractionEffectTypeEnum.REMOVE_ITEM:
        sid = resolve_item_spec_for_transfer(
            params, interaction_parameters, "REMOVE_ITEM"
        )
        bucket = item_bucket_for(
            effect,
            actor_bucket=actor,
            target_bucket=target,
            target_player_status=target_player_status,
        )
        bucket.extend((sid,) * read_quantity(params))
    elif effect_type == InteractionEffectTypeEnum.DEPOSIT_ITEM_TO_OBJECT:
        sid, _state_key, _target, deposited = deposit_removal_details(
            interior=interior,
            acting_object=acting_object,
            effect=effect,
            interaction_parameters=interaction_parameters,
            owned_item_spec_counts=owned_item_spec_counts,
        )
        actor.extend((sid,) * deposited)
    elif effect_type == InteractionEffectTypeEnum.COMBINE_ITEMS:
        actor.extend(
            item_spec_from_param(raw)
            for raw in params.get("input_item_spec_ids", [])
        )
    return tuple(actor), tuple(target)
