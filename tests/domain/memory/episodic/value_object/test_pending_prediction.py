"""PendingPrediction / PendingPredictionDraft の不変条件を検証する。

U10a (予測誤差統一設計 部品6・pending prediction)。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.memory.episodic.exception.episodic_exception import (
    PendingPredictionValidationException,
)
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PendingPrediction,
    PendingPredictionDraft,
)


def _draft(**overrides) -> dict:
    base = dict(
        text="夕方に木の下でカイトと会う",
        resolution_cues=("spot:12", "player:カイト"),
        tick_offset_from=0,
        tick_offset_to=5,
    )
    base.update(overrides)
    return base


def _pending(**overrides) -> dict:
    base = dict(
        pending_id="pending-1",
        text="夕方に木の下でカイトと会う",
        resolution_cues=("spot:12", "player:カイト"),
        tick_from=10,
        tick_to=15,
        origin_episode_id="ep-1",
        created_tick=10,
    )
    base.update(overrides)
    return base


class TestPendingPredictionDraft:
    """chunk 補完 LLM の抽出結果を表す draft VO の不変条件。"""

    def test_valid_draft_constructs(self) -> None:
        draft = PendingPredictionDraft(**_draft())
        assert draft.text == "夕方に木の下でカイトと会う"
        assert draft.resolution_cues == ("spot:12", "player:カイト")

    def test_blank_text_raises(self) -> None:
        with pytest.raises(PendingPredictionValidationException):
            PendingPredictionDraft(**_draft(text="   "))

    def test_empty_resolution_cues_raises(self) -> None:
        with pytest.raises(PendingPredictionValidationException):
            PendingPredictionDraft(**_draft(resolution_cues=()))

    def test_resolution_cue_without_known_prefix_raises(self) -> None:
        with pytest.raises(PendingPredictionValidationException):
            PendingPredictionDraft(**_draft(resolution_cues=("夕方",)))

    def test_resolution_cue_with_empty_suffix_raises(self) -> None:
        with pytest.raises(PendingPredictionValidationException):
            PendingPredictionDraft(**_draft(resolution_cues=("spot:",)))

    def test_negative_tick_offset_from_raises(self) -> None:
        with pytest.raises(PendingPredictionValidationException):
            PendingPredictionDraft(**_draft(tick_offset_from=-1, tick_offset_to=0))

    def test_tick_offset_to_before_from_raises(self) -> None:
        with pytest.raises(PendingPredictionValidationException):
            PendingPredictionDraft(**_draft(tick_offset_from=5, tick_offset_to=2))

    def test_equal_tick_offsets_are_allowed(self) -> None:
        draft = PendingPredictionDraft(**_draft(tick_offset_from=3, tick_offset_to=3))
        assert draft.tick_offset_from == draft.tick_offset_to == 3

    def test_bool_tick_offset_raises(self) -> None:
        """``bool`` は ``int`` のサブクラスだが、tick offset として渡るのは

        LLM 由来の不正値のはずなので明示的に弾く。"""
        with pytest.raises(PendingPredictionValidationException):
            PendingPredictionDraft(**_draft(tick_offset_from=True, tick_offset_to=5))


class TestPendingPrediction:
    """per-Being store に保持する確定版 VO の不変条件。"""

    def test_valid_pending_constructs(self) -> None:
        pending = PendingPrediction(**_pending())
        assert pending.pending_id == "pending-1"
        assert pending.tick_from == 10
        assert pending.tick_to == 15

    def test_blank_pending_id_raises(self) -> None:
        with pytest.raises(PendingPredictionValidationException):
            PendingPrediction(**_pending(pending_id=""))

    def test_blank_origin_episode_id_raises(self) -> None:
        with pytest.raises(PendingPredictionValidationException):
            PendingPrediction(**_pending(origin_episode_id="  "))

    def test_negative_created_tick_raises(self) -> None:
        with pytest.raises(PendingPredictionValidationException):
            PendingPrediction(**_pending(created_tick=-1))

    def test_tick_to_before_tick_from_raises(self) -> None:
        with pytest.raises(PendingPredictionValidationException):
            PendingPrediction(**_pending(tick_from=15, tick_to=10))

    def test_invalid_resolution_cue_raises(self) -> None:
        with pytest.raises(PendingPredictionValidationException):
            PendingPrediction(**_pending(resolution_cues=("unknown:x",)))

    def test_fields_are_stripped(self) -> None:
        pending = PendingPrediction(
            **_pending(pending_id="  pending-1  ", text="  会う  ")
        )
        assert pending.pending_id == "pending-1"
        assert pending.text == "会う"
