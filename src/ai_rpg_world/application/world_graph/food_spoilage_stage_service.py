"""食料腐敗ステージサービス (Phase D-2)。

`ItemSpec.spoils_after_ticks` が設定されたアイテム instance について、
毎 tick で経過時間を判定し、閾値を越えたものに `state['spoiled'] = True`
を立てる。腐敗が走った instance はオプションの callback (observation 通知用)
で runtime に伝える。

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
- callback には「腐ったアイテム instance id + spec id」を渡す
- 腐敗食を使ったときの damage 等は別 stage (LLM 経由 use_item の判定) で処理
- LLM プロンプト側で state[spoiled] を読み取って "(腐敗)" 表示する責務は
  prompt builder 側に持たせる
"""

from __future__ import annotations

from typing import Callable, Mapping, Optional

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


# (item_instance_id, item_spec_id, spec_name) を受けて observation を流す callback。
# spec_name は LLM 観測テキスト化に使う想定。
SpoiledCallback = Callable[[ItemInstanceId, ItemSpecId, str], None]


# state key 名。同名のリテラルを各所で書くと typo 事故が起きるので集約する。
STATE_KEY_ACQUIRED_AT_TICK = "acquired_at_tick"
STATE_KEY_SPOILED = "spoiled"


class FoodSpoilageStageService:
    """毎 tick で「腐るアイテム」を走査し、閾値を越えたものに spoiled フラグを立てる。

    spoils_after_ticks が設定された ItemSpec を構築時に列挙して保持する。
    runtime が新 spec を後から登録するケースは現状想定していない
    (シナリオ起動時に全 spec が出揃う前提)。
    """

    def __init__(
        self,
        item_repository: ItemRepository,
        spoilable_specs: Mapping[ItemSpecId, int],
        *,
        spec_name_lookup: Optional[Callable[[ItemSpecId], str]] = None,
        spoiled_callback: Optional[SpoiledCallback] = None,
    ) -> None:
        """
        Args:
            item_repository: ItemAggregate 取得用。find_by_spec_id を毎 tick 叩く。
            spoilable_specs: {ItemSpecId: spoils_after_ticks} の写像。
                空 dict なら stage は no-op になる (シナリオに腐る食料が無いとき)。
            spec_name_lookup: spec_id → 人間可読名の解決 (observation 用)。None なら
                callback には空文字列が渡る。
            spoiled_callback: 腐敗が走った instance ごとに 1 度だけ呼ばれる。
                runtime 側で「[腐敗] 生魚が腐った」のような観測イベントを流すために
                使う。None なら silent。
        """
        self._item_repository = item_repository
        # tuple of (spec_id, threshold_ticks) として固定化。dict.items() の順序は
        # CPython では挿入順だが、明示的に tuple にして反復順を安定化させる。
        self._spoilable: tuple[tuple[ItemSpecId, int], ...] = tuple(
            (spec_id, int(threshold)) for spec_id, threshold in spoilable_specs.items()
        )
        self._spec_name_lookup = spec_name_lookup
        self._spoiled_callback = spoiled_callback

    def set_spoiled_callback(self, callback: Optional[SpoiledCallback]) -> None:
        """callback を後から差し替える (runtime 構築後の bind 用)。

        weather / scenario_event の callback と同じ pattern。stage の構築は
        runtime インスタンスより先に必要なため、callback だけ遅延 bind する。
        """
        self._spoiled_callback = callback

    def run(self, current_tick: WorldTick) -> None:
        """全 spoilable spec を走査して acquired_at_tick / spoiled を更新する。"""
        if not self._spoilable:
            return
        tick_value = current_tick.value
        for spec_id, threshold in self._spoilable:
            instances = self._item_repository.find_by_spec_id(spec_id)
            for inst in instances:
                self._process_instance(inst, spec_id, threshold, tick_value)

    def _process_instance(
        self,
        item_aggregate: ItemAggregate,
        spec_id: ItemSpecId,
        threshold: int,
        current_tick_value: int,
    ) -> None:
        state = item_aggregate.state
        # 既に腐っているなら何もしない (callback の二重発火防止)
        if state.get(STATE_KEY_SPOILED) is True:
            return
        acquired = state.get(STATE_KEY_ACQUIRED_AT_TICK)
        # 遅延初期化: 初めて見たときに現在 tick を記録する
        if acquired is None:
            item_aggregate.merge_state({STATE_KEY_ACQUIRED_AT_TICK: current_tick_value})
            self._item_repository.save(item_aggregate)
            return
        # 不正値 (シナリオ初期 state で文字列等を入れたケース) は warning log で
        # surface してから silent に「閾値未到達扱い」として保守的に何もしない。
        # silent skip だけだとシナリオ作家ミスを誰も気づけない (腐敗が永久に
        # 効かないアイテムが生まれる)。
        if not isinstance(acquired, int):
            import logging
            logging.getLogger(__name__).warning(
                "Item instance %s has non-int acquired_at_tick=%r (type=%s), "
                "spoilage check skipped — シナリオ初期 state を見直すこと",
                item_aggregate.item_instance_id.value,
                acquired,
                type(acquired).__name__,
            )
            return
        if current_tick_value - acquired < threshold:
            return
        # 閾値到達: spoiled フラグを立てる
        item_aggregate.merge_state({STATE_KEY_SPOILED: True})
        self._item_repository.save(item_aggregate)
        if self._spoiled_callback is not None:
            spec_name = (
                self._spec_name_lookup(spec_id) if self._spec_name_lookup else ""
            )
            self._spoiled_callback(item_aggregate.item_instance_id, spec_id, spec_name)
