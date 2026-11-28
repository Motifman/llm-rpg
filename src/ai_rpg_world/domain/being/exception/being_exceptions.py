"""Being ドメインの例外定義。

DDD の原則に従い、ドメイン固有の意味を持つカスタム例外を使用する。
全ての Being ドメイン例外は ``BeingDomainException`` と適切なカテゴリ例外を
多重継承し、エラーコードは ``BEING.xxx`` の形式で統一する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_rpg_world.domain.common.exception import (
    BusinessRuleException,
    DomainException,
    NotFoundException,
    StateException,
    ValidationException,
)

if TYPE_CHECKING:
    from ai_rpg_world.being.domain.memo_book import MemoKind


class BeingDomainException(DomainException):
    """Being ドメインの基底例外。

    全ての Being ドメイン例外はこのクラスを継承する。
    """

    domain = "being"


# ===== 具体的な例外クラス =====


class BeingIdValidationException(BeingDomainException, ValidationException):
    """BeingId バリデーション例外。"""

    error_code = "BEING.ID_VALIDATION"


class PersonaValidationException(BeingDomainException, ValidationException):
    """Persona の名前や人柄の値が、空白だけか、型が違う。"""

    error_code = "BEING.PERSONA_VALIDATION"


class BeingNotFoundException(BeingDomainException, NotFoundException):
    """指定された BeingId の Being が見つからない場合の例外。"""

    error_code = "BEING.NOT_FOUND"


class BeingAttachmentValidationException(BeingDomainException, ValidationException):
    """BeingAttachment バリデーション例外 (world_id / player_id の型違反)。"""

    error_code = "BEING.ATTACHMENT_VALIDATION"


class BeingAlreadyAttachedException(BeingDomainException, StateException):
    """既に attachment を持つ Being への再 attach を防ぐ状態遷移例外。

    PR #462 §2.1 (R1): attachment は 0..1。同時に複数の world に乗ることは
    本 PR 時点で不許可 (= YAGNI)。乗り換える場合は先に ``detach`` する。
    """

    error_code = "BEING.ALREADY_ATTACHED"


class BeingIntroducedToItselfException(BeingDomainException, BusinessRuleException):
    """環境に入るときの紹介に、自分の名前が入っていた。"""

    error_code = "BEING.INTRODUCED_TO_ITSELF"


class BeingNotAttachedException(BeingDomainException, StateException):
    """どの環境にも入っていない Being を、環境から外そうとした。"""

    error_code = "BEING.NOT_ATTACHED"


class BeingSnapshotIncompleteException(BeingDomainException, ValidationException):
    """BeingSnapshot の構造が不整合な場合に投げる例外。

    PR #462 §2.1 R1 「all-or-nothing で復元の完全性を保証 (部分復元を構造的に
    禁止)」を強制する例外。snapshot の attachment フィールドが片方だけ埋まって
    いる / 認識できない memory_kind が含まれる等の構造的破綻時に投げる。
    """

    error_code = "BEING.SNAPSHOT_INCOMPLETE"


class BeingSnapshotVersionException(BeingDomainException, ValidationException):
    """BeingSnapshot のバージョンが現バージョン codec で復元不能な場合に投げる例外。

    将来の schema 進化に備えた構造化バージョニング (= 設計判断 5)。古い snapshot
    を新 codec で読む場合の明示的なフォールバック地点として使う。
    """

    error_code = "BEING.SNAPSHOT_VERSION"


class EpisodeValidationException(BeingDomainException, ValidationException):
    """エピソードや目次が決まり (空でない、長さの上限、呼び名、回数と時の並び) を満たさない。"""

    error_code = "BEING.EPISODE_VALIDATION"


class EpisodeConflictException(BeingDomainException, BusinessRuleException):
    """同じ Being の中で、ID か呼び名が重なるエピソードを置こうとした。"""

    error_code = "BEING.EPISODE_CONFLICT"


class EpisodeNotFoundException(BeingDomainException, NotFoundException):
    """書き戻そうとしたエピソードが、その Being の記録に無い。"""

    error_code = "BEING.EPISODE_NOT_FOUND"


class EpisodeWritingResponseException(BeingDomainException, ValidationException):
    """エピソードの書き起こしの応答が、決めた形になっていない。"""

    error_code = "BEING.EPISODE_WRITING_RESPONSE"


class MemoValidationException(BeingDomainException, ValidationException):
    """メモやメモ帳が決まり (空でない、長さの上限、分類と出どころの組み合わせ、呼び名、ターンの並び) を満たさない。"""

    error_code = "BEING.MEMO_VALIDATION"


class MemoTextTooLongException(MemoValidationException):
    """メモの文が、長さの上限を超えている。"""

    error_code = "BEING.MEMO_TEXT_TOO_LONG"


class MemoProvenanceMissingException(MemoValidationException):
    """分かったことのメモに、出どころと確かさが無い。"""

    error_code = "BEING.MEMO_PROVENANCE_MISSING"


class MemoProvenanceOutsideFactException(MemoValidationException):
    """分かったこと以外のメモに、出どころと確かさを持たせようとした。"""

    error_code = "BEING.MEMO_PROVENANCE_OUTSIDE_FACT"


class MemoHeardSourceFromMissingException(MemoValidationException):
    """人から聞いたことの出どころに、誰から聞いたかが無い。"""

    error_code = "BEING.MEMO_HEARD_SOURCE_FROM_MISSING"


class MemoEpisodeSourceFromMissingException(MemoValidationException):
    """エピソードから分かったことの出どころに、エピソードの呼び名が無い。"""

    error_code = "BEING.MEMO_EPISODE_SOURCE_FROM_MISSING"


class MemoSourceFromNotNeededException(MemoValidationException):
    """自分で確かめたことの出どころに、誰からかを書いた。"""

    error_code = "BEING.MEMO_SOURCE_FROM_NOT_NEEDED"


class MemoSourceNotEpisodeHandleException(MemoValidationException):
    """エピソードから分かったことの出どころが、エピソードの呼び名の形をしていない。"""

    error_code = "BEING.MEMO_SOURCE_NOT_EPISODE_HANDLE"


class MemoSourceEpisodeUnknownException(MemoValidationException):
    """エピソードから分かったことの出どころが、本人の知っているエピソードの呼び名に無い。"""

    error_code = "BEING.MEMO_SOURCE_EPISODE_UNKNOWN"

    def __init__(self, handle: str, message: str | None = None) -> None:
        self.handle = handle
        super().__init__(message or f"no episode {handle!r}")


class VisitedPlacesValidationException(BeingDomainException, ValidationException):
    """訪れた場所の記録が決まり (空でない名前、同じ場所を重ねない) を満たさない。"""

    error_code = "BEING.VISITED_PLACES_VALIDATION"


class MemoLimitReachedException(BeingDomainException, BusinessRuleException):
    """分類ごとの件数の上限に達したメモ帳に、同じ分類のメモを足そうとした。"""

    error_code = "BEING.MEMO_LIMIT_REACHED"

    def __init__(self, kind: MemoKind, message: str | None = None) -> None:
        self.kind = kind
        super().__init__(message or f"{kind.value} memos are at the limit")


class MemoNotFoundException(BeingDomainException, NotFoundException):
    """書き換えや消す対象の呼び名が、メモ帳に無い。"""

    error_code = "BEING.MEMO_NOT_FOUND"

    def __init__(self, handle: str, message: str | None = None) -> None:
        self.handle = handle
        super().__init__(message or f"no memo {handle!r}")


class ShortTermMemoryValidationException(BeingDomainException, ValidationException):
    """短期記憶の出来事やいきさつが決まり (手番の番号、結果と 1 手の対、並び、世代の上限) を満たさない。"""

    error_code = "BEING.SHORT_TERM_MEMORY_VALIDATION"


class ShortTermMemoryUnpairedResultException(BeingDomainException, BusinessRuleException):
    """結果を待っている 1 手が無いか、結果の呼び出しの ID が待っている 1 手と違う。"""

    error_code = "BEING.SHORT_TERM_MEMORY_UNPAIRED_RESULT"


class ShortTermMemoryStaleBackstoryException(BeingDomainException, BusinessRuleException):
    """届いたいきさつが、いま持っているいきさつと同じか前の範囲までのものだった。入れずに断る。"""

    error_code = "BEING.SHORT_TERM_MEMORY_STALE_BACKSTORY"


class WorkingMemoryOrderException(BeingDomainException, ValidationException):
    """作業記憶の区画が、書き換わりにくい順に並んでいない (#1630)。"""

    error_code = "BEING.WORKING_MEMORY_ORDER"


__all__ = [
    "BeingAlreadyAttachedException",
    "BeingAttachmentValidationException",
    "BeingDomainException",
    "BeingIdValidationException",
    "BeingNotAttachedException",
    "BeingNotFoundException",
    "BeingSnapshotIncompleteException",
    "BeingSnapshotVersionException",
    "EpisodeConflictException",
    "EpisodeNotFoundException",
    "EpisodeValidationException",
    "EpisodeWritingResponseException",
    "MemoEpisodeSourceFromMissingException",
    "MemoHeardSourceFromMissingException",
    "MemoLimitReachedException",
    "MemoNotFoundException",
    "MemoProvenanceMissingException",
    "MemoProvenanceOutsideFactException",
    "MemoSourceEpisodeUnknownException",
    "MemoSourceFromNotNeededException",
    "MemoSourceNotEpisodeHandleException",
    "MemoTextTooLongException",
    "MemoValidationException",
    "VisitedPlacesValidationException",
    "PersonaValidationException",
    "ShortTermMemoryStaleBackstoryException",
    "ShortTermMemoryUnpairedResultException",
    "ShortTermMemoryValidationException",
    "WorkingMemoryOrderException",
]
