"""prediction_context_id の発行・消費を管理する turn-scope 台帳 (U1)。

# 設計判断

予測誤差統一設計 §部品1 (``docs/memory_system/prediction_error_unified_memory_design.md``)
の「どのプロンプト (何が in-context だったか) で立てた予測が、どう外れたか」を
1 つの id で貫くための土台。id そのものの生成・寿命管理だけを担い、attribution
ledger 本体 (per-Being store 化して belief_id / episode_id を長期保持するもの) は
U4 のスコープ。ここでは「1 build = 1 発行、直後の 1 record = 1 消費」という
不変条件だけを守る軽量な in-memory 実装にとどめる。

**id の寿命 (不変条件)**:
- ``issue()`` は ``DefaultPromptBuilder.build()`` から呼ばれ、そのターンの
  prompt に何が in-context だったか (``episode_ids`` / ``belief_ids``) を
  添えて新しい id を発行する。
- ``consume()`` は ``ActionResultRecorder.record()`` から呼ばれ、直前に発行された
  id を取り出して ``ActionResultEntry`` に焼き込む。
- 同じ player に対して ``consume()`` されないまま次の ``issue()`` が来たら
  (= no-tool ターン / 例外で record に届かなかった / 途中で再スケジュールされた
  等)、古い id は静かに握りつぶさず **破棄扱いとして呼び出し元に返す**。
  呼び出し元 (prompt_builder) がそれを trace ``NOTE`` に残す。ledger 自身は
  trace recorder に依存しない (単体テストしやすさ優先)。
- player をまたいだ混線は player_id をキーにした dict で構造的に防ぐ。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from uuid import uuid4

from ai_rpg_world.domain.player.value_object.player_id import PlayerId


@dataclass(frozen=True)
class PredictionContext:
    """1 回の prompt build で発行された prediction_context_id とその in-context 集合。"""

    prediction_context_id: str
    episode_ids: Tuple[str, ...] = ()
    belief_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PredictionContextIssueResult:
    """``PredictionContextLedger.issue`` の戻り値。

    ``discarded`` は「前回発行されたが consume されないまま上書きされた」
    context (無ければ None)。呼び出し元が trace NOTE を出すかどうかの判断に使う。
    """

    prediction_context_id: str
    discarded: Optional[PredictionContext]


class PredictionContextLedger:
    """player_id ごとに直近未消費の :class:`PredictionContext` を 1 件だけ保持する。"""

    def __init__(self) -> None:
        self._pending: Dict[int, PredictionContext] = {}

    def issue(
        self,
        player_id: PlayerId,
        *,
        episode_ids: Tuple[str, ...] = (),
        belief_ids: Tuple[str, ...] = (),
    ) -> PredictionContextIssueResult:
        """新しい prediction_context_id を発行し、未消費の前回分があれば破棄して返す。"""
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        key = player_id.value
        discarded = self._pending.pop(key, None)
        new_id = f"predctx-{uuid4().hex}"
        self._pending[key] = PredictionContext(
            prediction_context_id=new_id,
            episode_ids=tuple(episode_ids),
            belief_ids=tuple(belief_ids),
        )
        return PredictionContextIssueResult(prediction_context_id=new_id, discarded=discarded)

    def consume(self, player_id: PlayerId) -> Optional[PredictionContext]:
        """未消費の pending context を取り出して ledger から消す (無ければ None)。"""
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        return self._pending.pop(player_id.value, None)

    def peek(self, player_id: PlayerId) -> Optional[PredictionContext]:
        """消費せずに現在の pending context を覗き見る (テスト・デバッグ用)。"""
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        return self._pending.get(player_id.value)


__all__ = [
    "PredictionContext",
    "PredictionContextIssueResult",
    "PredictionContextLedger",
]
