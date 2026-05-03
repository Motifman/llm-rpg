"""local_experiments/subjective_episode_mvp_vllm_experiment のスキーマ検証・決定論ヘルパのテスト。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_experiment_module():
    path = _PROJECT_ROOT / "local_experiments" / "subjective_episode_mvp_vllm_experiment.py"
    spec = importlib.util.spec_from_file_location("_subj_vllm_exp", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_subj_vllm_exp"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def exp():
    return _load_experiment_module()


class TestOpenAISchemaShape:
    """response_format に渡す JSON Schema の骨格が期待どおりであること。"""

    def test_response_format_has_json_schema_name(self, exp) -> None:
        """strict json_schema と schema キーを含む。"""
        rf = exp.openai_subjective_llm_response_format()
        assert rf.get("type") == "json_schema"
        inner = rf.get("json_schema") or {}
        assert inner.get("name") == "subjective_episode_mvp_llm_fields"
        assert inner.get("strict") is True
        schema = inner.get("schema") or {}
        assert schema.get("additionalProperties") is False
        props = schema.get("properties") or {}
        assert set(props.keys()) == {"interpreted", "recall_text"}
        assert schema.get("required") == ["interpreted", "recall_text"]
        recall_s = props["recall_text"]
        assert recall_s.get("maxLength") == exp.MAX_RECALL_CHARS
        assert recall_s.get("minLength") == 1
        interp_any = props["interpreted"].get("anyOf") or []
        assert len(interp_any) == 2
        str_branch = next(x for x in interp_any if x.get("type") == "string")
        assert str_branch.get("maxLength") == exp.MAX_INTERPRETED_CHARS


class TestParseAndMerge:
    """パース・マージが immutable を維持すること。"""

    def test_parse_llm_object_accepts_null_interpreted(self, exp) -> None:
        """interpreted が null のとき None に正規化される。"""
        i, r, errs = exp.parse_llm_object({"interpreted": None, "recall_text": "短い想起"})
        assert errs == []
        assert i is None
        assert r == "短い想起"

    def test_validate_llm_pair_rejects_long_fields(self, exp) -> None:
        """上限超えでエラーが返る。"""
        errs = exp.validate_llm_pair(
            interpreted="x" * (exp.MAX_INTERPRETED_CHARS + 1),
            recall_text="ok",
        )
        assert errs

    def test_merge_only_changes_interpreted_and_recall(self, exp) -> None:
        """apply_llm_to_draft が who / observed / cues を変えない。"""
        scenarios = exp.scenario_defs()
        draft = scenarios[0]["episode"]
        snap_before = exp.immutable_snapshot(draft)
        merged = exp.apply_llm_to_draft(
            draft,
            interpreted="意味づけ一文",
            recall_text="想起短文",
        )
        assert exp.immutable_snapshot(merged) == snap_before
        assert merged.interpreted == "意味づけ一文"
        assert merged.recall_text == "想起短文"


class TestScenarioDefs:
    """代表フィクスチャが 5 件あること。"""

    def test_five_scenarios(self, exp) -> None:
        """計画どおり 5 ケース。"""
        s = exp.scenario_defs()
        assert len(s) == 5
        for row in s:
            assert "id" in row and "episode" in row


class TestCharacterPersonaFromCharactersJson:
    """data/characters.json 由来の正式ペルソナが読み込めること。"""

    def test_load_default_gate_character(self, exp) -> None:
        """既定名「門前の少女」で personality_tags 等を含む dict が得られる。"""
        p = exp.load_character_persona_for_experiment()
        assert p["name"] == "門前の少女"
        assert p["first_person"] == "わたし"
        assert isinstance(p["personality_tags"], list)
        assert isinstance(p["speech_samples"], list)
        assert "values" in p and "strengths" in p
        assert isinstance(p["behavioral_rules"], list)

    def test_unknown_character_id_fails(self, exp, monkeypatch: pytest.MonkeyPatch) -> None:
        """存在しない ID は RuntimeError（短文フォールバックしない）。"""
        monkeypatch.setenv("SUBJECTIVE_EPISODE_VLLM_CHARACTER_ID", "__no_such_character__")
        with pytest.raises(RuntimeError, match="character id="):
            exp.load_character_persona_for_experiment()


class TestUserPromptPayloadWithPersona:
    """user prompt に character_persona・current_situation が含まれること。"""

    def test_prompt_contains_repo_persona_and_situation(self, exp) -> None:
        """runs / 検証で persona block が追える構造であること。"""
        cp = exp.load_character_persona_for_experiment()
        ep = exp.scenario_defs()[0]["episode"]
        payload = exp.build_user_prompt_payload(
            draft=ep,
            character_persona=cp,
            experiment_persona_notes="実験メモ: 語りを抑制",
        )
        assert payload["character_persona"]["name"] == "門前の少女"
        assert "current_situation" in payload
        assert payload["current_situation"]["lines"]["observed"] == ep.observed
        assert "immutable_episode_context" in payload
        assert "source_facts" in payload
        assert payload["experiment_persona_notes"] == "実験メモ: 語りを抑制"
        text = json.dumps(payload, ensure_ascii=False)
        assert "persona_usage_policy" in text
        assert "personality_tags" in text


class TestDryRunPipeline:
    """dry-run 実行経路の最小検証（httpx 不要）。"""

    def test_run_one_case_vllm_dry_run_ok(self, exp) -> None:
        """run_one_case_vllm(dry_run=True) が ok で immutable を保つ。"""
        draft = exp.scenario_defs()[0]["episode"]
        cp = exp.load_character_persona_for_experiment()
        row = exp.run_one_case_vllm(
            draft=draft,
            character_persona=cp,
            experiment_persona_notes=None,
            use_json_schema=True,
            dry_run=True,
        )
        assert row["ok"] is True
        assert row["immutable_ok"] is True
        assert row["http_status"] == 0
        assert row["merged_episode"] is not None
        up = json.loads(row["user_prompt"])
        assert up["character_persona"]["name"] == "門前の少女"
        assert "current_situation" in up


class TestHallucinationHeuristic:
    """簡易ハルシネーション検査のスモーク。"""

    def test_flags_unknown_ascii_word(self, exp) -> None:
        """コーパスに無い長い ASCII 語を検出しうる。"""
        hits = exp.heuristic_hallucination_hits(
            "Zorgonax appeared",
            "想起",
            ["想起"],
        )
        assert "Zorgonax" in hits


class TestSampleFixtureJsonRoundTrip:
    """サンプル fixture を JSON で丸めても検証が通ること（オフライン）。"""

    def test_fixture_payload_serializable(self, exp) -> None:
        """user prompt 用ペイロードが json.dumps 可能。"""
        cp = exp.load_character_persona_for_experiment()
        ep = exp.scenario_defs()[4]["episode"]
        payload = exp.build_user_prompt_payload(
            draft=ep,
            character_persona=cp,
            experiment_persona_notes=None,
        )
        text = json.dumps(payload, ensure_ascii=False)
        assert "immutable_episode_context" in text
        assert "source_facts" in text
        assert "門前の少女" in text
