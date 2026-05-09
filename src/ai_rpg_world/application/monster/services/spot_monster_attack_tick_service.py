"""tick 駆動でスポットグラフ世界のモンスターにプレイヤー攻撃を試みさせる。

世界 tick が 1 進むたびに本サービスを呼ぶ想定。各モンスターについて:
1. cooldown 切れ + ALIVE + faction=ENEMY をチェック (domain service 側)
2. 同スポットに居るプレイヤー集合を SpotGraphAggregate から取得
3. 視認 (環境光量 OR dark_vision) を満たすターゲットを 1 体選ぶ
4. domain service の `try_attack` で実際にダメージを適用
5. 成立したら `MonsterAttackedPlayerInSpotEvent` を SpotGraphAggregate に追加
6. 集約を保存

ターゲット選択は最小実装として「ID 昇順で先頭の生存プレイヤー 1 体」。複数
プレイヤーが居ても 1 個体は 1 攻撃のみ。後で「最も近い」「HP 最少」等の
戦略を入れる場合は本サービス内の `_pick_target` を差し替える。
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import (
    MonsterAggregate,
)
from ai_rpg_world.domain.monster.enum.monster_enum import (
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterRepository,
)
from ai_rpg_world.domain.monster.service.spot_monster_attack_service import (
    MonsterAttackOutcome,
    SpotMonsterAttackService,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAttackedPlayerInSpotEvent,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.service.spot_perception_service import (
    SpotPerceptionService,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId

logger = logging.getLogger(__name__)


class SpotMonsterAttackTickService:
    """tick が進むたびにモンスターからの攻撃を 1 回ずつ試みる。

    本サービスは UoW を持たず、呼び出し側 (presentation の tick driver や
    test fixture) が `tick()` 後にリポジトリを保存する責務を持つ。実装上は
    `monster_repository.save()` / `player_status_repository.save()` を内部で
    呼ぶが、aggregate の event はそのまま `add_event` 経由で蓄積する。
    """

    def __init__(
        self,
        spot_graph_repository: ISpotGraphRepository,
        monster_repository: MonsterRepository,
        player_status_repository: PlayerStatusRepository,
        attack_service: Optional[SpotMonsterAttackService] = None,
        perception_service: Optional[SpotPerceptionService] = None,
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._monster_repository = monster_repository
        self._player_status_repository = player_status_repository
        self._attack_service = attack_service or SpotMonsterAttackService()
        self._perception = perception_service or SpotPerceptionService()

    def tick(self, current_tick: WorldTick) -> List[MonsterAttackOutcome]:
        """1 tick 分のモンスター攻撃判定を一括実行する。

        Returns:
            当該 tick で実際に発生した attack の結果一覧（debug / 観測性用）。
        """
        graph = self._spot_graph_repository.find_graph()
        outcomes: List[MonsterAttackOutcome] = []

        # 全モンスター（スポットグラフ上に居る個体のみ）を ID 昇順に処理
        for monster_id in sorted(
            graph.monster_spot_mapping().keys(), key=lambda m: m.value
        ):
            spot_id = graph.get_monster_spot(monster_id)
            monster = self._monster_repository.find_by_id(monster_id)
            if monster is None:
                logger.debug(
                    "tick: monster_repository returned None for %s (placed at %s)",
                    monster_id.value,
                    spot_id.value,
                )
                continue

            # 早期スクリーニング: ENEMY 以外と DEAD は domain service でも
            # 弾かれるが、tick 全体のループ効率のため事前に飛ばす。
            if monster.template.faction != MonsterFactionEnum.ENEMY:
                continue
            if monster.status != MonsterStatusEnum.ALIVE:
                continue
            if not monster.can_attack_now(current_tick):
                continue

            target = self._pick_target(graph, spot_id)
            if target is None:
                continue

            effective_lighting = self._compute_lighting_for_spot(graph, spot_id)
            outcome = self._attack_service.try_attack(
                monster=monster,
                target_player=target,
                effective_lighting=effective_lighting,
                current_tick=current_tick,
            )
            outcomes.append(outcome)
            if not outcome.executed:
                continue

            # 被害者から見た視認は本実装では attacker 視点と同じ判定（暗闇 +
            # dark_vision で監督側だけ視認できるケースは「被害者は見えない」）。
            # 受信者ごとの視認は formatter 側で target_visible を見て切り替える。
            # 被害者は dark_vision を持たない前提のため、暗闇なら見えない。
            target_visible = effective_lighting not in (
                LightingEnum.DARK,
                LightingEnum.PITCH_BLACK,
            )
            graph.add_event(
                MonsterAttackedPlayerInSpotEvent.create(
                    aggregate_id=graph.graph_id,
                    aggregate_type="SpotGraphAggregate",
                    monster_id=monster_id,
                    spot_id=spot_id,
                    target_player_id=EntityId.create(target.player_id.value),
                    damage=outcome.damage,
                    target_downed=outcome.target_downed,
                    target_visible=target_visible,
                )
            )
            self._monster_repository.save(monster)
            self._player_status_repository.save(target)

        return outcomes

    def _pick_target(
        self, graph: SpotGraphAggregate, spot_id: SpotId
    ) -> Optional[PlayerStatusAggregate]:
        """同スポットに居るプレイヤーから ID 昇順で最初の生存者を返す。"""
        presence = graph.presence_at(spot_id)
        for entity_id in sorted(
            presence.present_entity_ids, key=lambda e: e.value
        ):
            player = self._player_status_repository.find_by_id(
                PlayerId(entity_id.value)
            )
            if player is None:
                # entity_id は presence に居るが player でない可能性 (NPC 等)。
                # 最小実装ではプレイヤー以外を target にしないので skip。
                continue
            if player.is_down:
                continue
            return player
        return None

    def _compute_lighting_for_spot(
        self, graph: SpotGraphAggregate, spot_id: SpotId
    ):
        """スポットの実効照明。光源所持の判定は最小実装では行わず、
        atmosphere 由来の base 照明を返す。

        TODO: 本格的には `SpotGraphCurrentStateBuilder` と同じロジックで
        光源持ちエンティティの有無を見て DIM へ引き上げる必要がある。
        ただしそれはプレイヤーごとの inventory 解決を要するため tick 一度
        の処理としてはコスト高。最小実装では「アトマンスフィアの素の値」
        で代用する（光源を持って入っても暗闇判定が固定される副作用あり）。
        """
        node = graph.get_spot(spot_id)
        atmosphere = node.atmosphere
        return self._perception.compute_effective_lighting(
            atmosphere, spot_has_any_light_bearer=False
        )


