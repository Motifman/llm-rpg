"""EpisodicReinterpretationEntry の being_id 必須化を検証する。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import (
    EpisodicReinterpretationEntry,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_status import (
    EpisodicReinterpretationStatus,
)

_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)
_BEING = BeingId("being_w1_p3")


def _entry(*, being_id: BeingId = _BEING) -> EpisodicReinterpretationEntry:
    return EpisodicReinterpretationEntry(
        entry_id="je-1",
        player_id=3,
        being_id=being_id,
        episode_id="ep-1",
        created_at=_NOW,
        turn_index=1,
        current_interpretation="意味づけ",
        current_recall_text="回想文",
        source_recall_ids=("r-1",),
    )


class TestEpisodicReinterpretationEntryBeingId:
    """being_id 必須・player_id 維持・型検証。"""

    def test_being_id_is_required_field(self) -> None:
        """being_id を渡すと VO が構築できる。"""
        entry = _entry()
        assert entry.being_id == _BEING

    def test_player_id_remains_int(self) -> None:
        """player_id は int のまま保持される。"""
        entry = _entry()
        assert entry.player_id == 3
        assert isinstance(entry.player_id, int)

    def test_non_being_id_raises_type_error(self) -> None:
        """being_id が BeingId でないと TypeError。"""
        with pytest.raises(TypeError, match="being_id must be BeingId"):
            EpisodicReinterpretationEntry(
                entry_id="je-1",
                player_id=3,
                being_id="being_w1_p3",  # type: ignore[arg-type]
                episode_id="ep-1",
                created_at=_NOW,
                turn_index=1,
                current_interpretation="意味づけ",
                current_recall_text="回想文",
                source_recall_ids=("r-1",),
            )

    def test_non_int_player_id_raises_type_error(self) -> None:
        """player_id が int でないと TypeError。"""
        with pytest.raises(TypeError, match="player_id must be int"):
            EpisodicReinterpretationEntry(
                entry_id="je-1",
                player_id="3",  # type: ignore[arg-type]
                being_id=_BEING,
                episode_id="ep-1",
                created_at=_NOW,
                turn_index=1,
                current_interpretation="意味づけ",
                current_recall_text="回想文",
                source_recall_ids=("r-1",),
            )

    def test_active_with_superseded_at_raises_value_error(self) -> None:
        """ACTIVE なのに superseded_at があると ValueError。"""
        with pytest.raises(ValueError, match="active entry must not have superseded_at"):
            EpisodicReinterpretationEntry(
                entry_id="je-1",
                player_id=3,
                being_id=_BEING,
                episode_id="ep-1",
                created_at=_NOW,
                turn_index=1,
                current_interpretation="意味づけ",
                current_recall_text="回想文",
                source_recall_ids=("r-1",),
                status=EpisodicReinterpretationStatus.ACTIVE,
                superseded_at=_NOW,
            )
