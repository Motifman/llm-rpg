from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Type, Optional as TypingOptional

from pydantic import BaseModel, Field, ValidationError

from game.action.action_orchestrator import ActionOrchestrator
from game.llm.config import get_settings
from game.llm.memory import PlayerMemoryStore, MessageBase
from game.action.candidates import ActionCandidates


class DecisionOutput(BaseModel):
    thought: str = Field(..., description="なぜこの行動を選んだのか、あなたの思考プロセスを記述してください。")
    action: str = Field(..., description="実行する行動の名前（例: 'move', 'list_item'）")
    arguments: Dict[str, Any] = Field(..., description="選択した行動に必要な引数をキーと値のペアで指定してください。")


@dataclass
class DecisionInput:
    player_id: str
    candidates: ActionCandidates
    memory: List[MessageBase]
    system_prompt: Optional[str] = None


class LiteLLMClient:
    """litellm を用いたOpenAI互換チャット呼び出し。

    - 単発: completion()
    - バッチ: batch_completion()
    """

    def __init__(self, model: Optional[str] = None):
        # 実行時に動的ロードするため、テストでsys.modulesにダミーを注入可能
        import importlib
        litellm = importlib.import_module("litellm")
        self._completion = getattr(litellm, "completion")
        self._batch_completion = getattr(litellm, "batch_completion")
        self._model = model or get_settings().model

    def complete_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        response_model: TypingOptional[Type[BaseModel]] = None,
    ) -> str:
        resp = self._completion(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_model,
        )
        return resp["choices"][0]["message"]["content"]

    def batch_complete_json(
        self,
        batch_messages: List[List[Dict[str, str]]],
        temperature: float,
        max_tokens: int,
        response_model: TypingOptional[Type[BaseModel]] = None,
    ) -> List[str]:
        resps = self._batch_completion(
            model=self._model,
            messages=batch_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_model,
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
        # LLMクライアントは遅延初期化（デモでmessagesのみ確認する用途のため）
        self._client: Optional[LiteLLMClient] = None

    def _ensure_client(self) -> LiteLLMClient:
        if self._client is None:
            self._client = LiteLLMClient(model=self._settings.model)
        return self._client

    def _build_messages(self, d: DecisionInput) -> List[Dict[str, str]]:
        system_prompt = d.system_prompt or (
            "あなたはRPGにおけるプレイヤーの次行動を選ぶアシスタントです。\n"
            "以下のルールに必ず従って、JSONのみを出力してください。\n"
            "\n"
            "[役割と目的]\n"
            "- 与えられた候補アクションと最近の出来事を読み取り、最も妥当な次の1手を選ぶ。\n"
            "\n"
            "[制約]\n"
            "- 候補にないアクションや引数を捏造しない。\n"
            "- 出力は厳密にJSONのみ（前後の解説・余白テキスト禁止）。\n"
        )

        # 候補を読みやすいテキストに整形
        candidates_text = d.candidates.to_text()

        # メモリ要約（読みやすい人間向け形式）
        memory_lines: List[str] = []
        for m in d.memory:
            tag = m.type
            content = m.content
            meta = (f" meta={m.metadata}" if m.metadata else "")
            memory_lines.append(f"- [{tag}] {content}{meta}")
        memory_text = "\n".join(memory_lines) if memory_lines else "(履歴なし)"

        # 実際の入力（ユーザー側メッセージ）: 状況のみを渡す
        user_text = (
            "以下が現在の状況です。候補から次の1手を選んで、指定仕様のJSONのみを返してください。\n\n"
            "[最近の出来事]\n" + memory_text + "\n"
            "[候補アクション]\n" + candidates_text + "\n\n"
        )

        user_block = {"role": "user", "content": user_text}
        return [
            {"role": "system", "content": system_prompt},
            user_block,
        ]

    def decide_for_player(self, player_id: str) -> DecisionOutput:
        candidates = self._orchestrator.get_action_candidates_for_llm(player_id)
        memory = self._memory_store.get_for_token_budget(player_id, token_budget=2048)
        messages = self._build_messages(DecisionInput(
            player_id=player_id,
            candidates=candidates,
            memory=memory,
        ))
        raw = self._ensure_client().complete_json(
            messages=messages,
            temperature=self._settings.temperature,
            max_tokens=self._settings.max_tokens,
            response_model=DecisionOutput,
        )
        try:
            data = json.loads(raw)
            return DecisionOutput.model_validate(data)
        except (json.JSONDecodeError, ValidationError):
            # フォールバック: 最初の候補を選ぶ
            fallback_action = candidates[0]["action_name"] if candidates else ""
            return DecisionOutput(thought="fallback", action=fallback_action, arguments={})

    def decide_for_players_batch(self, player_ids: Sequence[str]) -> Dict[str, DecisionOutput]:
        inputs: List[DecisionInput] = []
        for pid in player_ids:
            cands = self._orchestrator.get_action_candidates_for_llm(pid)
            inputs.append(DecisionInput(
                player_id=pid,
                candidates=cands,
                memory=self._memory_store.get_for_token_budget(pid, token_budget=2048),
            ))

        batch_messages = [self._build_messages(d) for d in inputs]
        raws = self._ensure_client().batch_complete_json(
            batch_messages=batch_messages,
            temperature=self._settings.temperature,
            max_tokens=self._settings.max_tokens,
            response_model=DecisionOutput,
        )

        outputs: Dict[str, DecisionOutput] = {}
        for d, raw in zip(inputs, raws):
            try:
                data = json.loads(raw)
                outputs[d.player_id] = DecisionOutput.model_validate(data)
            except (json.JSONDecodeError, ValidationError):
                fallback_action = d.candidates[0]["action_name"] if d.candidates else ""
                outputs[d.player_id] = DecisionOutput(thought="fallback", action=fallback_action, arguments={})
        return outputs

    # --- Demo/Debug helper ---
    def get_messages_preview(self, player_id: str, system_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        """LLMに渡す直前の messages を生成して返す（実際のLLM呼び出しは行わない）。"""
        candidates = self._orchestrator.get_action_candidates_for_llm(player_id)
        memory = self._memory_store.get_for_token_budget(player_id, token_budget=2048)
        return self._build_messages(DecisionInput(
            player_id=player_id,
            candidates=candidates,
            memory=memory,
            system_prompt=system_prompt,
        ))


