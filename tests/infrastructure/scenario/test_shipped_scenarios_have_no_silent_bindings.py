"""出荷シナリオに「状態を変えるのに観測を出さない」binding が無いことを監査する。

## なぜこの試験が要るか

`scenario_loader` は #383 で、完全に無音な reactive object binding を読み込み時に
warning するようになった。しかし **warning は構造ではない。**

- `scripts/run_scenario_experiment.py` の logging は `format="%(message)s"` で
  FileHandler も無い。警告は run 冒頭の stderr に**レベル名なしの 1 行**として
  流れるだけで、`OUT` 配下 (`trace.jsonl` / `report.md` /
  `experiment.config.resolved.json`) には一切残らない
- つまり `docs/trace_observability_review.md` の手順で run 後に確認しても検出でき
  ない。見落とせば、状態だけ静かに変わるシナリオがそのまま実験に乗る

#383 の作業では `relay_puzzle_demo.json` を直して `data/scenarios` の警告を 0 件に
した。**しかしその状態を守る仕組みが無かった** (レビュー指摘)。次に誰かが無音の
binding を持つシナリオを足しても、標準出力に 1 行流れるだけで CI は緑になる。

そこで corpus 全体を走査して落とす。既に
`test_interaction_action_name_audit.py` が同じ形 (全シナリオ走査 + hard assert) を
取っており、それに倣う。

## 意図的な無音はどう書くか

`"narrative_on_true": ""` を明示する。空文字は formatter 上 narrative 無しと同じく
無音だが、**書き忘れではないという著者の意思表示**になる。この試験も loader の
warning も、空文字を無音の明示として扱って通す。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, List, NamedTuple

from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    SILENT_REACTIVE_OBJECT_BINDING_WARNING as _SILENT_BINDING,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

_REPO_ROOT = Path(__file__).resolve().parents[3]

#: 出荷しているシナリオ。実験で実際に読まれるものだけを対象にする。
#: `tests/fixtures/scenarios/` は検査対象に含める (テスト出力に警告が鳴り続けると
#: 人が警告を無視するようになるので、出荷と同じ基準で扱う)。
_SCENARIO_DIRS = (
    _REPO_ROOT / "data" / "scenarios",
    _REPO_ROOT / "tests" / "fixtures" / "scenarios",
)


class _SilentBinding(NamedTuple):
    """観測を出さない binding 1 件を、直せる位置情報つきで表す。"""

    scenario: str
    index: int
    target: Any

    def __str__(self) -> str:  # pragma: no cover - 失敗表示用
        return f"{self.scenario} reactive_bindings.objects[{self.index}] target={self.target}"


def _scenario_files() -> List[Path]:
    return sorted(p for d in _SCENARIO_DIRS if d.is_dir() for p in d.glob("*.json"))


def _silent_bindings_by_reading_the_json(path: Path) -> List[_SilentBinding]:
    """JSON を直接読んで、無音な object binding を数える。

    loader を通さないのは、loader が落ちるシナリオ (別の理由で不正なもの) でも
    この監査を成立させるため。判定条件は loader 側と同じ ``is None`` を使う。
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, dict):
        return []
    objects = ((raw.get("reactive_bindings") or {}).get("objects") or [])
    out: List[_SilentBinding] = []
    for i, binding in enumerate(objects):
        if not isinstance(binding, dict):
            continue
        if (
            binding.get("narrative_on_true") is None
            and binding.get("narrative_on_false") is None
        ):
            out.append(_SilentBinding(path.name, i, binding.get("target")))
    return out


class TestTheAuditActuallyReadsSomething:
    """走査が空振りしていない。"""

    def test_every_configured_directory_contributes_scenarios(self) -> None:
        """``_SCENARIO_DIRS`` の**どのディレクトリからも** 1 本以上見つかる。

        当初は「合計 1 本以上」だけを見ていた。変異で走査先の片方
        (``data/scenarios``) を存在しないパスへ変えると、``tests/fixtures`` 側が
        生きているので **4 passed で素通りした**。合計で見ると片方の欠落が隠れる。

        走査先ごとに要求すれば、どちらが欠けても落ちる。
        """
        empty = [d for d in _SCENARIO_DIRS if not sorted(d.glob("*.json"))]

        assert not empty, (
            f"シナリオが 1 本も見つからない走査先があります: {empty}。"
            f" パス構成が変わると監査が静かに対象 0 件になります。"
        )

    def test_object_bindings_exist_somewhere_in_the_corpus(self) -> None:
        """corpus のどこかに reactive object binding が存在する。

        binding が 1 件も無ければ「無音な binding は無い」は自明に成立してしまう。
        監査が意味を持つ前提をここで固定する。
        """
        total = sum(
            len(((json.loads(p.read_text(encoding="utf-8")) or {}).get(
                "reactive_bindings") or {}).get("objects") or [])
            for p in _scenario_files()
            if p.read_text(encoding="utf-8").strip().startswith("{")
        )

        assert total > 0, "reactive_bindings.objects が corpus に 1 件もありません。"


class TestShippedScenariosHaveNoSilentObjectBindings:
    """状態を変えるのに観測を出さない binding が、出荷シナリオに無い。"""

    def test_no_silent_object_binding_is_shipped(self) -> None:
        """どのシナリオにも「どちらの向きにも narrative が無い」binding が無い。

        意図的な無音なら ``"narrative_on_true": ""`` を書く。空文字は無音の明示と
        して通る。書き忘れならその向きに観測文を書く。
        """
        silent = [b for p in _scenario_files() for b in _silent_bindings_by_reading_the_json(p)]

        assert not silent, (
            "状態を変えるのに観測を一切出さない reactive object binding があります。"
            " 意図的な無音なら narrative_on_true=\"\" を明示し、書き忘れなら観測文を"
            f" 書いてください:\n" + "\n".join(f"  - {b}" for b in silent)
        )

    def test_loading_every_scenario_emits_no_silent_binding_warning(
        self, caplog
    ) -> None:
        """実際に loader を通しても、この警告が 1 件も出ない。

        上の試験は JSON を直接読む。判定条件が loader 側とずれていないことを、
        loader を通した結果で確かめる (条件を片方だけ直しても気づけるように)。
        """
        offenders: List[str] = []
        for path in _scenario_files():
            caplog.clear()
            with caplog.at_level(logging.WARNING):
                try:
                    ScenarioLoader().load_from_file(str(path))
                except Exception:
                    # 別の理由で読めないシナリオはこの監査の対象外。
                    continue
            offenders += [
                f"{path.name}: {r.getMessage()}"
                for r in caplog.records
                if _SILENT_BINDING in r.getMessage()
            ]

        assert not offenders, "loader が無音 binding を警告しました:\n" + "\n".join(
            f"  - {o}" for o in offenders
        )
