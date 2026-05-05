"""AmbientSoundEmittedEvent を AtmosphereBuffer に流すハンドラ。

通常の観測パイプライン（ObservationPipeline → ObservationContextBuffer）には
乗せず、専用の薄い経路で AtmosphereBuffer に書き込む。プロンプト builder 側は
このバッファから 1 行サマリを生成してコンテキスト消費を最小化する。

責務:
    1. 配信先（同一スポットのプレイヤー）の解決
    2. per-player throttle（min_gap_ticks / dedup_window）の適用
    3. AtmosphereBuffer への append

設計のポイント:
    - throttle 状態は AtmosphereBuffer 自体が持つエントリ履歴から導出する。
      別途「per-player 状態テーブル」を持たない（バッファが SoT）。
    - SoundPropagationService 連携（隣接スポットへの減衰配信）は将来拡張点。
      現時点では同一スポット限定。
"""

from __future__ import annotations

from typing import Callable, Optional, Set

from ai_rpg_world.application.observation.contracts.atmosphere_dtos import (
    AtmosphereEntry,
)
from ai_rpg_world.application.observation.contracts.atmosphere_interfaces import (
    IAtmosphereBuffer,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    AmbientSoundEmittedEvent,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.value_object.ambient_sound_atlas import (
    AmbientSoundThrottleConfig,
)


CATEGORY_AMBIENT_SOUND = "ambient_sound"


class AmbientSoundEventHandler:
    """AmbientSoundEmittedEvent を受けて、配信先プレイヤーの AtmosphereBuffer に
    エントリを追加するハンドラ。"""

    def __init__(
        self,
        *,
        atmosphere_buffer: IAtmosphereBuffer,
        spot_graph_repository: ISpotGraphRepository,
        player_status_repository: PlayerStatusRepository,
        throttle: AmbientSoundThrottleConfig,
        tick_provider: Callable[[], WorldTick],
    ) -> None:
        self._buffer = atmosphere_buffer
        self._spot_graph_repository = spot_graph_repository
        self._player_status_repository = player_status_repository
        self._throttle = throttle
        self._tick_provider = tick_provider

    def handle(self, event: object) -> None:
        if not isinstance(event, AmbientSoundEmittedEvent):
            return

        recipients = self._resolve_recipients(event)
        if not recipients:
            return

        current_tick = self._tick_provider()
        for player_id in recipients:
            if self._is_throttled(player_id, event, current_tick):
                continue
            self._buffer.append(
                player_id,
                AtmosphereEntry(
                    category=CATEGORY_AMBIENT_SOUND,
                    prose=event.prose,
                    occurred_at_tick=current_tick.value,
                    source_id=event.ambient_sound_id,
                ),
            )

    def _resolve_recipients(self, event: AmbientSoundEmittedEvent) -> list:
        """発火スポットに居るプレイヤーを返す（隣接スポット伝播は将来拡張）。"""
        graph = self._spot_graph_repository.find_graph()
        known_player_ids: Set[int] = {
            s.player_id.value for s in self._player_status_repository.find_all()
        }
        result = []
        for entity_id, spot_id in graph.entity_spot_mapping().items():
            if spot_id != event.source_spot_id:
                continue
            if entity_id.value not in known_player_ids:
                continue
            result.append(PlayerId(entity_id.value))
        return result

    def _is_throttled(
        self,
        player_id: PlayerId,
        event: AmbientSoundEmittedEvent,
        current_tick: WorldTick,
    ) -> bool:
        # ambient_sound カテゴリの直近エントリを参照する（atmosphere バッファは
        # 他カテゴリも保持しうるため、フィルタしてから判定する）。
        recent_all = self._buffer.recent(
            player_id,
            max_count=max(self._throttle.dedup_window_size, 1),
        )
        ambient_recent = [
            e for e in recent_all if e.category == CATEGORY_AMBIENT_SOUND
        ]

        # ギャップチェック
        if ambient_recent and self._throttle.min_gap_ticks_per_player > 0:
            last_tick = ambient_recent[0].occurred_at_tick  # recent() は新しい順
            if (
                current_tick.value - last_tick
                < self._throttle.min_gap_ticks_per_player
            ):
                return True

        # 重複チェック
        if self._throttle.dedup_window_size > 0:
            window = ambient_recent[: self._throttle.dedup_window_size]
            if any(e.source_id == event.ambient_sound_id for e in window):
                return True

        return False


__all__ = [
    "AmbientSoundEventHandler",
    "CATEGORY_AMBIENT_SOUND",
]
