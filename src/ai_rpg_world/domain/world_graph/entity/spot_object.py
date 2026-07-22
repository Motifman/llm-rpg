from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, FrozenSet, Optional, Tuple

from ai_rpg_world.domain.world.exception.map_exception import SpotNameEmptyException
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    SpotObjectValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.object_description_variant import (
    ObjectDescriptionVariant,
)
from ai_rpg_world.domain.world_graph.value_object.puzzle_state import PuzzleState
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.trap_def import TrapDef


# 備蓄プールの内部 bookkeeping state key。lazy 再生用の生値なので、第三者
# プロンプトには常に出さない (visible_state で汎用除外する)。
_STOCK_POOL_STATE_KEYS: FrozenSet[str] = frozenset(
    {"stock", "stock_capacity", "stock_tick", "stock_refill_interval"}
)

# 再利用待ちオブジェクトを表す内部 state key。`available` は条件判定用の
# bool で、`last_harvest_tick` は再生時刻計算用の内部 tick。どちらも生値の
# まま prompt に出すと「false」「42」のような、次の一手につながらない表示になる。
_REACTIVE_AVAILABILITY_STATE_KEY = "available"
_REACTIVE_LAST_HARVEST_TICK_STATE_KEY = "last_harvest_tick"
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

    def visible_state(self) -> Dict[str, Any]:
        """`hidden_state_keys` を除いた、第三者プロンプトに載せて良い state。

        プロンプトの「スポット内オブジェクトの状態」セクションを組み立てる
        builder から呼ばれる。effect 適用や永続化には影響しない。
        """
        # 備蓄プールの内部 bookkeeping key は常に除外する。生値のまま出すと
        # `stock=0` 等の未整形値が漏れ、lazy 再生を計算しないので「0 なのに
        # 採れる」矛盾が見える。per-object hidden_state_keys 設定に頼ると設定漏れ
        # で漏れる (コード内既知回帰) ため、pool key は汎用除外する。
        excluded = (
            self.hidden_state_keys
            | _STOCK_POOL_STATE_KEYS
            | frozenset({_REACTIVE_LAST_HARVEST_TICK_STATE_KEY})
        )
        visible: Dict[str, Any] = {}
        tags: list[str] = []
        for key, value in self.state.items():
            if key in excluded:
                continue
            if key == _REACTIVE_AVAILABILITY_STATE_KEY:
                if value is False:
                    tags.append(self.unavailable_hint or _DEFAULT_UNAVAILABLE_HINT)
                continue
            visible[key] = value
        if tags:
            visible = {VISIBLE_STATE_TAGS_KEY: tuple(tags), **visible}
        return visible

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
