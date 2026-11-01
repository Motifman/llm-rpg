"""一言 (``say_inline``) の書き方の説明が、出すツールに合わせて出たり消えたりすることを保証する (#1940)。"""

from __future__ import annotations

import json
from pathlib import Path

from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    get_spot_graph_specs,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_DRILL = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"

_TOOLS_WITH_SAY_INLINE = sorted(
    defn.name for defn, _ in get_spot_graph_specs() if "say_inline" in defn.parameters.get("properties", {})
)


def _drill_disabling(tmp_path: Path, disabled: list[str]) -> Path:
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    raw["disabled_tools"] = disabled
    path = tmp_path / "drill.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


class TestSayInlineGuidanceFollowsTheOfferedTools:
    """システムプロンプトの一言の説明を、出すツールが ``say_inline`` を持つかで出し分ける。"""

    def test_guidance_is_absent_when_no_offered_tool_takes_say_inline(self, tmp_path) -> None:
        """``say_inline`` を持つツールをすべて無効にした世界では、どのプレイヤーのシステムプロンプトにも ``say_inline`` が出ない。"""
        runtime = create_world_runtime(_drill_disabling(tmp_path, _TOOLS_WITH_SAY_INLINE))

        prompts = [runtime.build_system_prompt(pid) for pid in runtime.get_player_ids()]

        assert prompts
        assert all("say_inline" not in prompt for prompt in prompts)

    def test_guidance_is_present_when_one_offered_tool_takes_say_inline(self, tmp_path) -> None:
        """``say_inline`` を持つツールを 1 つだけ残した世界では、一言の説明がシステムプロンプトに出る。"""
        runtime = create_world_runtime(_drill_disabling(tmp_path, _TOOLS_WITH_SAY_INLINE[1:]))

        prompts = [runtime.build_system_prompt(pid) for pid in runtime.get_player_ids()]

        assert prompts
        assert all("`say_inline` を持つツールでは" in prompt for prompt in prompts)
