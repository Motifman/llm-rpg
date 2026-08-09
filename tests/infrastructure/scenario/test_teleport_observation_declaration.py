"""転移の観測文の宣言ミスが、起動時に止まることを保証する。

## なぜ起動時なのか

どの誤記も**静かに既定文へ縮退する**。綴り違いの鍵は誰も読まず、非文字列は None へ
落ち、未知のプレースホルダは展開されないまま出る。書いた作家から見ると「書いたのに
効かない」で、実行してみるまで気づけない。

対象 spot の欠落を読み込み時に落としているのと同じ理由で、ここも起動時に止める。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoadError

_DRILL = (
    Path(__file__).resolve().parents[3] / "data" / "scenarios" / "station_drill.json"
)


def _scenario_with(mutate) -> Path:
    scenario = json.loads(_DRILL.read_text(encoding="utf-8"))
    touched = 0
    for spot in scenario["spots"]:
        for obj in (spot.get("interior") or {}).get("objects") or []:
            for interaction in obj.get("interactions") or []:
                if interaction["action_name"].startswith("enter_vent"):
                    mutate(interaction["effects"][0]["parameters"])
                    touched += 1
    assert touched, "通気口の宣言が無いなら、この試験は何も守っていない"
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(scenario, handle, ensure_ascii=False)
    handle.close()
    return Path(handle.name)


class TestDeclaredObservationMistakesStopTheRun:
    """4 種類の誤記が、どれも読み込み時に落ちる。"""

    def test_the_unmodified_scenario_still_loads(self) -> None:
        """正の対照。手を加えなければ読み込めることを先に見る。"""
        assert create_world_runtime(_scenario_with(lambda params: None)) is not None

    def test_a_non_string_message_is_rejected(self) -> None:
        """数値を書くと、黙って既定文へ縮退せず読み込み時に落ちる。"""
        path = _scenario_with(
            lambda params: params.__setitem__("departure_observation_message", 42)
        )

        with pytest.raises(ScenarioLoadError, match="must be a string"):
            create_world_runtime(path)

    def test_a_misspelled_key_is_rejected(self) -> None:
        """鍵の綴りを間違えると、誰にも読まれないまま通さない。"""
        path = _scenario_with(
            lambda params: params.__setitem__("arrival_observation_mesage", "出た")
        )

        with pytest.raises(ScenarioLoadError, match="unknown parameters"):
            create_world_runtime(path)

    def test_an_unknown_placeholder_is_rejected(self) -> None:
        """展開されないプレースホルダは、そのまま観測に出る前に落とす。"""
        path = _scenario_with(
            lambda params: params.__setitem__(
                "arrival_observation_message", "{Actor}が出た"
            )
        )

        with pytest.raises(ScenarioLoadError, match="not a known placeholder"):
            create_world_runtime(path)

    def test_an_empty_message_is_rejected(self) -> None:
        """空文字は既定文と区別できないので、鍵ごと外させる。"""
        path = _scenario_with(
            lambda params: params.__setitem__("arrival_observation_message", "")
        )

        with pytest.raises(ScenarioLoadError, match="must not be empty"):
            create_world_runtime(path)

    @pytest.mark.parametrize(
        "broken", ["{actorが出た", "actorが出た}", "{{actor}が出た"]
    )
    def test_an_unbalanced_brace_is_rejected(self, broken: str) -> None:
        """波括弧が揃わない書き損じも落とす。

        閉じた ``{...}`` だけを見る検査では、``{actor`` や ``actor}`` が
        すり抜ける。formatter は完全一致しか置換しないので、**未展開のまま
        観測へ出る**。``{Actor}`` と同じ静かな誤記なので同じ扱いにする。
        """
        path = _scenario_with(
            lambda params: params.__setitem__("arrival_observation_message", broken)
        )

        with pytest.raises(ScenarioLoadError, match="brace"):
            create_world_runtime(path)

