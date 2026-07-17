"""BeliefEvidence VO の不変条件を保証する。

U2 (証拠台帳統一設計): 全ての学習の素材を正規化する中核データ。
domain 層のバリデーション違反はドメイン例外 (BeliefEvidenceValidationException)
で表現される契約を確認する。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.domain.memory.semantic.exception.semantic_exception import (
    BeliefEvidenceValidationException,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
    BELIEF_EVIDENCE_SALIENCE_HIGH,
    BELIEF_EVIDENCE_SALIENCE_LOW,
    BeliefEvidence,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)


def _evidence(**overrides) -> BeliefEvidence:
    base = dict(
        evidence_id="belief-evidence-1",
        source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR,
        episode_ids=("ep-1",),
        cue_signature="tool:explore|spot:1",
        text="探索は空振りだった",
        salience=BELIEF_EVIDENCE_SALIENCE_LOW,
        occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        tick=10,
    )
    base.update(overrides)
    return BeliefEvidence(**base)


class TestBeliefEvidenceSourceKindEnum:
    """U2 の DoD: 後続 PR ぶんの source_kind を最初から全て予約する。"""

    def test_all_source_kinds_are_reserved(self) -> None:
        expected = {
            "prediction_error",
            "structured_failure",
            "memo_distill",
            "familiarity",
            "confirmation",
            "pending_resolution",
            "hearsay",  # P9 (伝聞)
            "state_collapse",  # PR-D (状態破綻)
        }
        actual = {member.value for member in BeliefEvidenceSourceKind}
        assert actual == expected


class TestBeliefEvidenceConstruction:
    """正常系: 必須フィールドが揃っていれば構築できる。"""

    def test_valid_evidence_constructs(self) -> None:
        evidence = _evidence()
        assert evidence.source_kind == BeliefEvidenceSourceKind.PREDICTION_ERROR
        assert evidence.episode_ids == ("ep-1",)
        assert evidence.tick == 10

    def test_tick_defaults_to_none(self) -> None:
        """tick は chunk 完了時に current_tick_provider が無ければ None になる
        (async 完了で数 tick 遅れる不確実性の受け皿)。"""
        evidence = _evidence(tick=None)
        assert evidence.tick is None

    def test_salience_high_is_accepted(self) -> None:
        evidence = _evidence(salience=BELIEF_EVIDENCE_SALIENCE_HIGH)
        assert evidence.salience == BELIEF_EVIDENCE_SALIENCE_HIGH

    def test_in_context_belief_ids_defaults_to_empty_tuple(self) -> None:
        """U4 (予測誤差統一設計 部品3): 既定は空タプル (= attribution 機構 OFF
        と同じ形。旧データとの後方互換にもなる)。"""
        evidence = _evidence()
        assert evidence.in_context_belief_ids == ()

    def test_in_context_belief_ids_can_be_set(self) -> None:
        evidence = _evidence(in_context_belief_ids=("sem-1", "sem-2"))
        assert evidence.in_context_belief_ids == ("sem-1", "sem-2")


class TestBeliefEvidenceValidation:
    """不変条件違反はすべて BeliefEvidenceValidationException になる。"""

    def test_empty_evidence_id_raises(self) -> None:
        with pytest.raises(BeliefEvidenceValidationException):
            _evidence(evidence_id="")

    def test_non_enum_source_kind_raises(self) -> None:
        with pytest.raises(BeliefEvidenceValidationException):
            _evidence(source_kind="prediction_error")

    def test_empty_episode_ids_raises(self) -> None:
        """evidence は必ず episode に紐づく (traceability)。"""
        with pytest.raises(BeliefEvidenceValidationException):
            _evidence(episode_ids=())

    def test_blank_episode_id_in_tuple_raises(self) -> None:
        with pytest.raises(BeliefEvidenceValidationException):
            _evidence(episode_ids=("ep-1", "  "))

    def test_empty_cue_signature_raises(self) -> None:
        with pytest.raises(BeliefEvidenceValidationException):
            _evidence(cue_signature="")

    def test_empty_text_raises(self) -> None:
        with pytest.raises(BeliefEvidenceValidationException):
            _evidence(text="")

    def test_unknown_salience_raises(self) -> None:
        with pytest.raises(BeliefEvidenceValidationException):
            _evidence(salience="medium")

    def test_non_datetime_occurred_at_raises(self) -> None:
        with pytest.raises(BeliefEvidenceValidationException):
            _evidence(occurred_at="2026-07-01")

    def test_non_int_tick_raises(self) -> None:
        with pytest.raises(BeliefEvidenceValidationException):
            _evidence(tick="10")

    def test_non_tuple_in_context_belief_ids_raises(self) -> None:
        with pytest.raises(BeliefEvidenceValidationException):
            _evidence(in_context_belief_ids=["sem-1"])

    def test_blank_in_context_belief_id_in_tuple_raises(self) -> None:
        with pytest.raises(BeliefEvidenceValidationException):
            _evidence(in_context_belief_ids=("sem-1", "  "))
