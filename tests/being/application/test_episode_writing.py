from __future__ import annotations

from collections.abc import Iterator

from ai_rpg_world.being.application.episode_writing import AddEpisodesToMemory
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.domain.episode_writer import EpisodeContent, EpisodeContents
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import (
    InMemoryEpisodeRepository,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ADA = BeingId("being_ada")


def _ids() -> Iterator[str]:
    n = 0
    while True:
        n += 1
        yield f"3f2a7b9c-1d2e-4f00-8a00-{n:012d}"


def _content(about: str = "金庫を開けた", *, truncated: dict[str, int] | None = None) -> EpisodeContent:
    return EpisodeContent(
        index=EpisodeIndex(summary=about, recall_when="金庫の話が出たとき"),
        body="紙の番号で金庫が開いた。",
        truncated=truncated or {},
    )


def _add_episodes(
    repository: InMemoryEpisodeRepository | None = None,
) -> tuple[AddEpisodesToMemory, InMemoryEpisodeRepository]:
    repository = repository if repository is not None else InMemoryEpisodeRepository()
    ids = _ids()
    return AddEpisodesToMemory(repository, new_episode_id=lambda: next(ids)), repository


def _add(
    add_episodes: AddEpisodesToMemory,
    *contents: EpisodeContent,
    dropped_count: int = 0,
    environment_name: str = "地下の金庫室",
    written_turn: int = 12,
):
    return add_episodes.add(
        EpisodeContents(contents=contents, dropped_count=dropped_count),
        being_id=ADA,
        environment_name=environment_name,
        written_turn=written_turn,
    )


class TestAddEpisodesToMemory:
    """AddEpisodesToMemory が中身に ID と呼び名を付け、エピソードとして記憶に加えることを保証する。"""

    def test_each_content_becomes_an_episode_in_order(self) -> None:
        """中身の順に、目次と本文を持つエピソードとして記憶に加え、加えたエピソードを結果に返す。"""
        add_episodes, repository = _add_episodes()

        result = _add(add_episodes, _content("棚の紙"), _content("金庫が開いた"))

        saved = repository.list_by_being(ADA)
        assert [e.index.summary for e in saved] == ["棚の紙", "金庫が開いた"]
        assert [w.episode.episode_id for w in result.written] == [e.episode_id for e in saved]
        assert saved[0].body == "紙の番号で金庫が開いた。"

    def test_episode_keeps_environment_name_and_written_turn(self) -> None:
        """エピソードは、渡された環境の名前と書いた時 (Being の記憶のターン数) を持つ。"""
        add_episodes, repository = _add_episodes()

        _add(add_episodes, _content(), environment_name="港町", written_turn=40)

        (episode,) = repository.list_by_being(ADA)
        assert (episode.environment_name, episode.written_turn) == ("港町", 40)

    def test_no_content_adds_nothing(self) -> None:
        """中身が無ければ、何も加えない。"""
        add_episodes, repository = _add_episodes()

        result = _add(add_episodes)

        assert (result.written, repository.list_by_being(ADA)) == ((), ())

    def test_handles_already_used_by_the_being_are_avoided(self) -> None:
        """その Being がもう使っている呼び名と重なる ID なら、新しい側の呼び名を伸ばす。"""
        repository = InMemoryEpisodeRepository()
        existing = Episode.write(
            being_id=ADA,
            episode_id="3f2a7b9c-0000-4f00-8a00-000000000099",
            environment_name="港町",
            written_turn=1,
            index=EpisodeIndex(summary="前の記憶", recall_when="前の話のとき"),
            body="前のこと。",
        )
        repository.add(existing)
        add_episodes, _ = _add_episodes(repository)

        result = _add(add_episodes, _content(), _content())

        assert existing.handle == "ep_3f2a7b"
        assert [w.episode.handle for w in result.written] == ["ep_3f2a7b9", "ep_3f2a7b9c"]

    def test_truncation_and_dropped_count_are_carried_to_the_result(self) -> None:
        """中身の切り詰めた項目と、捨てた中身の数を結果に残す。"""
        add_episodes, _ = _add_episodes()

        result = _add(add_episodes, _content(truncated={"body": 405}), dropped_count=2)

        assert (result.written[0].truncated, result.dropped_count) == ({"body": 405}, 2)
