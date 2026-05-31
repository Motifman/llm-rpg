"""プレイヤー個別 outcome 解決ステージサービス (Phase E-3b)。

scenario 宣言された `outcome_resolution` 設定に従い、tick 駆動で以下を判定:

- 各 rescue_at_ticks (= 救助船通過 tick) で、signal_fire_flag が立ち、かつ
  summit_spot に居る UNRESOLVED プレイヤーを RESCUED に確定
- stranded_at_tick 到達時、まだ UNRESOLVED の全プレイヤーを STRANDED に確定

DEAD は別経路 (PlayerDownedOutcomeHandler) で確定する。本 stage はあくまで
「世界の側のタイミング」で発火する outcome 解決のみを扱う。
"""

from __future__ import annotations

import logging
from typing import Callable, FrozenSet, Sequence

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


_logger = logging.getLogger(__name__)


class PlayerOutcomeResolutionStageService:
    """tick 駆動で RESCUED / STRANDED を判定する。"""

    def __init__(
        self,
        outcome_registry: PlayerOutcomeRegistry,
        rescue_at_ticks: Sequence[int],
        stranded_at_tick: int,
        summit_spot_id: SpotId,
        signal_fire_flag: str,
        *,
        graph_provider: Callable[[], SpotGraphAggregate],
        flags_provider: Callable[[], FrozenSet[str]],
        player_ids: Sequence[PlayerId],
    ) -> None:
        """
        Args:
            outcome_registry: 更新先 registry。set_outcome は冪等 (resolved への
                上書きは silent skip) なので、既に DEAD のプレイヤーには影響しない。
            rescue_at_ticks: 救助判定 tick の列。同 tick を複数回宣言しても 1 回扱い。
            stranded_at_tick: timeout 判定 tick。これ以上で UNRESOLVED は STRANDED に。
            summit_spot_id: 山頂 (救助船から見える spot)。
            signal_fire_flag: 「狼煙が上がっている」を表す flag 名。
            graph_provider: tick 毎に最新 graph を引く callable。
                (presence_at で「summit に居るプレイヤー」を判定する)
            flags_provider: tick 毎に最新 world flags を引く callable。
            player_ids: 全プレイヤーの id 列。stranded 判定で unresolved を残らず
                走査するために必要 (registry.unresolved_player_ids でも代替可能だが、
                registry に登録漏れがあった場合の保険として明示的に渡す)。
        """
        self._outcome_registry = outcome_registry
        # 重複排除 + 昇順で固定化 (順序が ambiguous だと観測ログが揺れる)
        self._rescue_at_ticks: tuple[int, ...] = tuple(sorted(set(int(t) for t in rescue_at_ticks)))
        self._stranded_at_tick = int(stranded_at_tick)
        self._summit_spot_id = summit_spot_id
        self._signal_fire_flag = signal_fire_flag
        self._graph_provider = graph_provider
        self._flags_provider = flags_provider
        self._player_ids: tuple[PlayerId, ...] = tuple(player_ids)
        # 既に処理した rescue tick を記録 (二重発火防止)。tick 飛びにも対応するため
        # 「self._stranded_at_tick も含めて」 _processed_ticks で管理する。
        self._processed_ticks: set[int] = set()

    def run(self, current_tick: WorldTick) -> None:
        """tick 進行のたびに呼ばれる。該当 tick で resolution を実行する。"""
        tick_value = current_tick.value
        # 救助判定: tick 飛び (skip) があっても past 分を catch-up する。
        for rescue_tick in self._rescue_at_ticks:
            if rescue_tick in self._processed_ticks:
                continue
            if tick_value >= rescue_tick:
                self._process_rescue(rescue_tick)
                self._processed_ticks.add(rescue_tick)
        # STRANDED 判定: 救助 tick 全てを処理した後に走らせる (= 同 tick で救助
        # が走ったプレイヤーは先に RESCUED として確定し、残りが STRANDED に)
        if (
            tick_value >= self._stranded_at_tick
            and self._stranded_at_tick not in self._processed_ticks
        ):
            self._process_stranded()
            self._processed_ticks.add(self._stranded_at_tick)

    def _process_rescue(self, rescue_tick: int) -> None:
        """signal_fire が立っていて summit に居る UNRESOLVED プレイヤーを RESCUED に。"""
        flags = self._flags_provider()
        if self._signal_fire_flag not in flags:
            _logger.debug(
                "rescue_tick=%s: signal_fire_flag=%s not set, no rescue resolved",
                rescue_tick, self._signal_fire_flag,
            )
            return
        graph = self._graph_provider()
        presence = graph.presence_at(self._summit_spot_id)
        rescued_count = 0
        for player_id in self._player_ids:
            # 既に resolved (DEAD 等) のプレイヤーは set_outcome の冪等性で skip される
            entity_id = EntityId.create(int(player_id))
            if entity_id not in presence.present_entity_ids:
                continue
            if self._outcome_registry.set_outcome(
                player_id, PlayerOutcomeEnum.RESCUED,
            ):
                rescued_count += 1
        _logger.info(
            "rescue_tick=%s: resolved %d player(s) as RESCUED",
            rescue_tick, rescued_count,
        )

    def _process_stranded(self) -> None:
        """残った UNRESOLVED を全員 STRANDED に。"""
        stranded_count = 0
        for player_id in self._player_ids:
            if self._outcome_registry.set_outcome(
                player_id, PlayerOutcomeEnum.STRANDED,
            ):
                stranded_count += 1
        _logger.info(
            "stranded_at_tick=%s: resolved %d player(s) as STRANDED",
            self._stranded_at_tick, stranded_count,
        )
