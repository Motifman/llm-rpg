"""PlayerDownedStateCollapseEvidenceHandler の挙動検証 (PR-D)。

PlayerDownedEvent を受けて being_id を解決し、
StateCollapseEvidenceTranscriber.record_down_evidence を呼ぶ。being 解決が
できない (Being attachment 未配線) 場合や transcriber 側で例外が起きても、
pipeline 全体を止めない (best-effort)。
"""

from __future__ import annotations

from ai_rpg_world.application.player.handlers.player_downed_state_collapse_evidence_handler import (
    PlayerDownedStateCollapseEvidenceHandler,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _make_downed_event(player_id: int) -> PlayerDownedEvent:
    return PlayerDownedEvent.create(
        aggregate_id=PlayerId(player_id),
        aggregate_type="PlayerStatusAggregate",
    )


class _TranscriberSpy:
    def __init__(self) -> None:
        self.recorded: list[BeingId] = []

    def record_down_evidence(self, being_id: BeingId):
        self.recorded.append(being_id)
        return None


class _RaisingTranscriber:
    def record_down_evidence(self, being_id: BeingId):
        raise RuntimeError("boom")


class TestPlayerDownedStateCollapseEvidenceHandler:
    def test_being解決に成功すると_record_down_evidenceを呼ぶ(self) -> None:
        transcriber = _TranscriberSpy()
        being_id = BeingId("being-1")
        handler = PlayerDownedStateCollapseEvidenceHandler(
            transcriber=transcriber,
            being_id_resolver=lambda pid: being_id,
        )

        handler.handle(_make_downed_event(1))

        assert transcriber.recorded == [being_id]

    def test_being解決が_Noneのとき_transcriberを呼ばない(self) -> None:
        transcriber = _TranscriberSpy()
        handler = PlayerDownedStateCollapseEvidenceHandler(
            transcriber=transcriber,
            being_id_resolver=lambda pid: None,
        )

        handler.handle(_make_downed_event(1))

        assert transcriber.recorded == []

    def test_transcriberが例外を投げても_handleは例外を伝播しない(self) -> None:
        handler = PlayerDownedStateCollapseEvidenceHandler(
            transcriber=_RaisingTranscriber(),
            being_id_resolver=lambda pid: BeingId("being-1"),
        )

        handler.handle(_make_downed_event(1))  # 例外なく完了

    def test_being_id_resolverに渡されるのはevent由来のplayer_id(self) -> None:
        transcriber = _TranscriberSpy()
        received: list[PlayerId] = []

        def resolver(pid: PlayerId):
            received.append(pid)
            return BeingId("being-1")

        handler = PlayerDownedStateCollapseEvidenceHandler(
            transcriber=transcriber, being_id_resolver=resolver
        )

        handler.handle(_make_downed_event(42))

        assert received == [PlayerId(42)]
