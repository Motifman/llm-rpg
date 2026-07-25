"""倒れている間に自分を対象として行われた行為を、復活まで預かる。

倒れている player は observation の宛先から一律に外れる (Issue #621 Phase 4:
ターンが回らず観測を消化できないため)。一方で、奪う (take) が成立するのは
**倒れている相手だけ** である。つまり被害者は構造的に、自分が何をされたのかを
観測できない。

気を失っている間の出来事を「その瞬間に」知覚しないのは筋が通る。しかし起きた
あとも永久に分からないままだと、荷が減った理由を本人が説明できない。目を覚ま
した本人が「持ち物を漁られた形跡がある」と気付けるところまでは要る。

本 log は「その瞬間に配れない観測」を復活まで預かるだけの入れ物で、観測
パイプラインの代わりではない。復活時に
``PlayerRevivedPostHocObservationHandler`` が drain して post hoc summary
(Issue #621 Phase 5) に併せて渡す。

**snapshot には載せない。** 保持するのは「倒れてから起きるまで」の短命な
情報で、observation_buffer 自体が snapshot 対象でないのと揃える。倒れたまま
保存して再開した場合、被害の記憶は失われる (実験の連続性としては
observation_buffer と同じ粒度の欠落であり、per-Being store の永続化規約
(design_decisions #27) が対象とする state ではない)。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class DownedIncidentLog:
    """player ごとに「倒れている間にされたこと」の短い記述を溜める。"""

    #: 1 人あたりの保持上限。復活時の prose が長くなりすぎるのを防ぐ。
    #: 超えた分は古いものから捨てる (直近の被害の方が行動判断に効く)。
    MAX_ENTRIES_PER_PLAYER = 8

    def __init__(self) -> None:
        self._entries: Dict[int, List[str]] = defaultdict(list)

    def record(self, player_id: PlayerId, description: str) -> None:
        """``player_id`` が受けた行為を 1 件記録する。

        空文字は落とす。呼び出し側の組み立てが失敗したときに空行だけが
        目覚めの文に混ざるのを防ぐ。
        """
        text = (description or "").strip()
        if not text:
            return
        bucket = self._entries[int(player_id)]
        bucket.append(text)
        if len(bucket) > self.MAX_ENTRIES_PER_PLAYER:
            del bucket[: len(bucket) - self.MAX_ENTRIES_PER_PLAYER]

    def drain(self, player_id: PlayerId) -> Tuple[str, ...]:
        """``player_id`` ぶんを取り出して空にする。

        drain しないと、2 度目の復活で 1 度目の被害まで再び読まされる。
        """
        return tuple(self._entries.pop(int(player_id), []))

    def peek(self, player_id: PlayerId) -> Tuple[str, ...]:
        """消さずに覗く (テスト・デバッグ用)。"""
        return tuple(self._entries.get(int(player_id), []))
