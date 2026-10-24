from __future__ import annotations

import pytest

from ai_rpg_world.application.being._memory_payload_codecs import being_episode_to_dict
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import (
    InMemoryEpisodeRepository,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    EpisodeConflictException,
    EpisodeNotFoundException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ADA = BeingId("being_ada")
KAI = BeingId("being_kai")
INDEX = EpisodeIndex(summary="金庫の番号を探した", recall_when="金庫や鍵の話が出たとき")


def _episode(episode_id: str, *, taken_handles: set[str] | None = None, being_id: BeingId = ADA) -> Episode:
    return Episode.write(
        being_id=being_id,
        episode_id=episode_id,
        environment_name="地下の金庫室",
        written_turn=3,
        index=INDEX,
        body="棚の裏に紙が貼ってあった。",
        taken_handles=taken_handles or set(),
    )


FIRST_ID = "3f2a7b9c-1d2e-4f00-8a00-000000000001"
SECOND_ID = "aa11bb22-1d2e-4f00-8a00-000000000002"


def _first() -> Episode:
    return _episode(FIRST_ID)


def _second(being_id: BeingId = ADA) -> Episode:
    return _episode(SECOND_ID, being_id=being_id)


def _recalled(episode: Episode, *turns: int) -> Episode:
    for turn in turns:
        episode.recall(turn=turn)
    return episode


def _variant(episode: Episode, **changes: object) -> Episode:
    """同じ ID で中身の一部を変えた版。保存先が後の版でない書き戻しを断るかを見るため。"""
    fields: dict[str, object] = {
        "being_id": episode.being_id,
        "episode_id": episode.episode_id,
        "handle": episode.handle,
        "environment_name": episode.environment_name,
        "written_turn": episode.written_turn,
        "index": episode.index,
        "body": episode.body,
        "recall_count": episode.recall_count,
        "last_recalled_turn": episode.last_recalled_turn,
        "index_history": episode.index_history,
    }
    fields.update(changes)
    return Episode(**fields)  # type: ignore[arg-type]


def _shape(episode: Episode | None) -> tuple[object, ...] | None:
    """集約は中身で比べないので、試験では中身の欄を並べて比べる。"""
    if episode is None:
        return None
    return (
        episode.being_id,
        episode.episode_id,
        episode.handle,
        episode.environment_name,
        episode.written_turn,
        episode.index,
        episode.body,
        episode.recall_count,
        episode.last_recalled_turn,
        episode.index_history,
    )


def _shapes(episodes: tuple[Episode, ...]) -> list[tuple[object, ...] | None]:
    return [_shape(e) for e in episodes]


class TestInMemoryEpisodeRepository:
    """InMemoryEpisodeRepository が、Being ごとにエピソードを足した順に持ち、呼び名で引けることを保証する。"""

    def test_added_episode_is_found_by_its_handle(self) -> None:
        """足したエピソードは、その呼び名で引ける。"""
        repo = InMemoryEpisodeRepository()

        repo.add(_first())

        assert _shape(repo.find_by_handle(ADA, "ep_3f2a7b")) == _shape(_first())

    def test_unknown_handle_returns_none(self) -> None:
        """記録に無い呼び名で引くと None を返す。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_first())

        assert repo.find_by_handle(ADA, "ep_000000") is None

    def test_longer_handle_finds_only_the_episode_that_owns_it(self) -> None:
        """6 文字の呼び名が重なって 7 文字になったエピソードは 7 文字で引け、6 文字の呼び名は前からあるエピソードを指したままになる。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_first())
        taken = {e.handle for e in repo.list_by_being(ADA)}
        clash = _episode("3f2a7bcc-1d2e-4f00-8a00-000000000003", taken_handles=taken)

        repo.add(clash)

        assert _shape(repo.find_by_handle(ADA, "ep_3f2a7b")) == _shape(_first())
        assert _shape(repo.find_by_handle(ADA, "ep_3f2a7bc")) == _shape(clash)

    def test_episodes_are_kept_apart_per_being(self) -> None:
        """ある Being に足したエピソードは、別の Being の一覧にも呼び名にも出ない。"""
        repo = InMemoryEpisodeRepository()

        repo.add(_first())

        assert repo.list_by_being(KAI) == ()
        assert repo.find_by_handle(KAI, _first().handle) is None

    def test_list_returns_episodes_in_the_order_added(self) -> None:
        """一覧は足した順に返る。"""
        repo = InMemoryEpisodeRepository()

        repo.add(_second())
        repo.add(_first())

        assert _shapes(repo.list_by_being(ADA)) == [_shape(_second()), _shape(_first())]

    def test_adding_the_same_id_again_is_rejected(self) -> None:
        """同じ ID のエピソードをもう一度足すと EpisodeConflictException を投げ、記録は 1 件のままになる。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_first())

        with pytest.raises(EpisodeConflictException):
            repo.add(_recalled(_first(), 5))
        assert _shapes(repo.list_by_being(ADA)) == [_shape(_first())]

    def test_adding_a_taken_handle_is_rejected(self) -> None:
        """使われている呼び名のエピソードを足すと EpisodeConflictException を投げ、記録は増えない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_first())
        clash = _episode("3f2a7bcc-1d2e-4f00-8a00-000000000003")

        with pytest.raises(EpisodeConflictException):
            repo.add(clash)
        assert _shapes(repo.list_by_being(ADA)) == [_shape(_first())]

    def test_save_writes_back_in_the_same_position(self) -> None:
        """呼び出したエピソードを書き戻すと、同じ ID の記録が置き換わり、一覧の位置は変わらない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_first())
        repo.add(_second())
        recalled = _recalled(_first(), 8)

        repo.save(recalled)

        assert _shapes(repo.list_by_being(ADA)) == [_shape(recalled), _shape(_second())]
        assert _shape(repo.find_by_handle(ADA, _first().handle)) == _shape(recalled)

    def test_save_of_an_unknown_episode_is_rejected(self) -> None:
        """記録に無いエピソードを書き戻すと EpisodeNotFoundException を投げ、記録は増えない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_first())

        with pytest.raises(EpisodeNotFoundException):
            repo.save(_second())
        assert _shapes(repo.list_by_being(ADA)) == [_shape(_first())]

    def test_save_that_changes_the_handle_is_rejected(self) -> None:
        """同じ ID でも呼び名が変わったエピソードを書き戻すと EpisodeConflictException を投げ、記録は変わらない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_first())
        renamed = _episode(FIRST_ID, taken_handles={_first().handle})

        with pytest.raises(EpisodeConflictException):
            repo.save(renamed)
        assert _shapes(repo.list_by_being(ADA)) == [_shape(_first())]

    @pytest.mark.parametrize(
        "changes",
        [
            {"body": "書き換えた本文"},
            {"written_turn": 4},
            {"environment_name": "島"},
        ],
        ids=["body", "written_turn", "environment_name"],
    )
    def test_save_that_changes_what_was_written_is_rejected(self, changes: dict[str, object]) -> None:
        """本文・書いた時・環境の名前のどれかを変えた版を書き戻すと EpisodeConflictException を投げ、記録は変わらない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_first())

        with pytest.raises(EpisodeConflictException):
            repo.save(_variant(_first(), **changes))
        assert _shapes(repo.list_by_being(ADA)) == [_shape(_first())]

    def test_save_that_drops_index_history_is_rejected(self) -> None:
        """目次の履歴から前の版を消した版を書き戻すと EpisodeConflictException を投げ、履歴は残る。"""
        repo = InMemoryEpisodeRepository()
        revised = _first()
        revised.revise_index(EpisodeIndex(summary="番号を見つけた", recall_when="数字のとき"), turn=6)
        repo.add(revised)

        with pytest.raises(EpisodeConflictException):
            repo.save(_variant(revised, index=INDEX, index_history=()))
        assert _shapes(repo.list_by_being(ADA)) == [_shape(revised)]

    def test_save_that_lowers_recall_count_is_rejected(self) -> None:
        """呼び出された回数を減らした版を書き戻すと EpisodeConflictException を投げ、回数は変わらない。"""
        repo = InMemoryEpisodeRepository()
        recalled = _recalled(_first(), 5, 6)
        repo.add(recalled)

        with pytest.raises(EpisodeConflictException):
            repo.save(_recalled(_first(), 7))
        assert _shapes(repo.list_by_being(ADA)) == [_shape(recalled)]

    def test_save_that_replaces_index_without_history_is_rejected(self) -> None:
        """前の版を履歴に残さずに目次だけを替えた版を書き戻すと EpisodeConflictException を投げ、目次は変わらない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_first())

        with pytest.raises(EpisodeConflictException):
            repo.save(_variant(_first(), index=EpisodeIndex(summary="別の目次", recall_when="別の条件")))
        assert _shapes(repo.list_by_being(ADA)) == [_shape(_first())]

    def test_save_with_forged_previous_index_is_rejected(self) -> None:
        """履歴に足した前の版が、記録の目次と違う版を書き戻すと EpisodeConflictException を投げ、記録は変わらない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_first())
        forged = _variant(_first(), index=EpisodeIndex(summary="偽の前の版", recall_when="偽の条件"))
        forged.revise_index(EpisodeIndex(summary="新しい目次", recall_when="新しい条件"), turn=6)

        with pytest.raises(EpisodeConflictException):
            repo.save(forged)
        assert _shapes(repo.list_by_being(ADA)) == [_shape(_first())]

    def test_save_that_moves_last_recall_back_is_rejected(self) -> None:
        """回数は同じでも、最後に呼び出した時を前のターンに戻した版を書き戻すと EpisodeConflictException を投げる。"""
        repo = InMemoryEpisodeRepository()
        recalled = _recalled(_first(), 8)
        repo.add(recalled)

        with pytest.raises(EpisodeConflictException):
            repo.save(_recalled(_first(), 5))
        assert _shapes(repo.list_by_being(ADA)) == [_shape(recalled)]

    def test_replace_all_overwrites_the_being(self) -> None:
        """全部を書き戻すと、その Being の記録が渡した並びに置き換わり、前の記録は残らない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_first())

        repo.replace_all_by_being(ADA, [_second()])

        assert _shapes(repo.list_by_being(ADA)) == [_shape(_second())]
        assert repo.find_by_handle(ADA, _first().handle) is None

    def test_replace_all_with_nothing_empties_the_being(self) -> None:
        """空の並びで全部を書き戻すと、その Being の記録が無くなり、ほかの Being は変わらない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_first())
        repo.add(_second(KAI))

        repo.replace_all_by_being(ADA, [])

        assert repo.list_by_being(ADA) == ()
        assert _shapes(repo.list_by_being(KAI)) == [_shape(_second(KAI))]

    @pytest.mark.parametrize(
        "episodes",
        [
            [_first(), _recalled(_first(), 5)],
            [_first(), _episode("3f2a7bcc-1d2e-4f00-8a00-000000000003")],
        ],
        ids=["same_id", "same_handle"],
    )
    def test_replace_all_with_overlaps_is_rejected(self, episodes: list[Episode]) -> None:
        """ID か呼び名が重なる並びで全部を書き戻すと EpisodeConflictException を投げ、前の記録が残る。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_second())

        with pytest.raises(EpisodeConflictException):
            repo.replace_all_by_being(ADA, episodes)
        assert _shapes(repo.list_by_being(ADA)) == [_shape(_second())]


class TestTheRepositoryHandsOutCopies:
    """InMemoryEpisodeRepository が、出し入れのたびに写しを渡し、save し忘れた書き換えを保存したように見せないことを保証する。"""

    def test_recalling_a_found_episode_without_saving_leaves_the_store(self) -> None:
        """呼び名で引いたエピソードを呼び出しても、save しなければ、次に引いたエピソードは前のまま。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_first())

        found = repo.find_by_handle(ADA, "ep_3f2a7b")
        assert found is not None
        found.recall(turn=8)

        assert _shape(repo.find_by_handle(ADA, "ep_3f2a7b")) == _shape(_first())

    def test_revising_a_listed_episode_without_saving_leaves_the_store(self) -> None:
        """一覧で取ったエピソードの目次を直しても、save しなければ、記録は前のまま。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_first())

        (listed,) = repo.list_by_being(ADA)
        listed.revise_index(EpisodeIndex(summary="番号を見つけた", recall_when="数字のとき"), turn=6)

        assert _shapes(repo.list_by_being(ADA)) == [_shape(_first())]

    @pytest.mark.parametrize("how", ["add", "save", "replace_all"])
    def test_changing_an_episode_after_storing_leaves_the_store(self, how: str) -> None:
        """足した・書き戻した・全部を書き戻したあとで渡したエピソードを呼び出しても、記録は渡した時のまま。"""
        repo = InMemoryEpisodeRepository()
        episode = _first()
        if how == "add":
            repo.add(episode)
        elif how == "save":
            repo.add(_first())
            repo.save(episode)
        else:
            repo.replace_all_by_being(ADA, [episode])

        episode.recall(turn=8)

        assert _shapes(repo.list_by_being(ADA)) == [_shape(_first())]

    def test_recorded_events_are_not_stored(self) -> None:
        """呼び出してためたイベントは保存先に残らず、引いたエピソードはイベントを持たない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_first())

        repo.save(_recalled(_first(), 8))

        found = repo.find_by_handle(ADA, "ep_3f2a7b")
        assert found is not None and found.get_events() == []

    def test_every_field_comes_back_through_the_store(self) -> None:
        """呼び出しも目次の直しも済んだエピソードを足して引くと、snapshot に書く欄がすべて同じ値で戻る。

        写しを作る処理が欄を落とすと、保存先が静かに中身を失う。試験の _shape と写しの処理が一緒に古くなっても、snapshot の欄で気づける。
        """
        repo = InMemoryEpisodeRepository()
        episode = _recalled(_first(), 5, 8)
        episode.revise_index(EpisodeIndex(summary="番号を見つけた", recall_when="数字のとき"), turn=9)

        repo.add(episode)

        (stored,) = repo.list_by_being(ADA)
        assert being_episode_to_dict(stored) == being_episode_to_dict(episode)


class TestTheRepositoryFilesEpisodesByTheirOwner:
    """InMemoryEpisodeRepository が、エピソードが持つ BeingId で分けて持ち、別の Being のエピソードを混ぜないことを保証する。"""

    def test_an_episode_is_filed_under_its_own_being(self) -> None:
        """別の Being が書いたエピソードを足すと、その Being の一覧にだけ出る。"""
        repo = InMemoryEpisodeRepository()

        repo.add(_second(KAI))

        assert (repo.list_by_being(ADA), [e.being_id for e in repo.list_by_being(KAI)]) == ((), [KAI])

    def test_replace_all_with_an_episode_of_another_being_is_rejected(self) -> None:
        """全部を書き戻す並びに別の Being のエピソードが混ざっていると EpisodeConflictException を投げ、前の記録が残る。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_first())

        with pytest.raises(EpisodeConflictException):
            repo.replace_all_by_being(ADA, [_second(KAI)])
        assert _shapes(repo.list_by_being(ADA)) == [_shape(_first())]

    def test_save_does_not_reach_an_episode_of_another_being(self) -> None:
        """同じ ID でも別の Being のエピソードとして書き戻すと、その Being には記録が無いので EpisodeNotFoundException を投げる。"""
        repo = InMemoryEpisodeRepository()
        repo.add(_first())

        with pytest.raises(EpisodeNotFoundException):
            repo.save(_episode(FIRST_ID, being_id=KAI))
        assert _shapes(repo.list_by_being(ADA)) == [_shape(_first())]
