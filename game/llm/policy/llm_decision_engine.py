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
    help_info: Dict[str, Any]
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
        self._client = LiteLLMClient(model=self._settings.model)

    def _build_messages(self, d: DecisionInput) -> List[Dict[str, str]]:
        # 簡易プロンプト（日本語）。本番は prompts/ を読み込む想定
        system_prompt = d.system_prompt or (
            "あなたはRPGの行動選択アシスタントです。候補から1つを選び、JSONのみを出力してください。"
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

        # ヘルプ情報を読みやすい形式に整形
        help_info = d.help_info or {}
        help_lines: List[str] = [
            f"利用可能アクション数: {help_info.get('available_actions_count', 0)}",
        ]
        types_info = help_info.get('action_types') or {}
        help_lines.append(
            f"  種別内訳: state_specific={types_info.get('state_specific', 0)}, spot_specific={types_info.get('spot_specific', 0)}"
        )
        usage = (help_info.get('usage_instructions') or {})
        if usage:
            help_lines.append("  使い方:")
            if usage.get('action_selection'):
                help_lines.append(f"    - {usage.get('action_selection')}")
            if usage.get('argument_format'):
                help_lines.append(f"    - {usage.get('argument_format')}")
            arg_types = usage.get('argument_types') or {}
            if arg_types:
                help_lines.append("    - 引数タイプ: choice=候補から選択, free_input=自由入力")
        help_text = "\n".join(help_lines)

        # ユーザーブロックを可読な文章で
        user_text = (
            "以下は現在の状況と候補アクション情報です。これを踏まえて最適な1手を選び、指定スキーマに従うJSONを返してください。\n\n"
            "[候補アクション]\n" + candidates_text + "\n\n"
            "[補助情報]\n" + help_text + "\n\n"
            "[最近の出来事]\n" + memory_text + "\n\n"
            "[出力スキーマ]\n"
            "{\n  \"thought\": string,\n  \"action\": string,\n  \"arguments\": object\n}"
        )

        user_block = {"role": "user", "content": user_text}
        return [
            {"role": "system", "content": system_prompt},
            user_block,
        ]

    def decide_for_player(self, player_id: str) -> DecisionOutput:
        candidates = self._orchestrator.get_action_candidates_for_llm(player_id)
        # 同じ候補からヘルプを派生させて重複処理を回避（後方互換フォールバック）
        if hasattr(self._orchestrator, "build_action_help_from_candidates"):
            help_info = self._orchestrator.build_action_help_from_candidates(candidates)  # type: ignore[attr-defined]
        else:
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
            if hasattr(self._orchestrator, "build_action_help_from_candidates"):
                help_info = self._orchestrator.build_action_help_from_candidates(cands)  # type: ignore[attr-defined]
            else:
                help_info = self._orchestrator.get_action_help_for_llm(pid)
            inputs.append(DecisionInput(
                player_id=pid,
                candidates=cands,
                help_info=help_info,
                memory=self._memory_store.get_for_token_budget(pid, token_budget=2048),
            ))

        batch_messages = [self._build_messages(d) for d in inputs]
        raws = self._client.batch_complete_json(
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


