"""HeardClaim — 他者が語った「世界や人がどうであるか」の主張 1 件 (P9 伝聞)。

belief_hearsay_design.md §2 ステップ 1: chunk 主観補完 LLM が、その期間に他者が
語った主張 (場所・物事・人物について。噂話も含む) を抽出した結果。約束
(``PendingPredictionDraft``) と同じく、``SubjectiveEpisode`` に一時的に載せて
chunk 完了点まで運ぶ **スクラッチフィールド** であり、HEARSAY evidence に転記
した後は用済みになる (store / snapshot には永続化しない)。

``speaker`` (誰が言ったか) と ``claim`` (何を言ったか) だけを持つ。claim の
**対象** (cue) は転記側 (``BeliefEvidenceTranscriber``) が noun matcher で決める。
speaker は cue と混ぜず ``BeliefEvidence.source_speaker`` に分離して保持する
(混ぜると「話者についての belief」に化ける — 設計メモ §2 ステップ 2)。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.memory.episodic.exception.episodic_exception import (
    HeardClaimValidationException,
)


@dataclass(frozen=True)
class HeardClaim:
    """他者が語った主張 1 件 (speaker: 話者 / claim: 主張の内容)。"""

    speaker: str
    claim: str

    def __post_init__(self) -> None:
        if not isinstance(self.speaker, str) or not self.speaker.strip():
            raise HeardClaimValidationException(
                "speaker must be non-empty str",
                field="speaker",
                value=self.speaker,
            )
        if not isinstance(self.claim, str) or not self.claim.strip():
            raise HeardClaimValidationException(
                "claim must be non-empty str",
                field="claim",
                value=self.claim,
            )
        object.__setattr__(self, "speaker", self.speaker.strip())
        object.__setattr__(self, "claim", self.claim.strip())


__all__ = ["HeardClaim"]
