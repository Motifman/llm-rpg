"""確からしさの日本語の呼び名。本人が予期に付ける値と、清算の問いに見せる値を同じにする。"""

from __future__ import annotations

from collections.abc import Mapping

from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)

LIKELIHOOD_LABELS: Mapping[Likelihood, str] = {
    Likelihood.ALMOST_CERTAIN: "ほぼ確実",
    Likelihood.PROBABLY: "たぶん",
    Likelihood.EVEN: "半々",
    Likelihood.MAYBE: "もしかしたら",
}

LIKELIHOOD_BY_LABEL: Mapping[str, Likelihood] = {
    label: likelihood for likelihood, label in LIKELIHOOD_LABELS.items()
}


__all__ = ["LIKELIHOOD_BY_LABEL", "LIKELIHOOD_LABELS"]
