"""loot / merchants / item_specs / needs の読み取り。"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

from ai_rpg_world.domain.item.value_object.item_effect import (
    CompositeItemEffect,
    DamageHpEffect,
    ExpEffect,
    GoldEffect,
    HealEffect,
    ItemEffect,
    RecoverMpEffect,
    ReviveEffect,
    SatisfyNeedEffect,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.service.item_interaction_registry import ItemInteractionRegistry
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError
from ai_rpg_world.infrastructure.scenario.models import (
    InitialItemSpec,
    ItemSpecDefinition,
    ScenarioLootEntry,
    ScenarioLootTableDefinition,
    ScenarioMerchantDefinition,
    ScenarioMerchantPriceEntry,
    ScenarioNeedsConfig,
)
from ai_rpg_world.infrastructure.scenario.parse_helpers import parse_bool
from ai_rpg_world.infrastructure.scenario.parse_interactions import parse_interaction_def
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper

def parse_loot_tables(
    raw_list: List[Dict[str, Any]],
    mapper: ScenarioIdMapper,
) -> Tuple[ScenarioLootTableDefinition, ...]:
    """`loot_tables` block を解析する (PR #1 動的 loot)。

    スキーマ:
      "loot_tables": [
        {
          "id": "deep_fishing_loot",
          "name": "沖の釣り" (optional),
          "entries": [
            {"item_spec": "raw_fish", "weight": 70, "min_quantity": 1, "max_quantity": 2},
            {"item_spec": "shellfish", "weight": 20},
            {"item_spec": "treasure_compass", "weight": 1}
          ]
        }
      ]

    IDs は mapper に "loot_table" 名前空間で登録する。
    """
    out: List[ScenarioLootTableDefinition] = []
    for raw in raw_list:
        string_id = raw.get("id")
        if not isinstance(string_id, str) or not string_id:
            raise ScenarioLoadError(
                f"loot_tables[*].id is required (got {string_id!r})"
            )
        table_id = mapper.register("loot_table", string_id)
        entries_raw = raw.get("entries", [])
        if not entries_raw:
            raise ScenarioLoadError(
                f"loot_tables[{string_id!r}].entries must be non-empty"
            )
        entries: List[ScenarioLootEntry] = []
        for index, e in enumerate(entries_raw):
            item_sid = e.get("item_spec")
            if not isinstance(item_sid, str):
                raise ScenarioLoadError(
                    f"loot_tables[{string_id!r}].entries[{index}].item_spec required"
                )
            # PR #1 follow-up: 数値変換失敗 (例: weight="abc") は Python の
            # ValueError として落ちると場所が分からない。シナリオ作家が
            # 直すべき項目を ScenarioLoadError に包んで surface する。
            try:
                weight = int(e.get("weight", 1))
                min_q = int(e.get("min_quantity", 1))
                max_q = int(e.get("max_quantity", 1))
            except (TypeError, ValueError) as exc:
                raise ScenarioLoadError(
                    f"loot_tables[{string_id!r}].entries[{index}] has "
                    f"non-integer weight/quantity: {e!r}"
                ) from exc
            if weight < 0:
                raise ScenarioLoadError(
                    f"loot_tables[{string_id!r}].entries[{index}].weight "
                    f"must be >= 0 (got {weight})"
                )
            if min_q < 1:
                raise ScenarioLoadError(
                    f"loot_tables[{string_id!r}].entries[{index}].min_quantity "
                    f"must be >= 1 (got {min_q})"
                )
            if max_q < min_q:
                raise ScenarioLoadError(
                    f"loot_tables[{string_id!r}].entries[{index}].max_quantity "
                    f"({max_q}) must be >= min_quantity ({min_q})"
                )
            entries.append(ScenarioLootEntry(
                item_spec_id=mapper.get_int("item_spec", item_sid),
                weight=weight,
                min_quantity=min_q,
                max_quantity=max_q,
            ))
        out.append(ScenarioLootTableDefinition(
            string_id=string_id,
            table_id=table_id,
            name=raw.get("name", ""),
            entries=tuple(entries),
        ))
    return tuple(out)

def parse_merchants(
    raw_block: Any,
    mapper: ScenarioIdMapper,
) -> Tuple[ScenarioMerchantDefinition, ...]:
    """`merchants` block を解析する (経済統合 Phase 0)。

    スキーマ:
      "merchants": [
        {
          "id": "gustav",
          "name": "商人グスタフ",
          "spot": "market_square",
          "sells": [{"item_spec": "bread", "price": 10}],
          "buys": [{"item_spec": "herb", "price": 6}]
        }
      ]

    未宣言・空配列はどちらも空 tuple (商人の居ない世界) として扱う。
    参照 (spot / item_spec) はこの時点で解決し、実在しない名前は
    実行前に落とす。
    """
    if raw_block is None:
        return ()
    if not isinstance(raw_block, list):
        raise ScenarioLoadError(
            f"merchants は配列で宣言してください (got {type(raw_block).__name__})"
        )

    merchants: List[ScenarioMerchantDefinition] = []
    seen_ids: set = set()
    seen_names: set = set()
    for index, raw in enumerate(raw_block):
        if not isinstance(raw, dict):
            raise ScenarioLoadError(
                f"merchants[{index}] はオブジェクトで宣言してください "
                f"(got {type(raw).__name__})"
            )
        string_id = parse_merchant_id(raw.get("id"), index=index)
        if string_id in seen_ids:
            raise ScenarioLoadError(
                f"merchants[{index}].id が重複しています: {string_id!r}"
            )
        seen_ids.add(string_id)

        name = parse_merchant_name(raw.get("name"), string_id=string_id)
        if name in seen_names:
            # 名前が重なると、将来 LLM が名前で商人を指すときに
            # どちらの商人か決まらない。宣言の時点で潰す。
            raise ScenarioLoadError(
                f"merchants[{string_id!r}].name がほかの商人と重複しています: {name!r}"
            )
        seen_names.add(name)

        spot_id = parse_merchant_spot(
            raw.get("spot"), mapper, string_id=string_id,
        )
        sells = parse_merchant_price_list(
            raw.get("sells"), mapper, string_id=string_id, section="sells",
        )
        buys = parse_merchant_price_list(
            raw.get("buys"), mapper, string_id=string_id, section="buys",
        )
        if not sells and not buys:
            raise ScenarioLoadError(
                f"merchants[{string_id!r}] は sells と buys が両方空です。"
                "売る品か買い取る品のどちらかを宣言してください"
            )

        merchants.append(ScenarioMerchantDefinition(
            string_id=string_id,
            merchant_id=mapper.register("merchant", string_id),
            name=name,
            spot_id=spot_id,
            sells=sells,
            buys=buys,
        ))
    return tuple(merchants)

def parse_merchant_id(raw: Any, *, index: int) -> str:
    """`merchants[].id` を検証する。"""
    if not isinstance(raw, str) or not raw:
        raise ScenarioLoadError(
            f"merchants[{index}].id は空でない文字列で宣言してください (got {raw!r})"
        )
    return raw

def parse_merchant_name(raw: Any, *, string_id: str) -> str:
    """`merchants[].name` を検証する (表示名なので空白のみも弾く)。"""
    if not isinstance(raw, str) or not raw.strip():
        raise ScenarioLoadError(
            f"merchants[{string_id!r}].name は空でない文字列で宣言してください "
            f"(got {raw!r})"
        )
    return raw.strip()

def parse_merchant_spot(
    raw: Any, mapper: ScenarioIdMapper, *, string_id: str,
) -> SpotId:
    """`merchants[].spot` を検証し、実在する spot への参照へ解決する。"""
    if not isinstance(raw, str) or not raw:
        raise ScenarioLoadError(
            f"merchants[{string_id!r}].spot は空でない文字列で宣言してください "
            f"(got {raw!r})"
        )
    if not mapper.contains("spot", raw):
        raise ScenarioLoadError(
            f"merchants[{string_id!r}].spot が実在しない spot を参照しています: {raw!r}"
        )
    return SpotId.create(mapper.get_int("spot", raw))

def parse_merchant_price_list(
    raw_list: Any,
    mapper: ScenarioIdMapper,
    *,
    string_id: str,
    section: str,
) -> Tuple[ScenarioMerchantPriceEntry, ...]:
    """`merchants[].sells` / `.buys` を解析する。

    同じ item_spec を同一リスト内に 2 度書くのは、どちらの価格が効くか
    決まらないので弾く。sells と buys にまたがる重複はスプレッドの土台
    なので許す。
    """
    if raw_list is None:
        return ()
    if not isinstance(raw_list, list):
        raise ScenarioLoadError(
            f"merchants[{string_id!r}].{section} は配列で宣言してください "
            f"(got {type(raw_list).__name__})"
        )

    entries: List[ScenarioMerchantPriceEntry] = []
    seen_item_specs: set = set()
    for index, raw in enumerate(raw_list):
        if not isinstance(raw, dict):
            raise ScenarioLoadError(
                f"merchants[{string_id!r}].{section}[{index}] はオブジェクトで"
                f"宣言してください (got {type(raw).__name__})"
            )
        item_spec = raw.get("item_spec")
        if not isinstance(item_spec, str) or not item_spec:
            raise ScenarioLoadError(
                f"merchants[{string_id!r}].{section}[{index}].item_spec は"
                f"空でない文字列で宣言してください (got {item_spec!r})"
            )
        if not mapper.contains("item_spec", item_spec):
            raise ScenarioLoadError(
                f"merchants[{string_id!r}].{section}[{index}].item_spec が"
                f"実在しない item_spec を参照しています: {item_spec!r}"
            )
        if item_spec in seen_item_specs:
            raise ScenarioLoadError(
                f"merchants[{string_id!r}].{section} に同じ item_spec が"
                f"二度宣言されています: {item_spec!r}"
            )
        seen_item_specs.add(item_spec)

        price = raw.get("price")
        # bool を除くのは、True が int として通ると price=1 の宣言と
        # 見分けが付かなくなるため。
        if isinstance(price, bool) or not isinstance(price, int):
            raise ScenarioLoadError(
                f"merchants[{string_id!r}].{section}[{index}].price は"
                f"整数で宣言してください (got {price!r})"
            )
        if price <= 0:
            raise ScenarioLoadError(
                f"merchants[{string_id!r}].{section}[{index}].price は"
                f"1 以上で宣言してください (got {price})"
            )
        entries.append(ScenarioMerchantPriceEntry(
            item_spec_id=mapper.get_int("item_spec", item_spec),
            price=price,
        ))
    return tuple(entries)

def parse_item_interaction_registry(
    items_raw: List[Dict[str, Any]],
    mapper: ScenarioIdMapper,
) -> ItemInteractionRegistry:
    """item_specs の操作を world_graph 側の登録簿へ射影する。

    次の効果は物体 interaction では対象省略時に操作元の物体へ作用する。
    道具 interaction にはその物体が無いため、``target_object`` の明示を
    必須にする: ``DEPOSIT_ITEM_TO_OBJECT``, ``INCREMENT_OBJECT_STATE``,
    ``CONSUME_OBJECT_STOCK``, ``CHANGE_OBJECT_STATE``,
    ``RECORD_OBJECT_STATE_TICK``, ``WRITE_PLAYER_TEXT``,
    ``SHOW_PLAYER_TEXT``。省略を黙って無効化すると、作者の宣言だけが残る
    静かな失敗になるため読み込み時に止める。

    道具の待ち時間キーは ``(ItemSpecId, cooldown_key)`` で、共有単位は
    ``cooldown_scope`` が actor / world のどちらかを決める。group 未指定なら
    action_name ごとに独立し、同じ group を明示した操作だけが待ち時間を共有する。
    ItemSpecId を含めるので、別品目の同名 group は衝突しない。
    """
    implicit_object_effects = frozenset(
        {
            InteractionEffectTypeEnum.DEPOSIT_ITEM_TO_OBJECT,
            InteractionEffectTypeEnum.INCREMENT_OBJECT_STATE,
            InteractionEffectTypeEnum.CONSUME_OBJECT_STOCK,
            InteractionEffectTypeEnum.CHANGE_OBJECT_STATE,
            InteractionEffectTypeEnum.RECORD_OBJECT_STATE_TICK,
            InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
            InteractionEffectTypeEnum.SHOW_PLAYER_TEXT,
        }
    )
    entries: Dict[ItemSpecId, Tuple[InteractionDef, ...]] = {}
    for item in items_raw:
        interactions = tuple(
            parse_interaction_def(raw, mapper)
            for raw in item.get("interactions", [])
        )
        action_names = [interaction.action_name for interaction in interactions]
        if len(set(action_names)) != len(action_names):
            duplicated = next(
                name for name in action_names if action_names.count(name) > 1
            )
            raise ScenarioLoadError(
                f"item '{item['id']}' interaction action_name "
                f"'{duplicated}' が重複しています"
            )
        for interaction in interactions:
            for effect in interaction.effects:
                if (
                    effect.effect_type in implicit_object_effects
                    and "object_id" not in effect.parameters
                ):
                    raise ScenarioLoadError(
                        f"item '{item['id']}' interaction "
                        f"'{interaction.action_name}': {effect.effect_type.value} "
                        "requires parameters.target_object"
                    )
        if interactions:
            entries[ItemSpecId.create(mapper.get_int("item_spec", item["id"]))] = (
                interactions
            )
    return ItemInteractionRegistry(entries)

def parse_consume_effect( raw: Any, sid: str,
) -> Optional[ItemEffect]:
    """JSON の consume_effect (単一 dict or list) を ItemEffect に変換する。

    対応形式:
    - None / 未指定 → None (使えないアイテム)
    - 単一 dict: `{"type": "heal_hp", "amount": 5}`
    - list: `[{"type": "heal_hp", "amount": 5}, {"type": "satisfy_need", ...}]`
      → CompositeItemEffect でまとめる (1 要素なら単一として返す)
    """
    if raw is None:
        return None
    # 統一して list に正規化
    entries = raw if isinstance(raw, list) else [raw]
    if not entries:
        return None
    parsed = [parse_single_consume_effect(e, sid) for e in entries]
    if len(parsed) == 1:
        return parsed[0]
    return CompositeItemEffect(effects=tuple(parsed))

def parse_single_consume_effect( entry: Dict[str, Any], sid: str,
) -> ItemEffect:
    """1 つの effect dict を ItemEffect サブクラスに変換する。"""
    if not isinstance(entry, dict):
        raise ValueError(
            f"item '{sid}': consume_effect entry must be a dict, got {type(entry).__name__}"
        )
    etype = entry.get("type")
    if not etype:
        raise ValueError(f"item '{sid}': consume_effect entry missing 'type'")
    if etype == "heal_hp":
        return HealEffect(amount=int(entry["amount"]))
    if etype == "damage_hp":
        return DamageHpEffect(amount=int(entry["amount"]))
    if etype == "recover_mp":
        return RecoverMpEffect(amount=int(entry["amount"]))
    if etype == "gold":
        return GoldEffect(amount=int(entry["amount"]))
    if etype == "exp":
        return ExpEffect(amount=int(entry["amount"]))
    if etype == "satisfy_need":
        need = entry.get("need_type") or entry.get("need_type_name")
        if not need:
            raise ValueError(
                f"item '{sid}': satisfy_need requires 'need_type' (e.g. 'HUNGER')"
            )
        return SatisfyNeedEffect(
            need_type_name=str(need), amount=int(entry["amount"]),
        )
    if etype == "revive":
        # Issue #621 Phase 3a: ダウン player を蘇生する効果。
        # hp_rate は max_hp に対する比率 (0.0-1.0)。範囲 validation は
        # ReviveEffect.__post_init__ が ItemEffectValidationException で行う。
        if "hp_rate" not in entry:
            raise ValueError(
                f"item '{sid}': revive requires 'hp_rate' (e.g. 0.4)"
            )
        return ReviveEffect(hp_rate=float(entry["hp_rate"]))
    raise ValueError(
        f"item '{sid}': unknown consume_effect type '{etype}' "
        "(expected: heal_hp / damage_hp / recover_mp / gold / exp / satisfy_need / revive)"
    )

def parse_item_specs( items_raw: List[Dict[str, Any]], mapper: ScenarioIdMapper,
) -> List[ItemSpecDefinition]:
    defs: List[ItemSpecDefinition] = []
    for item in items_raw:
        sid = item["id"]
        numeric = mapper.register("item_spec", sid)
        spoils_raw = item.get("spoils_after_ticks")
        spoils_after_ticks: Optional[int] = None
        if spoils_raw is not None:
            # 不正値はシナリオ作家ミスとして boundary で弾く。ItemSpec の
            # __post_init__ でも弾かれるが、ここで明示しておくと loader 段で
            # 早期 fail し、エラー位置が JSON 単位で分かりやすい。
            spoils_after_ticks = int(spoils_raw)
            if spoils_after_ticks <= 0:
                raise ValueError(
                    f"item '{sid}': spoils_after_ticks must be positive, got {spoils_after_ticks}"
                )
        consume_effect = parse_consume_effect(
            item.get("consume_effect"), sid,
        )
        fatigue_recovery_raw = item.get("fatigue_recovery", 0)
        try:
            fatigue_recovery = int(fatigue_recovery_raw)
        except (TypeError, ValueError):
            raise ValueError(
                f"item '{sid}': fatigue_recovery must be int, got {fatigue_recovery_raw!r}"
            )
        if fatigue_recovery < 0:
            raise ValueError(
                f"item '{sid}': fatigue_recovery must be non-negative, got {fatigue_recovery}"
            )
        usage_hint_raw = item.get("usage_hint", "")
        if not isinstance(usage_hint_raw, str):
            raise ValueError(
                f"item '{sid}': usage_hint must be string, got {usage_hint_raw!r}"
            )
        usage_hint = usage_hint_raw.strip()
        if "usage_hint" in item and not usage_hint:
            raise ValueError(f"item '{sid}': usage_hint must not be blank")
        defs.append(ItemSpecDefinition(
            string_id=sid,
            spec_id=ItemSpecId.create(numeric),
            name=item["name"],
            description=item.get("description", ""),
            category=item.get("category", "GENERAL"),
            is_light_source=parse_bool(
                item.get("is_light_source", False),
                path=f"item {sid}.is_light_source",
            ),
            spoils_after_ticks=spoils_after_ticks,
            consume_effect=consume_effect,
            fatigue_recovery=fatigue_recovery,
            usage_hint=usage_hint,
        ))
    return defs

def parse_initial_item(
    raw: Any,
    mapper: ScenarioIdMapper,
    *,
    owner_id: str,
) -> InitialItemSpec:
    """`initial_items` の 1 要素を `InitialItemSpec` にパース。

    受け付ける形式は 2 つ:
      - `"spec_string_id"` (state なし、Phase 4-A 以前のシナリオと互換)
      - `{"spec": "spec_string_id", "state": {...}}` (state を仕込める Phase 4-D 形式)
    どちらも 1 つの InitialItemSpec に正規化される。
    """
    if isinstance(raw, str):
        spec_id = ItemSpecId.create(mapper.get_int("item_spec", raw))
        return InitialItemSpec(spec_id=spec_id, state={})
    if isinstance(raw, dict):
        spec_string = raw.get("spec")
        if not isinstance(spec_string, str) or not spec_string:
            raise ScenarioLoadError(
                f"players[{owner_id}].initial_items[*].spec is required "
                f"(got {spec_string!r})"
            )
        spec_id = ItemSpecId.create(mapper.get_int("item_spec", spec_string))
        state_raw = raw.get("state", {})
        if not isinstance(state_raw, dict):
            raise ScenarioLoadError(
                f"players[{owner_id}].initial_items[*].state must be an object "
                f"(got {type(state_raw).__name__})"
            )
        return InitialItemSpec(spec_id=spec_id, state=dict(state_raw))
    raise ScenarioLoadError(
        f"players[{owner_id}].initial_items[*] must be a string or object "
        f"(got {type(raw).__name__})"
    )

def parse_needs_config(raw: Any) -> ScenarioNeedsConfig:
    """needs 機構の調整値を読み、無宣言なら飢餓ダメージを無効にする。"""
    if raw is None:
        return ScenarioNeedsConfig()
    if not isinstance(raw, dict):
        raise ScenarioLoadError("needs must be an object")
    starvation_damage = raw.get("starvation_damage_per_tick", 0)
    if (
        isinstance(starvation_damage, bool)
        or not isinstance(starvation_damage, int)
        or starvation_damage < 0
    ):
        raise ScenarioLoadError(
            "needs.starvation_damage_per_tick must be a non-negative integer"
        )
    return ScenarioNeedsConfig(
        starvation_damage_per_tick=starvation_damage,
    )

