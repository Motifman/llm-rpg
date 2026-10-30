from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.tool_category import ToolCategory
from ai_rpg_world.application.llm.services.memo_arguments import (
    REJECTED_FROM_NOT_NEEDED,
    REJECTED_MISSING_FROM,
    REJECTED_MISSING_ID,
    REJECTED_MISSING_PROVENANCE,
    REJECTED_MISSING_TEXT,
    REJECTED_NOT_A_LIST,
    REJECTED_NOT_AN_OBJECT,
    REJECTED_TEXT_TOO_LONG,
    REJECTED_UNKNOWN_DO,
    REJECTED_UNKNOWN_KIND,
    feedback_text,
    read_memo_operations,
    rejection_text,
)
from ai_rpg_world.application.llm.services.tool_catalog.memo_argument import (
    with_memo_schema,
)
from ai_rpg_world.being.application.memo_writing import (
    REJECTED_LIMIT_REACHED,
    REJECTED_NO_SUCH_MEMO,
    REJECTED_PROVENANCE_OUTSIDE_FACT,
    AddMemo,
    EditMemo,
    RemoveMemo,
)
from ai_rpg_world.being.domain.memo_book import (
    MemoCertainty,
    MemoKind,
    MemoProvenance,
    MemoSource,
)

HEARD_GUESS = MemoProvenance(source=MemoSource.HEARD, certainty=MemoCertainty.GUESS, source_from="門番")


def _read(*items: Any, episode: bool = False):
    return read_memo_operations({"memo": list(items)}, episode_source_offered=episode)


class TestReadingMemoOperations:
    """read_memo_operations が、引数 memo の操作を 1 件ずつ確かめ、崩れた操作だけを外すことを保証する。"""

    def test_missing_argument_is_not_present(self) -> None:
        """引数 memo が無ければ、操作も外した操作も無く、引数は無かったと返す。"""
        read = read_memo_operations({"inner_thought": "…"}, episode_source_offered=False)

        assert (read.operations, read.rejected, read.present) == ((), (), False)

    def test_null_is_present_but_empty(self) -> None:
        """引数 memo が null なら、引数はあったが操作は無いと返す。"""
        read = read_memo_operations({"memo": None}, episode_source_offered=False)

        assert (read.operations, read.rejected, read.present) == ((), (), True)

    def test_not_a_list_is_rejected_as_a_whole(self) -> None:
        """引数 memo が配列でなければ、位置を持たない 1 件として外す。"""
        read = read_memo_operations({"memo": {"do": "add"}}, episode_source_offered=False)

        assert [(r.index, r.reason) for r in read.rejected] == [(None, REJECTED_NOT_A_LIST)]

    def test_three_operations_are_read_with_their_positions(self) -> None:
        """足す・書き換える・消すを並べると、それぞれの操作を配列の位置と一緒に返す。"""
        read = _read(
            {"do": "add", "kind": "todo", "text": " 事務所で鍵を取る "},
            {"do": "edit", "id": "m_3f2a7b", "text": "鍵を二つ取る"},
            {"do": "remove", "id": "m_91c0de"},
        )

        assert read.operations == (
            (0, AddMemo(MemoKind.TODO, "事務所で鍵を取る", None)),
            (1, EditMemo("m_3f2a7b", "鍵を二つ取る", None)),
            (2, RemoveMemo("m_91c0de")),
        )

    def test_heard_fact_keeps_who(self) -> None:
        """人から聞いた分かったことは、出どころ・確かさ・誰からを持つ。"""
        read = _read(
            {
                "do": "add",
                "kind": "fact",
                "text": "弁は目盛りが関係する",
                "source": "heard",
                "certainty": "guess",
                "from": "門番",
            }
        )

        assert read.operations == ((0, AddMemo(MemoKind.FACT, "弁は目盛りが関係する", HEARD_GUESS)),)

    def test_a_broken_operation_does_not_stop_the_others(self) -> None:
        """崩れた操作があっても、その前後の操作は読む。"""
        read = _read({"do": "add", "kind": "todo", "text": "鍵"}, "壊れた", {"do": "remove", "id": "m_3f2a7b"})

        assert [i for i, _ in read.operations] == [0, 2]
        assert [(r.index, r.reason, r.raw) for r in read.rejected] == [(1, REJECTED_NOT_AN_OBJECT, "壊れた")]

    @pytest.mark.parametrize(
        ("item", "reason"),
        [
            ({"do": "write", "kind": "todo", "text": "鍵"}, REJECTED_UNKNOWN_DO),
            ({"do": "add", "kind": "plan", "text": "鍵"}, REJECTED_UNKNOWN_KIND),
            ({"do": "add", "kind": "todo", "text": "  "}, REJECTED_MISSING_TEXT),
            ({"do": "add", "kind": "todo", "text": "あ" * 61}, REJECTED_TEXT_TOO_LONG),
            ({"do": "edit", "text": "鍵"}, REJECTED_MISSING_ID),
            ({"do": "remove"}, REJECTED_MISSING_ID),
            ({"do": "add", "kind": "fact", "text": "鍵"}, REJECTED_MISSING_PROVENANCE),
            ({"do": "add", "kind": "fact", "text": "鍵", "source": "self"}, REJECTED_MISSING_PROVENANCE),
            (
                {"do": "add", "kind": "fact", "text": "鍵", "source": "heard", "certainty": "sure"},
                REJECTED_MISSING_FROM,
            ),
            (
                {"do": "add", "kind": "fact", "text": "鍵", "source": "self", "certainty": "sure", "from": "門番"},
                REJECTED_FROM_NOT_NEEDED,
            ),
            (
                {"do": "add", "kind": "todo", "text": "鍵", "source": "self", "certainty": "sure"},
                REJECTED_PROVENANCE_OUTSIDE_FACT,
            ),
            (
                {
                    "do": "add",
                    "kind": "fact",
                    "text": "鍵",
                    "source": "episode",
                    "certainty": "sure",
                    "from": "ep_a07c33",
                },
                REJECTED_MISSING_PROVENANCE,
            ),
        ],
        ids=[
            "unknown_do",
            "unknown_kind",
            "blank_text",
            "text_61_chars",
            "edit_without_id",
            "remove_without_id",
            "fact_without_provenance",
            "fact_without_certainty",
            "heard_without_from",
            "self_with_from",
            "todo_with_provenance",
            "episode_source_not_offered",
        ],
    )
    def test_broken_operation_is_rejected_with_its_reason(self, item: dict[str, Any], reason: str) -> None:
        """崩れた操作は、崩れ方ごとの理由と元の値を持って外れる。"""
        read = _read(item)

        assert read.operations == ()
        assert [(r.reason, r.raw) for r in read.rejected] == [(reason, item)]

    @pytest.mark.parametrize(
        "provenance",
        [{"source": ["self"], "certainty": "sure"}, {"source": "self", "certainty": {"v": "sure"}}],
        ids=["source_list", "certainty_dict"],
    )
    def test_unhashable_provenance_is_rejected_without_raising(self, provenance: dict[str, Any]) -> None:
        """source や certainty に配列や辞書が入っていても例外を投げず、出どころが崩れた操作として外す。"""
        item = {"do": "add", "kind": "fact", "text": "鍵", **provenance}

        read = _read(item)

        assert [(r.reason, r.raw) for r in read.rejected] == [(REJECTED_MISSING_PROVENANCE, item)]

    def test_episode_source_is_read_when_offered(self) -> None:
        """出どころの選択肢にエピソードを出す設定では、エピソードの呼び名を出どころとして読む。"""
        read = _read(
            {
                "do": "add",
                "kind": "fact",
                "text": "籠は 3 人まで",
                "source": "episode",
                "certainty": "sure",
                "from": "ep_a07c33",
            },
            episode=True,
        )

        ((_, operation),) = read.operations
        assert isinstance(operation, AddMemo)
        assert operation.provenance == MemoProvenance(
            source=MemoSource.EPISODE, certainty=MemoCertainty.SURE, source_from="ep_a07c33"
        )


class TestFeedback:
    """外した操作を、本人が直し方の分かる文で返すことを保証する。"""

    def test_limit_names_the_kind_and_its_limit(self) -> None:
        """上限で外れたやることには、分類と件数と直し方を返す。"""
        assert rejection_text(REJECTED_LIMIT_REACHED, kind=MemoKind.TODO) == (
            "やることが上限 (5 件) です。消すか書き換えてください。"
        )

    def test_unknown_handle_names_the_handle(self) -> None:
        """無い呼び名で外れた操作には、その呼び名を添えて返す。"""
        assert rejection_text(REJECTED_NO_SUCH_MEMO, detail="m_000000") == "m_000000 というメモはありません。"

    def test_feedback_lists_each_rejection_by_position(self) -> None:
        """外した操作を、配列の何件目かと理由の文を 1 行ずつ並べて返す。"""
        text = feedback_text([(0, "text が空です。"), (None, "memo は操作の配列で書いてください。")])

        assert text == (
            "\n\n[メモ] 次の操作は書けませんでした。\n"
            "- 1 件目: text が空です。\n"
            "- memo: memo は操作の配列で書いてください。"
        )

    def test_no_rejection_gives_no_feedback(self) -> None:
        """外した操作が無ければ、結果の文に何も足さない。"""
        assert feedback_text([]) == ""


class TestMemoSchema:
    """with_memo_schema が、環境の tool に省略できる引数 memo を足すことを保証する。"""

    def _definition(self) -> ToolDefinitionDto:
        return ToolDefinitionDto(
            name="wait",
            description="待つ",
            parameters={
                "type": "object",
                "properties": {"inner_thought": {"type": "string"}},
                "required": ["inner_thought"],
            },
            category=ToolCategory.WORLD_ACTION,
        )

    def test_memo_is_added_but_not_required(self) -> None:
        """memo を properties に足し、required には足さない。元の引数はそのまま残る。"""
        definition = with_memo_schema(self._definition(), episode_source_offered=False)

        assert set(definition.parameters["properties"]) == {"inner_thought", "memo"}
        assert definition.parameters["required"] == ["inner_thought"]

    def test_episode_source_is_not_offered_unless_asked(self) -> None:
        """エピソードを出どころに出さない設定では、選択肢にも説明にも episode と ep_ が出ない。"""
        memo = with_memo_schema(self._definition(), episode_source_offered=False).parameters["properties"]["memo"]

        assert memo["items"]["properties"]["source"]["enum"] == ["self", "heard"]
        assert "episode" not in memo["description"]
        assert "ep_" not in memo["description"]

    def test_episode_source_is_offered_when_asked(self) -> None:
        """エピソードを出どころに出す設定では、選択肢と説明に episode が出る。"""
        memo = with_memo_schema(self._definition(), episode_source_offered=True).parameters["properties"]["memo"]

        assert memo["items"]["properties"]["source"]["enum"] == ["self", "heard", "episode"]
        assert "ep_" in memo["description"]

    def test_episode_source_is_limited_to_handles_in_the_index(self) -> None:
        """エピソードを出どころに出す設定では、【思い出せる出来事】にある呼び名だけを書き、無ければ episode を選ばないと説明する。

        確認の run (`var/runs/mine_v1_008_check`) で、エピソードがまだ無い回に episode を選び、
        呼び名の代わりに ep_? と書いて外された。
        """
        memo = with_memo_schema(self._definition(), episode_source_offered=True).parameters["properties"]["memo"]

        assert "【思い出せる出来事】にある呼び名だけ書ける" in memo["description"]
        assert "無ければ episode は選ばない" in memo["description"]
