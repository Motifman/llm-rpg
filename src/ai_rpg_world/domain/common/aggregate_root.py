import logging
from collections import Counter
from typing import Any, List

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent


logger = logging.getLogger(__name__)


class AggregateRoot:
    """集約ルートの基底クラス"""

    def __init__(self):
        self._events: List[BaseDomainEvent[Any, Any]] = []

    def add_event(self, event: BaseDomainEvent[Any, Any]) -> None:
        """ドメインイベントを追加"""
        self._events.append(event)

    def get_events(self) -> List[BaseDomainEvent[Any, Any]]:
        """未発行のイベントを取得"""
        return self._events.copy()

    def clear_events(self) -> None:
        """イベントをクリア"""
        self._events.clear()

    def warn_if_pending_events(self, *, context: str) -> None:
        """PR-L (B1): ``add_event`` した events が publish されずに残っている
        状態を検出するための観測 only ヘルパ。

        events が非空のときに warning ログを出す。**副作用なし** (= events を
        clear しないし、events を消費もしない)。Repository.save() の末尾や、
        Application Service の境界 (= 「ここで publish 漏れがあったらバグ」と
        判断できる箇所) で **opt-in** に呼び出す。

        全 save に強制的に組み込まない理由:
        - 「graph events が別経路で flow する」「intentional に events を持ち
          越す」ケースで noise が増える
        - aggregate に events が積まれている状態自体は不正ではない (= publish
          のタイミング設計次第)
        - 呼出側が「ここでは消費されているはず」と確信を持って呼ぶ所だけで
          検出に意味がある

        Args:
            context: どこで pending を検出したかを特定するための文字列
                (例: ``"SpotAttackOrchestrator.execute_monster_attack"``)。
                warning メッセージに含まれる。
        """
        pending = self.get_events()
        if not pending:
            return
        counts = Counter(type(e).__name__ for e in pending)
        breakdown = ", ".join(f"{name}={n}" for name, n in counts.most_common())
        logger.warning(
            "Aggregate has %d pending domain events at %s; publish_all() may "
            "have been forgotten. event_types: %s",
            len(pending), context, breakdown,
        )
