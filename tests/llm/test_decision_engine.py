import json
from types import SimpleNamespace

from pydantic import ValidationError

from game.llm.policy.llm_decision_engine import LLMDecisionEngine, DecisionOutput
from game.llm.memory import PlayerMemoryStore, ObservationMessage


class _DummyOrchestrator:
    def __init__(self):
        self._candidates = [
            {"action_name": "移動", "required_arguments": [{"name": "target_spot_id", "type": "choice", "candidates": ["A", "B"]}]}
        ]

    def get_action_candidates_for_llm(self, pid):
        return self._candidates

    def get_action_help_for_llm(self, pid):
        return {"available_actions_count": len(self._candidates)}


def test_decide_for_player_with_litellm_monkeypatch(monkeypatch):
    # litellm.completion をモック
    def fake_completion(**kwargs):
        return {
            "choices": [{"message": {"content": json.dumps({
                "action_name": "移動",
                "action_args": {"target_spot_id": "A"},
                "rationale": "テスト",
            }, ensure_ascii=False)}}]
        }

    monkeypatch.setitem(__import__("litellm").__dict__, "completion", fake_completion)
    # batch はここでは未使用
    monkeypatch.setitem(__import__("litellm").__dict__, "batch_completion", lambda **kwargs: [])

    orchestrator = _DummyOrchestrator()
    memory = PlayerMemoryStore()
    memory.append("p1", ObservationMessage(content="見た"))

    engine = LLMDecisionEngine(orchestrator, memory)
    out = engine.decide_for_player("p1")

    assert isinstance(out, DecisionOutput)
    assert out.action_name == "移動"
    assert out.action_args == {"target_spot_id": "A"}


def test_decide_for_players_batch(monkeypatch):
    # litellm.batch_completion をモック
    def fake_batch_completion(model, messages, **kwargs):
        # 各メッセージに対応する応答を作る
        responses = []
        for _ in messages:
            responses.append({
                "choices": [{"message": {"content": json.dumps({
                    "action_name": "移動",
                    "action_args": {"target_spot_id": "B"},
                }, ensure_ascii=False)}}]
            })
        return responses

    def fake_completion(**kwargs):
        return {"choices": [{"message": {"content": "{}"}}]}

    ll = __import__("litellm")
    monkeypatch.setitem(ll.__dict__, "batch_completion", fake_batch_completion)
    monkeypatch.setitem(ll.__dict__, "completion", fake_completion)

    orchestrator = _DummyOrchestrator()
    memory = PlayerMemoryStore()
    engine = LLMDecisionEngine(orchestrator, memory)

    outs = engine.decide_for_players_batch(["p1", "p2", "p3"])
    assert set(outs.keys()) == {"p1", "p2", "p3"}
    for o in outs.values():
        assert o.action_args == {"target_spot_id": "B"}


