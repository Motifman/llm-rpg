"""履歴には、次に真似しても通る形の引数だけが残る。

## なぜ

resolver は崩れた表記 (``"祭壇"`` のような quote つき) を救って成功させる。
ところが履歴 (直近の出来事) には LLM が送った生値がそのまま積まれていたので、
**「その書き方で通った」と読めてしまい、崩れが定着していた**。供物競争 run で
実際に、quote つきの ``destination_label`` が成功例として履歴に並び、以降ずっと
同じ形で送られ続けた。

同じ run で ``action_name`` は quote 救済が実装されておらず (ツール定義は
target_label 側で「quote ごとでも解釈する」と約束していたのに) 、表示どおりに
``"offer_wheat"`` と渡した手番が失敗していた。

本ファイルは 2 つを対で守る。**救って成功させる**ことと、**成功した形だけを
履歴に残す**ことは、どちらか片方だけでは崩れを増やす。
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    CANONICAL_IDENTIFIERS_KEY,
    normalize_action_name_candidates,
    record_canonical_identifier,
)
from ai_rpg_world.application.llm.services.action_summary_format import (
    project_action_arguments_for_history,
)


class TestBrokenActionNamesAreRecognized:
    """表示の写し崩れから、実在する操作名の候補を取り出せる。"""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ('"offer_wheat"', "offer_wheat"),
            ("'offer_wheat'", "offer_wheat"),
            ('麦を刈る → "reap_wheat"', "reap_wheat"),
            ("麦を刈る → reap_wheat", "reap_wheat"),
        ],
    )
    def test_the_intended_name_is_among_the_candidates(
        self, raw: str, expected: str
    ) -> None:
        """quote つき・表示行の丸ごとコピーから、操作名が候補に現れる。"""
        assert expected in normalize_action_name_candidates(raw)

    def test_a_clean_name_stays_first(self) -> None:
        """崩れていない名前は、そのまま先頭候補になる (**正の対照**)。"""
        assert normalize_action_name_candidates("offer_wheat")[0] == "offer_wheat"

    def test_an_invented_name_gains_nothing(self) -> None:
        """存在しない名前を発明しても、候補は増えない。

        65 run で 111 件あった「表示に無い操作の発明」は救わない — 救うと
        「適当に書いても通る」を教えることになる。
        """
        assert normalize_action_name_candidates("check_gold") == ["check_gold"]


class TestTheHistoryKeepsTheCanonicalForm:
    """履歴の識別引数は、解決に使った正規値に置き換わる。"""

    def test_a_canonical_value_replaces_the_raw_one(self) -> None:
        """崩れた生値ではなく、正規値が履歴に残る。"""
        identifiers, _ = project_action_arguments_for_history(
            {"destination_label": '"祭りの広場"', "inner_thought": "行くか"},
            canonical_identifiers={"destination_label": "祭りの広場"},
        )

        assert identifiers["destination_label"] == "祭りの広場"

    def test_without_canonical_the_raw_value_is_kept(self) -> None:
        """正規値が無ければ従来どおり生値を残す (**後方互換**)。

        救済の対象でない引数まで黙って書き換えない。
        """
        identifiers, _ = project_action_arguments_for_history(
            {"destination_label": "祭りの広場"}
        )

        assert identifiers["destination_label"] == "祭りの広場"

    def test_free_text_is_still_only_named(self) -> None:
        """自由文は従来どおり名前だけ残る (正規値の導入で壊れていない)。"""
        identifiers, free_text = project_action_arguments_for_history(
            {"content": "やあ", "destination_label": "広場"},
            canonical_identifiers={"destination_label": "広場"},
        )

        assert "content" not in identifiers
        assert free_text == ("content",)


class TestRecordingTheCanonicalValue:
    """正規値の記録は、生値と違うときだけ足す。"""

    def test_a_difference_is_recorded(self) -> None:
        args: Dict[str, Any] = {"destination_label": '"広場"'}

        record_canonical_identifier(args, "destination_label", "広場")

        assert args[CANONICAL_IDENTIFIERS_KEY] == {"destination_label": "広場"}

    def test_no_difference_adds_nothing(self) -> None:
        """生値と同じなら記録しない (無駄な差分を作らない)。"""
        args: Dict[str, Any] = {"destination_label": "広場"}

        record_canonical_identifier(args, "destination_label", "広場")

        assert CANONICAL_IDENTIFIERS_KEY not in args


class TestTheWholePathWithARealWorld:
    """実シナリオ・実 dispatch で、崩れた入力が通り、履歴が正規化される。"""

    @pytest.fixture()
    def race(self):
        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )

        return create_world_runtime("data/scenarios/offering_race_v1.json")

    def _dispatch(self, race, player_int: int, tool: str, args: Dict[str, Any]):
        from ai_rpg_world.application.llm.services.world_llm_turn import tool_dispatch
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
            _WorldLlmWiring,
        )

        class _Client:
            def invoke(self, messages, tools, tool_choice="required", **kwargs):
                return {"name": "wait", "arguments": {}}

        wiring = _WorldLlmWiring(
            runtime=race,
            observation_buffer=race._obs_buffer,
            short_term_memory=race._short_term_memory,
            llm_client=_Client(),
        )
        prompt = race.build_full_prompt(PlayerId(player_int))
        handler = wiring._tool_handlers[tool]
        return handler(
            PlayerId(player_int), args, prompt["tool_runtime_context"]
        )

    def test_a_quoted_action_name_now_succeeds(self, race) -> None:
        """``"offer_wheat"`` (quote つき) で納品が通る。

        run t73 で失敗した実際の入力。ツール定義が target_label 側で約束して
        いた「quote ごとでも解釈する」を action_name にも適用した。
        """
        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            grant_item_specs_to_inventory,
        )
        from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from tests.support.overflow_sinks import IGNORE_OVERFLOW

        spec = race.id_mapper.get_int("item_spec", "wheat")
        grant_item_specs_to_inventory(
            PlayerId(1), (ItemSpecId.create(spec),),
            race._item_repo, race._item_spec_repo,
            race._player_inventory_repo, overflow_sink=IGNORE_OVERFLOW,
        )

        result = self._dispatch(race, 1, "interact", {
            "target_label": '"東の祭壇"',
            "action_name": '"offer_wheat"',
            "inner_thought": "納める",
        })

        assert result.success, result.message

    def test_the_history_shows_the_clean_form(self, race) -> None:
        """崩れた入力で成功しても、履歴には正規形が残る。

        ここが崩れると、次のターンの LLM は「quote つきで通った」を学ぶ。
        """
        result = self._dispatch(race, 1, "travel_to", {
            "destination_label": '"麦畑"',
            "inner_thought": "行く",
        })
        assert result.success, result.message

        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        summary = race._action_result_store.get_recent(PlayerId(1), 1)[-1].action_summary

        assert "麦畑" in summary
        assert '\\"' not in summary, f"履歴に quote が残っている: {summary}"
