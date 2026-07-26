"""世界全体のモード (Phase: 自由時間 / 会議)。

`world_flag` に `phase:meeting` のようなフラグを立てる表現は採らない。
フラグは排他を保証しないので、`phase:meeting` と `phase:free` が同時に
立った状態を型が止められず、「会議が終わったのに消し忘れて永久に会議」が
静かに起きる (docs/memory_system/meeting_and_voting_design.md §2.1)。

day_night に相乗りする案も採らない。「夜」と「会議中」は直交する概念で、
掛け合わせたくなった瞬間に破綻する。

状態を 2 つに絞ってあるのは意図的である。本家 Among Us は「議論時間 →
投票時間」と分かれているが、実際には議論中いつでも投票できるので、投票を
MEETING 中に使える tool にすれば 1 状態で足りる。状態を増やさないぶん、
遷移の抜けと snapshot の追従漏れが減る。
"""

from enum import Enum


class GamePhase(Enum):
    """世界がいまどのモードにあるか。"""

    #: 自由時間。移動・探索・対人行為ができる。
    FREE_ROAM = "FREE_ROAM"

    #: 会議中。発言と投票ができ、移動と対人行為はできない
    #: (前提条件で弾くのではなく toolset から外す: 設計 doc §2.5)。
    MEETING = "MEETING"
