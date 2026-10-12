"""エピソードの目次を、毎ターンのプロンプトの【思い出せる出来事】に出す文にする (#1623)。"""

from __future__ import annotations

from collections.abc import Sequence

from ai_rpg_world.being.domain.episode import Episode

EPISODE_INDEX_HEADING = "【思い出せる出来事】"
EMPTY_EPISODE_INDEX_TEXT = "(まだ無い)"


def _line(episode: Episode) -> str:
    return (
        f"[{episode.handle}] {episode.index.summary}"
        f" — 思い出すとき: {episode.index.recall_when}"
        f" (呼び出し {episode.recall_count} 回)"
    )


def format_episode_index(
    episodes: Sequence[Episode], *, current_environment_name: str
) -> str:
    """``episodes`` は並べ方が選んだ順。前にいた環境の分は、環境ごとの見出しでまとめる。

    空でも欄を消さない。呼び出しのツールは出ているので、空の理由が分からないと
    呼び名を作って呼ばせることになる。
    """
    if not episodes:
        return EMPTY_EPISODE_INDEX_TEXT
    lines = [_line(e) for e in episodes if e.environment_name == current_environment_name]
    elsewhere: dict[str, list[Episode]] = {}
    for episode in episodes:
        if episode.environment_name != current_environment_name:
            elsewhere.setdefault(episode.environment_name, []).append(episode)
    for environment_name, grouped in elsewhere.items():
        lines.append(f"前にいた場所 ({environment_name}) で:")
        lines.extend(f"  {_line(e)}" for e in grouped)
    return "\n".join(lines)


__all__ = ["EMPTY_EPISODE_INDEX_TEXT", "EPISODE_INDEX_HEADING", "format_episode_index"]
