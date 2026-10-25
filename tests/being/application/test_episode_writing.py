from __future__ import annotations

from collections.abc import Iterator

from ai_rpg_world.being.application.episode_writing import EpisodeKeeper
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.domain.episode_writer import EpisodeDraft, EpisodeDrafts
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


def _draft(about: str = "金庫を開けた", *, truncated: dict[str, int] | None = None) -> EpisodeDraft:
    return EpisodeDraft(index=EpisodeIndex(summary=about, recall_when="金庫の話が出たとき"), body="紙の番号で金庫が開いた。", truncated=truncated or {})


def _keeper(repository: InMemoryEpisodeRepository | None = None) -> tuple[EpisodeKeeper, InMemoryEpisodeRepository]:
    repository = repository if repository is not None else InMemoryEpisodeRepository()
    ids = _ids()
    return EpisodeKeeper(repository, new_episode_id=lambda: next(ids)), repository


def _keep(keeper: EpisodeKeeper, *drafts: EpisodeDraft, dropped_count: int = 0, environment_name: str = "地下の金庫室", written_turn: int = 12):
    return keeper.keep(EpisodeDrafts(drafts=drafts, dropped_count=dropped_count), being_id=ADA, environment_name=environment_name, written_turn=written_turn)


class TestEpisodeKeeper:
    """EpisodeKeeper が下書きに ID と呼び名を付け、Being の記録に足すことを保証する。"""

    def test_each_draft_becomes_an_episode_in_order(self) -> None:
        """下書きの順に、目次と本文を持つエピソードとして保存し、保存したエピソードを結果に返す。"""
        keeper, repository = _keeper()

        result = _keep(keeper, _draft("棚の紙"), _draft("金庫が開いた"))

        saved = repository.list_by_being(ADA)
        assert [e.index.summary for e in saved] == ["棚の紙", "金庫が開いた"]
        assert [w.episode.episode_id for w in result.written] == [e.episode_id for e in saved]
        assert saved[0].body == "紙の番号で金庫が開いた。"

    def test_episode_keeps_environment_name_and_written_turn(self) -> None:
        """エピソードは、渡された環境の名前と書いた時 (Being の記憶のターン数) を持つ。"""
        keeper, repository = _keeper()

        _keep(keeper, _draft(), environment_name="港町", written_turn=40)

        (episode,) = repository.list_by_being(ADA)
        assert (episode.environment_name, episode.written_turn) == ("港町", 40)

    def test_no_draft_saves_nothing(self) -> None:
        """下書きが無ければ、何も保存しない。"""
        keeper, repository = _keeper()

        result = _keep(keeper)

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
        keeper, _ = _keeper(repository)

        result = _keep(keeper, _draft(), _draft())

        assert existing.handle == "ep_3f2a7b"
        assert [w.episode.handle for w in result.written] == ["ep_3f2a7b9", "ep_3f2a7b9c"]

    def test_truncation_and_dropped_count_are_carried_to_the_result(self) -> None:
        """下書きの切り詰めた項目と、捨てた下書きの数を結果に残す。"""
        keeper, _ = _keeper()

        result = _keep(keeper, _draft(truncated={"body": 405}), dropped_count=2)

        assert (result.written[0].truncated, result.dropped_count) == ({"body": 405}, 2)
