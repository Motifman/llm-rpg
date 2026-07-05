"""BeliefEvidence — 学習の素材を正規化する証拠 VO。

U2 (証拠台帳統一設計): semantic_learning_consolidation_design.md
「中核データ: BeliefEvidence (証拠)」参照。

すべての学習の素材 (予測誤差 / 手続き失敗 / memo / 親密度クラスタ 等) を
1 つの型に正規化する。本 PR (U2) では ``PREDICTION_ERROR`` の転記だけを
配線するが、``source_kind`` は後続 PR ぶんも含めて最初から全種別を
``BeliefEvidenceSourceKind`` に予約している。

固着パス (belief journal への統合、U3) は本 VO を直接 semantic store に
書き込まない。evidence buffer に溜まった証拠を LLM が定期的に読んで
belief を作る/直す、という別レイヤーの仕事であり、本 PR のスコープ外。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Tuple

from ai_rpg_world.domain.memory.semantic.exception.semantic_exception import (
    BeliefEvidenceValidationException,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)

# salience: low | high (high = 即時固着候補。設計上は chunk 主観補完 LLM が
# 書き込み時に一度だけ判定する想定だが、U2 時点ではその LLM フィールドが
# 未配線 (U6 で追加予定) なので、転記側は常に "low" を渡す。
BELIEF_EVIDENCE_SALIENCE_LOW = "low"
BELIEF_EVIDENCE_SALIENCE_HIGH = "high"
_VALID_SALIENCE_VALUES = frozenset(
    {BELIEF_EVIDENCE_SALIENCE_LOW, BELIEF_EVIDENCE_SALIENCE_HIGH}
)


@dataclass(frozen=True)
class BeliefEvidence:
    """学習の素材を正規化した証拠 1 件分 (immutable)。"""

    evidence_id: str
    source_kind: BeliefEvidenceSourceKind
    episode_ids: Tuple[str, ...]
    cue_signature: str
    text: str
    salience: str
    occurred_at: datetime
    tick: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_id, str) or not self.evidence_id.strip():
            raise BeliefEvidenceValidationException(
                "evidence_id must be non-empty str",
                field="evidence_id",
                value=self.evidence_id,
            )
        object.__setattr__(self, "evidence_id", self.evidence_id.strip())

        if not isinstance(self.source_kind, BeliefEvidenceSourceKind):
            raise BeliefEvidenceValidationException(
                "source_kind must be BeliefEvidenceSourceKind",
                field="source_kind",
                value=self.source_kind,
            )

        if not isinstance(self.episode_ids, tuple):
            raise BeliefEvidenceValidationException(
                "episode_ids must be tuple[str, ...]",
                field="episode_ids",
                value=self.episode_ids,
            )
        if not self.episode_ids:
            raise BeliefEvidenceValidationException(
                "episode_ids must not be empty (evidence must be traceable "
                "to at least one episode)",
                field="episode_ids",
            )
        for idx, eid in enumerate(self.episode_ids):
            if not isinstance(eid, str) or not eid.strip():
                raise BeliefEvidenceValidationException(
                    f"episode_ids[{idx}] must be non-empty str",
                    field="episode_ids",
                    index=idx,
                )

        if not isinstance(self.cue_signature, str) or not self.cue_signature.strip():
            raise BeliefEvidenceValidationException(
                "cue_signature must be non-empty str",
                field="cue_signature",
                value=self.cue_signature,
            )
        object.__setattr__(self, "cue_signature", self.cue_signature.strip())

        if not isinstance(self.text, str) or not self.text.strip():
            raise BeliefEvidenceValidationException(
                "text must be non-empty str",
                field="text",
                value=self.text,
            )
        object.__setattr__(self, "text", self.text.strip())

        if self.salience not in _VALID_SALIENCE_VALUES:
            raise BeliefEvidenceValidationException(
                f"salience must be one of {sorted(_VALID_SALIENCE_VALUES)}",
                field="salience",
                value=self.salience,
            )

        if not isinstance(self.occurred_at, datetime):
            raise BeliefEvidenceValidationException(
                "occurred_at must be datetime",
                field="occurred_at",
                value=self.occurred_at,
            )

        if self.tick is not None and not isinstance(self.tick, int):
            raise BeliefEvidenceValidationException(
                "tick must be int or None",
                field="tick",
                value=self.tick,
            )


__all__ = [
    "BeliefEvidence",
    "BELIEF_EVIDENCE_SALIENCE_LOW",
    "BELIEF_EVIDENCE_SALIENCE_HIGH",
]
