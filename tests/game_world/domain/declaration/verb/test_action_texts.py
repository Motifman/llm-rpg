from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.verb.action_texts import ActionTextKey, ActionTexts
from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import (
    ActionTextMissingException,
    UnfilledNameInActionTextException,
)
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from tests.game_world.support.world_design_for_tests import action_texts


def _with(
    *,
    summaries: dict[ActionTextKey, TextWithUnassignedPeople] | None = None,
    done: dict[ActionTextKey, TextWithUnassignedPeople] | None = None,
    without_summary: ActionTextKey | None = None,
    without_done: ActionTextKey | None = None,
) -> ActionTexts:
    base = action_texts()
    all_summaries = {**base.summaries, **(summaries or {})}
    all_done = {**base.done, **(done or {})}
    if without_summary is not None:
        del all_summaries[without_summary]
    if without_done is not None:
        del all_done[without_done]
    return ActionTexts(summaries=all_summaries, done=all_done)


class TestActionTexts:
    """ActionTexts が、行為の行ごとに要約と成功の文がそろい、書ける名前だけを書いていることを、作るときに確かめることを保証する。"""

    def test_every_row_needs_a_summary(self) -> None:
        """耳を澄ます行の要約が無いと、作るときに ActionTextMissingException を投げる。"""
        with pytest.raises(ActionTextMissingException):
            _with(without_summary=ActionTextKey.LISTEN)

    def test_built_in_rows_need_a_done_text(self) -> None:
        """移動の行の成功の文が無いと、作るときに ActionTextMissingException を投げる。"""
        with pytest.raises(ActionTextMissingException):
            _with(without_done=ActionTextKey.TRAVEL)

    def test_done_text_of_a_row_the_author_writes_is_refused(self) -> None:
        """物の操作の行に成功の文を書くと、作者が操作ごとに書く文と重なるので、ActionTextMissingException を投げる。"""
        with pytest.raises(ActionTextMissingException):
            _with(done={ActionTextKey.INTERACT_WITH_OBJECT: TextWithUnassignedPeople("操作できた。")})

    def test_name_the_row_cannot_fill_is_refused(self) -> None:
        """移動の行の要約に、移動では埋められない {item} を書くと UnfilledNameInActionTextException を投げる。"""
        with pytest.raises(UnfilledNameInActionTextException):
            _with(summaries={ActionTextKey.TRAVEL: TextWithUnassignedPeople("「{item}」へ移動した")})

    def test_names_the_row_can_fill_are_allowed(self) -> None:
        """渡す行の要約に {target} と {item} を書いても断らない。"""
        texts = _with(summaries={ActionTextKey.HAND_OVER: TextWithUnassignedPeople("「{target}」に「{item}」を渡した")})

        assert texts.summary_of(ActionTextKey.HAND_OVER).template == "「{target}」に「{item}」を渡した"
