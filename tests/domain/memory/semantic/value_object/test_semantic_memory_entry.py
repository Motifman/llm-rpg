"""SemanticMemoryEntry の belief journal 拡張 (U3a) の不変条件を保証する。

U3a は belief journal の「構造」だけを入れる PR であり、LLM 呼び出しや
固着 coordinator は含まない。既定挙動 (未指定なら全 entry が active) が
不変であることをここで担保する。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.domain.memory.semantic.exception.semantic_exception import (
    SemanticMemoryEntryValidationException,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SEMANTIC_MEMORY_STATUS_ACTIVE,
    SEMANTIC_MEMORY_STATUS_INACTIVE,
    SEMANTIC_MEMORY_STATUS_SUPERSEDED,
    SemanticMemoryEntry,
)


def _entry(**overrides) -> SemanticMemoryEntry:
    base = dict(
        entry_id="entry-1",
        player_id=1,
        text="探索は空振りが多い",
        evidence_episode_ids=("ep-1",),
        confidence=0.6,
        created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return SemanticMemoryEntry(**base)


class TestBeliefIdFallback:
    """belief_id 未指定 (旧 entry 相当) の後方互換。"""

    def test_belief_id_未指定なら_entry_id_にフォールバックする(self) -> None:
        entry = _entry(entry_id="entry-42")
        assert entry.belief_id == "entry-42"

    def test_belief_id_を明示すればそのまま保持される(self) -> None:
        entry = _entry(entry_id="entry-42", belief_id="belief-noah-mood")
        assert entry.belief_id == "belief-noah-mood"

    def test_belief_id_の前後空白は_strip_される(self) -> None:
        entry = _entry(belief_id="  belief-x  ")
        assert entry.belief_id == "belief-x"


class TestStatusDefault:
    """status のデフォルトと後方互換。"""

    def test_status_未指定なら_active(self) -> None:
        entry = _entry()
        assert entry.status == SEMANTIC_MEMORY_STATUS_ACTIVE

    def test_不正な_status_はドメイン例外(self) -> None:
        with pytest.raises(SemanticMemoryEntryValidationException, match="status"):
            _entry(status="unknown_status")

    @pytest.mark.parametrize(
        "status",
        [
            SEMANTIC_MEMORY_STATUS_ACTIVE,
            SEMANTIC_MEMORY_STATUS_SUPERSEDED,
            SEMANTIC_MEMORY_STATUS_INACTIVE,
        ],
    )
    def test_有効な_status_は全て構築できる(self, status: str) -> None:
        entry = _entry(status=status)
        assert entry.status == status


class TestSupersedes:
    """supersedes の default と型バリデーション。"""

    def test_supersedes_未指定は_None(self) -> None:
        entry = _entry()
        assert entry.supersedes is None

    def test_supersedes_に空文字はドメイン例外(self) -> None:
        with pytest.raises(
            SemanticMemoryEntryValidationException, match="supersedes"
        ):
            _entry(supersedes="")

    def test_supersedes_を指定すれば保持される(self) -> None:
        entry = _entry(supersedes="entry-old")
        assert entry.supersedes == "entry-old"


class TestEvidenceIdTuples:
    """support_evidence_ids / contradict_evidence_ids の default とバリデーション。"""

    def test_未指定は空タプル(self) -> None:
        entry = _entry()
        assert entry.support_evidence_ids == ()
        assert entry.contradict_evidence_ids == ()

    def test_support_evidence_ids_の空文字要素はドメイン例外(self) -> None:
        with pytest.raises(
            SemanticMemoryEntryValidationException, match="support_evidence_ids"
        ):
            _entry(support_evidence_ids=("",))

    def test_contradict_evidence_ids_の空文字要素はドメイン例外(self) -> None:
        with pytest.raises(
            SemanticMemoryEntryValidationException, match="contradict_evidence_ids"
        ):
            _entry(contradict_evidence_ids=("",))

    def test_evidence_ids_がタプルでなければドメイン例外(self) -> None:
        with pytest.raises(
            SemanticMemoryEntryValidationException, match="support_evidence_ids"
        ):
            _entry(support_evidence_ids=["ev-1"])  # type: ignore[arg-type]


class TestExistingFieldsUnaffected:
    """U3a のフィールド追加が既存フィールドのバリデーションを壊していないこと。"""

    def test_既存フィールドのみで構築できる(self) -> None:
        entry = _entry()
        assert entry.entry_id == "entry-1"
        assert entry.confidence == 0.6


class TestConfirmationSupportCount:
    """P3b: confirmation_support_count (support の CONFIRMATION 内数) の不変条件。"""

    def test_default_is_zero(self) -> None:
        entry = _entry()
        assert entry.confirmation_support_count == 0

    def test_within_support_bounds_ok(self) -> None:
        entry = _entry(
            support_evidence_ids=("e1", "e2", "e3"),
            confirmation_support_count=2,
        )
        assert entry.confirmation_support_count == 2

    def test_exceeding_support_count_raises(self) -> None:
        """support 総数を超える CONFIRMATION 内数は不正 (内数なので <= 総数)。"""
        with pytest.raises(SemanticMemoryEntryValidationException):
            _entry(
                support_evidence_ids=("e1",),
                confirmation_support_count=2,
            )

    def test_negative_raises(self) -> None:
        with pytest.raises(SemanticMemoryEntryValidationException):
            _entry(confirmation_support_count=-1)


class TestHearsaySupportCount:
    """P10: hearsay_support_count (support の HEARSAY 内数) の不変条件。"""

    def test_default_is_zero(self) -> None:
        assert _entry().hearsay_support_count == 0

    def test_within_support_bounds_ok(self) -> None:
        entry = _entry(
            support_evidence_ids=("e1", "e2", "e3"),
            hearsay_support_count=2,
        )
        assert entry.hearsay_support_count == 2

    def test_exceeding_support_count_raises(self) -> None:
        with pytest.raises(SemanticMemoryEntryValidationException):
            _entry(support_evidence_ids=("e1",), hearsay_support_count=2)

    def test_negative_raises(self) -> None:
        with pytest.raises(SemanticMemoryEntryValidationException):
            _entry(hearsay_support_count=-1)

    def test_confirmation_plus_hearsay_exceeding_support_raises(self) -> None:
        """CONFIRMATION と HEARSAY は排他的な内数。合計が支持総数を超えたら不正。"""
        with pytest.raises(SemanticMemoryEntryValidationException):
            _entry(
                support_evidence_ids=("e1", "e2"),
                confirmation_support_count=1,
                hearsay_support_count=2,
            )

    def test_confirmation_plus_hearsay_within_support_ok(self) -> None:
        """合計が支持総数以内なら両方の内数を同時に持てる。"""
        entry = _entry(
            support_evidence_ids=("e1", "e2", "e3"),
            confirmation_support_count=1,
            hearsay_support_count=2,
        )
        assert entry.confirmation_support_count == 1
        assert entry.hearsay_support_count == 2
