"""知らない条件の種類を、読み込み時に落とす。

## 綴り間違いが永久に発火しない出来事を作っていた

``scenario_events`` の条件は文字列で、読み込みは何も照合していなかった。
評価器は知らない種類を False に落とす。

    {"condition_type": "TICK_AT_LEATS", "value": 3}
    → 読み込みが通り、この出来事は永久に発火しない

**誰も気づけない。** 例外も警告も出ず、ただ何も起きない。

これから妨害 (照明を落とす / 扉を閉める / 時間で悪化する) を書く予定で、
条件を大量に並べることになる。1 文字の違いが「なぜか妨害が起きない」に
なる前に塞ぐ。

## 行動の前提条件のほうは落ちていた。ただし生の例外で

``preconditions`` の ``condition_type`` は enum を引くので綴り間違いで
``KeyError`` になっていた。落ちること自体は正しいが、**呼び出し側が
捕まえているのは ``ScenarioLoadError``** なので読み込みの入口を素通りし、
どこが悪いかも分からなかった。同じ形に揃える。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    KNOWN_CONDITION_TYPES,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)

_DRILL = (
    Path(__file__).resolve().parents[3] / "data" / "scenarios" / "station_drill.json"
)


def _load_with(tmp_path: Path, mutate) -> None:
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "probe.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    ScenarioLoader().load_from_file(path)


def _with_event(condition_type: str):
    def mutate(raw: dict) -> None:
        raw.setdefault("scenario_events", []).append({
            "id": "probe",
            "trigger": "ON_TICK",
            "conditions": [{"condition_type": condition_type, "tick": 3}],
            "effects": [
                {"effect_type": "SET_FLAG", "parameters": {"flag": "x", "value": True}}
            ],
        })

    return mutate


class TestAMisspelledEventConditionIsRejected:
    """出来事の条件の綴り間違いが、読み込みで落ちる。"""

    def test_an_unknown_type_stops_the_load(self, tmp_path) -> None:
        """評価器が知らない種類を書くと落ちる。"""
        with pytest.raises(ScenarioLoadError) as caught:
            _load_with(tmp_path, _with_event("TICK_AT_LEATS"))

        assert "TICK_AT_LEATS" in str(caught.value)

    def test_the_message_says_where_to_look(self, tmp_path) -> None:
        """どの出来事のどの条件かと、使える種類が文面に出る。

        **落とすだけでは直せない。** 綴り間違いは正しい綴りが分かって
        初めて直せる。
        """
        with pytest.raises(ScenarioLoadError) as caught:
            _load_with(tmp_path, _with_event("TICK_AT_LEATS"))

        message = str(caught.value)
        assert "scenario_event[probe].conditions[0]" in message
        assert "TICK_AT_LEAST" in message

    def test_a_correct_type_still_loads(self, tmp_path) -> None:
        """正しい種類はそのまま通る。

        **「常に落ちる」でも上の 2 件は通る**ので、通る側を一緒に見る。
        """
        _load_with(tmp_path, _with_event("TICK_AT_LEAST"))

    def test_a_nested_child_is_checked_too(self, tmp_path) -> None:
        """入れ子の子条件も見る。

        ``AND`` の中に隠れた綴り間違いを見逃すと、**入れ子にした瞬間に
        検査が効かなくなる**。
        """

        def mutate(raw: dict) -> None:
            raw.setdefault("scenario_events", []).append({
                "id": "nested",
                "trigger": "ON_TICK",
                "conditions": [{
                    "condition_type": "AND",
                    "children": [
                        {"condition_type": "TICK_AT_LEAST", "tick": 1},
                        {"condition_type": "FLAG_SETT", "flag_name": "x"},
                    ],
                }],
                "effects": [
                    {
                        "effect_type": "SET_FLAG",
                        "parameters": {"flag": "x", "value": True},
                    }
                ],
            })

        with pytest.raises(ScenarioLoadError) as caught:
            _load_with(tmp_path, mutate)

        assert "FLAG_SETT" in str(caught.value)


class TestAMisspelledPreconditionIsRejectedTheSameWay:
    """行動の前提条件の綴り間違いも、同じ形で落ちる。"""

    def _typo_first_precondition(self, raw: dict) -> None:
        done: list[int] = []

        def walk(node) -> None:
            if isinstance(node, dict):
                if node.get("condition_type") == "PLAYER_STATE_IS" and not done:
                    node["condition_type"] = "PLAYER_STATE_1S"
                    done.append(1)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(raw)
        assert done, "PLAYER_STATE_IS が 1 つも無いなら、この節は何も守れない"

    def test_it_raises_the_loaders_own_error(self, tmp_path) -> None:
        """生の ``KeyError`` ではなく ``ScenarioLoadError`` になる。

        呼び出し側が捕まえているのはこちら。生の例外だと**読み込みの入口を
        素通りして**、どこが悪いかも分からない。
        """
        with pytest.raises(ScenarioLoadError) as caught:
            _load_with(tmp_path, self._typo_first_precondition)

        assert "PLAYER_STATE_1S" in str(caught.value)
        assert "PLAYER_STATE_IS" in str(caught.value)


class TestTheTableMatchesWhatTheEvaluatorCanDo:
    """照合に使う表が、評価器の分岐と一致している。"""

    def test_no_branch_is_missing_from_the_table(self) -> None:
        """評価器が判定できる種類は、すべて表に載っている。

        **載せ忘れると、正しい条件が読み込みで落ちる。** 分岐を足した人が
        表を忘れる形は、このリポジトリで今週 6 回起きている。

        本文から ``ctype == "..."`` を拾って突き合わせる。合成条件は
        別経路で扱うので手で足す。
        """
        source = Path(
            "src/ai_rpg_world/application/world_graph/scenario_condition_evaluator.py"
        ).read_text(encoding="utf-8")
        in_branches = set(re.findall(r'ctype == "([A-Z_]+)"', source)) | {
            "NOT",
            "AND",
            "OR",
        }

        assert in_branches, "分岐が 1 つも見つからないなら、この節は何も守れない"
        assert in_branches - KNOWN_CONDITION_TYPES == set(), (
            "評価器が判定できるのに表に無い種類がある"
        )

    def test_no_table_entry_is_dead(self) -> None:
        """表に載っている種類は、すべて評価器が判定できる。

        載せたが実装が無い種類は、**書けるのに常に偽**という別の静かな
        失敗になる。
        """
        source = Path(
            "src/ai_rpg_world/application/world_graph/scenario_condition_evaluator.py"
        ).read_text(encoding="utf-8")
        in_branches = set(re.findall(r'ctype == "([A-Z_]+)"', source)) | {
            "NOT",
            "AND",
            "OR",
        }

        assert KNOWN_CONDITION_TYPES - in_branches == set(), (
            "表にあるのに評価器が判定できない種類がある"
        )


class TestEveryShippedScenarioStillLoads:
    """同梱のシナリオが、新しい検査を通る。"""

    @pytest.mark.parametrize(
        "path",
        sorted((_DRILL.parent).glob("*.json")),
        ids=lambda p: p.name,
    )
    def test_it_loads(self, path: Path) -> None:
        """既存のシナリオを 1 本も壊していない。

        **検査を足すと、既に書かれているものが落ちうる。** 全部読み込んで
        確かめる。
        """
        ScenarioLoader().load_from_file(path)
