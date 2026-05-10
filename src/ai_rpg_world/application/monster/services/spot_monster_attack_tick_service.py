"""tick 駆動でスポットグラフ世界のモンスターにプレイヤー攻撃を試みさせる。

世界 tick が 1 進むたびに本サービスを呼ぶ想定。本サービスは「policy = 候補
選び」だけを担当し、実際の attack 処理（domain service 呼出 / event 発火 /
全 aggregate save）は `SpotAttackOrchestrator` に委譲する。

各モンスターについて:
1. ENEMY 以外 / DEAD / cooldown 中は事前スクリーニングで skip
2. 同スポットに居る生存プレイヤーを ID 昇順で 1 体ターゲット選定
3. orchestrator.execute_monster_attack に loaded aggregate を渡す
4. 戻ってきた `AttackOutcome` を debug 用に集めて返す

ターゲット選択は最小実装として「ID 昇順で先頭の生存プレイヤー」。複数
プレイヤーが居ても 1 個体は 1 攻撃のみ。後で「最も近い」「HP 最少」等の
戦略を入れる場合は本サービス内の `_pick_target` を差し替える。

呼び出し導線:
- 想定接続先は `application/llm/wiring/spot_graph_wiring.py` または
  presentation 側の tick driver。orchestrator が graph save まで責任を持つ
  ため tick service 側で別途 save は不要。
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
    SpotAttackOrchestrator,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.enum.monster_enum import (
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterRepository,
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
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.value_object.spot_attack_outcome import (
    AttackOutcome,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId

logger = logging.getLogger(__name__)


class SpotMonsterAttackTickService:
    """tick が進むたびにモンスターからの攻撃を 1 回ずつ試みる。

    本サービスは候補選定 (policy) のみ担当し、attack の実行/永続化は
    `SpotAttackOrchestrator` に委譲する設計。
    """

    def __init__(
        self,
        spot_graph_repository: ISpotGraphRepository,
        monster_repository: MonsterRepository,
        player_status_repository: PlayerStatusRepository,
        attack_orchestrator: SpotAttackOrchestrator,
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._monster_repository = monster_repository
        self._player_status_repository = player_status_repository
        self._orchestrator = attack_orchestrator

    def tick(self, current_tick: WorldTick) -> List[AttackOutcome]:
        """1 tick 分のモンスター攻撃判定を一括実行する。

        Returns:
            当該 tick で実際に発生した attack の結果一覧（debug / 観測性用）。
        """
        graph = self._spot_graph_repository.find_graph()
        outcomes: List[AttackOutcome] = []

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

            # 早期スクリーニング: ENEMY 以外と DEAD と cooldown 中は飛ばす。
            # 同等チェックは domain service にもあるが、tick 全体のループ
            # 効率と repository.save 不要を兼ねて事前で弾く。
            if monster.template.faction != MonsterFactionEnum.ENEMY:
                continue
            if monster.status != MonsterStatusEnum.ALIVE:
                continue
            if not monster.can_attack_now(current_tick):
                continue

            target = self._pick_target(graph, spot_id)
            if target is None:
                continue

            outcome = self._orchestrator.execute_monster_attack(
                attacker_monster=monster,
                target_player=target,
                graph=graph,
                spot_id=spot_id,
                current_tick=current_tick,
            )
            outcomes.append(outcome)

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
                continue
            if player.is_down:
                continue
            return player
        return None
