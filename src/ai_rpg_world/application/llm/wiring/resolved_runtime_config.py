"""``ResolvedLlmRuntimeConfig``: env から解決した LLM runtime 全設定を 1 か所に集約する frozen DTO。

# 何のため

PR #443 で連続発覚した silent failure (PR #439 / #441 / #444 / #446) の構造的
共通原因は「**env を読む経路が複数あり、各経路が独立に解釈する**」ことだった
(architect レビュー PR #444 後)。

- ``run_scenario_experiment.py`` が env を読んで run_start trace に書く
- ``wiring/_build_short_term_memory`` が env を読んで kind を解決する
- ``demos/escape_game/escape_game_runtime.py`` が **別経路で** env を読んで
  ``DefaultSlidingWindowMemory`` を直接作る (PR #439 で fix した silent failure
  の原因)
- ``demos/escape_game/escape_game_runtime.py`` が **また別経路で** env を読み
  忘れて ``SectionBasedContextFormatStrategy()`` を ClassVar で作る (PR #446
  で fix した silent failure)
- ``LiteLLMClient`` が env を読んで model / api_base / timeout を解決
- ``LiteLLMClient`` が **また別経路で** OpenRouter routing を解決

これらは各箇所で fail-fast 化 (PR #434) されているが、**「全部の経路で解決
結果が同じ」を構造で保証する仕組みがない**。trace に書かれた値と実体が
ズレうる。

本 DTO は env を **1 度だけ読む単一窓口** として定義し、entrypoint
(``run_scenario_experiment.py`` 等) で ``ResolvedLlmRuntimeConfig.from_env()``
を呼び、wiring 関数の引数として渡し回す形に統一する (PR 3/6 で実施)。

# 設計指針

1. **immutable** (``frozen=True``): 構築後に値が変わらない / hash 可能
2. **fail-fast**: env の typo / 不正値は ``from_env`` で即 ``ValueError``
   (PR #434 ポリシー継承)
3. **同 env を 2 回読まない**: ``from_env`` の内部で 1 度だけ ``os.environ``
   または引数 ``env`` を読む
4. **trace 表現**: ``to_trace_dict()`` で run_start payload に書ける dict を返す
5. **既存 resolver の活用**: 内部で既存 ``resolve_short_term_memory_kind`` 等を
   呼ぶ薄いラッパー (= 段階移行可能 / behavior 等価)

# 将来計画

- PR 2/6 (本 PR): DTO 定義 + ``from_env`` 実装 + tests
- PR 3/6: 既存 entrypoint / wiring を DTO ベースに移行
  (``_build_short_term_memory_from_env`` 等の env 直読 helper を廃止)
- PR 4/6: ``NullTraceRecorder`` と組み合わせて全 wiring に同一 instance を渡す
- PR 6/6: Builder pattern で staged construction を強制 → setter 後注入を廃止
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class ResolvedLlmRuntimeConfig:
    """env から resolve した LLM runtime 設定の単一 source of truth (PR #446 後続)。

    各フィールドは「**resolve 済み**」の最終値を持つ。env を直読する経路を本
    DTO の ``from_env`` だけに集約することで、PR #439 / #446 のような「同 env を
    2 箇所で別解釈する silent failure」を構造で防ぐ。

    Attributes:
        # === Short-term memory (Phase 2) ===
        short_term_memory_kind: ``"sliding_window"`` | ``"rolling_summary"``
        short_term_memory_scheduler_mode: ``"inline"`` | ``"thread_pool"``

        # === Prompt section ordering (Phase 0) ===
        prompt_section_order: ``"stable_to_volatile"`` | ``"legacy"``

        # === LLM client / model ===
        llm_client_kind: ``"stub"`` | ``"litellm"``
        llm_model: model 名 (例: ``"openrouter/google/gemma-4-31b-it"``)。
            未設定なら None (= LiteLLMClient default)
        llm_api_key: ``OPENAI_API_KEY`` の値。実 LLM を呼ぶときに必要
        llm_api_base: ``OPENAI_API_BASE`` の値 (vLLM / OpenRouter で必要)
        llm_request_timeout_seconds: litellm の request timeout (PR #444 で
            導入された long-tail hang 対策)

        # === OpenRouter provider routing (PR #426) ===
        openrouter_provider: provider 名 (例: ``"Parasail"``)。未設定なら None
        openrouter_quantization: quant 指定 (例: ``"fp8"``)。未設定なら None
        openrouter_require_params: True なら必須 param 全対応 provider のみ

        # === Episodic memory (Phase 1a / Phase B) ===
        episodic_enabled: ``LLM_EPISODIC_ENABLED=1`` で ON
        episodic_explore_related_enabled: ``EPISODIC_EXPLORE_RELATED_ENABLED=1``
            で memory_explore_related tool を露出

        # === Semantic memory (Phase 1b-1d) ===
        semantic_llm_gist_enabled: ``SEMANTIC_LLM_GIST_ENABLED=1`` で episodic →
            semantic 昇格時に LLM 要約を生成
        semantic_passive_top_k: ``SEMANTIC_PASSIVE_TOP_K`` 整数。>0 で prompt
            に §learned section が出る
        semantic_search_enabled: ``SEMANTIC_SEARCH_ENABLED=1`` で能動 semantic
            検索 tool を露出
    """

    # Short-term memory
    short_term_memory_kind: str
    short_term_memory_scheduler_mode: str

    # Prompt
    prompt_section_order: str

    # LLM client
    llm_client_kind: str
    llm_model: Optional[str]
    llm_api_key: Optional[str]
    llm_api_base: Optional[str]
    llm_request_timeout_seconds: float

    # OpenRouter routing
    openrouter_provider: Optional[str]
    openrouter_quantization: Optional[str]
    openrouter_require_params: bool

    # Episodic memory
    episodic_enabled: bool
    episodic_explore_related_enabled: bool

    # Semantic memory
    semantic_llm_gist_enabled: bool
    semantic_passive_top_k: int
    semantic_search_enabled: bool

    # ──────────────────────────────────────────────────────────────
    # Construction
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def from_env(
        cls,
        env: Optional[Mapping[str, str]] = None,
    ) -> "ResolvedLlmRuntimeConfig":
        """env から全フィールドを resolve する (PR 2/6 の核心)。

        - ``env`` 省略時は ``os.environ`` を読む。test では明示注入する
        - 各フィールドは既存 resolver (``feature_flags.resolve_*`` /
          ``context_format_strategy.resolve_section_order_from_env`` /
          ``_llm_client_factory`` の値) を呼ぶ薄いラッパー
        - 不正値は各 resolver が ``ValueError`` を投げる (PR #434 fail-fast 継承)
        - 環境変数を読むのは本メソッド内だけ (= 単一窓口)

        Raises:
            ValueError: env のいずれかが不正値のとき
        """
        # 既存 resolver の import は関数内で行い、循環参照を避ける
        from ai_rpg_world.application.llm.services.context_format_strategy import (
            resolve_section_order_from_env,
        )
        from ai_rpg_world.application.llm.wiring import _llm_client_factory
        from ai_rpg_world.application.llm.wiring.feature_flags import (
            resolve_episodic_explore_related_enabled,
            resolve_semantic_llm_gist_enabled,
            resolve_semantic_passive_top_k,
            resolve_semantic_search_enabled,
            resolve_short_term_memory_kind,
            resolve_short_term_memory_scheduler_mode,
        )

        source: Mapping[str, str] = env if env is not None else os.environ

        # 既存 resolver は env=None で os.environ を読むので、本関数の env が
        # 明示注入されている場合は env を渡す。同 env source を全 resolver で
        # 共有することで「同 env を 2 回読む」を回避する。
        short_term_memory_kind = resolve_short_term_memory_kind(env=source)
        short_term_memory_scheduler_mode = resolve_short_term_memory_scheduler_mode(
            env=source
        )
        prompt_section_order = resolve_section_order_from_env(env=source)
        episodic_explore_related_enabled = resolve_episodic_explore_related_enabled(
            env=source
        )
        semantic_llm_gist_enabled = resolve_semantic_llm_gist_enabled(env=source)
        semantic_passive_top_k = resolve_semantic_passive_top_k(env=source)
        semantic_search_enabled = resolve_semantic_search_enabled(env=source)

        # LLM client kind (factory と同じロジックで解決)
        llm_client_kind = _resolve_llm_client_kind(source)
        llm_model = _strip_or_none(source.get("LLM_MODEL"))
        llm_api_key = _strip_or_none(source.get("OPENAI_API_KEY"))
        llm_api_base = _strip_or_none(source.get("OPENAI_API_BASE"))
        llm_request_timeout_seconds = _resolve_timeout_seconds(source)

        # OpenRouter routing
        openrouter_provider = _strip_or_none(source.get("OPENROUTER_PROVIDER"))
        openrouter_quantization = _strip_or_none(source.get("OPENROUTER_QUANTIZATION"))
        openrouter_require_params = _parse_truthy(
            source.get("OPENROUTER_REQUIRE_PARAMS"), default=False
        )

        # Episodic on/off (旧来は episodic_stack.is_episodic_enabled が同等の
        # ロジック。bool 解釈は _parse_truthy で統一)
        episodic_enabled = _parse_truthy(source.get("LLM_EPISODIC_ENABLED"), default=False)

        return cls(
            short_term_memory_kind=short_term_memory_kind,
            short_term_memory_scheduler_mode=short_term_memory_scheduler_mode,
            prompt_section_order=prompt_section_order,
            llm_client_kind=llm_client_kind,
            llm_model=llm_model,
            llm_api_key=llm_api_key,
            llm_api_base=llm_api_base,
            llm_request_timeout_seconds=llm_request_timeout_seconds,
            openrouter_provider=openrouter_provider,
            openrouter_quantization=openrouter_quantization,
            openrouter_require_params=openrouter_require_params,
            episodic_enabled=episodic_enabled,
            episodic_explore_related_enabled=episodic_explore_related_enabled,
            semantic_llm_gist_enabled=semantic_llm_gist_enabled,
            semantic_passive_top_k=semantic_passive_top_k,
            semantic_search_enabled=semantic_search_enabled,
        )

    @classmethod
    def for_tests(cls, **overrides: Any) -> "ResolvedLlmRuntimeConfig":
        """test 用の safe default factory (PR #446 architect 提案)。

        全フィールドを「最も無害な default」で埋め、上書きしたい項目だけ
        keyword で渡す。test fixture の肥大化を防ぐ。

        - LLM 系は全部 ``stub`` / None で「実 LLM を呼ばない」
        - feature flag は全部 OFF
        - prompt_section_order は ``stable_to_volatile`` (= default)

        Usage:
            cfg = ResolvedLlmRuntimeConfig.for_tests(
                short_term_memory_kind="rolling_summary",
            )
        """
        defaults: dict[str, Any] = dict(
            short_term_memory_kind="sliding_window",
            short_term_memory_scheduler_mode="inline",
            prompt_section_order="stable_to_volatile",
            llm_client_kind="stub",
            llm_model=None,
            llm_api_key=None,
            llm_api_base=None,
            llm_request_timeout_seconds=90.0,
            openrouter_provider=None,
            openrouter_quantization=None,
            openrouter_require_params=False,
            episodic_enabled=False,
            episodic_explore_related_enabled=False,
            semantic_llm_gist_enabled=False,
            semantic_passive_top_k=0,
            semantic_search_enabled=False,
        )
        unknown = set(overrides) - set(defaults)
        if unknown:
            raise TypeError(
                f"Unknown override keys: {sorted(unknown)}. "
                f"valid: {sorted(defaults)}"
            )
        defaults.update(overrides)
        return cls(**defaults)

    # ──────────────────────────────────────────────────────────────
    # Observability
    # ──────────────────────────────────────────────────────────────

    def to_trace_dict(self) -> dict[str, Any]:
        """run_start trace payload 用の dict 表現 (PR 3/6 で entrypoint が利用)。

        ``llm_api_key`` は **必ずマスク** する (実値を trace に書かない安全弁)。
        その他は dataclass の全フィールドをそのまま出力。
        """
        d = asdict(self)
        # API key は trace に書かない (= 漏洩防止)
        if d.get("llm_api_key"):
            d["llm_api_key"] = "***"
        return d


# ──────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────


_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})


def _strip_or_none(value: Optional[str]) -> Optional[str]:
    """空文字 / None / 空白のみ → None、それ以外は strip した値。"""
    if value is None:
        return None
    s = value.strip()
    return s or None


def _parse_truthy(value: Optional[str], *, default: bool) -> bool:
    """bool 解釈。``_parse_bool_env`` と同じロジック (PR #434 ポリシー)。

    未設定 / 空文字 → ``default``
    truthy / falsy リテラル → True / False
    その他 → ValueError (fail-fast)
    """
    if value is None or not value.strip():
        return default
    raw = value.strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    raise ValueError(
        f"{value!r} is not a recognized boolean. "
        f"truthy: {sorted(_TRUTHY)}, falsy: {sorted(_FALSY)}"
    )


_VALID_LLM_CLIENT_KINDS = frozenset({"stub", "litellm"})


def _resolve_llm_client_kind(source: Mapping[str, str]) -> str:
    """``LLM_CLIENT`` を解決 (factory と同じロジック / PR #434 fail-fast 継承)。"""
    raw = (source.get("LLM_CLIENT") or "stub").strip().lower()
    if raw not in _VALID_LLM_CLIENT_KINDS:
        raise ValueError(
            f"LLM_CLIENT={raw!r} is not recognized. "
            f"valid: {sorted(_VALID_LLM_CLIENT_KINDS)}"
        )
    return raw


_DEFAULT_TIMEOUT_SECONDS = 90.0


def _resolve_timeout_seconds(source: Mapping[str, str]) -> float:
    """``LLM_REQUEST_TIMEOUT_SECONDS`` を解決 (LiteLLMClient と同じ default / fail-fast)。"""
    raw = (source.get("LLM_REQUEST_TIMEOUT_SECONDS") or "").strip()
    if not raw:
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        return float(raw)
    except ValueError:
        raise ValueError(
            f"LLM_REQUEST_TIMEOUT_SECONDS={raw!r} must be a number (seconds)"
        )


__all__ = ["ResolvedLlmRuntimeConfig"]
