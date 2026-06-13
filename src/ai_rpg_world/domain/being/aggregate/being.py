"""Being 集約ルート。

「経験を持つ AI」の主体。世界・run を跨いで永続化される第一級のドメイン概念。

Phase 2 PR1 (本 PR) では最小骨格のみ:

- ``BeingId`` (identity)
- ``BeingIdentity`` (persona 不変核)

後続 PR で以下を順次追加する (PR #462 §2.1 R1 / Issue #470 Phase 2):

- ``memory_refs``: 各記憶 store への所有参照 (L4/L5 / episodic / semantic / memo)
- ``attachments``: 現在どの世界のどの player に「乗って」いるか (0..1)
- ``habits``: System 1 キャッシュ (PR #462 §2.3 R3)

集約の粒度方針 (PR #462 §4 起案者推し): (b) **being_id を共有キーにした
store 連合 + all-or-nothing loader** から始める。記憶 store は書き込み頻度が
高く、集約に閉じるとロック競合するため、本 aggregate root は薄い identity
core を保持する。
"""

from __future__ import annotations

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_identity import BeingIdentity
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot


class Being(AggregateRoot):
    """Being 集約ルート。"""

    def __init__(self, being_id: BeingId, identity: BeingIdentity) -> None:
        super().__init__()
        if not isinstance(being_id, BeingId):
            raise TypeError(
                f"being_id must be BeingId, got {type(being_id).__name__}"
            )
        if not isinstance(identity, BeingIdentity):
            raise TypeError(
                f"identity must be BeingIdentity, got {type(identity).__name__}"
            )
        self._being_id = being_id
        self._identity = identity

    @property
    def being_id(self) -> BeingId:
        return self._being_id

    @property
    def identity(self) -> BeingIdentity:
        return self._identity

    def __repr__(self) -> str:
        return (
            f"Being(being_id={self._being_id!r}, identity={self._identity!r})"
        )


__all__ = ["Being"]
