"""world_runtime の scenario.metadata.llm_objective_text 駆動の挙動を保証する。

PR-B: 旧 _ESCAPE_GAME_OBJECTIVE_TEXT (「廃墟から外へ脱出する」) という world_runtime
シナリオ専用ハードコードを撤廃し、scenario JSON の llm_objective_text に勝利条件文を
書く設計に切り替えた。

C run v3 で survival_island_v2 を走らせても LLM の objective に「廃墟脱出」が出てしまい、
誰も狼煙台に向かわず物資収集と廃屋探索に陥った silent failure が起きた。同種の失敗を
構造的に塞ぐためのテスト群。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import (
    create_world_runtime,
)


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SURVIVAL_V2 = _REPO_ROOT / "data" / "scenarios" / "survival_island_v2.json"
_ABANDONED = _REPO_ROOT / "data" / "scenarios" / "abandoned_hospital.json"


class TestScenarioObjectiveDrivesPrompt:
    """シナリオ JSON の llm_objective_text が LLM 用 prompt にそのまま届く。"""

    def test_survival_island_v2_objective_mentions_signal_fire_and_summit(self) -> None:
        """survival_island_v2 の objective section に「狼煙」と「山頂 (summit)」が含まれる。

        旧 hardcoded「廃墟から外へ脱出」では絶対に出てこなかった概念。これが出るように
        なって初めて、LLM agent が救助フローを優先するベースが整う。
        """
        runtime = create_world_runtime(_SURVIVAL_V2)
        player_id = runtime.get_player_ids()[0]
        prompt = runtime.build_full_prompt(player_id)
        user = prompt["messages"][1]["content"]

        assert "【現在の目的】" in user
        assert "狼煙" in user
        assert "山頂" in user or "summit" in user.lower()
        # 旧 hardcoded が再混入していないことを保証
        assert "廃墟から外へ脱出する" not in user

    def test_abandoned_hospital_objective_still_mentions_escape(self) -> None:
        """abandoned_hospital のように本来「脱出」が目的のシナリオではちゃんと「脱出」と出る。

        ハードコード削除によって脱出系シナリオが壊れていないことを保証する。
        """
        runtime = create_world_runtime(_ABANDONED)
        player_id = runtime.get_player_ids()[0]
        prompt = runtime.build_full_prompt(player_id)
        user = prompt["messages"][1]["content"]

        assert "【現在の目的】" in user
        assert "脱出" in user


class TestScenarioObjectiveFailFast:
    """llm_objective_text が空のシナリオでは構築時に ValueError を投げる (fail-fast)。"""

    def test_empty_llm_objective_text_raises_value_error(self, tmp_path: Path) -> None:
        """llm_objective_text が空のシナリオで build_full_prompt 経路に入ると ValueError。

        fallback を持たない設計の保証: シナリオ A の objective を別シナリオで流用したり、
        書き忘れたまま LLM を回したりする silent failure を構造的に塞ぐ。
        """
        import json

        # abandoned_hospital をコピーして llm_objective_text を空にしたシナリオを作る
        original = json.loads(_ABANDONED.read_text(encoding="utf-8"))
        original["metadata"]["llm_objective_text"] = ""
        broken_path = tmp_path / "broken_no_objective.json"
        broken_path.write_text(
            json.dumps(original, ensure_ascii=False), encoding="utf-8"
        )

        runtime = create_world_runtime(broken_path)
        player_id = runtime.get_player_ids()[0]
        with pytest.raises(ValueError) as exc_info:
            runtime.build_full_prompt(player_id)

        # メッセージにシナリオ id とフィールド名のヒントが含まれる
        assert "llm_objective_text" in str(exc_info.value)

    def test_missing_llm_objective_text_field_also_raises(self, tmp_path: Path) -> None:
        """llm_objective_text のキー自体が無いシナリオも同じく ValueError。"""
        import json

        original = json.loads(_ABANDONED.read_text(encoding="utf-8"))
        del original["metadata"]["llm_objective_text"]
        broken_path = tmp_path / "broken_missing_objective.json"
        broken_path.write_text(
            json.dumps(original, ensure_ascii=False), encoding="utf-8"
        )

        runtime = create_world_runtime(broken_path)
        player_id = runtime.get_player_ids()[0]
        with pytest.raises(ValueError):
            runtime.build_full_prompt(player_id)
