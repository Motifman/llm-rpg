from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field, ValidationError

from game.action.action_orchestrator import ActionOrchestrator
from game.llm.config import get_settings
from game.llm.memory import PlayerMemoryStore, MessageBase


class DecisionOutput(BaseModel):
    action_name: str = Field(..., description="ActionOrchestratorに渡す行動名")
    action_args: Dict[str, Any] = Field(default_factory=dict)
    rationale: Optional[str] = Field(default=None)


@dataclass
class DecisionInput:
    player_id: str
    candidates: List[Dict[str, Any]]
    memory: List[MessageBase]
    help_info: Dict[str, Any]
    system_prompt: Optional[str] = None


class LiteLLMClient:
    """litellm を用いたOpenAI互換チャット呼び出し。

    - 単発: completion()
    - バッチ: batch_completion()
    """

    def __init__(self, model: Optional[str] = None):
        from litellm import completion, batch_completion  # lazy import
        self._completion = completion
        self._batch_completion = batch_completion
        self._model = model or get_settings().model

    def complete_json(self, messages: List[Dict[str, str]], temperature: float, max_tokens: int) -> str:
        resp = self._completion(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        # OpenAI 互換の戻り
        return resp["choices"][0]["message"]["content"]

    def batch_complete_json(self, batch_messages: List[List[Dict[str, str]]], temperature: float, max_tokens: int) -> List[str]:
        resps = self._batch_completion(
            model=self._model,
            messages=batch_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        outputs: List[str] = []
        for r in resps:
            outputs.append(r["choices"][0]["message"]["content"])  # type: ignore[index]
        return outputs


class LLMDecisionEngine:
    def __init__(self, orchestrator: ActionOrchestrator, memory_store: PlayerMemoryStore):
        self._orchestrator = orchestrator
        self._memory_store = memory_store
        self._settings = get_settings()
        self._client = LiteLLMClient(model=self._settings.model)

    def _build_messages(self, d: DecisionInput) -> List[Dict[str, str]]:
        # 簡易プロンプト（日本語）。本番は prompts/ を読み込む想定
        system_prompt = d.system_prompt or (
            "あなたはRPGの行動選択アシスタントです。候補から1つを選び、JSONのみを出力してください。"
        )
        user_block = {
            "role": "user",
            "content": json.dumps({
                "candidates": d.candidates,
                "help": d.help_info,
                "memory": [
                    {
                        "type": m.type,
                        "content": m.content,
                        "metadata": m.metadata,
                    } for m in d.memory
                ],
                "output_schema": {
                    "action_name": "string",
                    "action_args": "object",
                    "rationale": "string",
                },
            }, ensure_ascii=False),
        }
        return [
            {"role": "system", "content": system_prompt},
            user_block,
        ]

    def decide_for_player(self, player_id: str) -> DecisionOutput:
        candidates = self._orchestrator.get_action_candidates_for_llm(player_id)
        help_info = self._orchestrator.get_action_help_for_llm(player_id)
        memory = self._memory_store.get_for_token_budget(player_id, token_budget=2048)
        messages = self._build_messages(DecisionInput(
            player_id=player_id,
            candidates=candidates,
            memory=memory,
            help_info=help_info,
        ))
        raw = self._client.complete_json(
            messages=messages,
            temperature=self._settings.temperature,
            max_tokens=self._settings.max_tokens,
        )
        try:
            data = json.loads(raw)
            return DecisionOutput.model_validate(data)
        except (json.JSONDecodeError, ValidationError):
            # フォールバック: 最初の候補を選ぶ
            fallback = candidates[0] if candidates else {"action_name": "", "required_arguments": []}
            return DecisionOutput(action_name=fallback.get("action_name", ""), action_args={}, rationale="fallback")

    def decide_for_players_batch(self, player_ids: Sequence[str]) -> Dict[str, DecisionOutput]:
        inputs: List[DecisionInput] = []
        for pid in player_ids:
            inputs.append(DecisionInput(
                player_id=pid,
                candidates=self._orchestrator.get_action_candidates_for_llm(pid),
                help_info=self._orchestrator.get_action_help_for_llm(pid),
                memory=self._memory_store.get_for_token_budget(pid, token_budget=2048),
            ))

        batch_messages = [self._build_messages(d) for d in inputs]
        raws = self._client.batch_complete_json(
            batch_messages=batch_messages,
            temperature=self._settings.temperature,
            max_tokens=self._settings.max_tokens,
        )

        outputs: Dict[str, DecisionOutput] = {}
        for d, raw in zip(inputs, raws):
            try:
                data = json.loads(raw)
                outputs[d.player_id] = DecisionOutput.model_validate(data)
            except (json.JSONDecodeError, ValidationError):
                fallback = d.candidates[0] if d.candidates else {"action_name": ""}
                outputs[d.player_id] = DecisionOutput(action_name=fallback.get("action_name", ""), action_args={}, rationale="fallback")
        return outputs


