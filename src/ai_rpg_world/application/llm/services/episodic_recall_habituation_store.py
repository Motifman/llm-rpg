"""慣化ペナルティ (#526 後続) — 段階 2 の sidecar store。

人間の habituation を模す: 直近で recall された episode は、しばらく score
を下げる。これにより「同じ場所にいる間に毎ターン同じ episode が出続ける」
状態を抑える。

設計判断:
- ``episode`` 本体 (``SubjectiveEpisode``) は触らない。事実 (episode) と
  評価 (recall stats) は別寿命で管理し、再解釈経路を壊さない
- in-memory のみ。permanent な being snapshot を汚さず、experiment run
  の単位でリセットされる
- penalty 関数は純関数で境界値テスト可能
- protocol で外部置換可能にしておく (将来 redis / sqlite に差し替え)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Dict, Iterable, Optional, Protocol, runtime_checkable

from ai_rpg_world.domain.being.value_object.being_id import BeingId


def compute_habituation_penalty(
    *,
    last_recalled_tick: Optional[int],
    current_tick: int,
    decay_window: int,
) -> int:
    """直近 recall からの経過に応じた線形の慣化ペナルティ。

    - ``last_recalled_tick`` が ``None`` → penalty 0 (= 未 recall)
    - age = ``current_tick - last_recalled_tick`` が負 → 0 (異常値は無視)
    - age が ``decay_window`` 以上 → 0 (= 慣化解除)
    - それ以外 → ``decay_window - age`` (= 直近ほど大きく、線形に減衰)

    ``decay_window=0`` は機能 off の境界として許可、負値は誤設定として
    弾く (configuration validation)。
    """
    if not isinstance(decay_window, int) or isinstance(decay_window, bool):
        raise TypeError("decay_window must be int")
    if decay_window < 0:
        raise ValueError("decay_window must be 0 or greater")
    if last_recalled_tick is None:
        return 0
    age = current_tick - last_recalled_tick
    if age < 0 or age >= decay_window:
        return 0
    return decay_window - age


@runtime_checkable
class IEpisodicRecallHabituationStore(Protocol):
    """直近 recall された tick を episode 単位で記憶する sidecar store。

    実装は being ごとに隔離されること (二人プレイでの干渉を防ぐ)。
    """

    def get_last_recalled_tick(
        self, being_id: BeingId, episode_id: str
    ) -> Optional[int]:
        """指定 episode の直近 recall tick を返す。未記録なら ``None``。"""
        ...

    def record_recall(
        self,
        being_id: BeingId,
        episode_ids: Iterable[str],
        tick: int,
    ) -> None:
        """与えられた episode 群の ``last_recalled_tick`` を ``tick`` で更新する。

        空リストは no-op。同 tick で複数回呼ばれても idempotent。
        """
        ...

    def list_all_by_being(self, being_id: BeingId) -> Mapping[str, int]:
        """PR-G: snapshot capture 用に「episode_id → last_recalled_tick」の
        全エントリを返す。未記録なら空 dict。"""
        ...

    def replace_all_by_being(
        self,
        being_id: BeingId,
        mapping: Mapping[str, int],
    ) -> None:
        """PR-G: snapshot 復元用の bulk overwrite。"""
        ...


class InMemoryEpisodicRecallHabituationStore(IEpisodicRecallHabituationStore):
    """プロセスメモリ常駐の sidecar 実装。experiment run の単位で破棄される。

    being 内部は ``dict[episode_id → last_recalled_tick]`` で持つ。
    being 同士は外側の dict で分離 (相互干渉なし)。
    """

    def __init__(self) -> None:
        self._by_being: Dict[BeingId, Dict[str, int]] = {}

    def get_last_recalled_tick(
        self, being_id: BeingId, episode_id: str
    ) -> Optional[int]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        inner = self._by_being.get(being_id)
        if inner is None:
            return None
        return inner.get(episode_id)

    def record_recall(
        self,
        being_id: BeingId,
        episode_ids: Iterable[str],
        tick: int,
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(tick, int) or isinstance(tick, bool):
            raise TypeError("tick must be int")
        if tick < 0:
            raise ValueError("tick must be 0 or greater")
        ids = list(episode_ids)
        if not ids:
            return
        inner = self._by_being.setdefault(being_id, {})
        for eid in ids:
            inner[eid] = tick

    def list_all_by_being(self, being_id: BeingId) -> Mapping[str, int]:
        """PR-G: snapshot capture 用に「episode_id → last_recalled_tick」の
        全エントリを copy で返す (= 呼出側変更で内部 state を壊さない)。"""
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        return dict(self._by_being.get(being_id, {}))

    def replace_all_by_being(
        self,
        being_id: BeingId,
        mapping: Mapping[str, int],
    ) -> None:
        """PR-G: snapshot 復元用の bulk overwrite。中身が空なら being_id の
        state を完全に削除する (= capture 時の空状態と bit identity を保つ)。"""
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if mapping:
            self._by_being[being_id] = {
                str(k): int(v) for k, v in mapping.items()
            }
        else:
            self._by_being.pop(being_id, None)


__all__ = [
    "compute_habituation_penalty",
    "IEpisodicRecallHabituationStore",
    "InMemoryEpisodicRecallHabituationStore",
]
