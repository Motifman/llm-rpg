"""AmbientSoundEventHandler のテスト（配信先解決 + per-player throttle）。"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.atmosphere_dtos import (
    AtmosphereEntry,
)
from ai_rpg_world.application.observation.handlers.ambient_sound_event_handler import (
    AmbientSoundEventHandler,
    CATEGORY_AMBIENT_SOUND,
)
from ai_rpg_world.application.observation.services.atmosphere_buffer import (
    DefaultAtmosphereBuffer,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    AmbientSoundEmittedEvent,
)
from ai_rpg_world.domain.world_graph.value_object.ambient_sound_atlas import (
    AmbientSoundThrottleConfig,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


def _build_graph(placements: dict[int, int]) -> SpotGraphAggregate:
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    spots = set(placements.values())
    for sid in spots:
        graph.add_spot(SpotNode(
            spot_id=SpotId.create(sid),
            name=f"s{sid}",
            description="",
            category=SpotCategoryEnum.TOWN,
            parent_id=None,
        ))
    for eid, sid in placements.items():
        graph.place_entity(EntityId.create(eid), SpotId.create(sid))
    graph.clear_events()
    return graph


def _make_status_repo(player_ids: list[int]):
    repo = MagicMock()
    repo.find_all.return_value = [MagicMock(player_id=PlayerId(pid)) for pid in player_ids]
    return repo


def _event(spot_id: int, sound_id: str = "drip", prose: str = "水滴音") -> AmbientSoundEmittedEvent:
    return AmbientSoundEmittedEvent.create(
        aggregate_id=SpotGraphId.create(1),
        aggregate_type="SpotGraph",
        source_spot_id=SpotId.create(spot_id),
        ambient_sound_id=sound_id,
        prose=prose,
        sound_strength=0.3,
    )


def _make_handler(
    *,
    graph,
    known_players,
    throttle=None,
    tick=0,
    buffer=None,
):
    repo = MagicMock()
    repo.find_graph.return_value = graph
    if throttle is None:
        throttle = AmbientSoundThrottleConfig(min_gap_ticks_per_player=0, dedup_window_size=0)
    if buffer is None:
        buffer = DefaultAtmosphereBuffer(capacity=10)
    handler = AmbientSoundEventHandler(
        atmosphere_buffer=buffer,
        spot_graph_repository=repo,
        player_status_repository=_make_status_repo(known_players),
        throttle=throttle,
        tick_provider=lambda: WorldTick(tick) if isinstance(tick, int) else tick(),
    )
    return handler, buffer


class TestAmbientHandlerRecipientResolution:
    """AmbientSoundEventHandler の配信先解決とイベント受け入れ挙動。"""

    def test_delivers_to_players_at_source_spot(self) -> None:
        """発火スポットに居るプレイヤーにのみ AtmosphereBuffer エントリが追加される。"""
        graph = _build_graph({1: 10, 2: 10, 3: 20})
        handler, buf = _make_handler(graph=graph, known_players=[1, 2, 3])
        handler.handle(_event(spot_id=10))
        assert len(buf.all(PlayerId(1))) == 1
        assert len(buf.all(PlayerId(2))) == 1
        assert len(buf.all(PlayerId(3))) == 0

    def test_non_event_ignored(self) -> None:
        """AmbientSoundEmittedEvent 以外の入力は無視され、バッファに何も追加されない。"""
        graph = _build_graph({1: 10})
        handler, buf = _make_handler(graph=graph, known_players=[1])
        handler.handle("not_an_event")
        handler.handle(None)
        assert buf.all(PlayerId(1)) == []

    def test_appends_correct_entry(self) -> None:
        """イベントの prose / sound_id / 現在 tick が AtmosphereEntry に正しく転写される。"""
        graph = _build_graph({1: 10})
        handler, buf = _make_handler(graph=graph, known_players=[1], tick=42)
        handler.handle(_event(spot_id=10, sound_id="wind", prose="風の音"))
        entries = buf.all(PlayerId(1))
        assert len(entries) == 1
        e = entries[0]
        assert e.category == CATEGORY_AMBIENT_SOUND
        assert e.prose == "風の音"
        assert e.source_id == "wind"
        assert e.occurred_at_tick == 42


class TestAmbientHandlerThrottle:
    """per-player throttle（min_gap / dedup_window）による配信抑制挙動。"""

    def test_min_gap_blocks_too_soon(self) -> None:
        """直前配信から min_gap_ticks_per_player 未満の tick での配信はブロックされる。"""
        graph = _build_graph({1: 10})
        throttle = AmbientSoundThrottleConfig(min_gap_ticks_per_player=4, dedup_window_size=0)
        buf = DefaultAtmosphereBuffer(capacity=10)
        # 1回目: tick=0 で配信成功
        h1, _ = _make_handler(graph=graph, known_players=[1], throttle=throttle, tick=0, buffer=buf)
        h1.handle(_event(spot_id=10, sound_id="drip"))
        # 2回目: tick=2（ギャップ未満）→ ブロック
        h2, _ = _make_handler(graph=graph, known_players=[1], throttle=throttle, tick=2, buffer=buf)
        h2.handle(_event(spot_id=10, sound_id="other"))
        assert len(buf.all(PlayerId(1))) == 1

    def test_min_gap_allows_after_gap(self) -> None:
        """min_gap_ticks_per_player 経過後の配信は通常通り受け付けられる。"""
        graph = _build_graph({1: 10})
        throttle = AmbientSoundThrottleConfig(min_gap_ticks_per_player=4, dedup_window_size=0)
        buf = DefaultAtmosphereBuffer(capacity=10)
        h1, _ = _make_handler(graph=graph, known_players=[1], throttle=throttle, tick=0, buffer=buf)
        h1.handle(_event(spot_id=10, sound_id="drip"))
        h2, _ = _make_handler(graph=graph, known_players=[1], throttle=throttle, tick=4, buffer=buf)
        h2.handle(_event(spot_id=10, sound_id="other"))
        assert len(buf.all(PlayerId(1))) == 2

    def test_dedup_window_blocks_same_id(self) -> None:
        """直近 dedup_window 件に同じ sound_id があれば再配信をブロックする。"""
        graph = _build_graph({1: 10})
        throttle = AmbientSoundThrottleConfig(min_gap_ticks_per_player=0, dedup_window_size=3)
        buf = DefaultAtmosphereBuffer(capacity=10)
        h1, _ = _make_handler(graph=graph, known_players=[1], throttle=throttle, tick=0, buffer=buf)
        h1.handle(_event(spot_id=10, sound_id="drip"))
        h2, _ = _make_handler(graph=graph, known_players=[1], throttle=throttle, tick=10, buffer=buf)
        h2.handle(_event(spot_id=10, sound_id="drip"))  # 重複 → ブロック
        assert len(buf.all(PlayerId(1))) == 1

    def test_dedup_window_allows_different_id(self) -> None:
        """dedup_window 内に違う sound_id しか無ければ配信を受け付ける。"""
        graph = _build_graph({1: 10})
        throttle = AmbientSoundThrottleConfig(min_gap_ticks_per_player=0, dedup_window_size=3)
        buf = DefaultAtmosphereBuffer(capacity=10)
        h1, _ = _make_handler(graph=graph, known_players=[1], throttle=throttle, tick=0, buffer=buf)
        h1.handle(_event(spot_id=10, sound_id="drip"))
        h2, _ = _make_handler(graph=graph, known_players=[1], throttle=throttle, tick=1, buffer=buf)
        h2.handle(_event(spot_id=10, sound_id="wind"))
        assert len(buf.all(PlayerId(1))) == 2

    def test_other_categories_do_not_consume_throttle(self) -> None:
        """別カテゴリ（例: smell）が直前にあっても ambient のスロットルは独立に判定される。"""
        graph = _build_graph({1: 10})
        throttle = AmbientSoundThrottleConfig(min_gap_ticks_per_player=4, dedup_window_size=0)
        buf = DefaultAtmosphereBuffer(capacity=10)
        # smell エントリを直前に手で挿入
        buf.append(PlayerId(1), AtmosphereEntry(
            category="smell", prose="腐臭", occurred_at_tick=0,
        ))
        h, _ = _make_handler(graph=graph, known_players=[1], throttle=throttle, tick=1, buffer=buf)
        h.handle(_event(spot_id=10, sound_id="drip"))
        # ambient は別カテゴリなので、smell の存在に影響されず初回扱いで配信される
        ambient_entries = [e for e in buf.all(PlayerId(1)) if e.category == "ambient_sound"]
        assert len(ambient_entries) == 1
