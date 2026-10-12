"""Quality-check シナリオ ``prediction_v1``: 予測が外れた経験が次の予測を変えるか。

Issue #526 で議論した「予測 / 期待値の不在」(構造的不在 #3) に対する PR0〜PR3
(予測→学習ループ) の効果を、LLM を呼ばず prompt 構造で点検する baseline harness。

ループの閉じる側を 1 variant で見る (予測と実際を並べる ``immediate`` は、
行動ごとの結果の予想 expected_result と【前回の予測と実際】を消したとき #1631 で外した):

- ``learned``: 予測由来の学び (SemanticMemoryEntry) が既に semantic store にある
  状態で、次に同じ相手に会うターンの prompt。``【関連する学び】`` section にその
  学びが戻り、次の予測を変える材料になっているか (= PR3 のループ閉じ面) を見る。

ハーネス注:
- world_runtime runtime は episodic recall のみ配線し semantic recall
  (``【関連する学び】``) を配線しない。そのため ``learned`` variant は
  prompt builder へ ``SemanticPassiveRecallService`` を white-box 注入する。
- LLM は呼ばない。失敗するのは prompt が組めない等の runtime regression のみ。
  質感の判断は dump された ``.prompt.txt`` を人が読む。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# 循環 import 回避の warm-up (詳細は CLAUDE.md "Parallel Branch Note")。
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.services.semantic_passive_recall_service import (
    SemanticPassiveRecallService,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.runtime_config_helpers import episodic_config

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)
_DUMP_DIR = Path(__file__).resolve().parents[2] / "docs" / "quality_checks"


def _build_runtime():
    from ai_rpg_world.application.world_runtime.world_runtime import (
        create_world_runtime,
    )

    return create_world_runtime(_SCENARIO_PATH, config=episodic_config())


def _resolve_player_id(runtime, name: str) -> PlayerId:
    for spawn in runtime.scenario.player_spawns:
        if spawn.name == name:
            return PlayerId(spawn.player_id)
    raise AssertionError(f"player {name!r} not found in scenario")


def _dump_prompt(variant: str, prompt: dict) -> Path:
    """prompt を ``docs/quality_checks/prediction_v1_<variant>.prompt.txt`` に
    決定論的に書き出す (git diff で前回 PR との変化が見える)。"""
    _DUMP_DIR.mkdir(parents=True, exist_ok=True)
    path = _DUMP_DIR / f"prediction_v1_{variant}.prompt.txt"
    parts: list[str] = []
    parts.append(f"# prediction_v1 / {variant}\n")
    parts.append(
        "# このファイルは tests/quality/test_prediction_v1.py から再生成される。\n"
        "# 手で編集しないこと。baseline 所感は prediction_v1_baseline.md に書く。\n\n"
    )
    for i, msg in enumerate(prompt.get("messages", [])):
        role = msg.get("role", "?")
        content = msg.get("content", "")
        parts.append(f"=== messages[{i}] role={role} ===\n{content}\n")
    parts.append("\n=== tools ===\n")
    for tool in prompt.get("tools", []) or []:
        if isinstance(tool, dict):
            fn = tool.get("function", {})
            name = fn.get("name") if isinstance(fn, dict) else None
            parts.append(f"- {name or tool.get('name') or '?'}\n")
        else:
            parts.append(f"- {tool}\n")
    path.write_text("".join(parts), encoding="utf-8")
    return path


def _user_content(prompt: dict) -> str:
    return "\n".join(
        m.get("content", "") for m in prompt.get("messages", []) if m.get("role") == "user"
    )


@pytest.mark.quality
class TestPredictionV1Baseline:
    """``prediction_v1`` シナリオの learned variant を回し、prompt を dump する。

    LLM は呼ばない。assert は runtime regression 検知の sanity のみ。
    質感の判断は dump された ``.prompt.txt`` を人が読む。
    """

    def _seed_prediction_learning(self, runtime, rin_id: PlayerId) -> SemanticPassiveRecallService:
        """予測由来の学びを semantic store にシードし、recall service を返す。"""
        rin_being = runtime.aux_being_resolver.resolve_being_id(
            runtime.aux_being_default_world_id, rin_id
        )
        assert rin_being is not None
        store = InMemorySemanticMemoryStore()
        store.add_by_being(
            rin_being,
            SemanticMemoryEntry(
                entry_id="sem-noa-mood",
                player_id=int(rin_id.value),
                being_id=rin_being,
                text="QUALITY_MARKER_LEARNED: ノアは機嫌が悪いと、話しかけても無視することがある",
                evidence_episode_ids=("ep-noa-1",),
                confidence=0.7,
                created_at=datetime.now(timezone.utc) - timedelta(hours=2),
                importance_score=8,
                tags=("ノア", "会話"),
            ),
        )
        return SemanticPassiveRecallService(
            store,
        )

    def _push_noa_encounter(self, runtime, rin_id: PlayerId) -> None:
        """次にノアに会う場面の観測を流す (= 次の予測を立てる状況)。"""
        runtime._obs_buffer.append(
            rin_id,
            ObservationEntry(
                occurred_at=datetime.now(timezone.utc),
                output=ObservationOutput(
                    prose="ノアが広間に現れた。こちらをちらりと見ている。",
                    structured={
                        "type": "entity_appeared",
                        "about": "ノア",
                    },
                    observation_category="social",
                    schedules_turn=True,
                ),
                game_time_label=None,
            ),
        )

    def test_learned_baseline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """learned variant: 予測由来の学びが【関連する学び】に戻り、次の予測を
        変える材料になっているか。

        world_runtime runtime は semantic recall を配線しないため、prompt builder に
        SemanticPassiveRecallService を white-box 注入する。
        """
        runtime = _build_runtime()
        rin_id = _resolve_player_id(runtime, "リン")
        recall_svc = self._seed_prediction_learning(runtime, rin_id)
        # world_runtime runtime の prompt builder へ semantic recall を注入
        builder = runtime._get_or_build_default_prompt_builder()
        builder._semantic_passive_recall = recall_svc
        builder._semantic_passive_top_k = 3
        # 次にノアに会う場面
        self._push_noa_encounter(runtime, rin_id)
        prompt = runtime.build_full_prompt(rin_id)
        dump_path = _dump_prompt("learned", prompt)
        assert dump_path.exists()
        user = _user_content(prompt)
        # 予測由来の学びが prompt に戻っている (= 次の予測を変える材料)
        assert "【関連する学び】" in user, "semantic recall section が出ていない"
        assert "QUALITY_MARKER_LEARNED" in user, "予測由来の学びが prompt に戻っていない"
