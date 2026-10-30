"""situation_recall_review が、手法の載せた信念を場面ごとに重ねずに並べ、当否を手法ごとに数える挙動を保証する (#1454)。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.situation_recall_review import build_items, items_id, main, render_html, tally


def _result() -> dict:
    return {
        "run_dir": "runs/x",
        "narrowers": ["a", "b"],
        "texts": {"s1": "空腹なら食べる", "s2": "ノアは川沿いを推した", "s3": "</script><b>x"},
        "players": [
            {
                "name": "リオ",
                "scenes": [
                    {
                        "index": 7,
                        "place": "干潟",
                        "situation": {"いま起きたこと": ["空腹で動けない"]},
                        "old": ["s3"],
                        "new": {"a": ["s1", "s2"], "b": ["s2"]},
                    },
                    {
                        "index": 8,
                        "place": "干潟",
                        "situation": {"いま起きたこと": ["貝を拾った"]},
                        "old": [],
                        "new": {"a": ["s1"], "b": ["s1"]},
                    },
                ],
            }
        ],
    }


class TestBuildItems:
    """場面ごとの行の作り方を保証する。"""

    def test_beliefs_picked_by_several_methods_become_one_row_with_each_rank(self) -> None:
        """2 つの手法が同じ信念を載せたら 1 行にまとめ、手法ごとの順位を持つ。"""
        items = build_items(_result(), ["old", "a", "b"])

        rows = items["scenes"][0]["rows"]
        assert [r["id"] for r in rows] == ["s3", "s1", "s2"]
        assert rows[2]["picks"] == {"a": 2, "b": 1}

    def test_rows_are_numbered_across_scenes(self) -> None:
        """行の番号は場面をまたいで 1 から通しで振る。当否はこの番号で結びつく。"""
        items = build_items(_result(), ["old", "a", "b"])

        assert [r["n"] for s in items["scenes"] for r in s["rows"]] == [1, 2, 3, 4]

    def test_scenes_with_danger_words_are_marked(self) -> None:
        """いま起きたことに体の危険の語があれば、その場面に印を付ける。"""
        items = build_items(_result(), ["a"])

        assert [s["danger"] for s in items["scenes"]] == [True, False]

    def test_results_with_a_fallback_are_rejected(self) -> None:
        """選んだ手法が縮退した場面があれば ValueError で止まる。縮退した場面の 2 字組の結果を、その手法の枠として数えない。"""
        result = _result()
        result["players"][0]["scenes"][1]["fallback"] = {"a": "EmbeddingUnavailableError: timeout"}

        with pytest.raises(ValueError, match="fell back"):
            build_items(result, ["a", "b"])

    def test_a_fallback_of_an_unselected_method_is_ignored(self) -> None:
        """縮退したのが表に入れない手法なら、行は作る。"""
        result = _result()
        result["players"][0]["scenes"][1]["fallback"] = {"c": "timeout"}

        assert build_items(result, ["a", "b"])["scenes"]

    def test_a_belief_without_text_is_rejected(self) -> None:
        """本文の引けない信念があれば ValueError で止まる。「?」の行を黙って作らない。"""
        result = _result()
        del result["texts"]["s2"]

        with pytest.raises(ValueError, match="s2"):
            build_items(result, ["a"])

    def test_a_method_not_in_the_results_is_rejected(self) -> None:
        """結果に無い手法の名前は ValueError になる。空の列を黙って作らない。"""
        with pytest.raises(ValueError, match="c"):
            build_items(_result(), ["a", "c"])


class TestTally:
    """当否を手法ごとに数えることを保証する。"""

    def test_each_method_counts_only_the_rows_it_picked(self) -> None:
        """手法 b は 2 枠 (s2 と 2 場面目の s1)。当否の無い枠は「未」、危険の場面は別にも数える。"""
        items = build_items(_result(), ["old", "a", "b"])

        counts = tally(items, {"3": "Y", "4": "N"})

        assert counts["b"]["all"] == {"Y": 1, "?": 0, "N": 1, "未": 0}
        assert counts["b"]["danger"] == {"Y": 1, "?": 0, "N": 0, "未": 0}
        assert counts["a"]["all"] == {"Y": 1, "?": 0, "N": 1, "未": 1}


class TestHtml:
    """人が当否を付ける表を安全に作ることを保証する。"""

    def test_belief_text_cannot_close_the_script(self) -> None:
        """信念の文に </script> があっても、埋め込んだデータの外に出ない。"""
        page = render_html(build_items(_result(), ["old", "a"]), {})

        assert "</script><b>x" not in page
        assert page.count("</script>") == 1

    def test_the_saved_reviews_are_tied_to_the_rows(self) -> None:
        """ブラウザの保存先の名前に行の中身から作った印が入り、行が変われば保存先も変わる。作り直した行に古い当否が当たらない。"""
        items = build_items(_result(), ["a"])
        other = build_items(_result(), ["a", "b"])

        key = items_id(items)

        assert key in render_html(items, {})
        assert key != items_id(other)

    def test_claude_labels_are_embedded_per_row(self) -> None:
        """Claude の当否は行ごとに埋め込み、人の当否とは別に持つ。"""
        page = render_html(build_items(_result(), ["a"]), {"1": "Y"})

        assert '"c": "Y"' in page


class TestCommandLine:
    """当否の番号を壊す操作を止めることを保証する。"""

    def test_items_do_not_overwrite_existing_rows(self, tmp_path: Path) -> None:
        """行のファイルがあれば、--overwrite が無い限り上書きせずに止まる。"""
        results = tmp_path / "results.json"
        results.write_text(json.dumps(_result()), "utf-8")
        out = tmp_path / "items.json"
        out.write_text("{}", "utf-8")

        with pytest.raises(SystemExit):
            main(["items", "--results", str(results), "--methods", "a", "--out", str(out)])

        assert out.read_text("utf-8") == "{}"

    def test_labels_other_than_y_q_n_are_rejected(self, tmp_path: Path) -> None:
        """当否に Y / ? / N 以外の値があれば ValueError になる。"""
        results = tmp_path / "results.json"
        results.write_text(json.dumps(_result()), "utf-8")
        items = tmp_path / "items.json"
        main(["items", "--results", str(results), "--methods", "a", "--out", str(items)])
        labels = tmp_path / "labels.json"
        labels.write_text(json.dumps({"labels": {"1": "yes"}}), "utf-8")

        with pytest.raises(ValueError, match="yes"):
            main(["tally", "--items", str(items), "--labels", str(labels)])

    def test_labels_made_for_other_rows_are_rejected(self, tmp_path: Path) -> None:
        """書き出した当否の印 (items_id) がいまの行と違えば ValueError で止まる。別の行に当否を当てて数えない。"""
        results = tmp_path / "results.json"
        results.write_text(json.dumps(_result()), "utf-8")
        items = tmp_path / "items.json"
        main(["items", "--results", str(results), "--methods", "a", "--out", str(items)])
        labels = tmp_path / "labels.json"
        labels.write_text(json.dumps({"items_id": "000000000000", "labels": {"1": "Y"}}), "utf-8")

        with pytest.raises(ValueError, match="items_id"):
            main(["tally", "--items", str(items), "--labels", str(labels)])
