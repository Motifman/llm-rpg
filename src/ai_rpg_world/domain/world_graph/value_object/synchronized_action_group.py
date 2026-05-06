"""協力ギミック #13 (同時操作パズル) のための同期アクショングループ。

複数のプレイヤーがそれぞれ別のオブジェクトに対して `prepare_action` を
猶予窓内に行うと、まとめて on_complete 効果が発火する。窓内に揃わなければ
on_timeout 効果が発火し、全プレイヤーの prepare が解除される。

設計判断:
- 猶予窓は `window_ticks > 0` で必須。1 だと「同 tick のみ」、2 以上だと
  N tick の窓を許す。
- 必須アクション数は 2 以上（単独だと "sync" の意味が無い）。
- on_complete は 1 つ以上の effects 必須（無いと group の意味が無い）。
- on_timeout は省略可（タイムアウト時に何も起きないこともある）。
- on_prepare_observation_message が指定されていれば、誰かが prepare した
  ときに同じスポットの他プレイヤーへ観測として配信される（recipient
  strategy 側で同スポット判定）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    SynchronizedActionGroupValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)


@dataclass(frozen=True)
class SynchronizedActionGroup:
    """同期アクショングループの定義。

    Attributes:
        group_id: 一意な ID。シナリオ内で重複してはならない。
        required_action_ids: 揃えるべき prepare action_id のタプル。各々を
            異なるプレイヤーが prepare すると group が完成する想定。
        window_ticks: 最初の prepare から何 tick 以内に他全てが揃えば良いか。
            1 = 同 tick のみ、2 = +1 tick まで、…。
        on_complete: 全 required_action_ids が窓内に揃ったときに適用する効果。
        on_timeout: 窓を超えても揃わなかったときに適用する効果（省略可）。
        on_prepare_observation_message: 誰かが prepare したときに同じスポット
            の他プレイヤーへ届ける観測文。None なら観測しない。
    """

    group_id: str
    required_action_ids: Tuple[str, ...]
    window_ticks: int
    on_complete: Tuple[InteractionEffect, ...]
    on_timeout: Tuple[InteractionEffect, ...] = ()
    on_prepare_observation_message: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.group_id:
            raise SynchronizedActionGroupValidationException(
                "group_id must not be empty"
            )
        if len(self.required_action_ids) < 2:
            raise SynchronizedActionGroupValidationException(
                f"required_action_ids must have at least 2 entries "
                f"(got {len(self.required_action_ids)}); a synchronized group "
                f"with fewer required actions has no synchronization meaning"
            )
        # 重複は禁止（同じ action_id を 2 度書いても 1 つの prepare で
        # 両方を満たしてしまうのは混乱の元）。
        if len(set(self.required_action_ids)) != len(self.required_action_ids):
            raise SynchronizedActionGroupValidationException(
                f"required_action_ids must be unique: {self.required_action_ids}"
            )
        if self.window_ticks <= 0:
            raise SynchronizedActionGroupValidationException(
                f"window_ticks must be positive: {self.window_ticks}"
            )
        if not self.on_complete:
            raise SynchronizedActionGroupValidationException(
                "on_complete must contain at least one effect"
            )
