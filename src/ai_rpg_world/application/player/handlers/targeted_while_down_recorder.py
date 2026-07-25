"""倒れている相手を対象にした行為を、被害者が起きるまで預かる handler。

``PlayerInteractedWithPlayerEvent`` を受けて、対象が倒れていれば
``DownedIncidentLog`` に 1 行記録する。復活時に
``PlayerRevivedPostHocObservationHandler`` が drain して目覚めの観測に
併せて渡す。

observation pipeline に載せないのは、倒れている player が recipient から
一律に外れるため (Issue #621 Phase 4)。その除外は「ターンが回らない相手に
観測を積んでも消化されない」という妥当な設計なので、そこを崩さずに
「起きたときに読める場所」へ置くほうが筋が良い。
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from ai_rpg_world.application.player.services.downed_incident_log import (
    DownedIncidentLog,
)
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    PlayerInteractedWithPlayerEvent,
)

ActorNameResolver = Callable[[PlayerId], Optional[str]]


class TargetedWhileDownRecorder(EventHandler[PlayerInteractedWithPlayerEvent]):
    """対人行為の対象が倒れていたら、その事実を復活まで預かる。"""

    def __init__(
        self,
        *,
        incident_log: DownedIncidentLog,
        player_status_repository: PlayerStatusRepository,
        actor_name_resolver: ActorNameResolver,
    ) -> None:
        self._log = incident_log
        self._player_status_repository = player_status_repository
        self._actor_name_resolver = actor_name_resolver
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: PlayerInteractedWithPlayerEvent) -> None:
        try:
            target_pid = PlayerId(int(event.target_entity_id))
            # **行為が始まった時点で**倒れていたかで判定する。集約に「いま
            # 倒れているか」を問い合わせると、昏倒させた一撃そのものが
            # 「倒れている間にされたこと」に化ける (致死の一撃は必ずそうなる)。
            # 倒された事実は PlayerDownedEvent 由来の観測で本人に即座に届く
            # ので、目覚めの申し送りにも入れると同じ一撃が二重に語られる。
            if not getattr(event, "target_was_down", False):
                return
            self._log.record(target_pid, self._describe(event))
        except Exception:
            # 記録の失敗で行為そのものを倒さない。奪う処理は既に完了して
            # いるので、ここで例外を上げると「奪えたのに失敗と返る」になる。
            self._logger.exception(
                "failed to record downed incident for event=%s",
                type(event).__name__,
            )

    def _describe(self, event: PlayerInteractedWithPlayerEvent) -> str:
        """目覚めた本人が読む 1 行を組み立てる。

        行為者名は出す。誰にやられたか分からないと、疑う相手も問い詰める
        相手も決められず、社会的な反応が起こしようがない。
        """
        actor = self._actor_name_resolver(PlayerId(int(event.entity_id)))
        if not actor:
            actor = f"プレイヤー({int(event.entity_id)})"
        label = (event.action_display_label or "").strip() or event.action_name
        return f"{actor}に「{label}」をされた"
