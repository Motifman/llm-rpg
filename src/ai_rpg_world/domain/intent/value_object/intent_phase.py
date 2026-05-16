"""``IntentPhase`` 列挙。

同一 tick 内に投入された intent をどの順で解決するかを決める論理フェーズ。
値が小さいほど先に走る。

順序設計
--------
``MOVEMENT`` を先に流すのは「移動先の状況に応じて他の intent が late-binding
で解決できる」状態を作るため。たとえば「歩いて隣のスポットに移動した上で
そこのアイテムを拾う」を別 tick で連続して行わなくても、移動結果を踏まえた
解決が可能になる。``ATTACK`` は移動・interaction を経た「最新の戦闘配置」で
解決したいので後段。``SOCIAL`` (発話・囁き) は副作用が小さく、最後に流して
他フェーズの結果を反映した発話 (例: 失敗後の慌てた一言) を可能にする。
"""

from enum import IntEnum


class IntentPhase(IntEnum):
    """同 tick 内 intent の解決順を決める論理フェーズ。"""

    MOVEMENT = 10
    INTERACTION = 20
    ATTACK = 30
    SOCIAL = 40
    OTHER = 90
