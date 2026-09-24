"""Issue #1429 の比較実験で、候補表と集計の契約を保証する。"""

from scripts.compare_jev_candidate_table import (
    CaseLabel,
    EvaluatedChoice,
    build_candidate_table,
    summarize_choices,
)


def test_action_table_keeps_target_to_action_relationship() -> None:
    """操作名の表は、対象名とその対象で選べる操作名の対応を保つ。"""
    table = build_candidate_table(
        kind="action_name",
        tool="interact",
        argument_name="action_name",
        target="東の祭壇",
        candidates=["offer_wheat", "offer_gold"],
    )

    assert '- interact.target_label: "東の祭壇"' in table
    assert '- interact.action_name ("東の祭壇"): "offer_wheat", "offer_gold"' in table
    assert "成功を保証しない" in table


def test_target_table_only_lists_current_candidates() -> None:
    """対象名の表は、対象の引数名に現在の候補だけを引用符付きで載せる。"""
    table = build_candidate_table(
        kind="target_name",
        tool="give_item",
        argument_name="target_label",
        target="",
        candidates=["アキ", "ユノ"],
    )

    assert '- give_item.target_label: "アキ", "ユノ"' in table


def test_summary_separates_wrong_selection_no_match_and_unresolved() -> None:
    """集計は誤選択・正しい該当なし・未解決を混ぜず、適合率と再現率を出す。"""
    rows = [
        EvaluatedChoice(CaseLabel("a", "x"), "x", "selected", 10, 0.1),
        EvaluatedChoice(CaseLabel("b", "y"), "x", "selected", 20, 0.2),
        EvaluatedChoice(CaseLabel("c", None), None, "no_match", 30, 0.0),
        EvaluatedChoice(CaseLabel("d", "z"), None, "unresolved", 40, 0.0),
    ]

    summary = summarize_choices(rows)

    assert summary["accuracy"] == 0.5
    assert summary["precision"] == 0.5
    assert summary["recall"] == 1 / 3
    assert summary["wrong_selection"] == 1
    assert summary["correct_no_match"] == 1
    assert summary["unresolved"] == 1
