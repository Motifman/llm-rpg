from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.action_argument_classification import format_action_call_for_history
from ai_rpg_world.being.application.episode_index_revision_tool import (
    index_revision_call_text,
    read_index_revision,
)
from ai_rpg_world.being.domain.episode import EpisodeIndex


class TestReadIndexRevision:
    """read_index_revision が、目次を直す引数を、古い run と同じ決まりで読むことを保証する。"""

    def test_texts_are_stripped_and_cut_to_forty_characters(self) -> None:
        """前後の空白を外し、41 字の文は 40 字に切って、切る前の長さを残す。"""
        request = read_index_revision({"handle": " ep_3f2a7b ", "about": " " + "あ" * 41, "recall_when": "井戸の話"})

        assert request is not None
        assert (request.handle, request.index) == ("ep_3f2a7b", EpisodeIndex(summary="あ" * 40, recall_when="井戸の話"))
        assert request.truncated == {"about": 41}

    @pytest.mark.parametrize(
        "arguments",
        [
            {"about": "井戸", "recall_when": "井戸の話"},
            {"handle": "  ", "about": "井戸", "recall_when": "井戸の話"},
            {"handle": "ep_3f2a7b", "about": 3, "recall_when": "井戸の話"},
            {"handle": "ep_3f2a7b", "about": "井戸", "recall_when": " "},
        ],
    )
    def test_missing_blank_or_non_text_arguments_are_malformed(self, arguments: dict[str, object]) -> None:
        """呼び名が無い・空白だけ、文が文字列でない・空白だけなら、崩れているとして None を返す。"""
        assert read_index_revision(arguments) is None


class TestIndexRevisionCallText:
    """index_revision_call_text が、古い run の「呼び出し:」の行と同じ文を作ることを保証する。"""

    def test_call_text_matches_the_old_run(self) -> None:
        """呼び名だけを引用し、about と recall_when は古い run の置き換えの文にする。古い run の組み立てと 1 文字も違わない。"""
        arguments = {"handle": "ep_3f2a7b", "about": "井戸でサヨと話した", "recall_when": "井戸の話が出たとき"}

        assert index_revision_call_text("episode_revise_index", arguments) == format_action_call_for_history(
            "episode_revise_index", {"handle": "ep_3f2a7b"}, ("about", "recall_when")
        )
