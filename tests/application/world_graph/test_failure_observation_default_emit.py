"""#356 後続: 失敗観測のデフォルト emit + dedup throttle (他者の失敗から学ぶ)。

旧仕様:
- scenario JSON で `on_failure_observation` を宣言した interaction だけ
  失敗観測が他者に届く。宣言が無いと silent。

新仕様 (本テストが規定):
- 失敗 reason が乗った `SpotObjectInteractionFailedEvent` を **常に emit**
- formatter は `observation_message` (override) > `failure_reason` (自動構築)
  > silent の優先順で prose を組む
- 同 (actor, object, action, reason) の連発は `dedup_window` (デフォルト 24
  tick) 以内なら 2 度目以降を emit しない (= LLM retry loop の暴走を抑制)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    SpotObjectInteractionFailedEvent,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


class TestEventCarriesFailureReason:
    """`SpotObjectInteractionFailedEvent.failure_reason` を保持できる。"""

    def test_default_None(self) -> None:
        ev = SpotObjectInteractionFailedEvent.create(
            aggregate_id=SpotGraphId.create(1),
            aggregate_type="SpotGraphAggregate",
            entity_id=EntityId.create(1),
            spot_id=SpotId.create(1),
            object_id=SpotObjectId.create(1),
            action_name="open",
            observation_message="",
        )
        assert ev.failure_reason is None

    def test_event_included(self) -> None:
        """明示指定で event に乗る。"""
        ev = SpotObjectInteractionFailedEvent.create(
            aggregate_id=SpotGraphId.create(1),
            aggregate_type="SpotGraphAggregate",
            entity_id=EntityId.create(1),
            spot_id=SpotId.create(1),
            object_id=SpotObjectId.create(1),
            action_name="light_signal",
            observation_message="",
            failure_reason="火打ち石がなければ火を起こせない。",
        )
        assert ev.failure_reason == "火打ち石がなければ火を起こせない。"


class TestFormatterAutoComposesProse:
    """formatter は failure_reason から prose を自動構築する。"""

    @pytest.fixture
    def handler(self):
        # 循環 import 回避のため、関連 modules を import 順で先に触る。
        # (test_spot_graph_formatter.py が直接 import している依存連鎖と同等)
        import ai_rpg_world.application.llm  # noqa: F401
        from ai_rpg_world.application.observation.services.formatters._spot_graph_object_handler import (
            SpotGraphObjectHandler,
        )
        ctx = MagicMock()
        ctx.spot_graph_repository = None
        h = SpotGraphObjectHandler.__new__(SpotGraphObjectHandler)
        h._context = ctx
        # 名前 resolver: entity 1 → "ノア"、object 100 → "狼煙台"
        h._is_self = lambda eid, pid: int(eid) == int(pid)
        h._resolve_entity_name = lambda eid: "ノア" if int(eid) == 1 else "誰か"
        h._resolve_object_name = lambda sid, oid: "狼煙台"
        return h

    def test_uses_observation_message_override_prose(self, handler):
        """observationmessageoverride があればそれを prose に使う。"""
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        ev = SpotObjectInteractionFailedEvent.create(
            aggregate_id=SpotGraphId.create(1),
            aggregate_type="SpotGraphAggregate",
            entity_id=EntityId.create(1),
            spot_id=SpotId.create(1),
            object_id=SpotObjectId.create(100),
            action_name="light_signal",
            observation_message="ノアが何かを擦るような仕草をしている。",
            failure_reason="火打ち石が無い",
        )
        out = handler._format_interaction_failed(ev, PlayerId(2))
        assert out is not None
        assert out.prose == "ノアが何かを擦るような仕草をしている。"

    def test_override_reason_prose(self, handler):
        """override 無し reason 有りで prose を自動構築。"""
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        ev = SpotObjectInteractionFailedEvent.create(
            aggregate_id=SpotGraphId.create(1),
            aggregate_type="SpotGraphAggregate",
            entity_id=EntityId.create(1),
            spot_id=SpotId.create(1),
            object_id=SpotObjectId.create(100),
            action_name="light_signal",
            observation_message="",
            failure_reason="火打ち石がなければ火を起こせない。",
        )
        out = handler._format_interaction_failed(ev, PlayerId(2))
        assert out is not None
        assert "ノア" in out.prose
        assert "狼煙台" in out.prose
        assert "light_signal" in out.prose
        assert "火打ち石がなければ火を起こせない。" in out.prose

    def test_silent(self, handler):
        """両方 無ければ silent。"""
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        ev = SpotObjectInteractionFailedEvent.create(
            aggregate_id=SpotGraphId.create(1),
            aggregate_type="SpotGraphAggregate",
            entity_id=EntityId.create(1),
            spot_id=SpotId.create(1),
            object_id=SpotObjectId.create(100),
            action_name="light_signal",
            observation_message="",
            failure_reason=None,
        )
        out = handler._format_interaction_failed(ev, PlayerId(2))
        assert out is None

    def test_returns_none_actor_self(self, handler):
        """actor 本人には None を返す。"""
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        ev = SpotObjectInteractionFailedEvent.create(
            aggregate_id=SpotGraphId.create(1),
            aggregate_type="SpotGraphAggregate",
            entity_id=EntityId.create(1),
            spot_id=SpotId.create(1),
            object_id=SpotObjectId.create(100),
            action_name="light_signal",
            observation_message="",
            failure_reason="火打ち石が無い",
        )
        out = handler._format_interaction_failed(ev, PlayerId(1))
        assert out is None


class TestServiceDedupThrottle:
    """`SpotInteractionApplicationService` の dedup throttle 動作。"""

    def _make_service(self, dedup_window: int = 24):
        from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
            SpotInteractionApplicationService,
        )
        from ai_rpg_world.application.world_graph.world_flag_state import (
            MutableWorldFlagState,
        )

        service = SpotInteractionApplicationService(
            spot_graph_repository=MagicMock(),
            spot_interior_repository=MagicMock(),
            player_inventory_repository=MagicMock(),
            item_repository=MagicMock(),
            item_spec_repository=MagicMock(),
            world_flag_state=MutableWorldFlagState(),
            event_publisher=MagicMock(),
            failure_observation_dedup_window=dedup_window,
        )
        return service

    def _emit(self, service, *, tick: int, reason: str = "火打ち石が無い"):
        """直接 _maybe_emit_failure_observation を呼んで挙動を検証する。"""
        from ai_rpg_world.domain.common.value_object import WorldTick
        from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
        from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
        from ai_rpg_world.domain.world_graph.enum.spot_object_type import (
            SpotObjectTypeEnum,
        )

        obj_id = SpotObjectId.create(100)
        # idef は無い (= override 無し) シンプル interior を作る
        obj = SpotObject(
            object_id=obj_id,
            name="狼煙台",
            description="石組み",
            object_type=SpotObjectTypeEnum.OTHER,
            state={},
            interactions=(),
            is_visible=True,
        )
        interior = SpotInterior(
            sub_locations=(),
            objects=(obj,),
            ground_items=(),
            discoverable_items=(),
        )
        graph = MagicMock()
        graph.graph_id = SpotGraphId.create(1)
        service._maybe_emit_failure_observation(
            interior=interior,
            object_id=obj_id,
            action_name="light_signal",
            entity_id=EntityId.create(1),
            spot_id=SpotId.create(1),
            graph=graph,
            failure_reason=reason,
            current_tick=WorldTick(tick),
        )
        return service._event_publisher.publish_all.call_count

    def test_first_emit(self) -> None:
        """初回 emit される。"""
        service = self._make_service()
        assert self._emit(service, tick=10) == 1

    def test_dedup_window_two_skip(self) -> None:
        """dedup window 内 2回目は skip。"""
        service = self._make_service(dedup_window=24)
        assert self._emit(service, tick=10) == 1
        # tick 10 + 5 = window 24 以内 → skip
        assert self._emit(service, tick=15) == 1

    def test_dedup_window_exceeds_emit(self) -> None:
        """dedup window 超過なら 再度 emit。"""
        service = self._make_service(dedup_window=24)
        assert self._emit(service, tick=10) == 1
        # tick 10 + 24 = ちょうど window 境界 → 再 emit
        assert self._emit(service, tick=34) == 2

    def test_different_reason_independently_dedup(self) -> None:
        """別 reason は独立に dedup。"""
        service = self._make_service(dedup_window=24)
        assert self._emit(service, tick=10, reason="火打ち石が無い") == 1
        # 別 reason は別 key → 同 tick でも emit される
        assert self._emit(service, tick=12, reason="流木が足りない") == 2

    def test_current_tick_none_dedup_skip(self) -> None:
        """tick 不明の呼び出しでは dedup を無効化する (legacy 互換)。"""
        service = self._make_service()
        from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
        from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
        from ai_rpg_world.domain.world_graph.enum.spot_object_type import (
            SpotObjectTypeEnum,
        )

        obj_id = SpotObjectId.create(100)
        obj = SpotObject(
            object_id=obj_id, name="狼煙台", description="d",
            object_type=SpotObjectTypeEnum.OTHER, state={}, interactions=(),
            is_visible=True,
        )
        interior = SpotInterior(
            sub_locations=(), objects=(obj,),
            ground_items=(), discoverable_items=(),
        )
        graph = MagicMock()
        graph.graph_id = SpotGraphId.create(1)
        for _ in range(3):
            service._maybe_emit_failure_observation(
                interior=interior, object_id=obj_id, action_name="x",
                entity_id=EntityId.create(1), spot_id=SpotId.create(1),
                graph=graph, failure_reason="r", current_tick=None,
            )
        assert service._event_publisher.publish_all.call_count == 3
