import json

from ai_rpg_world.application.llm.services.prompt_dataset_capture import (
    PromptDatasetCallContext,
    PromptDatasetCaptureSink,
    compute_request_hash,
    reconstruct_request,
)


class TestPromptDatasetCaptureSink:
    """PromptDatasetCaptureSink が request/response を replay 可能な形で保存することを保証する。"""

    def test_reconstruct_request_restores_messages_tools_and_hash(self, tmp_path):
        """content_ref と tools_ref を戻すと、送信時の messages/tools と request_hash が一致する。"""

        sink = PromptDatasetCaptureSink(
            run_dir=tmp_path,
            run_id="run1",
            run_metadata={"profile": "test"},
        )
        context = PromptDatasetCallContext(
            llm_call_id="call-1",
            run_id="run1",
            world_id=1,
            being_id="being_w1_p1",
            player_id=1,
            persona_id="persona:sha256:test",
            character_name="エイダ",
            turn_index=1,
            world_tick=1,
        )
        request_kwargs = {
            "model": "stub",
            "messages": [
                {"role": "system", "content": "あなたはエイダです。"},
                {"role": "user", "content": "周囲を確認してください。"},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "spot_graph_explore",
                        "description": "周囲を見る",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            "tool_choice": "required",
            "api_key": "secret",
            "max_retries": 0,
        }
        response = {
            "id": "stub-response",
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "spot_graph_explore",
                                    "arguments": "{}",
                                },
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        sink.record_call(
            context=context,
            request_kwargs=request_kwargs,
            response=response,
            output={"name": "spot_graph_explore", "arguments": {}},
            metrics={"success": True},
        )

        call = _read_jsonl(tmp_path / "prompt_dataset" / "calls.jsonl")[0]
        system_prompts = {
            row["system_prompt_id"]: row
            for row in _read_jsonl(tmp_path / "prompt_dataset" / "system_prompts.jsonl")
        }
        toolsets = {
            row["toolset_id"]: row
            for row in _read_jsonl(tmp_path / "prompt_dataset" / "toolsets.jsonl")
        }

        restored = reconstruct_request(call, system_prompts, toolsets)

        assert restored["messages"] == request_kwargs["messages"]
        assert restored["tools"] == request_kwargs["tools"]
        assert "api_key" not in call["request"]["kwargs"]
        assert call["request"]["request_hash"] == compute_request_hash(
            call["request"]["kwargs"]
        )

    def test_output_is_derivable_from_raw_response(self, tmp_path):
        """保存した response.raw から、便宜 field の output と同じ tool_call を再導出できる。"""

        sink = PromptDatasetCaptureSink(
            run_dir=tmp_path,
            run_id="run1",
            run_metadata={},
        )
        context = PromptDatasetCallContext(
            llm_call_id="call-1",
            run_id="run1",
            world_id=1,
            being_id="being_w1_p1",
            player_id=1,
            persona_id="persona:sha256:test",
            character_name="エイダ",
            turn_index=1,
        )
        response = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "speak",
                                    "arguments": "{\"content\":\"こんにちは\"}",
                                }
                            }
                        ]
                    }
                }
            ]
        }
        sink.record_call(
            context=context,
            request_kwargs={
                "model": "stub",
                "messages": [{"role": "system", "content": "sys"}],
                "tools": [],
                "tool_choice": "required",
            },
            response=response,
            output={"name": "speak", "arguments": {"content": "こんにちは"}},
            metrics={"success": True},
        )

        call = _read_jsonl(tmp_path / "prompt_dataset" / "calls.jsonl")[0]

        assert _derive_tool_call(call["response"]["raw"]) == call["output"]


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _derive_tool_call(response):
    tool_call = response["choices"][0]["message"]["tool_calls"][0]
    function = tool_call["function"]
    return {
        "name": function["name"],
        "arguments": json.loads(function["arguments"]),
    }
