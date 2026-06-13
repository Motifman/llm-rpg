"""MemoryKind — Being が所有する記憶 store の種類を識別する enum。

PR #462 §2.1 (R1) の Being 集約構成要素:

    memory_refs: 各記憶 store への所有参照
                 (L4/L5 世代, episodic, semantic, memo, 関係)

集約粒度方針 (b) (= being_id を共有キーにした store 連合) に従い、本 enum は
**「どの store kind を所有しているか」の宣言** として機能する。Being 集約自体は
記憶インスタンスを保持せず、本宣言を見て all-or-nothing loader (Phase 2 PR4
予定) が対応 Repository から being_id keyed で load する。

Phase 2 PR3 (本 PR) では SHORT_TERM / EPISODIC / SEMANTIC / MEMO の 4 種類を
列挙する。Phase 1 で domain/memory/ 配下に昇格した 4 bounded context と 1:1 対応。

「関係」(= 他者モデル / relationship ledger) は Part I C6 / S2 で導入される
予定で、本 PR の対象外 (= 後続 PR で追加)。
"""

from __future__ import annotations

from enum import Enum


class MemoryKind(str, Enum):
    """Being が所有しうる記憶 store の種類。

    str を継承しているのは、シリアライズ時に enum value を文字列として扱える
    ようにするため (= 既存 ``EpisodicReinterpretationStatus`` と同じパターン)。
    """

    SHORT_TERM = "short_term"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    MEMO = "memo"


__all__ = ["MemoryKind"]
