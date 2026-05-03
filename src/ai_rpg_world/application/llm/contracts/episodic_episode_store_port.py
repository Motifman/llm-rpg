"""MVP エピソード記憶の保存ポート（旧 SubjectiveEpisode store 契約とは別名・別 API）。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.application.llm.contracts.episodic_memory import EpisodicCue, SubjectiveEpisode


class IEpisodicEpisodeStore(ABC):
    """
    SubjectiveEpisode をプレイヤー単位で保持する最小ストア。
    永続化は含まない（in-memory 実装を想定）。
    """

    @abstractmethod
    def put(self, episode: SubjectiveEpisode) -> None:
        """エピソードを保存する。同一 (player_id, episode_id) は上書き（upsert）。"""

    @abstractmethod
    def get(self, player_id: int, episode_id: str) -> SubjectiveEpisode | None:
        """指定プレイヤーの episode_id を返す。無ければ None。"""

    @abstractmethod
    def list_recent(self, player_id: int, limit: int) -> list[SubjectiveEpisode]:
        """
        occurred_at の新しい順で最大 limit 件を返す。
        同一タイムスタンプでは episode_id の降順で安定化する。
        limit が 0 以下のときは空リスト。
        """

    @abstractmethod
    def list_by_cue(self, player_id: int, cue: EpisodicCue, limit: int) -> list[SubjectiveEpisode]:
        """
        cue.to_canonical() に一致する cue を少なくとも 1 つ含むエピソードを返す。
        並びは list_recent と同じ（occurred_at 降順、同一時刻は episode_id 降順）。
        limit が 0 以下のときは空リスト。
        """
