from __future__ import annotations

from ai_rpg_world.application.being._memory_payload_codecs import _dict_to_route, _route_to_dict
from ai_rpg_world.being.contract import OwnActionResult


class TestOwnActionResultRouteCodec:
    """Being の snapshot が、自分の行動の結果の経路を、行動の要約ごと読み書きすることを保証する。"""

    def test_summary_survives_a_round_trip(self) -> None:
        """要約「「井戸」へ移動した」を持つ結果は、書いて読み直しても同じ要約を持つ。"""
        route = OwnActionResult(call_id="call-1", succeeded=True, action_summary="「井戸」へ移動した")

        assert _dict_to_route(_route_to_dict(route)) == route

    def test_result_saved_before_summaries_reads_without_a_summary(self) -> None:
        """要約を足す前に保存した結果 (action_summary の欄が無い) は、要約の無い結果として読む。"""
        saved = {"kind": "own_action_result", "call_id": "call-1", "succeeded": False}

        assert _dict_to_route(saved) == OwnActionResult(call_id="call-1", succeeded=False)
