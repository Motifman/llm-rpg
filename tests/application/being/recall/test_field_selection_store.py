"""NextTurnFieldSelections が、清算したターンの選択を、次にプロンプトを組むときだけ渡す挙動を保証する。"""

from __future__ import annotations

from ai_rpg_world.application.being.recall.selection_store import (
    DEGRADED_NO_SELECTION,
    DEGRADED_STALE_SELECTION,
    NextTurnFieldSelections,
)
from ai_rpg_world.application.being.recall.situation import (
    FieldSelection,
    SituationField,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ALICE = BeingId("being_w1_p1")
BOB = BeingId("being_w1_p2")
INTENT_ONLY = FieldSelection(kept=frozenset({SituationField.INTENT}))


class TestSelectionForTheNextPrompt:
    """選択が、清算したターンと同じターン番号でプロンプトを組むときにだけ使われることを保証する。"""

    def test_selection_settled_at_the_current_turn_is_used(self) -> None:
        """ターン 3 で清算した選択は、ターン番号が 3 のままプロンプトを組むときに使われる。"""
        store = NextTurnFieldSelections()
        store.put(ALICE, settled_turn=3, selection=INTENT_ONLY)

        assert store.for_prompt(ALICE, current_turn=3) == INTENT_ONLY

    def test_selection_of_an_older_turn_degrades_as_stale(self) -> None:
        """清算したターンより先にターンが進んでいれば、古い選択を使わず、全部の欄に縮退する。"""
        store = NextTurnFieldSelections()
        store.put(ALICE, settled_turn=3, selection=INTENT_ONLY)

        selection = store.for_prompt(ALICE, current_turn=5)

        assert selection.degraded_reason == DEGRADED_STALE_SELECTION
        assert "3" in selection.degraded_detail
        assert "5" in selection.degraded_detail

    def test_selection_of_a_later_turn_is_not_used(self) -> None:
        """選択の番号がいまのターンより新しい (ターン番号が戻った) ときも使わず、古い選択と同じく縮退する。"""
        store = NextTurnFieldSelections()
        store.put(ALICE, settled_turn=5, selection=INTENT_ONLY)

        assert store.for_prompt(ALICE, current_turn=3).degraded_reason == DEGRADED_STALE_SELECTION

    def test_missing_selection_degrades_as_no_selection(self) -> None:
        """一度も清算していない Being (再開した直後を含む) は、選択が無いことを理由に全部の欄に縮退する。"""
        store = NextTurnFieldSelections()
        store.put(BOB, settled_turn=3, selection=INTENT_ONLY)

        selection = store.for_prompt(ALICE, current_turn=3)

        assert selection.degraded_reason == DEGRADED_NO_SELECTION

    def test_later_put_replaces_the_earlier_selection(self) -> None:
        """同じ Being に選択を入れ直すと、後の選択だけが残る。"""
        store = NextTurnFieldSelections()
        store.put(ALICE, settled_turn=3, selection=FieldSelection(kept=frozenset()))
        store.put(ALICE, settled_turn=4, selection=INTENT_ONLY)

        assert store.for_prompt(ALICE, current_turn=4) == INTENT_ONLY
