"""停滞 reflect 注入 → 次行動での熟考、を橋渡しする一発ラッチ (案A: band-gated thinking)。

停滞 (stalled/misaligned) の reflect 気づきが本人に注入された「その場」で ``arm`` し、
そのエージェントの次の行動の直前に ``consume`` する。consume は 1 度きりで True を返し
即座に落ちる (= 「注入直後の 1 行動」だけ熟考を候補にする)。

**なぜ store でなくラッチ / なぜ snapshot 非対象か**: これは記憶でも継続性状態でも
なく、同一セッション内の一発の制御信号にすぎない。再開時に失っても「熟考の起動が
最大 1 回遅れる」だけで、次の reflect 注入で自己回復する。よって
``BeingMemorySnapshotService`` (checklist #27 = per-Being 継続性 store) には
**意図的に載せない**。player_id keyed であり being にも紐づけない。
"""

from __future__ import annotations

from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class InMemoryStagnationReasoningLatch:
    """player_id ごとに「直前に停滞 reflect が注入された」フラグを一発保持する。"""

    def __init__(self) -> None:
        self._armed: set[int] = set()

    def arm(self, player_id: PlayerId) -> None:
        """停滞 reflect の注入に成功した直後に立てる。多重 arm は冪等。"""
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        self._armed.add(player_id.value)

    def is_armed(self, player_id: PlayerId) -> bool:
        """立っているかを覗くだけで消費しない (peek)。

        案A HIGH 2 対応: 熟考を焚くかの決定 (resolve) は行動 (invoke) の前に行うが、
        ラッチの消費と AGENT_REASONING_ENGAGED trace は invoke 成功後の commit まで
        遅らせる。そのため決定時はここで peek し、実際の消費は ``consume`` で行う。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        return player_id.value in self._armed

    def consume(self, player_id: PlayerId) -> bool:
        """立っていれば True を返して即座に落とす。立っていなければ False。

        band が strong でなくても呼び出し側は consume する (古いフラグを残さない)。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if player_id.value in self._armed:
            self._armed.discard(player_id.value)
            return True
        return False


__all__ = ["InMemoryStagnationReasoningLatch"]
