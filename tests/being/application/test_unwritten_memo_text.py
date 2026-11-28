from __future__ import annotations

import pytest

from ai_rpg_world.being.application.memo_arguments import (
    REJECTED_FROM_NOT_NEEDED,
    REJECTED_INVALID,
    REJECTED_LIMIT_REACHED,
    REJECTED_MISSING_EPISODE_FROM,
    REJECTED_MISSING_FROM,
    REJECTED_MISSING_ID,
    REJECTED_MISSING_PROVENANCE,
    REJECTED_MISSING_TEXT,
    REJECTED_NO_SUCH_MEMO,
    REJECTED_NOT_A_LIST,
    REJECTED_NOT_AN_OBJECT,
    REJECTED_PROVENANCE_OUTSIDE_FACT,
    REJECTED_TEXT_TOO_LONG,
    REJECTED_UNKNOWN_DO,
    REJECTED_UNKNOWN_EPISODE,
    REJECTED_UNKNOWN_KIND,
)
from ai_rpg_world.being.application.unwritten_memo_text import (
    WHOLE_MEMO,
    attempted_raw_operation,
    short_reason,
    unwritten_memo_line,
    unwritten_memo_lines,
)
from ai_rpg_world.being.application.write_memos import UnwrittenMemo
from ai_rpg_world.being.domain.memo_book import MemoKind


class TestUnwrittenMemoLine:
    """unwritten_memo_line が、何をしようとして、なぜ書けなかったかを 1 文にすることを保証する。"""

    def test_attempt_and_reason_are_in_one_sentence(self) -> None:
        """「{しようとしたこと}」は書けなかった（理由: {理由}）の形で、理由の括弧は全角になる。"""
        assert unwritten_memo_line("m_3f2a7b を消す", "そのメモはない") == (
            "「m_3f2a7b を消す」は書けなかった（理由: そのメモはない）"
        )


class TestAttemptedRawOperation:
    """attempted_raw_operation が、読めなかった操作を、書かれていた中身からできるだけ言うことを保証する。"""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ({"do": "add", "kind": "todo", "text": "鍵を取る"}, "やることに「鍵を取る」を書く"),
            ({"do": "add", "kind": "fact", "text": " 鍵を取る "}, "分かったことに「鍵を取る」を書く"),
            ({"do": "add", "kind": "person", "text": "鍵を取る"}, "人についてのメモに「鍵を取る」を書く"),
            ({"do": "add", "kind": "wish", "text": "鍵を取る"}, "「鍵を取る」を書く"),
            ({"do": "add"}, "メモを足す"),
            ({"do": "edit", "id": "m_1", "text": "開いた"}, "m_1 を「開いた」に書き換える"),
            ({"do": "edit", "id": "m_1"}, "m_1 を書き換える"),
            ({"do": "edit"}, "メモを書き換える"),
            ({"do": "remove", "id": "m_1"}, "m_1 を消す"),
            ({"do": "remove"}, "メモを消す"),
            ({"do": "fly"}, '{"do": "fly"}'),
            ("鍵を取る", '"鍵を取る"'),
        ],
    )
    def test_what_can_be_read_is_said(self, raw: object, expected: str) -> None:
        """do・kind・text・id のうち読めたものから言い、do が分からなければ書かれたものをそのまま JSON で示す。"""
        assert attempted_raw_operation(raw) == expected

    def test_whole_memo_is_called_the_memo_writing(self) -> None:
        """引数ごと崩れていたときは、メモの書き込み全体を指す。"""
        assert WHOLE_MEMO == "メモの書き込み"


class TestShortReason:
    """short_reason が、外した理由ごとに、操作と重ならない短い理由を返すことを保証する。"""

    @pytest.mark.parametrize(
        ("reason", "expected"),
        [
            (REJECTED_NOT_A_LIST, "memo は操作の配列で書く"),
            (REJECTED_NOT_AN_OBJECT, '操作は {"do": ...} の形で書く'),
            (REJECTED_UNKNOWN_DO, "do は add / edit / remove のどれか"),
            (REJECTED_UNKNOWN_KIND, "kind は todo / fact / person のどれか"),
            (REJECTED_MISSING_TEXT, "text が空"),
            (REJECTED_TEXT_TOO_LONG, "text は 60 字まで"),
            (REJECTED_MISSING_ID, "id に m_ で始まる呼び名がない"),
            (REJECTED_MISSING_PROVENANCE, "分かったことには source と certainty が要る"),
            (REJECTED_MISSING_FROM, "人から聞いたことには from に誰から聞いたかが要る"),
            (REJECTED_MISSING_EPISODE_FROM, "エピソードから分かったことには from にエピソードの呼び名が要る"),
            (REJECTED_FROM_NOT_NEEDED, "自分で確かめたことには from を書かない"),
            (REJECTED_PROVENANCE_OUTSIDE_FACT, "source と certainty は分かったことにだけ書ける"),
            (REJECTED_NO_SUCH_MEMO, "そのメモはない"),
            (REJECTED_UNKNOWN_EPISODE, "そのエピソードはない"),
            (REJECTED_INVALID, "書けない形だった"),
        ],
    )
    def test_each_reason_has_a_short_text(self, reason: str, expected: str) -> None:
        """理由ごとに決まった短い文を返す。"""
        assert short_reason(reason) == expected

    def test_limit_names_the_kind_and_its_limit(self) -> None:
        """上限に達したときは、分類と件数の上限を言う。"""
        assert short_reason(REJECTED_LIMIT_REACHED, kind=MemoKind.TODO) == "やることが上限の 5 件。消すか書き換える"

    def test_unknown_reason_falls_back_to_the_invalid_text(self) -> None:
        """知らない理由は、書けない形だったとして返す。"""
        assert short_reason("something_new") == "書けない形だった"


class TestUnwrittenMemoLines:
    """unwritten_memo_lines が、書けなかった操作を、書かれていた順に 1 行ずつの文にすることを保証する。"""

    def test_lines_follow_the_written_order_with_the_whole_memo_first(self) -> None:
        """位置の順に並べ直し、引数ごと崩れていたときの行を先頭に置く。"""
        lines = unwritten_memo_lines(
            (
                UnwrittenMemo(2, REJECTED_NO_SUCH_MEMO, {"do": "remove", "id": "m_3f2a7b"}),
                UnwrittenMemo(
                    0, REJECTED_LIMIT_REACHED, {"do": "add", "kind": "todo", "text": "鍵"}, kind=MemoKind.TODO
                ),
                UnwrittenMemo(None, REJECTED_NOT_A_LIST, "書いた"),
            )
        )

        assert lines == (
            "「メモの書き込み」は書けなかった（理由: memo は操作の配列で書く）",
            "「やることに「鍵」を書く」は書けなかった（理由: やることが上限の 5 件。消すか書き換える）",
            "「m_3f2a7b を消す」は書けなかった（理由: そのメモはない）",
        )
