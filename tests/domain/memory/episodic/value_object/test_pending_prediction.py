"""PendingPrediction / PendingPredictionDraft の不変条件を検証する。

U10a (予測誤差統一設計 部品6・pending prediction)。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.memory.episodic.exception.episodic_exception import (
    PendingPredictionValidationException,
)
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PENDING_KIND_PLAN,
    PENDING_KIND_PROMISE,
    PendingPrediction,
    PendingPredictionDraft,
    PendingResolutionVerdict,
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


class TestPendingKind:
    """P11: pending prediction の種別 (promise / plan) の不変条件。"""

    def test_draft_kind_defaults_to_promise(self) -> None:
        """kind 未指定の draft は promise (導入前の pending は全て約束扱い)。"""
        assert PendingPredictionDraft(**_draft()).kind == PENDING_KIND_PROMISE

    def test_pending_kind_defaults_to_promise(self) -> None:
        assert PendingPrediction(**_pending()).kind == PENDING_KIND_PROMISE

    def test_draft_accepts_plan_kind(self) -> None:
        assert PendingPredictionDraft(**_draft(kind="plan")).kind == PENDING_KIND_PLAN

    def test_pending_accepts_plan_kind(self) -> None:
        assert PendingPrediction(**_pending(kind="plan")).kind == PENDING_KIND_PLAN

    def test_draft_invalid_kind_raises(self) -> None:
        with pytest.raises(PendingPredictionValidationException):
            PendingPredictionDraft(**_draft(kind="hunch"))

    def test_pending_invalid_kind_raises(self) -> None:
        with pytest.raises(PendingPredictionValidationException):
            PendingPrediction(**_pending(kind="hunch"))


class TestPendingResolutionVerdict:
    """PendingResolutionVerdict (U10b 清算判定 VO) の不変条件を保証する。"""

    def test_fulfilled_verdict_is_accepted(self) -> None:
        v = PendingResolutionVerdict(pending_id="pending-1", verdict="fulfilled")
        assert v.pending_id == "pending-1"
        assert v.verdict == "fulfilled"

    def test_broken_verdict_is_accepted(self) -> None:
        v = PendingResolutionVerdict(pending_id="pending-1", verdict="broken")
        assert v.verdict == "broken"

    def test_pending_id_is_stripped(self) -> None:
        v = PendingResolutionVerdict(pending_id="  pending-1  ", verdict="broken")
        assert v.pending_id == "pending-1"

    def test_empty_pending_id_raises(self) -> None:
        with pytest.raises(PendingPredictionValidationException):
            PendingResolutionVerdict(pending_id="   ", verdict="fulfilled")

    def test_unknown_verdict_raises(self) -> None:
        """fulfilled / broken 以外の verdict は受け付けない (曖昧語を排除)。"""
        with pytest.raises(PendingPredictionValidationException):
            PendingResolutionVerdict(pending_id="pending-1", verdict="maybe")
