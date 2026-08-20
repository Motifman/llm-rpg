"""交換ツールの schema が、同じきまりを 2 度書かないことを保証する。

## なぜこの試験が要るか

`gives` (差し出すもの) と `asks` (求めるもの) は同じ形をしている。そのため
**同じきまりが両側に書かれていた**。

    gives: 「gold は gives と asks のどちらか片側にだけ置ける…」
    asks : 「gold は gives と asks のどちらか片側にだけ置ける…」

schema は LLM が読む形なので、**同じことを 2 か所に書いても意味は増えず、長さ
だけが増える**。

## 縮めることより、落とさないことが大事

この試験の主目的は**きまりが消えていないこと**である。短くすることは目的では
ない。今日、**表示の一語が 66 手番にわたって行動を止めていた**のを見たばかりで、
説明を削るのは慎重にやる必要がある。

だからここでは「1 回だけ出る」を見る。0 回になれば落ちる。
"""

from __future__ import annotations

import json

import pytest

from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    get_spot_graph_specs,
)

#: 交換を正しく組み立てるために要る事実。**これが消えたら削りすぎ。**
_RULES_THAT_MUST_SURVIVE = (
    "どちらか片側にだけ",      # gold を両側に置けない
    "金だけの両替はできない",
    "所持アイテム",            # 品名の書き方
    "相手の持ち物は見えない",  # 求める品を名前で指名する理由
    "凍結",                    # 返事まで使えなくなる
    "部分的には成立しない",
)


@pytest.fixture(scope="module")
def trade_offer_text() -> str:
    definition = next(
        d for d, _ in get_spot_graph_specs() if d.name == "trade_offer"
    )
    return str(definition.description) + json.dumps(
        definition.parameters, ensure_ascii=False
    )


class TestEveryRuleSurvives:
    """削っても、交換のきまりは全部残っている。"""

    @pytest.mark.parametrize("rule", _RULES_THAT_MUST_SURVIVE)
    def test_the_rule_is_still_there(self, trade_offer_text, rule) -> None:
        """きまりが 1 つも消えていない。

        **短くすることより、落とさないことが大事。**
        """
        assert rule in trade_offer_text


class TestNoRuleIsStatedTwice:
    """同じきまりが 2 度書かれていない。"""

    @pytest.mark.parametrize("rule", ["どちらか片側にだけ", "相手の持ち物は見えない"])
    def test_the_rule_appears_once(self, trade_offer_text, rule) -> None:
        """差し出す側と求める側の両方に書かない。

        両側に書いても意味は増えず、長さだけが増える。
        """
        assert trade_offer_text.count(rule) == 1
