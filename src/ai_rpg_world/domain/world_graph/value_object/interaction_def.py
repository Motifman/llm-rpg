from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
from ai_rpg_world.domain.world_graph.enum.interaction_actor_plane import (
    InteractionActorPlane,
)
from ai_rpg_world.domain.world_graph.enum.interaction_cooldown_scope import (
    InteractionCooldownScope,
)
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionEffectValidationException,
)
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
        witness_observation_message_in_dark: 暗所で使う目撃者文面。指定時だけ
            実効照明で明所文と切り替える。行為者を伏せる文では ``{actor}`` を
            書かず、本文と構造化データの両方から名前を除く。
        witness_policy: Phase G #1: 成功観測の配信範囲。
            - SAME_SPOT (デフォルト): 同 spot の他プレイヤーに観測が流れる
              (既存挙動と互換)
            - ACTOR_ONLY: 行為者本人にしか観測が届かない (私的な閲覧・
              壁の写真を見つめる等)。設計 §1 / §5 の「秘匿行為」を成立させる
            on_failure_observation 自体は本フィールドの影響を受けない
            (failure_message は別 channel)。本フィールドは成功 event の配信のみを制御
        notify_target: 可視性の 3 軸目。対人 interaction で「対象本人に
            行為が届くか」だけを決める。``witness_policy`` (第三者に届くか) と
            ``EffectVisibility`` (効果が届くか) では表現できない。
            - False (デフォルト): 既存挙動
            - True: ACTOR_ONLY でも対象本人にだけ観測が届く。「毒を盛られた
              本人だけが異変に気づく」はこの組み合わせでしか書けない
            SAME_SPOT では対象は既に「同スポットの他プレイヤー」として
            含まれるので、本フィールドの有無で配信先は変わらない。
            物体 interaction には対象プレイヤーが居ないので意味を持たない
            (loader が読み込み時に落とす)。
        target_observation_message: 対象本人にだけ見せる観測メッセージ。
            秘匿行為では「誰にやられたか」を伏せたいことがあるので、目撃者
            向けの ``witness_observation_message`` とは別に書ける。
            省略時は目撃者向けの文面に「(あなたが対象だった)」を添える。
        cooldown_ticks: 同じ行為者が再び使えるようになるまでの tick 数。
            0 (既定) なら制限しない。**成功したときだけ**起点が更新される。
            空振りで待たされると、前提条件を確かめる行動そのものが罰になる。

            engine は「殺し」を知らない。どの行為に間隔を置くかはシナリオが
            決める。実 run 008 でインポスターが tick 4 と 6 に連続殺害して
            tick 7 で終わったのが動機。
        cooldown_group: 複数の action が共有する待ち時間の識別子。省略時は
            ``action_name`` を使う。明所用・暗所用のように同じ意味の行為を
            複数の宣言へ分けても、交互に使って待ち時間を迂回させない。
        cooldown_scope: 待ち時間を共有する単位。``actor`` (既定) は行為者ごと、
            ``world`` は行為者を問わず同じ世界で一つの起点を使う。役職や陣営の
            意味は engine に持ち込まず、共有が必要な操作だけをシナリオが宣言する。
        allowed_actor_planes: 実行できる主体の存在層。既定は生者だけ。
            候補表示と実行拒否が同じ宣言を参照する。
        hide_when_flag_preconditions_fail: 世界フラグを解禁条件に使う操作を、
            不成立中は候補ごと伏せる。既定では失敗理由つきで残すため、
            時限ギミックのように操作の存在自体がまだ世界に現れていない場合だけ
            明示する。
    """

    action_name: str
    display_label: str
    preconditions: Tuple[InteractionCondition, ...]
    effects: Tuple[InteractionEffect, ...]
    on_failure_observation: Optional[str] = None
    witness_observation_message: Optional[str] = None
    witness_observation_message_in_dark: Optional[str] = None
    witness_policy: WitnessPolicy = WitnessPolicy.SAME_SPOT
    notify_target: bool = False
    target_observation_message: Optional[str] = None
    cooldown_ticks: int = 0
    cooldown_group: Optional[str] = None
    cooldown_scope: InteractionCooldownScope = InteractionCooldownScope.ACTOR
    allowed_actor_planes: Tuple[InteractionActorPlane, ...] = (
        InteractionActorPlane.LIVING,
    )
    hide_when_flag_preconditions_fail: bool = False

    def __post_init__(self) -> None:
        """会議開始を通常効果と同じinteractionへ混在させない。"""
        has_meeting_call = any(
            effect.effect_type is InteractionEffectTypeEnum.CALL_MEETING
            for effect in self.effects
        )
        if has_meeting_call and len(self.effects) != 1:
            raise InteractionEffectValidationException(
                "CALL_MEETING は単独の効果として宣言してください。"
                "会議開始は通常効果とは別のcommandです"
            )

    def allows_actor_plane(self, plane: InteractionActorPlane) -> bool:
        """候補表示と実行拒否が共有する、主体の存在層の判定を返す。"""
        return plane in self.allowed_actor_planes

    @property
    def effective_display_label(self) -> str:
        """意味表示を返し、loaderを迂回した空値だけaction_nameへ戻す。"""
        label = str(self.display_label or "").strip()
        return label or self.action_name

    @property
    def cooldown_key(self) -> str:
        """待ち時間を記録する共有キーを返す。"""
        group = str(self.cooldown_group or "").strip()
        return group or self.action_name
