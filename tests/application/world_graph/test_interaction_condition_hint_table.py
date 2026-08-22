"""条件のヒント文が、種別ごとに表で網羅されていることを保証する。

## なぜ表にしたか

否定形の文は、肯定形の機械的な反転ではない。

    TIME_OF_DAY_IS      → 「朝のみ」
    TIME_OF_DAY_IS_NOT  → 「朝不可」

種別が別々だったころは、分岐を書き忘れてもヒントが出ないだけだった。抜けは
見れば分かる。ところが `negate` を分岐の中で読む形にすると、**書き忘れた
分岐は否定を無視して肯定の文を出す**。「嵐不可」の規則に「嵐のみ」と表示
される。出ないのではなく、嘘が出る。

実際にそうなった。`negate` を入れて loader が旧種別を畳んだ直後、v4 の
「夜不可・嵐不可」が「夜のみ・嵐のみ」と表示され、既存テストが捕まえた。

だからヒント層は表にした。**分岐は `negate` を読まない。** 表が肯定と否定の
2 つを持ち、呼び出し側がどちらを使うかだけ決める。あとは「全種別が表に
載っているか」を機械的に確かめれば、書き忘れが構造的に起こらなくなる。
"""

from __future__ import annotations

from ai_rpg_world.application.world_graph.interaction_condition_hint_text import (
    _HINT_RENDERERS,
)
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)

#: ヒントを出さないと決めた種別と、その理由。
#:
#: **「まだ書いていない」と「出さないと決めた」を区別する**ためにここへ書く。
#: 空欄のまま放置すると、どちらなのか誰にも分からなくなる。
_NO_HINT_CONDITIONS = {
    # 常に成立するので添える情報が無い。
    "ALWAYS",
    # 物体行では所持品の不足が remediation に出るため重複する。
    "HAS_ITEMS",
    # 状態そのものが object 行の (…) に出るので二重になる。
    "OBJECT_STATE",
    "OBJECT_STOCK_AT_LEAST",
    # 世界フラグは player から見えない内部状態。出しても行動に繋がらない。
    "FLAG_SET",
    "FLAG_NOT_SET",
    # 同席人数・準備済み行動・パズル入力は、行動の文脈から自明。
    "PLAYERS_AT_SPOT",
    "PREPARED_ACTION",
    "PUZZLE_INPUT_MATCH",
    # アイテム instance の状態は持ち物欄に出る。
    "ITEM_INSTANCE_STATE",
    "TARGET_ITEM_INSTANCE_STATE",
    # 身体の状態は「身体の状態」section に出る。
    "PLAYER_NEED_AT_LEAST",
    # 所持金は現在状態に常に出ているので、額の不足は本人が計算できる。
    # 足りないときは failure_message が要求額ごと伝える。
    "PLAYER_GOLD_AT_LEAST",
    "PLAYER_HP_RATIO_BELOW",
    "PLAYER_HP_RATIO_AT_LEAST",
    # 役割などの秘匿条件。**ヒントに出すと役割が漏れる** (#905)。
    "PLAYER_STATE_IS",
    "TARGET_PLAYER_STATE_IS",
    # 対象が倒れているかは同席者行に「(倒れて動かない)」と出るので二重。
    "TARGET_PLAYER_IS_INCAPACITATED",
    # 場所は「その物体が在るスポット」でしか表示されないので常に自明。
    # 否定形も同じ理由で出さない (畳み先にヒントが無いので旧種別も残る)。
    "AT_SPOT_IS",
    "AT_SPOT_IS_NOT",
}


class TestEveryConditionTypeIsAccountedFor:
    """すべての条件が、表に載っているか「出さない」と宣言されている。"""

    def test_no_condition_type_is_unaccounted(self) -> None:
        """どちらにも無い種別が存在しない。

        落ちたら、足した条件のヒントを書くか `_NO_HINT_CONDITIONS` に
        **理由と共に**足す。理由の無い追加は、次に読む人が判断できない。
        """
        declared = {c.value for c in _HINT_RENDERERS}
        unaccounted = sorted(
            c.value
            for c in InteractionConditionTypeEnum
            if c.value not in declared and c.value not in _NO_HINT_CONDITIONS
        )

        assert not unaccounted, f"ヒントの扱いが未定の条件: {unaccounted}"

    def test_the_no_hint_list_names_only_real_conditions(self) -> None:
        """消えた条件が「出さない」一覧に残らない。"""
        known = {c.value for c in InteractionConditionTypeEnum}
        stale = sorted(c for c in _NO_HINT_CONDITIONS if c not in known)

        assert not stale, f"実在しない条件が残っています: {stale}"


class TestNegatedTypesRenderTheNegatedWording:
    """否定専用の種別は、否定の文を出す。

    **ここが今回の発端。** 否定を「結果の反転」で扱おうとしたとき、表が
    無いと肯定の文が出た。v4 の「夜不可」が「夜のみ」と表示された。
    種別ごとに文を持たせておけば、その化け方が起こらない。
    """

    def test_each_negated_type_has_its_own_wording(self) -> None:
        """否定専用の種別すべてに、専用の文がある。"""
        from ai_rpg_world.application.world_graph.interaction_condition_hint_text import (  # noqa: E501
            _LEGACY_NEGATED_PAIRS,
        )

        missing = []
        for negated, base in _LEGACY_NEGATED_PAIRS.items():
            if _HINT_RENDERERS.get(base) is None:
                continue  # 肯定側もヒントを出さない種別
            if _HINT_RENDERERS.get(negated) is None:
                missing.append(negated.value)

        assert not missing, f"否定の文が無い種別: {missing}"

    def test_the_negated_wording_differs_from_the_positive_one(self) -> None:
        """否定の文が、肯定の文と別物になっている。

        同じ文が出るなら、否定を表現できていない。
        """
        from ai_rpg_world.application.world_graph.interaction_condition_hint_text import (  # noqa: E501
            _LEGACY_NEGATED_PAIRS,
        )

        class _Cond:
            required_time_of_day_phase = "night"
            required_weather_type = "STORM"
            required_lighting = "DARK"
            target_item_spec_id = None
            required_quantity = 1

        # 時刻帯の呼び名はシナリオが持つので、renderer を直接叩くときは
        # 世界の語彙を渡す。渡さないと時刻帯側は None になり、否定との差が
        # 「どちらも None」になって比較が成立しない。
        phase_label = {"night": "夜"}.get

        for negated, base in _LEGACY_NEGATED_PAIRS.items():
            base_renderers = _HINT_RENDERERS.get(base)
            negated_renderers = _HINT_RENDERERS.get(negated)
            if base_renderers is None or negated_renderers is None:
                continue
            positive = base_renderers[0](_Cond(), None, None, phase_label)
            negative = negated_renderers[0](_Cond(), None, None, phase_label)
            if positive is None and negative is None:
                continue
            assert positive != negative, negated.value
