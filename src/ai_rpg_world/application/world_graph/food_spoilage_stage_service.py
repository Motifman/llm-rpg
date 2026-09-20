"""食料腐敗ステージサービス (Phase D-2)。

`ItemSpec.spoils_after_ticks` が設定されたアイテム instance について、
毎 tick で経過時間を判定し、閾値を越えたものに `state['spoiled'] = True`
を立てる。腐敗が走った instance は `ItemSpoiledEvent` を積み、確定後の通知は
`CommandScope` のdispatcherへ委ねる。

## 設計のキモ

### acquired_at_tick の遅延初期化

「いつ取得したか」を厳密にトラッキングするには gather / drop / loot / craft の
全パスでイベントを拾って `state['acquired_at_tick']` を書き込む必要があるが、
それは scope 爆発する。代わりに「最初にこの stage が見た tick」を
acquired_at_tick として遅延書き込みする方式を採る:

- pros: 取得パスに手を入れなくて済む。scenario 開始時に既に存在するアイテム
  も自然に「scenario 開始 tick から数える」になる
- cons: tick 飛び (skip) 中に gather しても古い tick が記録される可能性がある。
  ただし現状の tick driver はサーバ実行中は飛ばないので実害なし

### spoils 判定の純粋性

state[spoiled] を `True` にする以外の副作用は持たない。
- 腐敗時のeventには「腐ったアイテム instance id + spec id + spec名」を記録する
- 腐敗食を使ったときの damage 等は別 stage (LLM 経由 use_item の判定) で処理
- LLM プロンプト側で state[spoiled] を読み取って "(腐敗)" 表示する責務は
  prompt builder 側に持たせる
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Mapping, Optional

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.spoilage import (
    STATE_KEY_ACQUIRED_AT_TICK,
    SpoilageAdvanceKind,
)

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope_factory import (
        CommandScopeFactoryPort,
    )
    from ai_rpg_world.application.world_graph.food_spoilage_command_repository_provider import (
        FoodSpoilageCommandRepositoryProviderPort,
    )

logger = logging.getLogger(__name__)


class FoodSpoilageStageService:
    """毎 tick で「腐るアイテム」を走査し、閾値を越えたものに spoiled フラグを立てる。

    spoils_after_ticks が設定された ItemSpec を構築時に列挙して保持する。
    runtime が新 spec を後から登録するケースは現状想定していない
    (シナリオ起動時に全 spec が出揃う前提)。
    """

    def __init__(
        self,
        spoilable_specs: Mapping[ItemSpecId, int],
        *,
        command_scope_factory: Optional[
            "CommandScopeFactoryPort[FoodSpoilageCommandRepositoryProviderPort]"
        ] = None,
    ) -> None:
        """
        Args:
            spoilable_specs: {ItemSpecId: spoils_after_ticks} の写像。
                空 dict なら stage は no-op になる (シナリオに腐る食料が無いとき)。
        """
        # tuple of (spec_id, threshold_ticks) として固定化。dict.items() の順序は
        # CPython では挿入順だが、明示的に tuple にして反復順を安定化させる。
        self._spoilable: tuple[tuple[ItemSpecId, int], ...] = tuple(
            (spec_id, int(threshold)) for spec_id, threshold in spoilable_specs.items()
        )
        self._command_scope_factory = command_scope_factory

    def set_command_scope_factory(
        self,
        factory: "CommandScopeFactoryPort[FoodSpoilageCommandRepositoryProviderPort]",
    ) -> None:
        """本番stageを全対象itemの1回の確定境界へ接続する。"""
        self._command_scope_factory = factory

    def run(self, current_tick: WorldTick) -> None:
        """全 spoilable spec を走査して acquired_at_tick / spoiled を更新する。

        腐敗eventはscope由来repositoryから`CommandContext`へ集め、確定後の
        dispatcherが日次集約用の観測バッファへ渡す。
        """
        if not self._spoilable:
            return
        scope_factory = self._command_scope_factory
        if scope_factory is None:
            raise RuntimeError(
                "food spoilageにはCommandScopeFactoryの配線が必要です"
            )
        with scope_factory.create() as scope:
            repositories = scope.repositories
            if repositories is None:
                raise RuntimeError(
                    "food spoilage用repository providerがありません"
                )
            self._run_with_repository(
                current_tick,
                repositories.items,
            )

    def _run_with_repository(
        self,
        current_tick: WorldTick,
        item_repository: ItemRepository,
    ) -> None:
        """指定repository上の全対象itemへ腐敗規則を適用する。"""
        for spec_id, _threshold in self._spoilable:
            instances = item_repository.find_by_spec_id(spec_id)
            for inst in instances:
                self._process_instance(
                    inst,
                    current_tick,
                    item_repository,
                )

    def _process_instance(
        self,
        item_aggregate: ItemAggregate,
        current_tick: WorldTick,
        item_repository: ItemRepository,
    ) -> None:
        result = item_aggregate.advance_spoilage(current_tick)
        if result.kind is SpoilageAdvanceKind.INVALID_ACQUIRED_AT:
            logger.warning(
                "Item instance %s has non-int acquired_at_tick=%r (type=%s), "
                "spoilage check skipped — シナリオ初期 state を見直すこと",
                item_aggregate.item_instance_id.value,
                item_aggregate.state.get(STATE_KEY_ACQUIRED_AT_TICK),
                type(item_aggregate.state.get(STATE_KEY_ACQUIRED_AT_TICK)).__name__,
            )
            return
        if result.state_changed:
            item_repository.save(item_aggregate)
