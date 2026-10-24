from __future__ import annotations

from ai_rpg_world.being.application.episode_index_text import (
    EMPTY_EPISODE_INDEX_TEXT,
    format_episode_index,
)
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex

ISLAND = "島"
MINE = "廃坑の山村"


def _episode(
    number: int,
    *,
    summary: str = "金庫の番号を探した",
    recall_when: str = "金庫や鍵の話が出たとき",
    environment_name: str = ISLAND,
    recalls: int = 0,
) -> Episode:
    episode = Episode.write(
        episode_id=f"{number:06x}00-0000-4000-8000-000000000000",
        environment_name=environment_name,
        written_turn=1,
        index=EpisodeIndex(summary=summary, recall_when=recall_when),
        body="本文",
    )
    for turn in range(recalls):
        episode.recall(turn=2 + turn)
    return episode


class TestFormatEpisodeIndex:
    """format_episode_index が、選んだエピソードを 1 件 1 行の目次にし、前にいた環境の分を見出しでまとめることを保証する。"""

    def test_one_line_holds_handle_summary_recall_when_and_recall_count(self) -> None:
        """1 件は呼び名・どんな記憶か・どんな時に思い出すか・呼び出した回数を 1 行に並べる。"""
        episode = _episode(1, recalls=2)

        text = format_episode_index([episode], current_environment_name=ISLAND)

        assert text == f"[{episode.handle}] 金庫の番号を探した — 思い出すとき: 金庫や鍵の話が出たとき (呼び出し 2 回)"

    def test_never_recalled_episode_shows_zero(self) -> None:
        """一度も呼び出していないエピソードは、呼び出した回数を 0 回と出す。"""
        episode = _episode(1)

        text = format_episode_index([episode], current_environment_name=ISLAND)

        assert text.endswith("(呼び出し 0 回)")

    def test_keeps_the_given_order(self) -> None:
        """渡した順 (並べ方が選んだ順) のまま行を並べ、並べ直さない。"""
        first, second = _episode(2, summary="二つ目"), _episode(1, summary="一つ目")

        lines = format_episode_index([first, second], current_environment_name=ISLAND).splitlines()

        assert [line.split("]")[0] for line in lines] == [f"[{first.handle}", f"[{second.handle}"]

    def test_other_environments_are_grouped_under_a_heading_after_the_current_one(self) -> None:
        """前にいた環境で書いたものは 1 件ずつ添えず、今の環境の分のあとに環境ごとの見出しでまとめる。"""
        mine = _episode(1, summary="籠に乗った", environment_name=MINE)
        here = _episode(2, summary="浜で火を起こした")
        mine_again = _episode(3, summary="坑道で迷った", environment_name=MINE)

        text = format_episode_index([mine, here, mine_again], current_environment_name=ISLAND)

        assert text.splitlines() == [
            f"[{here.handle}] 浜で火を起こした — 思い出すとき: 金庫や鍵の話が出たとき (呼び出し 0 回)",
            f"前にいた場所 ({MINE}) で:",
            f"  [{mine.handle}] 籠に乗った — 思い出すとき: 金庫や鍵の話が出たとき (呼び出し 0 回)",
            f"  [{mine_again.handle}] 坑道で迷った — 思い出すとき: 金庫や鍵の話が出たとき (呼び出し 0 回)",
        ]

    def test_empty_index_says_there_is_nothing_yet(self) -> None:
        """エピソードが 1 件も無ければ、欄を消さずに「まだ無い」と出す。"""
        text = format_episode_index([], current_environment_name=ISLAND)

        assert text == EMPTY_EPISODE_INDEX_TEXT
        assert text == "(まだ無い)"
