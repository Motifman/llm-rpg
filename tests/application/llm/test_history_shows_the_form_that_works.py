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
    canonical_identifiers,
    normalize_action_name_candidates,
)
from ai_rpg_world.application.llm.services.action_summary_format import (
    CANONICAL_IDENTIFIERS_KEY,
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


class TestCollectingTheCanonicalValue:
    """正規値は、生値と違うものだけを集める。raw args は変更しない。"""

    def test_a_difference_is_collected(self) -> None:
        args: Dict[str, Any] = {"destination_label": '"広場"'}

        assert canonical_identifiers(
            args, destination_label="広場"
        ) == {"destination_label": "広場"}

    def test_no_difference_collects_nothing(self) -> None:
        """生値と同じなら集めない (無駄な差分を作らない)。"""
        args: Dict[str, Any] = {"destination_label": "広場"}

        assert canonical_identifiers(args, destination_label="広場") == {}

    def test_the_raw_arguments_are_left_untouched(self) -> None:
        """入力 dict を書き換えない。

        raw args は fingerprint と行動要約のフォールバック表示にも使われる。
        内部キーを混ぜると、そちらへ漏れる。
        """
        args: Dict[str, Any] = {"destination_label": '"広場"'}

        canonical_identifiers(args, destination_label="広場")

        assert args == {"destination_label": '"広場"'}


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

        entry = race._action_result_store.get_recent(PlayerId(1), 1)[-1]

        assert entry.identifier_arguments["destination_label"] == "麦畑", (
            f"履歴に正規形が残っていない: {entry.identifier_arguments}"
        )

    def test_the_history_of_an_interaction_is_clean_too(self, race) -> None:
        """interact も同じ: 崩れた対象名・操作名が履歴では正規形になる。

        travel_to だけ直しても、他の識別引数が崩れたまま積まれれば同じ
        定着が起きる。両方の経路を見る。
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
            "action_name": '麦束を納める → "offer_wheat"',
            "inner_thought": "納める",
        })
        assert result.success, result.message

        ids = race._action_result_store.get_recent(PlayerId(1), 1)[-1].identifier_arguments

        assert ids["action_name"] == "offer_wheat", ids
        assert ids["target_label"] == "東の祭壇", ids

    def test_a_generic_tool_path_is_normalized_too(self, race) -> None:
        """do_* を通らない tool (use_item) でも履歴が正規化される。

        射影を読むのは executor の 5 経路だけで、それ以外は phase_b が raw
        から作り直していた。**届けないと、正規値を報告する resolver を
        増やしても何も起きない静かな no-op になる。** dispatch が raw args
        にも射影を置くことで、両方の記録経路が同じ値を見る。
        """
        from ai_rpg_world.application.llm.services.action_summary_format import (
            ACTION_HISTORY_PROJECTION_KEY,
            action_history_projection,
        )
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

        args = {"item_label": '"麦束"', "inner_thought": "使ってみる"}
        self._dispatch(race, 1, "use_item", args)

        assert ACTION_HISTORY_PROJECTION_KEY in args, (
            "generic 経路へ射影が届いていない"
        )
        identifiers, _ = action_history_projection(args)
        assert identifiers["item_label"] == "麦束", identifiers

    def test_an_invented_action_still_fails_with_the_list(self, race) -> None:
        """表示に無い操作の発明は救わず、利用可能な一覧を返す (**負の対照**)。

        救済を「候補を作ったら通す」に広げると、この失敗が消えて
        「適当に書いても通る」を教えることになる (65 run で 111 件の主因)。
        """
        result = self._dispatch(race, 1, "interact", {
            "target_label": "東の祭壇",
            "action_name": "check_contents",
            "inner_thought": "中を見たい",
        })

        assert result.success is False
        assert "offer_wheat" in result.message


class TestWhichIdentifiersAreNormalizedSoFar:
    """正規化済みの識別引数を表で持ち、抜けを見えるようにする。

    識別引数 (IDENTIFIER_STRING) は 12 種類ある。resolver が救済しても
    正規値を報告しなければ履歴には崩れが残るので、**どこまで塞いだかを
    表にして、残りが見えない状態にしない**。増やしたらこの表に足す。
    """

    #: (引数名, 正規値を報告する resolver がある)
    _COVERAGE = {
        "destination_label": True,   # travel_to
        "target_label": True,        # interact
        "action_name": True,         # interact
        "item_label": True,          # use_item / drop_item
        "ground_item_label": False,  # pickup_item
        "merchant_label": False,     # buy_item / sell_item
        "offerer_player_label": False,  # trade_accept / decline
        "sub_location_label": False,    # set_sub_location
        "channel": False,            # speak (resolver を通らない)
        "handle": False,             # memory_*
    }

    def test_the_table_only_names_real_identifier_arguments(self) -> None:
        """表の名前が、実在する識別引数の分類と一致する。

        名前を間違えると表が空振りする (実在しない引数は誰も報告しない
        ので、False のまま永久に緑)。
        """
        from ai_rpg_world.application.llm.contracts.action_argument_classification import (
            ACTION_ARGUMENT_CLASSIFICATIONS,
            ActionArgumentDisplayKind,
        )

        identifiers = {
            name
            for name, kind in ACTION_ARGUMENT_CLASSIFICATIONS.items()
            if kind is ActionArgumentDisplayKind.IDENTIFIER_STRING
        }

        assert set(self._COVERAGE) <= identifiers, (
            f"表に実在しない引数がある: {set(self._COVERAGE) - identifiers}"
        )

    def test_the_covered_ones_are_actually_covered(self) -> None:
        """True と書いた引数は、resolver が本当に正規値を報告している。"""
        import inspect

        from ai_rpg_world.application.llm.services._argument_resolvers import (
            spot_graph_resolver,
        )

        source = inspect.getsource(spot_graph_resolver)
        for name, covered in self._COVERAGE.items():
            if covered:
                assert f"{name}=" in source, (
                    f"{name} は正規化済みのはずだが canonical_identifiers に無い"
                )

