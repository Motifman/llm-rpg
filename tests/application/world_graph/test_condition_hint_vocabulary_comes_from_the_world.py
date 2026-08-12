"""前提条件ヒントの呼び名が、内部識別子を漏らさないことを保証する。

## なぜこの試験が要るか

`world_vocabulary` は「enum の生値をプロンプトに出さない」ために作られた。その
docstring は過去の事故をこう記録している。

    ``LightingEnum`` は 4 件なのに表は 3 件で、``PITCH_BLACK`` だけ生値が出た。
    しかも夜 + 嵐の屋外で実際に到達する。**この仕組みが消しに来た生値が、
    一番暗いときにだけ残っていた**

そして同じ docstring が `interaction_condition_hint_text` について宣言している。

    語尾が違う表を持っている。**それは統合しない。** ただし**キーの集合は同じで
    なければならない**ので、走査は同じ enum から引く。

**この宣言が守られていなかった。** `interaction_condition_hint_text` 側は

- 未知値に対して ``.get(value, value)`` で**生値を返していた**
- 網羅テストが 1 本も無かった

つまり `world_vocabulary` が塞いだ穴が、別ファイルにそのまま残っていた。

## 時刻帯だけ扱いが違う理由

天候 / 明るさ / 気温は **engine の enum** が値の集合を決める。シナリオはこれらを
増やせない (増やすには enum を触る = コード変更) ので、既定の呼び名をコードが
持つのは筋が通る。

時刻帯は違う。`DayNightPhaseDef` は「シナリオ自由命名」と明記されており、
**呼び名 (`display_text`) もシナリオが宣言している**。だからコードが表を持つのは
`world_briefing` が直した「写しは腐る」と同型で、実際に腐っていた。

    シナリオ v3_coop / v4_coop が宣言:  predawn(未明) morning noon night
    コードの表:                        morning noon afternoon evening night

``predawn`` が表に無く、``afternoon`` はどのシナリオも宣言していない。**両方向に
ずれていた。** `predawn` を要求する条件を書いた瞬間に ``"predawnのみ"`` と生値が出る。

だから時刻帯は表を捨て、シナリオが宣言した呼び名を引く。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from ai_rpg_world.application.world_graph import interaction_condition_hint_text as H
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef


def _interaction(*conditions: InteractionCondition) -> InteractionDef:
    return InteractionDef(
        action_name="probe",
        display_label="調べる",
        preconditions=tuple(conditions),
        effects=(),
    )


class TestTheEnumBackedTablesCoverTheirEnums:
    """engine が値を決める呼び名の表が、enum 全件を持つ。"""

    def test_tables_are_declared_for_scanning(self) -> None:
        """走査対象の (enum, 表) の組が宣言されている。

        組が空だと以下の網羅試験は「対象 0 件で成功」になる。
        """
        assert H.ENUM_BACKED_LABEL_TABLES, (
            "ENUM_BACKED_LABEL_TABLES が空です。表を足したらここにも足してください。"
        )

    def test_every_label_table_in_the_module_is_scanned(self) -> None:
        """モジュールにある呼び名の表が、**全部**走査対象に入っている。

        変異で ``(LightingEnum, _LIGHTING_LABELS)`` を走査リストから外したら
        **139 passed で素通りした**。表を足した人が走査リストへ足し忘れる、あるいは
        既存の行を消す形が検出できていなかった。走査リスト自体が静かに縮む。

        モジュール側の ``_*_LABELS`` を数え上げて突き合わせる。表を足せば自動で
        対象になるので、リストへ足し忘れればここで落ちる。
        """
        defined = {
            name
            for name, value in vars(H).items()
            if name.endswith("_LABELS") and isinstance(value, dict)
        }
        scanned_ids = {id(table) for _enum, table in H.ENUM_BACKED_LABEL_TABLES}
        unscanned = sorted(
            name for name in defined if id(getattr(H, name)) not in scanned_ids
        )

        assert not unscanned, (
            f"走査対象に入っていない呼び名の表があります: {unscanned}。"
            " ENUM_BACKED_LABEL_TABLES に (enum, 表) を足してください。"
        )

    def test_no_enum_value_is_missing_a_label(self) -> None:
        """どの enum 値にも呼び名がある。

        値を 1 つ足して表に載せ忘れると、その値だけ生値がプロンプトへ出る。
        `world_vocabulary` の PITCH_BLACK 事故と同じ形。
        """
        for enum_cls, table in H.ENUM_BACKED_LABEL_TABLES:
            missing = sorted(e.value for e in enum_cls if e.value not in table)
            assert missing == [], (enum_cls.__name__, missing)

    def test_no_table_keeps_a_stale_key(self) -> None:
        """表に、enum から消えた値のキーが残っていない。"""
        for enum_cls, table in H.ENUM_BACKED_LABEL_TABLES:
            known = {e.value for e in enum_cls}
            stale = sorted(set(table) - known)
            assert stale == [], (enum_cls.__name__, stale)

    def test_the_keys_match_the_shared_vocabulary(self) -> None:
        """`world_vocabulary` と**キーの集合が一致する**。

        語尾は違ってよい (「暗い」 と 「暗い場所のみ」)。しかし片方にだけ値がある
        状態は、どちらかが生値を出す side を持つことを意味する。docstring が
        「キーの集合は同じでなければならない」と書いていた関係を、文章ではなく
        テストで縛る。
        """
        from ai_rpg_world.application.llm.services.world_vocabulary import (
            DISPLAY_TABLES,
        )

        shared = {enum_cls.__name__: set(table) for enum_cls, table in DISPLAY_TABLES}
        for enum_cls, table in H.ENUM_BACKED_LABEL_TABLES:
            name = enum_cls.__name__
            if name not in shared:
                continue
            assert set(table) == shared[name], (
                name,
                sorted(set(table) ^ shared[name]),
            )


class TestAnUnknownValueNeverLeaksIntoTheHint:
    """表に無い値でも、生の識別子をヒストに出さない。"""

    def test_an_unknown_weather_drops_the_hint(self) -> None:
        """未知の天候はヒントを落とす。生値も裸の接尾辞も出さない。

        `.get(value, "")` にすると ``"のみ"`` だけが残って、かえって読めない。
        既存の `_has_item` と同じく**その条件のヒントだけ落とす**。
        """
        interaction = _interaction(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.WEATHER_IS,
                required_weather_type="SOMETHING_NEW",
            )
        )

        hints = H.declarative_condition_hints(interaction)

        assert hints == (), hints

    def test_an_unknown_lighting_drops_the_hint(self) -> None:
        """未知の明るさもヒントを落とす。"""
        interaction = _interaction(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.SPOT_LIGHTING_IS,
                required_lighting="SOMETHING_NEW",
            )
        )

        hints = H.declarative_condition_hints(interaction)

        assert hints == (), hints

    def test_a_known_weather_still_renders(self) -> None:
        """既知の天候は従来どおりヒントになる (正の対照)。

        これが無いと「常に落とす」実装でも上の 2 件が通る。
        """
        interaction = _interaction(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.WEATHER_IS,
                required_weather_type="RAIN",
            )
        )

        hints = H.declarative_condition_hints(interaction)

        assert len(hints) == 1
        assert "雨" in hints[0]


class TestTimeOfDayLabelComesFromTheScenario:
    """時刻帯の呼び名は、シナリオが宣言した `display_text` から来る。"""

    def _time_condition(self, phase: str) -> InteractionDef:
        return _interaction(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.TIME_OF_DAY_IS,
                required_time_of_day_phase=phase,
            )
        )

    def test_the_declared_display_text_is_used(self) -> None:
        """resolver が返した呼び名がヒントに出る。

        シナリオが ``{"name": "predawn", "display_text": "未明"}`` と宣言していれば
        「未明のみ」と出る。コード側の表には ``predawn`` が無かったので、以前は
        ``"predawnのみ"`` と生値が出ていた。
        """
        hints = H.declarative_condition_hints(
            self._time_condition("predawn"),
            time_of_day_phase_label_resolver=lambda name: {"predawn": "未明"}.get(name),
        )

        assert len(hints) == 1
        assert "未明" in hints[0]
        assert "predawn" not in hints[0]

    def test_an_undeclared_phase_drops_the_hint(self) -> None:
        """宣言に無いフェーズはヒントを落とす。生値を出さない。"""
        hints = H.declarative_condition_hints(
            self._time_condition("dawn"),
            time_of_day_phase_label_resolver=lambda name: {"predawn": "未明"}.get(name),
        )

        assert hints == (), hints

    def test_without_a_resolver_the_hint_is_dropped(self) -> None:
        """resolver を渡さない呼び出しでは時刻帯ヒントを落とす。

        コード側に既定の表を持たない、という判断をここで固定する。表を戻すと
        シナリオが宣言した呼び名と二重管理になり、また腐る。
        """
        hints = H.declarative_condition_hints(self._time_condition("night"))

        assert hints == (), hints

    def test_the_module_has_no_hardcoded_phase_table(self) -> None:
        """コードに時刻帯の呼び名表が残っていない。

        表を戻したら落とす。時刻帯の呼び名の所有者はシナリオである。
        """
        assert not hasattr(H, "_TIME_OF_DAY_PHASE_LABELS"), (
            "時刻帯の呼び名表がコードに戻っています。"
            " シナリオの day_night phases の display_text を使ってください。"
        )
