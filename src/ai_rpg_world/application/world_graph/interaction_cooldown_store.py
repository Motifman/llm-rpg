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

## world 局所の状態である

tick 基準で PlayerId をキーにするので、Being の snapshot ではなく world
snapshot に載る (`game_phase` と同じ)。Being は世界をまたいで永続するが、
「tick 12 に使った」を別の世界へ持ち越しても意味が無い。tick の採番が違う。

**store を足す PR で codec も同時に入れる。** 「あとで足す」と、長走実験の
終了 → 再開で間隔がリセットされ、連続殺害が静かに復活する
(design_decisions #27 と同じ理由)。
"""

from __future__ import annotations

from typing import Dict, Iterable, Mapping, Optional, Tuple

from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class InteractionCooldownStore:
    """player_id × action_name → 最後に成功した tick。"""

    def __init__(self) -> None:
        self._last_success: Dict[int, Dict[str, int]] = {}

    def record_success(
        self, player_id: PlayerId, action_name: str, tick: int
    ) -> None:
        """成功した対人行為の tick を控える。"""
        if not isinstance(tick, int) or isinstance(tick, bool):
            raise TypeError(f"tick must be int (got {type(tick)!r})")
        if tick < 0:
            raise ValueError(f"tick must be >= 0 (got {tick})")
        self._last_success.setdefault(int(player_id), {})[str(action_name)] = tick

    def remaining_ticks(
        self,
        player_id: PlayerId,
        action_name: str,
        *,
        cooldown_ticks: int,
        current_tick: int,
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
        last = self._last_success.get(int(player_id), {}).get(str(action_name))
        if last is None:
            return 0
        elapsed = current_tick - last
        if elapsed < 0:
            return 0
        return max(0, cooldown_ticks - elapsed)

    def snapshot(self) -> Mapping[int, Mapping[str, int]]:
        """保存用に中身を読み出す。"""
        return {
            pid: dict(actions) for pid, actions in self._last_success.items()
        }

    def replace_all(
        self, entries: Iterable[Tuple[int, str, int]]
    ) -> None:
        """復元用にすべて差し替える。

        追記ではなく差し替えにする。追記だと、復元前に走った tick の記録が
        混ざって**再開後だけ間隔が伸びる**。
        """
        replaced: Dict[int, Dict[str, int]] = {}
        for player_id, action_name, tick in entries:
            replaced.setdefault(int(player_id), {})[str(action_name)] = int(tick)
        self._last_success = replaced

    def last_success_tick(
        self, player_id: PlayerId, action_name: str
    ) -> Optional[int]:
        """最後に成功した tick。無ければ None。"""
        return self._last_success.get(int(player_id), {}).get(str(action_name))
