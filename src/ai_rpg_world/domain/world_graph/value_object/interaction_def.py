from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect


@dataclass(frozen=True)
class InteractionDef:
    """インタラクションの定義。

    Attributes:
        action_name: 操作名（"submit_code" など）。
        display_label: UI 表示用ラベル。
        preconditions: 全て真でないと実行できない前提条件群（暗黙の AND）。
        effects: 成功時に適用される効果群。
        on_failure_observation: 前提条件が満たされず実行が拒否されたとき、
            同じスポットに居る他プレイヤーへ届ける観測メッセージ。
            アクター本人にはツール結果として `failure_message` が返る。
            None の場合は失敗観測を発行しない。
        witness_observation_message: 成功時に同じスポットの目撃者へ届ける
            観測メッセージ。本人向けの `result_message` とは別で、掲示の
            中身など行為者だけが得た情報を他者へ漏らさないための文面。
            `{actor}` / `{object}` / `{action}` を formatter で展開できる。
        witness_policy: Phase G #1: 成功観測の配信範囲。
            - SAME_SPOT (デフォルト): 同 spot の他プレイヤーに観測が流れる
              (既存挙動と互換)
            - ACTOR_ONLY: 行為者本人にしか観測が届かない (私的な閲覧・
              壁の写真を見つめる等)。設計 §1 / §5 の「秘匿行為」を成立させる
            on_failure_observation 自体は本フィールドの影響を受けない
            (failure_message は別 channel)。本フィールドは成功 event の配信のみを制御
    """

    action_name: str
    display_label: str
    preconditions: Tuple[InteractionCondition, ...]
    effects: Tuple[InteractionEffect, ...]
    on_failure_observation: Optional[str] = None
    witness_observation_message: Optional[str] = None
    witness_policy: WitnessPolicy = WitnessPolicy.SAME_SPOT
