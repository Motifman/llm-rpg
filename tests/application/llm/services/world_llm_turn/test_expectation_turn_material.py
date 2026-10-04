"""ゲームの 1 ターンの出来事を予期の清算の材料に写すとき、tool の名前を文に残さない挙動を保証する (#1509)。

清算の時系列は、外れた予期の信念の材料にそのまま載る。tool の名前が残ると信念に
ゲームの用語が入る (「大樫の樹は travel_to で訪れる場所」)。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    UnifiedRecentEventEntry,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.world_llm_turn.expectation_turn import (
    turn_material,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)

AT = datetime(2026, 10, 4, tzinfo=timezone.utc)
_ASCII_WORD = re.compile(r"[A-Za-z0-9_]+")


def _identifiers(line: str) -> list[str]:
    """小文字で始まる語と、小文字と数字を両方含む 6 文字以上の語。tool の名前と ID の形。"""
    return [
        w
        for w in _ASCII_WORD.findall(line)
        if w[0].islower()
        or (len(w) >= 6 and any(c.isdigit() for c in w) and any(c.islower() for c in w))
    ]


def _action(action_summary: str, result_summary: str, tool_name: str) -> UnifiedRecentEventEntry:
    return UnifiedRecentEventEntry.from_action_result(
        ActionResultEntry(
            occurred_at=AT,
            action_summary=action_summary,
            result_summary=result_summary,
            tool_name=tool_name,
            game_time_label="Day 1 4:30",
        )
    )


def _observation(prose: str) -> UnifiedRecentEventEntry:
    return UnifiedRecentEventEntry.from_observation(
        ObservationEntry(
            occurred_at=AT,
            output=ObservationOutput(prose=prose, structured={"type": "action_failed"}),
            game_time_label="Day 1 4:30",
        )
    )


class TestToolNamesAreLeftOut:
    """行動の要約、行動の結果、観測の文に入った tool の名前が、材料の文では「操作」に置き換わる挙動を保証する。"""

    @pytest.mark.parametrize(
        ("entry", "expected"),
        [
            (
                _action("「大樫の樹」に climb_tree した", "対象の名前には使えません", "interact"),
                "[Day 1 4:30] リオ: 「大樫の樹」に操作した → 対象の名前には使えません",
            ),
            (
                _action(
                    "「大樫の樹」を調べた",
                    "「大樫の樹」は隣の場所です。 そこへ行くなら travel_to を使う。",
                    "inspect_target",
                ),
                "[Day 1 4:30] リオ: 「大樫の樹」を調べた → 「大樫の樹」は隣の場所です。 そこへ行くなら操作を使う。",
            ),
            (
                _observation("interact を試みたが失敗した: 船倉はもう漁り尽くした。"),
                "[Day 1 4:30] 操作を試みたが失敗した: 船倉はもう漁り尽くした。",
            ),
        ],
        ids=["scenario_action_name", "tool_name_in_result_hint", "single_word_tool_name"],
    )
    def test_tool_name_becomes_generic_word(
        self, entry: UnifiedRecentEventEntry, expected: str
    ) -> None:
        """snake_case の操作名も下線の無い tool の名前も、小文字の英字で始まる語は「操作」の 1 語に置き換わる。"""
        material = turn_material([entry], self_name="リオ")

        assert material.actions == (expected,)

    def test_material_has_no_ascii_identifiers(self) -> None:
        """実 run に出た形の行動と観測 (下線の無い操作名、メモの ID を含む) を写した材料には、小文字で始まる語も、小文字と数字を含む ID も残らない。"""
        entries = [
            _action("「難破船の船倉」に search_wreck_hold した", "行動が拒否された: 船倉はもう漁り尽くした。", "interact"),
            _action("「カイ」に「貝」を渡した", "give_item 結果:\n貝 → カイ: OK", "give_item"),
            _action("「流木の山」に gather した", "行動が拒否された: 流木はもう拾ってしまった。", "interact"),
            _action("メモを書いた", "メモを追加しました（ID: a8cbc3…）。", "memo_add"),
            _action("メモを書いた", "メモを追加しました（ID: 774c5e…）。", "memo_add"),
            _observation("interact を試みたが失敗した: 修正のヒント: ツール説明を確認してください。"),
        ]

        material = turn_material(entries, self_name="リオ")

        leaked = [w for line in material.actions for w in _identifiers(line)]
        assert leaked == []

    def test_memo_id_is_removed_not_renamed(self) -> None:
        """数字を含むメモの ID は「操作」に置き換えず、文から消す。"""
        entries = [_action("メモを書いた", "メモを追加しました（ID: 774c5e…）。", "memo_add")]

        material = turn_material(entries, self_name="リオ")

        assert material.actions == ("[Day 1 4:30] リオ: メモを書いた → メモを追加しました（ID:…）。",)

    def test_quantity_with_unit_is_kept(self) -> None:
        """数と単位 (1.5kg、10m) は ID ではないので、行動の結果の文に残す。"""
        entries = [_action("「流木の山」を調べた", "1.5kg ほどの流木が 10m 先にある", "inspect_target")]

        material = turn_material(entries, self_name="リオ")

        assert material.actions == ("[Day 1 4:30] リオ: 「流木の山」を調べた → 1.5kg ほどの流木が 10m 先にある",)

    def test_speech_is_copied_as_is(self) -> None:
        """発言は本人たちの言葉なので、小文字の英語を含んでいても置き換えない。"""
        entries = [
            UnifiedRecentEventEntry.from_observation(
                ObservationEntry(
                    occurred_at=AT,
                    output=ObservationOutput(
                        prose="ノア「wait, the wreck is open」",
                        structured={"type": "player_spoke"},
                    ),
                    game_time_label=None,
                )
            )
        ]

        material = turn_material(entries, self_name="リオ")

        assert material.speeches == ("ノア「wait, the wreck is open」",)

    def test_uppercase_words_in_speech_are_kept(self) -> None:
        """小文字を含まない英字の語 (SOS など) と数は識別子ではないので、文に残す。"""
        entries = [
            UnifiedRecentEventEntry.from_observation(
                ObservationEntry(
                    occurred_at=AT,
                    output=ObservationOutput(
                        prose="ノア「浜に SOS と書こう。天候は CLEAR、残り 10 本」",
                        structured={"type": "player_spoke"},
                    ),
                    game_time_label=None,
                )
            )
        ]

        material = turn_material(entries, self_name="リオ")

        assert material.speeches == ("ノア「浜に SOS と書こう。天候は CLEAR、残り 10 本」",)
