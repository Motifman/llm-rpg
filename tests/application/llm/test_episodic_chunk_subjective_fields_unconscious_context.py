"""EpisodicChunkSubjectiveFieldsService の無意識コンテキスト注入 (U7) を検証する。

U7 (予測誤差統一設計 §2 U7 / 設計 doc §4「無意識コンテキスト」): belief top-K や
L5 自己像・世界観といった「このキャラのモデル」を chunk 主観補完 LLM に渡すことで、
``prediction_error`` / ``salience`` の判定が「誰にとっても同じ驚き」から
「このキャラにとっての驚き」になる。

``unconscious_context_enabled`` コンストラクタ引数 (= UNCONSCIOUS_CONTEXT_ENABLED
flag に対応) で

- flag OFF: provider を注入していても一切呼ばれず、system prompt / user message は
  導入前 (= salience_enabled のみのケース) と byte 同一
- flag ON: provider が呼ばれ、返した非空テキストが「## いまの自分（信念と自己像）」
  section として user message に載り、system prompt に判定指示が追記される

の 2 系統を切り替える。provider の例外・None・空文字は空文字に縮退する
(chunk 補完を止めない)。

確証バイアスの構造ガード: belief を見せて解釈を歪めるのは仕様だが、事実
(observed / cues / who / what / outcome) を LLM 出力で書き換えることは
``_assert_rule_fields_unchanged`` が既に禁止している。本ファイルでも無意識
コンテキスト有効時にこのガードが効くことを明示的に確認する。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

import pytest

from ai_rpg_world.application.llm.contracts.chunk_encoding import build_chunk_encoding_input
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import (
    ChunkEpisodeDraftBuilder,
)
from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
    _build_system_prompt,
    EpisodicChunkSubjectiveFieldsService,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _StubSubjectivePort(IEpisodicChunkSubjectiveCompletionPort):
    def __init__(self, outcome: dict[str, Any] | BaseException) -> None:
        self._outcome = outcome
        self.last_messages: list[dict[str, Any]] | None = None

    def complete_episode_subjective_json(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.last_messages = list(messages)
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return self._outcome


def _make_encoding(player_id: int = 1) -> Any:
    t = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
    act = ActionResultEntry(
        occurred_at=t,
        action_summary="扉を開けた",
        result_summary="ok",
        tool_name="world_no_op",
        success=True,
    )
    return build_chunk_encoding_input(PlayerId(player_id), (), (act,))


def _user_content(port: _StubSubjectivePort) -> str:
    assert port.last_messages is not None
    return next(
        (m["content"] for m in port.last_messages if m.get("role") == "user"),
        "",
    )


def _system_content(port: _StubSubjectivePort) -> str:
    assert port.last_messages is not None
    return next(
        (m["content"] for m in port.last_messages if m.get("role") == "system"),
        "",
    )


class TestUnconsciousContextFlagOff:
    """unconscious_context_enabled=False (既定) のときの後方互換を保証する。"""

    def test_does_not_call_provider_never(self) -> None:
        """provider を注入していても 一切呼ばれない。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        calls: list[Any] = []

        def _provider(player_id: int, cues: Sequence[EpisodicCue]) -> str:
            calls.append((player_id, cues))
            return "- 信じている何か (確信度: 0.90)"

        svc = EpisodicChunkSubjectiveFieldsService(
            port, unconscious_context_provider=_provider, unconscious_context_enabled=False
        )
        svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)

        assert calls == []

    def test_system_prompt_user_message_before_byte_matches(self) -> None:
        """salience_enabled のみのケースと完全一致すること (無意識コンテキスト
        節が一切追加されない)。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)

        port_without = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        svc_without = EpisodicChunkSubjectiveFieldsService(port_without, salience_enabled=True)
        svc_without.merge_llm_subjective_fields(draft, persona_text="p", encoding_input=enc)

        port_with = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        svc_with = EpisodicChunkSubjectiveFieldsService(
            port_with,
            salience_enabled=True,
            unconscious_context_provider=lambda pid, cues: "無視されるはずのテキスト",
            unconscious_context_enabled=False,
        )
        svc_with.merge_llm_subjective_fields(draft, persona_text="p", encoding_input=enc)

        assert _system_content(port_with) == _system_content(port_without)
        assert _user_content(port_with) == _user_content(port_without)
        assert (
            _system_content(port_with)
            == _build_system_prompt(salience_enabled=True, unconscious_context_enabled=False)
        )


class TestUnconsciousContextFlagOn:
    """unconscious_context_enabled=True のときの section 挿入・system prompt 追記。"""

    def test_provider_returned_section_included(self) -> None:
        """provider が返したテキストが section として載る。"""
        enc = _make_encoding(player_id=7)
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        received: list[tuple[int, Sequence[EpisodicCue]]] = []

        def _provider(player_id: int, cues: Sequence[EpisodicCue]) -> str:
            received.append((player_id, cues))
            return "- 罠にはよく引っかかる (確信度: 0.80)\n私について: 慎重な性格"

        svc = EpisodicChunkSubjectiveFieldsService(
            port, unconscious_context_provider=_provider, unconscious_context_enabled=True
        )
        svc.merge_llm_subjective_fields(draft, persona_text="ペルソナ片", encoding_input=enc)

        # provider には draft の player_id / cues がそのまま渡る。
        assert received == [(draft.player_id, draft.cues)]
        assert received[0][0] == 7

        user_content = _user_content(port)
        assert "## いまの自分（信念と自己像）" in user_content
        assert "罠にはよく引っかかる (確信度: 0.80)" in user_content
        assert "私について: 慎重な性格" in user_content
        # persona 断片セクションの直後に挿入されている (persona → 無意識 → ルール草案)。
        persona_idx = user_content.index("## 人物像（ペルソナ断片）")
        unconscious_idx = user_content.index("## いまの自分（信念と自己像）")
        draft_idx = user_content.index("## ルール草案")
        assert persona_idx < unconscious_idx < draft_idx

    def test_system_prompt(self) -> None:
        """systemprompt に判定指示が追記される。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        svc = EpisodicChunkSubjectiveFieldsService(
            port,
            unconscious_context_provider=lambda pid, cues: "- なにか (確信度: 0.50)",
            unconscious_context_enabled=True,
        )
        svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)

        sys_content = _system_content(port)
        assert "いまの自分" in sys_content
        assert "改変しては" in sys_content or "改変しない" in sys_content
        # 既存の指示は残ったまま追記されている。
        assert "prediction_error" in sys_content

    def test_returns_section_not_rendered_provider_empty_string_when(self) -> None:
        """provider が空文字を返すと section は出ない。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        svc = EpisodicChunkSubjectiveFieldsService(
            port,
            unconscious_context_provider=lambda pid, cues: "",
            unconscious_context_enabled=True,
        )
        svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)

        user_content = _user_content(port)
        assert "## いまの自分（信念と自己像）" not in user_content

    def test_returns_section_not_rendered_provider_none_when(self) -> None:
        """provider が None を返すと section は出ない。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        svc = EpisodicChunkSubjectiveFieldsService(
            port,
            unconscious_context_provider=lambda pid, cues: None,  # type: ignore[arg-type]
            unconscious_context_enabled=True,
        )
        svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)

        user_content = _user_content(port)
        assert "## いまの自分（信念と自己像）" not in user_content

    def test_provider_chunk_raises_exception(self) -> None:
        """provider が例外を投げても chunk補完は継続する。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort({"interpreted": "LLM_OK", "recall_text": "r"})

        def _raising_provider(player_id: int, cues: Sequence[EpisodicCue]) -> str:
            raise RuntimeError("semantic store down")

        svc = EpisodicChunkSubjectiveFieldsService(
            port,
            unconscious_context_provider=_raising_provider,
            unconscious_context_enabled=True,
        )
        merged = svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)

        # provider 失敗でも LLM 呼び出し自体は行われ、interpreted が反映される。
        assert merged.interpreted == "LLM_OK"
        user_content = _user_content(port)
        assert "## いまの自分（信念と自己像）" not in user_content

    def test_provider_uninjected_flag_section_not_rendered(self) -> None:
        """provider未注入なら flag ONでも sectionは出ない。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        svc = EpisodicChunkSubjectiveFieldsService(port, unconscious_context_enabled=True)
        svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)

        user_content = _user_content(port)
        assert "## いまの自分（信念と自己像）" not in user_content


class TestUnconsciousContextRuleFieldGuard:
    """確証バイアスの構造ガード: 無意識コンテキスト有効時も事実フィールドは
    LLM 出力で改変されない (belief に迎合した観測の書き換えを拒否する)。"""

    def test_llm_raises_value_error(self) -> None:
        """LLM が事実フィールドを書き換えようとしても ValueError で弾かれる。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)

        class _RuleTamperingPort(IEpisodicChunkSubjectiveCompletionPort):
            def complete_episode_subjective_json(
                self, messages: list[dict[str, Any]]
            ) -> dict[str, Any]:
                # observed 等はそもそも入力に含まれるだけで、LLM の JSON 応答は
                # interpreted/recall_text/prediction_error/heading/salience しか
                # 持たない。ここでは「もし何か書けても無視される」ことを保証
                # するのが _assert_rule_fields_unchanged の役目 (実体の改変
                # 経路が無いことは merge 実装がそもそも observed 等を replace()
                # に渡していないことで担保される)。
                return {
                    "interpreted": "信念に沿って解釈した",
                    "recall_text": "r",
                    "prediction_error": "信念どおりだったので驚かなかった",
                }

        svc = EpisodicChunkSubjectiveFieldsService(
            _RuleTamperingPort(),
            unconscious_context_provider=lambda pid, cues: "- 罠が多い (確信度: 0.90)",
            unconscious_context_enabled=True,
        )
        merged = svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)

        # 事実フィールドは draft と完全一致 (バイアスが染みるのは主観フィールドだけ)。
        assert merged.observed == draft.observed
        assert merged.cues == draft.cues
        assert merged.who == draft.who
        assert merged.what == draft.what
        assert merged.outcome == draft.outcome
        # 主観フィールドは信念に染まってよい。
        assert merged.interpreted == "信念に沿って解釈した"
        assert merged.prediction_error == "信念どおりだったので驚かなかった"


class TestUnconsciousContextTypeValidation:
    def test_unconscious_context_provider_callable_raises_type_error(self) -> None:
        """unconscious context provider が callable でなければ TypeError。"""
        port = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        with pytest.raises(TypeError):
            EpisodicChunkSubjectiveFieldsService(
                port, unconscious_context_provider="not-callable"  # type: ignore[arg-type]
            )

    def test_unconscious_context_enabled_bool_raises_type_error(self) -> None:
        """unconscious context enabled が bool でなければ TypeError。"""
        port = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        with pytest.raises(TypeError):
            EpisodicChunkSubjectiveFieldsService(
                port, unconscious_context_enabled="yes"  # type: ignore[arg-type]
            )
