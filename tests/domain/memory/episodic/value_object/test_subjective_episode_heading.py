"""SubjectiveEpisode の heading フィールドが、Afterglow index で使う
1 行見出しとして安全に出し入れできることを保証する。

heading は recall されたエピソードを「鮮明には浮かばないがヒントを与えれば
思い出せる」状態として並べる際の見出しとして使う。新規 LLM コールを増やさず
既存の主観文付与経路 (interpreted / recall_text を生成しているコール) に
ついでに書かせる方針のため、フィールドとしては Optional に保ち、欠落・空白・
未指定のいずれも壊れずに None として畳み込むのが本テストの対象範囲。
"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode


def _episode(**overrides) -> SubjectiveEpisode:
    """heading 以外の必須フィールドを最小構成で埋めた SubjectiveEpisode を作る。

    各テストは heading の振る舞いだけを検証したいので、他のフィールドの
    バリデーションエラーで邪魔されないよう、ここで安全な既定値を用意する。
    """
    base = dict(
        episode_id="ep-1",
        player_id=1,
        occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-1",)),
        location=EpisodeLocation(),
        action=EpisodeAction(tool_name="t"),
        who=("p",),
        what="w",
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=(),
        recall_text=None,
    )
    base.update(overrides)
    return SubjectiveEpisode(**base)


class TestSubjectiveEpisodeHeading:
    """heading フィールドが Afterglow index 用の Optional 見出しとして
    安全に初期化される挙動を保証する。"""

    def test_heading_default_is_none(self) -> None:
        """既存の SubjectiveEpisode 構築箇所が heading を意識せずに作っても
        壊れない (= デフォルト None で後方互換)。"""
        ep = _episode()
        assert ep.heading is None

    def test_empty_heading_raises_value_error(self) -> None:
        """既存の interpreted / recall_text などと同じく、value object 層
        では空文字を許さず ValueError で弾く (= 「heading は無い」を表現
        したいなら None を渡す)。LLM 出力経由で空文字が来るケースは
        application 層の _normalize_llm_str が None に潰してから渡す
        ため、この層では正規化済みの値だけを受ける契約にしておく。"""
        import pytest

        with pytest.raises(ValueError):
            _episode(heading="")

    def test_whitespace_only_heading_raises_value_error(self) -> None:
        """空白文字だけを heading として受け入れると afterglow index に
        「見えない見出し」が並んでしまうため、空文字と同様に value object
        層で弾く。"""
        import pytest

        with pytest.raises(ValueError):
            _episode(heading="   ")
