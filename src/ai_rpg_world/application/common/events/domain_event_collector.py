"""オペレーション境界でドメインイベントを収集する ``DomainEventCollector``。

ドメインイベント配信一元化リファクタ (docs/refactor_plans/) の Stage 2 で導入する
基盤機能。狙いは棚卸し (stage0a_inventory.md) で判明した 2 つの問題を、収集を
オペレーション境界に寄せることで解く土台を作ること:

1. 「その場生成」イベントが 9 サイトあり、repo-tracking (UoW 収集) では拾えない。
   → collector なら集約イベントも手作りイベントも同じ入口で ``add`` できる。
2. deepcopy された同一イベントが tick を跨いで再放出されうる (#746 で止血した根)。
   → event_id ベースの operation-local dedup で「同じ event を 1 オペレーションで
   二重 dispatch しない」を構造的に保証する。

契約は stage1_contract.md §4 に対応する。この collector は「収集 + 冪等化」だけを
担い、相 (①a/①b/①c/②/③) ごとの dispatch は呼び出し側 / 後段の dispatcher が行う。

**例外方針**: ``add`` は event_id を持たないオブジェクトを渡されたら即座に失敗する
(fail-fast)。静かに無視すると「collect したつもりで配信されない」静かな失敗になる。
"""

from __future__ import annotations

from typing import Iterable, List, Set

from ai_rpg_world.domain.common.domain_event import DomainEvent


class DomainEventCollector:
    """1 オペレーション分のドメインイベントを収集し、event_id で冪等化する buffer。

    - ``add`` / ``add_all`` で収集。挿入順を保持する。
    - 同一 ``event_id`` の二重 add は 2 件目以降を捨てる (operation-local dedup)。
    - ``drain`` で収集済みイベントを挿入順に返し、内部状態を空にする。

    event_id は ``BaseDomainEvent`` が ``uuid.uuid4().int`` で必ず持つ (int)。
    deepcopy された同一イベントでも event_id は等しいため、再放出対策に合致する。
    """

    def __init__(self) -> None:
        self._events: List[DomainEvent] = []
        self._seen_event_ids: Set[int] = set()

    def add(self, event: DomainEvent) -> None:
        """イベントを 1 件収集する。同一 event_id は 2 件目以降を捨てる。

        event_id を持たないオブジェクトは ``ValueError`` で即失敗する (fail-fast)。

        **dedup の意味**: この dedup が守るのは「同一イベント (同じ event_id を持つ
        オブジェクト、deepcopy を含む) を 1 オペレーションで二重に add してしまう」
        ケースのみ (#746 の再放出対策)。``BaseDomainEvent.create`` は
        ``uuid.uuid4().int`` で毎回別の event_id を振るため、本来別のイベントが
        誤って畳まれることはない。ただしテスト/ファクトリが event_id を手で固定した
        場合、別意図のイベントでも同 id なら 2 件目が黙って捨てられる点に注意。
        """
        if not hasattr(event, "event_id"):
            raise ValueError(
                f"DomainEventCollector.add に event_id を持たないオブジェクト "
                f"{type(event).__name__} が渡された。ドメインイベントのみ収集できる。"
            )
        event_id = event.event_id
        if event_id is None:
            raise ValueError(
                f"DomainEventCollector.add に event_id=None のイベント "
                f"{type(event).__name__} が渡された。"
            )
        if event_id in self._seen_event_ids:
            return
        self._seen_event_ids.add(event_id)
        self._events.append(event)

    def add_all(self, events: Iterable[DomainEvent]) -> None:
        """複数イベントを収集順に add する。"""
        for event in events:
            self.add(event)

    def drain(self) -> List[DomainEvent]:
        """収集済みイベントを挿入順に返し、buffer を空にする。

        呼び出し後は再収集できる (dedup 状態も含めてリセットされる)。
        """
        drained = self._events
        self._events = []
        self._seen_event_ids = set()
        return drained

    def __len__(self) -> int:
        return len(self._events)


__all__ = ["DomainEventCollector"]
