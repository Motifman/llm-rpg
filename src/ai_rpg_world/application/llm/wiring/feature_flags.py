"""LLM 配線まわりの env-driven feature flag。

実験スクリプトから A/B 検証する用途で、scenario 内容と直交する knob を
ここに集約する。既存の他の env var (``SUBJECTIVE_EPISODE_DB_PATH``,
``LLM_MODEL`` 等) と
同じ慣例に揃える。

設計指針:

- **default は OFF** (新規機能を実験中の検証変数として導入するため、env で
  明示的に ON にしたときだけ動かす)。詳細は
  ``docs/memory_system/semantic_memory_activation_plan.md`` §9
- **「配線 (wire)」と「有効化 (enable)」を分離**: コードパスは常に通って
  いるが env 未設定なら不活性
"""

from __future__ import annotations

from collections.abc import Mapping

# ──────────────────────────────────────────────────────────────────
# Short-term memory: rolling summary (Phase 2)
# ──────────────────────────────────────────────────────────────────


ENV_SHORT_TERM_MEMORY_TURN_CAP = "SHORT_TERM_MEMORY_TURN_CAP"
ENV_SHORT_TERM_MEMORY_TURN_COMPACT_COUNT = "SHORT_TERM_MEMORY_TURN_COMPACT_COUNT"


def resolve_short_term_memory_turn_window(
    env: Mapping[str, str] | None = None,
) -> tuple[int, int]:
    """自分のターン単位の窓上限と、一度に畳むターン数を解決する。

    ``compact_count`` は ``cap`` より小さくなければならない。等しい値を
    許すと、畳んだ直後に直近出来事が空になり、自己の連続性が切れる。
    """
    if env is None:
        raise TypeError(
            "env mapping is required; use ResolvedLlmRuntimeConfig.from_mapping()"
        )

    def _positive_int(name: str, default: int) -> int:
        raw = (env.get(name) or "").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer: {raw!r}") from exc
        if value <= 0:
            raise ValueError(f"{name} must be greater than 0: {value}")
        return value

    cap = _positive_int(ENV_SHORT_TERM_MEMORY_TURN_CAP, 20)
    compact_count = _positive_int(
        ENV_SHORT_TERM_MEMORY_TURN_COMPACT_COUNT, 10
    )
    if compact_count >= cap:
        raise ValueError(
            f"{ENV_SHORT_TERM_MEMORY_TURN_COMPACT_COUNT} must be smaller than "
            f"{ENV_SHORT_TERM_MEMORY_TURN_CAP}: {compact_count} >= {cap}"
        )
    return cap, compact_count
