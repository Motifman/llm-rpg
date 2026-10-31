from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import (
    Episode,
    EpisodeIndex,
    EpisodeIndexRevised,
    EpisodeRecalled,
    EpisodeWrittenEvent,
    IndexRevision,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    EpisodeValidationException,
)

ADA = BeingId("being_ada")

EPISODE_ID = "3f2a7b9c-1d2e-4f00-8a00-000000000001"
INDEX = EpisodeIndex(summary="金庫の番号を探した", recall_when="金庫や鍵の話が出たとき")


def _write(**overrides: object) -> Episode:
    fields: dict[str, object] = {
        "being_id": ADA,
        "episode_id": EPISODE_ID,
        "environment_name": "地下の金庫室",
        "written_turn": 5,
        "index": INDEX,
        "body": "棚の裏に紙が貼ってあり、番号の半分だけが読めた。",
    }
    fields.update(overrides)
    return Episode.write(**fields)  # type: ignore[arg-type]


class TestEpisodeIndex:
    """EpisodeIndex が「どんな記憶か」と「どんな時に思い出すか」を、空でなく 40 字までの文で持つことを保証する。"""

    @pytest.mark.parametrize("field", ["summary", "recall_when"])
    def test_forty_characters_are_accepted(self, field: str) -> None:
        """目次のどちらの文も、ちょうど 40 字なら受け付ける。"""
        values = {"summary": "金庫", "recall_when": "鍵の話"}
        values[field] = "あ" * 40

        index = EpisodeIndex(**values)

        assert getattr(index, field) == "あ" * 40

    @pytest.mark.parametrize("field", ["summary", "recall_when"])
    def test_forty_one_characters_are_rejected(self, field: str) -> None:
        """目次のどちらの文も、41 字あると EpisodeValidationException を投げる。"""
        values = {"summary": "金庫", "recall_when": "鍵の話"}
        values[field] = "あ" * 41

        with pytest.raises(EpisodeValidationException):
            EpisodeIndex(**values)

    @pytest.mark.parametrize("field", ["summary", "recall_when"])
    @pytest.mark.parametrize("blank", ["", "   ", "\n"])
    def test_blank_text_is_rejected(self, field: str, blank: str) -> None:
        """目次のどちらの文も、空や空白だけなら EpisodeValidationException を投げる。"""
        values = {"summary": "金庫", "recall_when": "鍵の話"}
        values[field] = blank

        with pytest.raises(EpisodeValidationException):
            EpisodeIndex(**values)


class TestWritingAnEpisode:
    """Episode.write が、目次と本文を受け取り、ID から呼び名を作り、まだ呼び出されていないエピソードを返すことを保証する。"""

    def test_written_episode_records_episode_written(self) -> None:
        """書いたエピソードは、Being・ID・呼び名・環境・書いたターン・目次・本文を持つ EpisodeWrittenEvent を 1 件ためる。"""
        episode = _write()

        (event,) = episode.get_events()
        assert isinstance(event, EpisodeWrittenEvent)
        assert (
            event.being_id,
            event.episode_id,
            event.handle,
            event.environment_name,
            event.written_turn,
            event.index,
            event.body,
        ) == (ADA, EPISODE_ID, "ep_3f2a7b", "地下の金庫室", 5, INDEX, episode.body)

    def test_written_episode_event_carries_the_truncation(self) -> None:
        """書くときに渡した切り詰めた項目と元の長さを、EpisodeWrittenEvent が持つ。渡さなければ空。エピソード自体は持たない。"""
        truncated = Episode.write(
            being_id=ADA,
            episode_id=EPISODE_ID,
            environment_name="地下の金庫室",
            written_turn=5,
            index=INDEX,
            body="紙。",
            truncated={"about": 52},
        )

        (event,) = truncated.get_events()
        (plain,) = _write().get_events()
        assert (event.truncated, plain.truncated) == ({"about": 52}, {})

    def test_written_episode_has_handle_from_id_and_no_recall_yet(self) -> None:
        """作ったエピソードは、呼び名が ep_ と ID の先頭 6 文字で、呼び出された回数 0、最後に呼び出した時なし、目次の履歴が空になる。"""
        episode = _write()

        assert episode.handle == "ep_3f2a7b"
        assert episode.environment_name == "地下の金庫室"
        assert episode.written_turn == 5
        assert episode.index == INDEX
        assert episode.body == "棚の裏に紙が貼ってあり、番号の半分だけが読めた。"
        assert (episode.recall_count, episode.last_recalled_turn, episode.index_history) == (0, None, ())

    def test_handle_grows_by_one_character_when_it_is_taken(self) -> None:
        """同じ Being の中で 6 文字の呼び名がもう使われていれば、ID の先頭 7 文字の呼び名になる。"""
        episode = _write(taken_handles={"ep_3f2a7b"})

        assert episode.handle == "ep_3f2a7b9"

    def test_handle_keeps_growing_past_the_hyphen_until_it_is_free(self) -> None:
        """呼び名は ID の区切りの - を飛ばして伸び、使われていない長さになるまで伸びる。"""
        episode = _write(taken_handles={"ep_3f2a7b", "ep_3f2a7b9", "ep_3f2a7b9c"})

        assert episode.handle == "ep_3f2a7b9c1"

    def test_handle_ignores_taken_handles_of_other_prefixes(self) -> None:
        """使われている呼び名が別の ID の先頭なら、6 文字のままになる。"""
        episode = _write(taken_handles={"ep_000000", "ep_3f2a7c"})

        assert episode.handle == "ep_3f2a7b"

    def test_id_that_is_not_a_uuid_is_rejected(self) -> None:
        """ID が UUID の文字列でなければ EpisodeValidationException を投げる。"""
        with pytest.raises(EpisodeValidationException):
            _write(episode_id="ep-1")

    def test_uppercase_uuid_is_rejected(self) -> None:
        """ID が大文字の UUID なら、呼び名の文字が揺れないよう EpisodeValidationException を投げる。"""
        with pytest.raises(EpisodeValidationException):
            _write(episode_id=EPISODE_ID.upper())

    @pytest.mark.parametrize("blank", ["", "  "])
    def test_blank_environment_name_is_rejected(self, blank: str) -> None:
        """環境の名前が空や空白だけなら EpisodeValidationException を投げる。"""
        with pytest.raises(EpisodeValidationException):
            _write(environment_name=blank)

    def test_negative_written_turn_is_rejected(self) -> None:
        """書いた時が負のターンなら EpisodeValidationException を投げる。"""
        with pytest.raises(EpisodeValidationException):
            _write(written_turn=-1)

    def test_body_of_four_hundred_characters_is_accepted(self) -> None:
        """本文はちょうど 400 字なら受け付ける。"""
        episode = _write(body="あ" * 400)

        assert len(episode.body) == 400

    def test_body_of_four_hundred_one_characters_is_rejected(self) -> None:
        """本文が 401 字あると EpisodeValidationException を投げる。"""
        with pytest.raises(EpisodeValidationException):
            _write(body="あ" * 401)

    @pytest.mark.parametrize("blank", ["", " \n "])
    def test_blank_body_is_rejected(self, blank: str) -> None:
        """本文が空や空白だけなら EpisodeValidationException を投げる。"""
        with pytest.raises(EpisodeValidationException):
            _write(body=blank)


class TestEpisodeInvariants:
    """直接組み立てた Episode (記憶の持ち越しから戻すとき) でも、呼び名・回数・履歴の決まりが崩れないことを保証する。"""

    def _fields(self, **overrides: object) -> dict[str, object]:
        episode = _write()
        fields: dict[str, object] = {
            "being_id": episode.being_id,
            "episode_id": episode.episode_id,
            "handle": episode.handle,
            "environment_name": episode.environment_name,
            "written_turn": episode.written_turn,
            "index": episode.index,
            "body": episode.body,
        }
        fields.update(overrides)
        return fields

    def test_episode_holds_its_owner(self) -> None:
        """エピソードは、書いた Being の ID を持つ。"""
        assert _write().being_id == ADA

    def test_an_owner_that_is_not_a_being_id_is_rejected(self) -> None:
        """BeingId でない持ち主を渡すと EpisodeValidationException を投げる。"""
        with pytest.raises(EpisodeValidationException):
            _write(being_id="being_ada")

    @pytest.mark.parametrize("handle", ["ep_3f2a7", "ep_3f2a7c", "3f2a7b", "ep_3f2a7b9c-"])
    def test_handle_that_does_not_come_from_the_id_is_rejected(self, handle: str) -> None:
        """呼び名が ep_ と ID の先頭 6 文字以上でなければ EpisodeValidationException を投げる。"""
        with pytest.raises(EpisodeValidationException):
            Episode(**self._fields(handle=handle))  # type: ignore[arg-type]

    def test_recalled_turn_without_recall_count_is_rejected(self) -> None:
        """呼び出された回数が 0 なのに最後に呼び出した時があると EpisodeValidationException を投げる。"""
        with pytest.raises(EpisodeValidationException):
            Episode(**self._fields(recall_count=0, last_recalled_turn=6))  # type: ignore[arg-type]

    def test_recall_count_without_recalled_turn_is_rejected(self) -> None:
        """呼び出された回数が 1 以上なのに最後に呼び出した時が無いと EpisodeValidationException を投げる。"""
        with pytest.raises(EpisodeValidationException):
            Episode(**self._fields(recall_count=1, last_recalled_turn=None))  # type: ignore[arg-type]

    def test_recalled_before_written_is_rejected(self) -> None:
        """最後に呼び出した時が書いた時より前なら EpisodeValidationException を投げる。"""
        with pytest.raises(EpisodeValidationException):
            Episode(**self._fields(recall_count=1, last_recalled_turn=4))  # type: ignore[arg-type]

    def test_revision_before_written_is_rejected(self) -> None:
        """目次を直した時が書いた時より前の履歴があると EpisodeValidationException を投げる。"""
        history = (IndexRevision(previous=INDEX, revised_turn=4),)

        with pytest.raises(EpisodeValidationException):
            Episode(**self._fields(index_history=history))  # type: ignore[arg-type]

    def test_revisions_out_of_order_are_rejected(self) -> None:
        """目次の履歴で、直した時が前の版より戻っていると EpisodeValidationException を投げる。"""
        history = (
            IndexRevision(previous=INDEX, revised_turn=8),
            IndexRevision(previous=INDEX, revised_turn=7),
        )

        with pytest.raises(EpisodeValidationException):
            Episode(**self._fields(index_history=history))  # type: ignore[arg-type]

    def test_body_cannot_be_reassigned(self) -> None:
        """作ったエピソードの本文に代入しようとすると AttributeError になり、本文は変わらない。本文を変える操作は無い。"""
        episode = _write()

        with pytest.raises(AttributeError):
            episode.body = "書き換えた本文"  # type: ignore[misc]
        assert episode.body == "棚の裏に紙が貼ってあり、番号の半分だけが読めた。"


class TestRecallingAnEpisode:
    """Episode.recall が、そのエピソードの中身を書き換えて、呼び出された回数を 1 増やし、最後に呼び出した時を記録することを保証する。"""

    def test_first_recall_counts_one_and_records_the_turn(self) -> None:
        """初めて呼び出すと、回数が 1 になり、最後に呼び出した時がそのターンになり、recall は何も返さない。"""
        episode = _write()

        returned = episode.recall(turn=9)

        assert returned is None
        assert (episode.recall_count, episode.last_recalled_turn) == (1, 9)

    def test_second_recall_counts_two_and_moves_the_turn(self) -> None:
        """もう一度呼び出すと、回数が 2 になり、最後に呼び出した時が新しいターンに進む。"""
        episode = _write()
        episode.recall(turn=9)

        episode.recall(turn=12)

        assert (episode.recall_count, episode.last_recalled_turn) == (2, 12)

    def test_recall_in_the_same_turn_counts_again(self) -> None:
        """同じターンに 2 回呼び出すと、回数は 2 になり、最後に呼び出した時はそのターンのままになる。"""
        episode = _write()
        episode.recall(turn=9)

        episode.recall(turn=9)

        assert (episode.recall_count, episode.last_recalled_turn) == (2, 9)

    def test_recall_does_not_change_body_or_index(self) -> None:
        """呼び出しても、本文・目次・呼び名・ID は変わらない。"""
        episode = _write()
        before = (episode.episode_id, episode.handle, episode.index, episode.body)

        episode.recall(turn=9)

        assert (episode.episode_id, episode.handle, episode.index, episode.body) == before

    def test_recall_records_episode_recalled(self) -> None:
        """呼び出すと、ID・呼び名・ターン・呼び出したあとの回数を持つ EpisodeRecalled が 1 件たまる。"""
        episode = _write()
        episode.clear_events()

        episode.recall(turn=9)

        (event,) = episode.get_events()
        assert isinstance(event, EpisodeRecalled)
        assert (event.being_id, event.episode_id, event.handle, event.turn, event.recall_count) == (
            ADA,
            EPISODE_ID,
            "ep_3f2a7b",
            9,
            1,
        )

    @pytest.mark.parametrize("turn", [8, 4, -1])
    def test_recall_that_goes_back_in_time_changes_nothing(self, turn: int) -> None:
        """最後に呼び出した時や書いた時より前、または負のターンで呼び出すと EpisodeValidationException を投げ、回数もイベントも変えない。"""
        episode = _write()
        episode.recall(turn=9)
        episode.clear_events()

        with pytest.raises(EpisodeValidationException):
            episode.recall(turn=turn)

        assert (episode.recall_count, episode.last_recalled_turn, episode.get_events()) == (1, 9, [])


class TestRevisingTheIndex:
    """Episode.revise_index が、そのエピソードの目次を新しい版に替え、前の版を直した時と一緒に履歴に残すことを保証する。"""

    NEW_INDEX = EpisodeIndex(summary="番号の半分を見つけた", recall_when="数字の並びを考えるとき")

    def test_revision_replaces_index_and_keeps_previous_one(self) -> None:
        """目次を直すと、目次が新しい版になり、履歴に前の版と直した時が 1 件残り、revise_index は何も返さない。"""
        episode = _write()

        returned = episode.revise_index(self.NEW_INDEX, turn=10)

        assert returned is None
        assert episode.index == self.NEW_INDEX
        assert episode.index_history == (IndexRevision(previous=INDEX, revised_turn=10),)

    def test_two_revisions_keep_both_previous_versions_in_order(self) -> None:
        """2 回直すと、履歴に最初の版と 2 番目の版が直した順に残る。"""
        third = EpisodeIndex(summary="番号は棚にあった", recall_when="棚を調べるとき")
        episode = _write()
        episode.revise_index(self.NEW_INDEX, turn=10)

        episode.revise_index(third, turn=14)

        assert episode.index == third
        assert episode.index_history == (
            IndexRevision(previous=INDEX, revised_turn=10),
            IndexRevision(previous=self.NEW_INDEX, revised_turn=14),
        )

    def test_revision_does_not_change_body_handle_or_recalls(self) -> None:
        """目次を直しても、本文・呼び名・ID・呼び出された回数は変わらない。"""
        episode = _write()
        episode.recall(turn=7)

        episode.revise_index(self.NEW_INDEX, turn=10)

        assert (episode.episode_id, episode.handle, episode.body, episode.recall_count, episode.last_recalled_turn) == (
            EPISODE_ID,
            "ep_3f2a7b",
            "棚の裏に紙が貼ってあり、番号の半分だけが読めた。",
            1,
            7,
        )

    def test_revision_records_episode_index_revised(self) -> None:
        """目次を直すと、前の版と新しい版とターンを持つ EpisodeIndexRevised が 1 件たまる。"""
        episode = _write()
        episode.clear_events()

        episode.revise_index(self.NEW_INDEX, turn=10)

        (event,) = episode.get_events()
        assert isinstance(event, EpisodeIndexRevised)
        assert (event.being_id, event.episode_id, event.handle, event.previous, event.index, event.turn) == (
            ADA,
            EPISODE_ID,
            "ep_3f2a7b",
            INDEX,
            self.NEW_INDEX,
            10,
        )

    @pytest.mark.parametrize(
        "index,turn",
        [(INDEX, 9), (INDEX, 4), (INDEX, -1), ("番号の半分", 12)],
        ids=["before_the_last_revision", "before_written", "negative_turn", "not_an_index"],
    )
    def test_a_rejected_revision_changes_nothing(self, index: object, turn: int) -> None:
        """前に直した時より前のターンや、目次でない値で直すと EpisodeValidationException を投げ、目次も履歴もイベントも変えない。"""
        episode = _write()
        episode.revise_index(self.NEW_INDEX, turn=10)
        episode.clear_events()

        with pytest.raises(EpisodeValidationException):
            episode.revise_index(index, turn=turn)  # type: ignore[arg-type]

        assert (episode.index, len(episode.index_history), episode.get_events()) == (self.NEW_INDEX, 1, [])


class TestFollows:
    """Episode.follows が、同じ持ち主の、呼び出しと目次の直しだけで行き着ける版だけを後の版と認めることを保証する。"""

    def test_a_recalled_copy_follows_the_original(self) -> None:
        """同じ持ち主のエピソードを呼び出した版は、元の版の後の版になる。"""
        later = _write()
        later.recall(turn=9)

        assert later.follows(_write()) is True

    def test_the_same_episode_of_another_being_does_not_follow(self) -> None:
        """ID も中身も同じでも、持ち主が違うエピソードは後の版ではない。"""
        assert _write(being_id=BeingId("being_kai")).follows(_write()) is False
