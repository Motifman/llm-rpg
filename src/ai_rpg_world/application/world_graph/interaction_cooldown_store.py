"""対人行為の再使用間隔を覚えておく。

## なぜ要るか

実 run 008 で、インポスターが tick 4 と tick 6 で連続殺害して tick 7 に
終わった。**歩ける速さで殺し続けられる。** クルーは死体を見つける前に
数を減らされ、通報も会議も起きなかった。

本家 (Among Us) には殺害の間隔がある。engine に「殺し」の概念を持ち込まず、
**対人行為一般の再使用間隔**として表現する。

## 「キルのクールダウン」を作らない

engine が知っているのは「宣言された対人行為」までで、そのうちどれが殺しか
は知らない。知らせると、殺しのある世界とない世界で engine が分岐を持つ。
どの行為に間隔を置くかはシナリオが決める。

    { "action_name": "strike_down", "cooldown_ticks": 5 }

## 成功したときだけ起点を更新する

空振りで待たされるのは理不尽で、しかも**前提条件を試すことが罰になる**。
「暗くないので襲えなかった」で 5 tick 封じられると、条件を確かめる行動が
取れなくなる。

## actor / world の共有単位もシナリオが決める

既定は従来どおり player_id ごと。``world`` を宣言した行為だけは player_id を
無視し、同じ行為キーの起点を世界で一つ持つ。engine に役職や陣営を教えず、
どの操作を共有するかはシナリオへ残す。

## world 局所の状態である

tick 基準の記録なので、Being の snapshot ではなく world snapshot に載る
(`game_phase` と同じ)。Being は世界をまたいで永続するが、
「tick 12 に使った」を別の世界へ持ち越しても意味が無い。tick の採番が違う。

**store を足す PR で codec も同時に入れる。** 「あとで足す」と、長走実験の
終了 → 再開で間隔がリセットされ、連続殺害が静かに復活する
(design_decisions #27 と同じ理由)。
"""

from __future__ import annotations

from typing import Dict, Iterable, Mapping, Optional, Tuple

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.interaction_cooldown_scope import (
    InteractionCooldownScope,
)


#: 物体操作の記録キーに使う engine 予約の接頭辞。
#:
#: 対人行為はキーに action_name をそのまま使うので、接頭辞を片方に付けるだけでは
#: **規約に頼った分離**にしかならない。対人行為を ``object:1:draw_water`` と
#: 名付けると、物体 1 の ``draw_water`` と同じキーになる (codex が実測)。
#:
#: 読み込み時にこの接頭辞で始まる action_name を落として、構造で分ける。
#: snapshot のキー形式を変えないので、既存の保存データの移行が要らない。
RESERVED_ACTION_NAME_PREFIX = "object:"
ITEM_ACTION_NAME_PREFIX = "item:"


def object_action_key(object_id: int, action_name: str) -> str:
    """物体操作を覚えておくときのキー。

    行為の名前だけでは足りない。survival_island_v2 は ``harvest`` /
    ``open_chest`` / ``drink_water`` を**別の物体に 2 つずつ**宣言している。
    名前だけで数えると、井戸を汲んだせいで手押しポンプが使えなくなる。

    対人行為の名前と衝突しないよう接頭辞を付ける。組み立て方はここに 1 つだけ
    置く。呼び出し側で文字列を組むと、記録する側と読む側で綴りがずれたときに
    **待ち時間が黙って効かなくなる**。
    """
    return f"{RESERVED_ACTION_NAME_PREFIX}{int(object_id)}:{action_name}"


def item_action_key(item_spec_id: int, action_name: str) -> str:
    """道具操作を品目と action_name の組で覚えるキー。

    instance ID は含めない。同じ品目を 2 個持って待ち時間を迂回できないよう、
    ItemSpecId 単位で共有する。一方 action_name は必ず含め、同じ道具に宣言した
    別操作の待ち時間は独立させる。
    """
    return f"{ITEM_ACTION_NAME_PREFIX}{int(item_spec_id)}:{action_name}"


class InteractionCooldownStore:
    """actor scope と world scope の行為キー → 最後に成功した tick。

    対人行為は action_name をそのまま、物体操作は ``object_action_key``、
    道具操作は ``item_action_key`` が組み立てたキーを使う。
    """

    def __init__(self) -> None:
        self._last_success: Dict[int, Dict[str, int]] = {}
        self._world_last_success: Dict[str, int] = {}

    def record_success(
        self,
        player_id: PlayerId,
        action_name: str,
        tick: int,
        *,
        scope: InteractionCooldownScope,
    ) -> None:
        """成功した対人行為の tick を控える。"""
        if not isinstance(tick, int) or isinstance(tick, bool):
            raise TypeError(f"tick must be int (got {type(tick)!r})")
        if tick < 0:
            raise ValueError(f"tick must be >= 0 (got {tick})")
        if scope is InteractionCooldownScope.WORLD:
            self._world_last_success[str(action_name)] = tick
            return
        self._last_success.setdefault(int(player_id), {})[str(action_name)] = tick

    def remaining_ticks(
        self,
        player_id: PlayerId,
        action_name: str,
        *,
        cooldown_ticks: int,
        current_tick: int,
        scope: InteractionCooldownScope,
    ) -> int:
        """あと何 tick 待てば使えるか。使えるなら 0。

        一度も成功していなければ 0。**最初の 1 回は待たせない。**
        開始直後を封じたい世界は別の宣言 (初回の間隔) が要る話で、ここに
        混ぜると「使ったことがない」と「待っている」の区別が消える。

        現在 tick が記録より前に戻っている場合 (snapshot の取り違え等) は
        0 を返す。負の残りを返すより、使える側に倒して**おかしさを行動として
        観測できる**ようにする。
        """
        if cooldown_ticks <= 0:
            return 0
        last = (
            self._world_last_success.get(str(action_name))
            if scope is InteractionCooldownScope.WORLD
            else self._last_success.get(int(player_id), {}).get(str(action_name))
        )
        if last is None:
            return 0
        elapsed = current_tick - last
        if elapsed < 0:
            return 0
        return max(0, cooldown_ticks - elapsed)

    def snapshot(
        self,
    ) -> Tuple[Mapping[int, Mapping[str, int]], Mapping[str, int]]:
        """保存用に actor scope と world scope を分けて読み出す。"""
        return (
            {pid: dict(actions) for pid, actions in self._last_success.items()},
            dict(self._world_last_success),
        )

    def replace_all(
        self,
        entries: Iterable[Tuple[int, str, int]],
        world_entries: Iterable[Tuple[str, int]] = (),
    ) -> None:
        """復元用にすべて差し替える。

        追記ではなく差し替えにする。追記だと、復元前に走った tick の記録が
        混ざって**再開後だけ間隔が伸びる**。
        """
        replaced: Dict[int, Dict[str, int]] = {}
        for player_id, action_name, tick in entries:
            replaced.setdefault(int(player_id), {})[str(action_name)] = int(tick)
        self._last_success = replaced
        self._world_last_success = {
            str(action_name): int(tick) for action_name, tick in world_entries
        }

    def last_success_tick(
        self,
        player_id: PlayerId,
        action_name: str,
        *,
        scope: InteractionCooldownScope = InteractionCooldownScope.ACTOR,
    ) -> Optional[int]:
        """最後に成功した tick。無ければ None。"""
        if scope is InteractionCooldownScope.WORLD:
            return self._world_last_success.get(str(action_name))
        return self._last_success.get(int(player_id), {}).get(str(action_name))
