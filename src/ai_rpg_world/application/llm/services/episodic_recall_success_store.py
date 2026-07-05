"""U9b (予測誤差統一設計 部品5・想起の信用割り当て): 的中側の sidecar store。

「この記憶を思い出して立てた予測が当たった」回数を episode 単位で数える。
的中回数が多い episode ほど「思い出す価値が高いと確認された記憶」として
recall ranking で boost される (``episodic_passive_recall_retrieval.py``)。

設計判断 (``episodic_recall_habituation_store.py`` と対称):
- ``episode`` 本体 (``SubjectiveEpisode``) は触らない。事実 (episode) と
  評価 (的中回数) は別寿命で管理し、再解釈経路を壊さない
- in-memory のみ。慣化 sidecar と同じ理由 (permanent な being snapshot を
  汚さず、experiment run の単位でリセットされる)。SQLite 実装は
  慣化 sidecar にも存在しない (= 型紙どおり)
- protocol で外部置換可能にしておく (将来 redis / sqlite に差し替え)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Dict, Protocol, runtime_checkable

from ai_rpg_world.domain.being.value_object.being_id import BeingId


@runtime_checkable
class IEpisodicRecallSuccessStore(Protocol):
    """「思い出して立てた予測が当たった」回数を episode 単位で記憶する sidecar store。

    実装は being ごとに隔離されること (二人プレイでの干渉を防ぐ)。
    """

    def get_hit_count_by_being(self, being_id: BeingId, episode_id: str) -> int:
        """指定 episode の的中回数を返す。未記録なら ``0``。"""
        ...

    def record_hit_by_being(self, being_id: BeingId, episode_id: str) -> None:
        """指定 episode の的中回数を 1 加算する。"""
        ...

    def list_all_by_being(self, being_id: BeingId) -> Mapping[str, int]:
        """snapshot capture 用に「episode_id → hit_count」の全エントリを返す。

        未記録なら空 dict。"""
        ...

    def replace_all_by_being(
        self,
        being_id: BeingId,
        mapping: Mapping[str, int],
    ) -> None:
        """snapshot 復元用の bulk overwrite。"""
        ...


class InMemoryEpisodicRecallSuccessStore(IEpisodicRecallSuccessStore):
    """プロセスメモリ常駐の sidecar 実装。experiment run の単位で破棄される。

    being 内部は ``dict[episode_id → hit_count]`` で持つ。being 同士は
    外側の dict で分離 (相互干渉なし)。
    """

    def __init__(self) -> None:
        self._by_being: Dict[BeingId, Dict[str, int]] = {}

    def get_hit_count_by_being(self, being_id: BeingId, episode_id: str) -> int:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        inner = self._by_being.get(being_id)
        if inner is None:
            return 0
        return inner.get(episode_id, 0)

    def record_hit_by_being(self, being_id: BeingId, episode_id: str) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(episode_id, str) or not episode_id.strip():
            raise ValueError("episode_id must be a non-empty str")
        inner = self._by_being.setdefault(being_id, {})
        inner[episode_id] = inner.get(episode_id, 0) + 1

    def list_all_by_being(self, being_id: BeingId) -> Mapping[str, int]:
        """copy で返す (= 呼出側変更で内部 state を壊さない)。"""
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        return dict(self._by_being.get(being_id, {}))

    def replace_all_by_being(
        self,
        being_id: BeingId,
        mapping: Mapping[str, int],
    ) -> None:
        """中身が空なら being_id の state を完全に削除する (= capture 時の

        空状態と bit identity を保つ)。"""
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if mapping:
            self._by_being[being_id] = {
                str(k): int(v) for k, v in mapping.items()
            }
        else:
            self._by_being.pop(being_id, None)


__all__ = [
    "IEpisodicRecallSuccessStore",
    "InMemoryEpisodicRecallSuccessStore",
]
