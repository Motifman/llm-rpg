"""実際の道具呼出しIDを失わず、providerに無いIDを捏造しない。"""
from types import SimpleNamespace

import pytest

from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient


@pytest.mark.parametrize('provider_id', ['provider-real-id', None])
def test_parser_preserves_only_a_supplied_tool_call_id(provider_id):
    """応答にある識別子だけを実行へ渡し、応答に無ければ追加しない。"""
    client = object.__new__(LiteLLMClient)
    call = SimpleNamespace(id=provider_id, function=SimpleNamespace(name='sns_read', arguments='{"view":"posts"}'))
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call]))])
    parsed = client._parse_tool_call(response, [], [])
    assert parsed['name'] == 'sns_read'
    if provider_id is None:
        assert 'tool_call_id' not in parsed
    else:
        assert parsed['tool_call_id'] == provider_id
