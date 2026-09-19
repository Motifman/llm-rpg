"""型付き判断ポートのファクトリ (#1319)。

## 足りない設定は起動前に落とす

``provider=jev`` なのにキーが無い run は、1 件目の判断まで進んでから失敗する。
そこまでに使った時間と API 費用は戻らない。ここで落とす (design_decisions #10)。

とくに ``EMPTY`` を弾く。ローカル vLLM 構成では ``OPENAI_API_KEY`` が ``EMPTY``
になる (無認証の endpoint 向けの置き値)。その値で OpenRouter に送ると 401 に
なるので、キーが「在る」と数えてはいけない。

## キーの在り処

profile には env の名前だけを書く (既定 ``OPENROUTER_API_KEY``)。値は書かせない。
profile は run の記録として残るので、書かれたキーは記録へ焼き付く。

指定の env が空なら ``OPENAI_API_KEY`` に落ちる。この repo では OpenRouter の
キーがそこに入っているためだが、**名前と実体がずれている**ので、落ちたことは
警告に残す。
"""

from __future__ import annotations

import logging
import os
from typing import Mapping, Optional, TYPE_CHECKING

from ai_rpg_world.application.llm.ports.typed_judgment_port import ITypedJudgmentPort
from ai_rpg_world.application.llm.services.typed_judgment_stub import (
    DeterministicTypedJudgmentPort,
)

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
        ResolvedLlmRuntimeConfig,
    )

logger = logging.getLogger(__name__)

#: OpenAI 互換の無認証 endpoint 向けにキー欄へ置く値。キーではない。
_PLACEHOLDER_KEY = "EMPTY"

#: 指定の env が空のときに見る名前。この repo では OpenRouter のキーがここに入る。
_FALLBACK_KEY_ENV = "OPENAI_API_KEY"


def create_typed_judgment_port_from_config(
    config: "ResolvedLlmRuntimeConfig",
    *,
    env: Optional[Mapping[str, str]] = None,
) -> Optional[ITypedJudgmentPort]:
    """解決済み設定に応じて型付き判断ポートを組む。``off`` なら None。

    フィールドは直接参照する (``getattr`` の縮退を使わない)。名前の typo や
    誤った型の config を渡したときに、黙って ``off`` へ縮退させない。

    Args:
        config: 解決済み設定
        env: キーを読む環境。省略時は ``os.environ``

    Raises:
        ValueError: ``provider=jev`` なのに使えるキーが無いとき
    """
    provider = config.typed_judgment_provider.strip().lower()
    if provider == "off":
        return None
    if provider == "stub":
        return DeterministicTypedJudgmentPort()
    if provider != "jev":
        # config 側の検証を通っていれば届かない。届いたら設定の解決経路が
        # 2 つに割れている合図なので、黙って stub へ縮退させない。
        raise ValueError(f"unsupported typed judgment provider: {provider!r}")

    source: Mapping[str, str] = os.environ if env is None else env
    api_key = _resolve_api_key(config.typed_judgment_api_key_env, source)

    from ai_rpg_world.infrastructure.llm.jev_typed_judgment_adapter import (
        JevTypedJudgmentAdapter,
    )

    return JevTypedJudgmentAdapter(
        api_key=api_key,
        endpoint=config.typed_judgment_endpoint,
        model=config.typed_judgment_model,
        timeout_seconds=config.typed_judgment_timeout_seconds,
    )


def _resolve_api_key(named_env: str, source: Mapping[str, str]) -> str:
    named = (source.get(named_env) or "").strip()
    if named and named != _PLACEHOLDER_KEY:
        return named

    fallback = (source.get(_FALLBACK_KEY_ENV) or "").strip()
    if fallback and fallback != _PLACEHOLDER_KEY:
        logger.warning(
            "typed judgment key was not in %s; falling back to %s. "
            "The fallback is named after OpenAI but holds the OpenRouter key in "
            "this repository.",
            named_env,
            _FALLBACK_KEY_ENV,
        )
        return fallback

    # 「置いていない」と「置いた値が使えない」を同じ文面にしない。後者は
    # 設定したのに読まれていないと誤読される。
    placeholders = [
        name
        for name, value in ((named_env, named), (_FALLBACK_KEY_ENV, fallback))
        if value == _PLACEHOLDER_KEY
    ]
    detail = (
        f" {placeholders} hold the placeholder {_PLACEHOLDER_KEY!r}, which is not a "
        "key (it is what OpenAI-compatible endpoints without auth expect)."
        if placeholders
        else ""
    )
    raise ValueError(
        f"TYPED_JUDGMENT_PROVIDER=jev needs an API key in {named_env} "
        f"(or {_FALLBACK_KEY_ENV}).{detail}"
    )


__all__ = ["create_typed_judgment_port_from_config"]
