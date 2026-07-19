"""``spot_graph_attack`` の description が戦闘のリアリティ情報を含むか
(Y_after_pr639_640_200tick 後続、PR-Z)。

Y_after_pr639_640 の分析で観測された問題:
- モンスターからの攻撃が **36 件** (P3 15 tick 連続 / P2 4 連発被弾) 受けた
  にもかかわらず、``spot_graph_attack`` の呼び出しは **0 件**
- 4 プレイヤー全員が「反撃せず逃げる or 被弾を放置」の判断
- attack description は「同じスポットに居るモンスターを攻撃する。」の 1 行
  のみで、勝率 / 威力 / 武器要件 / 逃走選択肢の hint がゼロ

LLM 視点で「勝てるか / 逆に殺されるか」判断材料が皆無なので、リスク回避
方向に倒れるのは合理的だが、シナリオ (survival) 上は反撃も選択肢に
入れられるよう description を強化する。

## 変更方針

description に以下を明示する:

- 素手攻撃の威力は小さい (LLM が「殴れば倒せる」誤解しない)
- 武器 (装備) を持っていれば威力が上がる
- 相手 HP を「健康 / 弱っている / 瀕死」の 3 段階でしか観測できないので、
  bucket をよく見て判断する
- 逃走 (travel_to で別 spot へ移動) も戦術的選択肢

description は静的文字列 (prefix cache 安全)。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    ATTACK_DEFINITION,
)


class TestAttackDescriptionHasCombatHints:
    """attack description が戦闘のリアリティ情報を伝える。"""

    def test_documented_behavior_2(self) -> None:
        """「殴れば倒せる」誤読を防ぐため、素手のダメージが小さいことを書く。"""
        desc = ATTACK_DEFINITION.description
        assert (
            "素手" in desc or "武器" in desc
        ), "武器 / 素手 に関する情報が description に無い"

    def test_target_hp_bucket(self) -> None:
        """`health_bucket` (健康/弱っている/瀕死) の観測を判断材料に使う旨。"""
        desc = ATTACK_DEFINITION.description
        assert (
            "健康" in desc
            or "弱って" in desc
            or "瀕死" in desc
            or "health" in desc.lower()
        ), "相手 HP の観測手段が説明されていない"

    def test_documented_behavior(self) -> None:
        """「攻撃 or 逃走」の判断枠組みを LLM に示す。"""
        desc = ATTACK_DEFINITION.description
        assert (
            "逃" in desc or "退" in desc or "travel_to" in desc
        ), "逃走 / travel_to への言及が無く、attack が唯一の対処と誤読される"

    def test_description_static_placeholder(self) -> None:
        """description は static で placeholder なし。"""
        desc = ATTACK_DEFINITION.description
        assert isinstance(desc, str)
        assert "{" not in desc, "placeholder の疑い"
