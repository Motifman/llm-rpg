"""PlayerRevivedStateCollapseEvidenceHandler の挙動検証 (PR-D)。

PlayerRevivedEvent を受けて being_id を解決し、
StateCollapseEvidenceTranscriber.clear_down_state を呼ぶ。これにより次回
down したとき (PlayerDownedStateCollapseEvidenceHandler 側) に新しい evidence
が積めるようになる。**PlayerDownedStateCollapseEvidenceHandler の
record_down_evidence と対になる dedup リセット** である点に注意
(順序自体は down→revive で自然に守られる。同一 player が同時に両方の
event を受けることはない)。
"""

from __future__ import annotations

from ai_rpg_world.application.player.handlers.player_revived_state_collapse_evidence_handler import (
    PlayerRevivedStateCollapseEvidenceHandler,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.event.status_events import PlayerRevivedEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _make_revived_event(player_id: int, hp: int = 40) -> PlayerRevivedEvent:
    return PlayerRevivedEvent.create(
        aggregate_id=PlayerId(player_id),
        aggregate_type="PlayerStatusAggregate",
        hp_recovered=hp,
        total_hp=hp,
    )


class _TranscriberSpy:
    def __init__(self) -> None:
        self.cleared: list[BeingId] = []

    def clear_down_state(self, being_id: BeingId) -> None:
        self.cleared.append(being_id)


class _RaisingTranscriber:
    def clear_down_state(self, being_id: BeingId) -> None:
        raise RuntimeError("boom")


class TestPlayerRevivedStateCollapseEvidenceHandler:
    def test_succeeds_clear_down_state_calls_being(self) -> None:
        """being解決に成功すると clear down stateを呼ぶ。"""
        transcriber = _TranscriberSpy()
        being_id = BeingId("being-1")
        handler = PlayerRevivedStateCollapseEvidenceHandler(
            transcriber=transcriber,
            being_id_resolver=lambda pid: being_id,
        )

        handler.handle(_make_revived_event(1))

        assert transcriber.cleared == [being_id]

    def test_being_none_transcriber_does_not_call(self) -> None:
        """being解決が Noneのとき transcriberを呼ばない。"""
        transcriber = _TranscriberSpy()
        handler = PlayerRevivedStateCollapseEvidenceHandler(
            transcriber=transcriber,
            being_id_resolver=lambda pid: None,
        )

        handler.handle(_make_revived_event(1))

        assert transcriber.cleared == []

    def test_transcriber_handle_raises_exception(self) -> None:
        """transcriberが例外を投げても handleは例外を伝播しない。"""
        handler = PlayerRevivedStateCollapseEvidenceHandler(
            transcriber=_RaisingTranscriber(),
            being_id_resolver=lambda pid: BeingId("being-1"),
        )

        handler.handle(_make_revived_event(1))  # 例外なく完了
