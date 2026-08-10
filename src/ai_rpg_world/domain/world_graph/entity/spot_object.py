from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, FrozenSet, Optional, Tuple

from ai_rpg_world.domain.world.exception.map_exception import SpotNameEmptyException
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    SpotObjectValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.object_description_variant import (
    ObjectDescriptionVariant,
)
from ai_rpg_world.domain.world_graph.value_object.puzzle_state import PuzzleState
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.state_display_rule import (
    StateDisplayRule,
    state_display_values_equal,
)
from ai_rpg_world.domain.world_graph.value_object.trap_def import TrapDef


# 備蓄プールの内部 bookkeeping state key。lazy 再生用の生値なので、第三者
# プロンプトには常に出さない (visible_state で汎用除外する)。
_STOCK_POOL_STATE_KEYS: FrozenSet[str] = frozenset(
    {"stock", "stock_capacity", "stock_tick", "stock_refill_interval"}
)

# 再利用待ちオブジェクトを表す内部 state key。生値のまま prompt に出すと
# 「false」のような、次の一手につながらない表示になる。
#
# ここにかつて `last_harvest_tick` という**綴りが 1 つ直書き**されていた。
# 流木や木の実はその名前を選んだので守られ、`last_lit_tick` と名付けた
# 焚き火跡は守られずに漏れていた。守るべきは名前ではなく「手番を記録する
# 効果が書いた key」なので、判断を書き込む側 (RECORD_OBJECT_STATE_TICK と
# scenario_loader の導出) へ移した。
#
# 線引き: engine が自分で作る名前 (_STOCK_POOL_STATE_KEYS) は直書きしてよい。
# シナリオが決める名前を直書きしてはいけない。
_REACTIVE_AVAILABILITY_STATE_KEY = "available"
VISIBLE_STATE_TAGS_KEY = "__tags__"
_DEFAULT_UNAVAILABLE_HINT = "今は採れない・時間を置けば戻る"


@dataclass(frozen=True)
class SpotObject:
    object_id: SpotObjectId
    name: str
    description: str
    object_type: SpotObjectTypeEnum
    state: Dict[str, Any]
    interactions: Tuple[InteractionDef, ...]
    description_variants: Tuple[ObjectDescriptionVariant, ...] = ()
    is_visible: bool = True
    # 蓄光表示や自発光などにより、照明が無くても位置と操作が分かる物体。
    # ``is_visible`` が false の物体を明るさだけで公開してはいけないため、
    # 通常の可視性とは独立した追加条件として扱う。
    is_visible_in_dark: bool = False
    trap: Optional[TrapDef] = None
    puzzle: Optional[PuzzleState] = None
    detail_read_by: FrozenSet[int] = frozenset()
    # `available=false` のとき prompt 用 state に出す作者指定の復帰ヒント。
    # state の実値は bool のまま保ち、表示だけを scenario 側で調整できるようにする。
    unavailable_hint: Optional[str] = None
    # Phase 4-E: 第三者プロンプトに載せたくない state キー (例: trap_armed,
    # secret_solution)。`SpotGraphCurrentStateBuilder` が
    # `SpotGraphObjectEntry.state` を組み立てるときに除外する。
    # effect の visibility (HIDDEN) とは独立で、こちらは「state 値そのもの
    # を周囲のプレイヤーに常に見せない」という静的な視認性属性。
    hidden_state_keys: FrozenSet[str] = frozenset()
    # state の生値を prompt 用の作者文言へ変換する完全一致 / 整数下限ルール。
    # どちらにも該当しない state は従来どおり生値を出し、宣言漏れを検出する。
    state_display: Tuple[StateDisplayRule, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise SpotNameEmptyException("Spot object name cannot be empty")
        if self.unavailable_hint is not None:
            if not isinstance(self.unavailable_hint, str) or not self.unavailable_hint.strip():
                raise SpotObjectValidationException(
                    "Spot object unavailable_hint must be a non-empty string"
                )

    def with_state(self, new_state: Dict[str, Any]) -> SpotObject:
        return replace(self, state=dict(new_state))

    def with_additional_hidden_state_keys(self, keys: FrozenSet[str]) -> SpotObject:
        """`hidden_state_keys` に新たな key を追加した (和集合) コピーを返す。

        PR-J: 「書いた内容は examine した本人だけが読める」看板のように、
        state key を書き込む effect 自体が「これは第三者に見せない」ことを
        自分で保証したいケースのためのヘルパ。シナリオ JSON 側で
        hidden_state_keys を設定する運用に頼ると、設定漏れがあれば本文が
        `visible_state()` 経由で周囲に漏れる (実際に発生した回帰)。
        """
        if not keys:
            return self
        return replace(self, hidden_state_keys=self.hidden_state_keys | frozenset(keys))

    def visible_state(
        self,
        *,
        current_tick: int | None = None,
        effective_lighting: LightingEnum | None = None,
    ) -> Dict[str, Any]:
        """`hidden_state_keys` を除いた、第三者プロンプトに載せて良い state。

        プロンプトの「スポット内オブジェクトの状態」セクションを組み立てる
        builder から呼ばれる。effect 適用や永続化には影響しない。時限規則は
        hidden な記録手番を評価して作者文言だけを返し、生の数値は返さない。
        """
        # 備蓄プールの内部 bookkeeping key は常に除外する。生値のまま出すと
        # `stock=0` 等の未整形値が漏れ、lazy 再生を計算しないので「0 なのに
        # 採れる」矛盾が見える。per-object hidden_state_keys 設定に頼ると設定漏れ
        # で漏れる (コード内既知回帰) ため、pool key は汎用除外する。
        excluded = self.hidden_state_keys | _STOCK_POOL_STATE_KEYS
        rules_by_key: dict[str, list[StateDisplayRule]] = {}
        for rule in self.state_display:
            rules_by_key.setdefault(rule.key, []).append(rule)
        if any(rule.within_ticks is not None for rule in self.state_display):
            if current_tick is None:
                raise SpotObjectValidationException(
                    "SpotObject.visible_state requires current_tick for within_ticks rules"
                )
        if any(rule.requires_light for rule in self.state_display):
            if effective_lighting is None:
                raise SpotObjectValidationException(
                    "SpotObject.visible_state requires effective_lighting "
                    "for requires_light rules"
                )

        visible: Dict[str, Any] = {}
        tags: list[str] = []
        for key, value in self.state.items():
            rules = rules_by_key.get(key, ())
            recent_rules = tuple(
                rule for rule in rules if rule.within_ticks is not None
            )
            if recent_rules:
                # loader は within_ticks を RECORD_OBJECT_STATE_TICK の key に
                # だけ許し、その key を hidden にする。entity 側でも生値を
                # 決して返さず、構築直後の直接利用でも tick 漏洩を防ぐ。
                if type(value) is int:
                    matched_rule = min(
                        (
                            rule
                            for rule in recent_rules
                            if value <= current_tick
                            and current_tick - value <= rule.within_ticks
                        ),
                        key=lambda rule: rule.within_ticks,
                        default=None,
                    )
                    if matched_rule is not None and self._rule_is_visible_in_light(
                        matched_rule, effective_lighting
                    ):
                        tags.append(matched_rule.text)
                continue
            if key in excluded:
                continue
            if rules:
                matched_rule = next(
                    (
                        rule
                        for rule in rules
                        if rule.at_least is None
                        and state_display_values_equal(rule.value, value)
                    ),
                    None,
                )
                if matched_rule is None and type(value) is int:
                    matched_rule = max(
                        (
                            rule
                            for rule in rules
                            if rule.at_least is not None
                            and value >= rule.at_least
                        ),
                        key=lambda rule: rule.at_least,
                        default=None,
                    )
                if matched_rule is not None:
                    if self._rule_is_visible_in_light(
                        matched_rule, effective_lighting
                    ):
                        tags.append(matched_rule.text)
                    continue
                # 完全一致にも at_least にも該当しなければ生値を出す。ここで
                # 隠したり最近傍へ丸めたりすると、シナリオ作者の宣言漏れが
                # prompt からもテストからも見えなくなる。
                visible[key] = value
                continue
            if key == _REACTIVE_AVAILABILITY_STATE_KEY:
                if value is False:
                    tags.append(self.unavailable_hint or _DEFAULT_UNAVAILABLE_HINT)
                continue
            visible[key] = value
        if tags:
            visible = {VISIBLE_STATE_TAGS_KEY: tuple(tags), **visible}
        return visible

    @staticmethod
    def _rule_is_visible_in_light(
        rule: StateDisplayRule,
        effective_lighting: LightingEnum | None,
    ) -> bool:
        """requires_light の規則を、他の照明判断と同じ enum で評価する。

        現在の閾値は ``SpotPerceptionService.can_see_objects`` と同じだが、
        「物体が見えるか」と「細かな痕跡を読めるか」は別の問いとして保つ。
        閾値を分岐させるときは、両方の判断と試験を意図的に見直すこと。
        """
        if not rule.requires_light:
            return True
        return effective_lighting in (LightingEnum.BRIGHT, LightingEnum.DIM)

    def with_visible(self, visible: bool) -> SpotObject:
        return replace(self, is_visible=visible)

    def with_puzzle(self, puzzle: Optional[PuzzleState]) -> SpotObject:
        return replace(self, puzzle=puzzle)

    def with_detail_read(self, entity_id: int) -> SpotObject:
        """エージェントが詳細を「読んだ」ことを記録する。"""
        return replace(self, detail_read_by=self.detail_read_by | {entity_id})

    def resolved_description(
        self,
        world_flags: FrozenSet[str],
        *,
        viewer_entity_id: int | None = None,
    ) -> str:
        """状態とフラグに応じた説明を返す。

        requires_read=True のバリアントは viewer_entity_id が
        detail_read_by に含まれる場合のみ適用される。
        """
        for variant in self.description_variants:
            if variant.requires_read:
                if viewer_entity_id is None or viewer_entity_id not in self.detail_read_by:
                    continue
            if variant.required_flag and variant.required_flag not in world_flags:
                continue
            if variant.required_state:
                if any(self.state.get(k) != v for k, v in variant.required_state.items()):
                    continue
            return variant.description
        return self.description
