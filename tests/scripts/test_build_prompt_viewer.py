"""``scripts/build_prompt_viewer.py`` のユニットテスト。

「実際に LLM へ送った prompt を読む」ための HTML 生成が、capture の形
(prompt_dataset/calls.jsonl) から本文・出力・ハイライトを落とさずに
組み立てられることを保証する。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_prompt_viewer import (
    HIGHLIGHT_RULES,
    _load_calls,
    _render_body,
    _tool_names_of,
    render_html,
)


def _call(
    *,
    llm_call_id: str = "c1",
    tick: int = 3,
    player_id: int = 2,
    name: str = "ノア",
    phase: str = "one_step",
    user: str = "【現在地と周囲】\n現在地: 難破船の浜",
    tool: str = "explore",
    arguments: dict | None = None,
    system_content: str = "",
) -> dict:
    return {
        "llm_call_id": llm_call_id,
        "world_tick": tick,
        "player_id": player_id,
        "character_name": name,
        "phase": phase,
        "prompt": {
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user},
            ],
            "system_prompt_id": "system_prompt:sha256:abc",
            "toolset_id": "toolset:sha256:def",
        },
        "output": {"name": tool, "arguments": arguments or {"inner_thought": "見て回る"}},
        "metrics": {"wall_latency_ms": 1200, "prompt_tokens": 900, "cached_tokens": 400},
    }


def _write(
    tmp_path: Path,
    calls: list[dict],
    *,
    profile: str = "p",
    system_prompts: list[dict] | None = None,
    toolsets: list[dict] | None = None,
) -> Path:
    run_dir = tmp_path / "run"
    ds = run_dir / "prompt_dataset"
    ds.mkdir(parents=True)
    with (ds / "calls.jsonl").open("w", encoding="utf-8") as f:
        for c in calls:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    (ds / "run.json").write_text(json.dumps({"profile": profile}), encoding="utf-8")
    if system_prompts is not None:
        with (ds / "system_prompts.jsonl").open("w", encoding="utf-8") as f:
            for row in system_prompts:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    if toolsets is not None:
        with (ds / "toolsets.jsonl").open("w", encoding="utf-8") as f:
            for row in toolsets:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return run_dir


class TestLoadCalls:
    def test_reads_user_message_and_chosen_tool(self, tmp_path) -> None:
        """calls.jsonl の user message 本文と output の tool 名・引数を取り出す。"""
        run_dir = _write(tmp_path, [_call(user="【直近の出来事】\nエイダが言った", tool="speak")])
        calls = _load_calls(run_dir)
        assert len(calls) == 1
        assert calls[0].user_content == "【直近の出来事】\nエイダが言った"
        assert calls[0].tool_name == "speak"
        assert calls[0].tool_arguments == {"inner_thought": "見て回る"}

    def test_system_body_is_resolved_from_the_side_table(self, tmp_path) -> None:
        """calls.jsonl の system は参照化されて空なので、system_prompts.jsonl から
        本文を引いて実際に送った内容を復元する。"""
        run_dir = _write(
            tmp_path,
            [_call(system_content="")],
            system_prompts=[
                {
                    "system_prompt_id": "system_prompt:sha256:abc",
                    "content": "あなたは次のペルソナとして行動する。",
                }
            ],
        )
        call = _load_calls(run_dir)[0]
        assert call.system_content == "あなたは次のペルソナとして行動する。"

    def test_unresolvable_system_reference_is_left_empty_not_faked(
        self, tmp_path
    ) -> None:
        """参照先が無い run では本文を捏造せず空のままにし、id を保持して
        「解決できなかった」と表示できる状態にする。"""
        run_dir = _write(tmp_path, [_call(system_content="")])
        call = _load_calls(run_dir)[0]
        assert call.system_content == ""
        assert call.system_prompt_id == "system_prompt:sha256:abc"

    def test_tool_names_are_resolved_from_the_toolset_table(self, tmp_path) -> None:
        """その call で使えた tool 名を toolsets.jsonl から引く。「その手が
        選べたのか、そもそも出ていなかったのか」を prompt 側で切り分けるため。"""
        run_dir = _write(
            tmp_path,
            [_call()],
            toolsets=[
                {
                    "toolset_id": "toolset:sha256:def",
                    "tool_names": ["speak", "explore", "travel_to"],
                }
            ],
        )
        assert _load_calls(run_dir)[0].tool_names == ["speak", "explore", "travel_to"]

    def test_calls_are_sorted_by_world_tick(self, tmp_path) -> None:
        """記録順がばらけていても tick 昇順に並べ替えて時系列で読めるようにする。"""
        run_dir = _write(
            tmp_path,
            [_call(llm_call_id="b", tick=9), _call(llm_call_id="a", tick=2)],
        )
        assert [c.llm_call_id for c in _load_calls(run_dir)] == ["a", "b"]

    def test_broken_json_line_is_skipped_with_a_warning(self, tmp_path, capsys) -> None:
        """1 行が壊れていても残りの call を読み、飛ばしたことを stderr に残す
        (= 黙って件数が減らない)。"""
        run_dir = _write(tmp_path, [_call(llm_call_id="ok")])
        path = run_dir / "prompt_dataset" / "calls.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write("{壊れた\n")
        calls = _load_calls(run_dir)
        assert [c.llm_call_id for c in calls] == ["ok"]
        assert "warning" in capsys.readouterr().err

    def test_missing_dataset_raises_with_the_flag_to_set(self, tmp_path) -> None:
        """capture 無効の run を渡したら、有効化に必要なフラグ名を含めて失敗する。"""
        (tmp_path / "run").mkdir()
        with pytest.raises(FileNotFoundError, match="PROMPT_DATASET_CAPTURE_ENABLED"):
            _load_calls(tmp_path / "run")


class TestHighlights:
    def test_strong_stagnation_line_is_labelled(self, tmp_path) -> None:
        """停滞 (強) の表出が本文にあると、その call にラベルが付いて絞り込める。"""
        run_dir = _write(
            tmp_path,
            [_call(user="  → 同じことばかり繰り返している焦りが拭えない。")],
        )
        assert _load_calls(run_dir)[0].highlights == ["停滞 (強)"]

    def test_call_without_notable_lines_has_no_label(self, tmp_path) -> None:
        """注目行が無い call にはラベルを付けない (= 全件が該当扱いにならない)。"""
        run_dir = _write(tmp_path, [_call(user="【現在地と周囲】\n現在地: 干潟")])
        assert _load_calls(run_dir)[0].highlights == []

    def test_highlight_needles_are_not_empty(self) -> None:
        """空文字の needle はすべての行に一致してハイライトが無意味になるため、
        HIGHLIGHT_RULES の needle と label は必ず中身を持つ。"""
        for cls, label, needle in HIGHLIGHT_RULES:
            assert cls and label and needle


class TestRenderBody:
    def test_splits_user_message_into_bracket_sections(self) -> None:
        """本文を 【見出し】 単位の details に分け、見出しを summary に出す。"""
        out = _render_body("【現在の目的】\n救助される\n【現在地と周囲】\n浜")
        assert "<summary>現在の目的</summary>" in out
        assert "<summary>現在地と周囲</summary>" in out

    def test_section_containing_a_notable_line_is_marked(self) -> None:
        """注目行を含む section に data-marked を付け、折りたたんでも所在が分かる。"""
        out = _render_body("【身体の状態】\n  → 同じことばかり繰り返している焦りが拭えない。")
        assert 'data-marked="1"' in out

    def test_section_without_notable_lines_is_not_marked(self) -> None:
        """注目行が無い section には data-marked を付けない。"""
        assert 'data-marked="1"' not in _render_body("【現在地と周囲】\n現在地: 干潟")

    def test_html_in_body_is_escaped(self) -> None:
        """本文に山括弧が入っても HTML として解釈させない。"""
        out = _render_body("【所持】\n<script>alert(1)</script>")
        assert "<script>alert(1)</script>" not in out
        assert "&lt;script&gt;" in out

    def test_body_without_headings_is_still_rendered(self) -> None:
        """見出しの無い本文 (assess phase 等) も 1 ブロックとして本文を出す。"""
        out = _render_body("見出しの無い本文")
        assert "見出しの無い本文" in out
        assert "(見出しなし)" in out

    def test_empty_body_says_so_instead_of_rendering_nothing(self) -> None:
        """user message が空なら、空であることを明示する (= 無言で空白にしない)。"""
        assert "空" in _render_body("")


class TestRenderHtml:
    def test_page_contains_one_article_per_call(self, tmp_path) -> None:
        """call 1 件につき 1 つの article を出し、件数が落ちない。"""
        run_dir = _write(tmp_path, [_call(llm_call_id="a"), _call(llm_call_id="b")])
        page = render_html(_load_calls(run_dir), run_id="r", profile="p")
        assert page.count('<article class="call"') == 2

    def test_filters_offer_every_observed_player_phase_and_tool(self, tmp_path) -> None:
        """絞り込みの選択肢は実際に出現した player / phase / tool から作る。"""
        run_dir = _write(
            tmp_path,
            [
                _call(player_id=1, name="エイダ", phase="one_step", tool="speak"),
                _call(player_id=2, name="ノア", phase="assess_phase", tool="explore"),
            ],
        )
        page = render_html(_load_calls(run_dir), run_id="r", profile="p")
        for token in ("エイダ", "ノア", "assess_phase", "speak", "explore"):
            assert token in page

    def test_page_is_self_contained(self, tmp_path) -> None:
        """CSS / JS を内蔵し、外部ホストへの参照を持たない (オフラインで読める)。"""
        run_dir = _write(tmp_path, [_call()])
        page = render_html(_load_calls(run_dir), run_id="r", profile="p")
        assert "<style>" in page and "<script>" in page
        assert "http://" not in page and "https://" not in page

    def test_page_declares_both_themes(self, tmp_path) -> None:
        """閲覧側のテーマに追従できるよう、明暗どちらの配色も宣言する。"""
        run_dir = _write(tmp_path, [_call()])
        page = render_html(_load_calls(run_dir), run_id="r", profile="p")
        assert "prefers-color-scheme: dark" in page
        assert '[data-theme="light"]' in page


class TestToolNamesOf:
    """_tool_names_of が toolsets.jsonl の形の違いを吸収する挙動を保証する。"""

    def test_prefers_the_precomputed_tool_names_list(self) -> None:
        """``tool_names`` があればそれをそのまま使う。"""
        assert _tool_names_of({"tool_names": ["speak", "wait"]}) == ["speak", "wait"]

    def test_falls_back_to_function_names_in_tools(self) -> None:
        """``tool_names`` が無い行では ``tools`` の function.name から組み立てる。"""
        row = {"tools": [{"function": {"name": "explore"}}, {"function": {"name": "speak"}}]}
        assert _tool_names_of(row) == ["explore", "speak"]

    def test_accepts_tools_stored_as_a_json_string(self) -> None:
        """``tools`` が JSON 文字列で入っている場合も解いて名前を取り出す。"""
        row = {"tools": json.dumps([{"function": {"name": "wait"}}])}
        assert _tool_names_of(row) == ["wait"]

    def test_returns_empty_when_nothing_is_resolvable(self) -> None:
        """名前を取れない行では空 list を返し、呼び出し側が「解決できなかった」と
        表示できるようにする (= 捏造しない)。"""
        assert _tool_names_of({}) == []
