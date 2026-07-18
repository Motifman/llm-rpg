"""停滞感 → 熟考 (reasoning) の発火ポリシー (案A: band-gated thinking)。

「停滞の気づき (reflect) が本人に注入された直後の行動」かつ「停滞感 band が
strong」のときだけ、その 1 行動で reasoning を有効化する、という判断を 1 箇所の
純関数に集約する。inner_thought は tool_call 確定後の後付けで行動に影響しないが、
reasoning は tool_call の前に走るため、詰まった局面だけ「熟考してから選ぶ」を
実現できる。効用勾配ではなく世界の予測誤差 (停滞) を入口にする第一原理は保つ。
"""

from __future__ import annotations

from typing import Optional

from ai_rpg_world.domain.memory.goal.service.stagnation_pressure_band import (
    STAGNATION_PRESSURE_BAND_STRONG,
)

STAGNATION_REASONING_EFFORT = "low"
"""strong 停滞時に開く reasoning の予算段階。minimal は実プロンプトに対して薄すぎる
恐れがあるため low。効果を見て調整する 1 箇所の SSOT。"""


def resolve_stagnation_reasoning_effort(
    band: str, fresh_reflect: bool
) -> Optional[str]:
    """停滞感 band と「直前に停滞 reflect が注入されたか」から reasoning effort を決める。

    - ``band == "strong"`` かつ ``fresh_reflect`` が True → ``STAGNATION_REASONING_EFFORT``
    - それ以外 → ``None`` (= override しない = 既定のまま reasoning OFF)

    band を strong に限るのは、light (1〜2 回の停滞) は通常の難しさの範囲で、毎回
    熟考させると常時発火に近づくため。fresh_reflect を条件にするのは、恣意的な間引き
    間隔を新設せず、既に鼓動 (stall_min_interval) で throttle 済みの reflect 注入
    イベントに熟考を相乗りさせるため。
    """
    if fresh_reflect and band == STAGNATION_PRESSURE_BAND_STRONG:
        return STAGNATION_REASONING_EFFORT
    return None


__all__ = [
    "STAGNATION_REASONING_EFFORT",
    "resolve_stagnation_reasoning_effort",
]
