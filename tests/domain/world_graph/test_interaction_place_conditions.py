"""場所・明るさ・対象の状態を前提条件として書けることを保証する。

設計 doc (docs/memory_system/interpersonal_interaction_design.md §3.2) の
PR 3 にあたる。「暗い場所ならどこでも襲える」「特定の部屋でだけ使える」
「crew だけを対象にできる」を **1 回の宣言で** 書けるようにする。

3 条件はいずれも対人行為に限らず汎用である。物体 interaction でも同じ形で
使える。

判定に要る現在値 (実効照明 / 現在地 / 対象の state) が渡っていない場合は
**必ず拒否する**。silent pass させると「宣言したのに効かない」前提条件が
シナリオに残り、実 run で初めて気付くことになる。既存の
``TIME_OF_DAY_IS`` (provider 不在で拒否) と揃えた判断である。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
    SpotInteractionService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


@pytest.fixture
def svc() -> SpotInteractionService:
    return SpotInteractionService()


@pytest.fixture
def obj() -> SpotObject:
    return SpotObject(
        object_id=SpotObjectId.create(1),
        name="test_obj",
        description="test",
        object_type=ObjectTypeEnum.RESOURCE,
        state={},
        interactions=(),
    )


def _status(player_id: int, state: dict) -> PlayerStatusAggregate:
    """自由 state だけを持たせた最小の PlayerStatusAggregate を作る。"""
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(
            max_hp=100, max_mp=50, attack=10, defense=10, speed=10,
            critical_rate=0.05, evasion_rate=0.05,
        ),
        stat_growth_factor=StatGrowthFactor(1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=100, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
        state=state,
    )


class TestSpotLightingIs:
    """SPOT_LIGHTING_IS: 現在の実効照明が required_lighting と一致すれば成立。"""

    def test_matching_lighting_passes(self, svc, obj) -> None:
        """required_lighting=DARK で現在 DARK なら成立する。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.SPOT_LIGHTING_IS,
            required_lighting="DARK",
        )
        ok, msg = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_effective_lighting=LightingEnum.DARK,
        )
        assert (ok, msg) == (True, None)

    def test_brighter_spot_is_rejected_with_the_authored_message(self, svc, obj) -> None:
        """明るい場所では拒否し、シナリオが書いた失敗文をそのまま返す。

        失敗文は LLM が読む唯一の手がかりなので、汎用文で上書きしない。
        """
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.SPOT_LIGHTING_IS,
            required_lighting="DARK",
            failure_message="明るすぎる。誰かに見られる。",
        )
        ok, msg = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_effective_lighting=LightingEnum.BRIGHT,
        )
        assert ok is False
        assert msg == "明るすぎる。誰かに見られる。"

    def test_missing_current_lighting_is_rejected(self, svc, obj) -> None:
        """実効照明が渡っていなければ拒否する。

        黙って成立させると、明るい場所でも暗所限定の行為が通ってしまう。
        配線漏れは「常に失敗する」形で表に出すほうが安全側。
        """
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.SPOT_LIGHTING_IS,
            required_lighting="DARK",
        )
        ok, _ = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_effective_lighting=None,
        )
        assert ok is False

    def test_missing_required_lighting_is_rejected(self, svc, obj) -> None:
        """required_lighting を書き忘れた宣言は成立させない。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.SPOT_LIGHTING_IS,
        )
        ok, _ = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_effective_lighting=LightingEnum.DARK,
        )
        assert ok is False


class TestSpotLightingIsNot:
    """SPOT_LIGHTING_IS_NOT: 現在の実効照明が required_lighting でなければ成立。"""

    def test_different_lighting_passes(self, svc, obj) -> None:
        """required_lighting=PITCH_BLACK で現在 DARK なら成立する。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.SPOT_LIGHTING_IS_NOT,
            required_lighting="PITCH_BLACK",
        )
        ok, msg = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_effective_lighting=LightingEnum.DARK,
        )
        assert (ok, msg) == (True, None)

    def test_same_lighting_is_rejected(self, svc, obj) -> None:
        """完全な暗闇では拒否する (「暗すぎて手元が見えない」の表現)。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.SPOT_LIGHTING_IS_NOT,
            required_lighting="PITCH_BLACK",
            failure_message="暗すぎて手元が見えない。",
        )
        ok, msg = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_effective_lighting=LightingEnum.PITCH_BLACK,
        )
        assert (ok, msg) == (False, "暗すぎて手元が見えない。")


class TestAtSpotIs:
    """AT_SPOT_IS: 行為者の現在地が required_spot_id と一致すれば成立。"""

    def test_matching_spot_passes(self, svc, obj) -> None:
        """指定スポットに居れば成立する。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.AT_SPOT_IS,
            required_spot_id=SpotId.create(7),
        )
        ok, msg = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_spot_id=SpotId.create(7),
        )
        assert (ok, msg) == (True, None)

    def test_other_spot_is_rejected(self, svc, obj) -> None:
        """別のスポットに居れば拒否する。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.AT_SPOT_IS,
            required_spot_id=SpotId.create(7),
            failure_message="ここではできない。",
        )
        ok, msg = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_spot_id=SpotId.create(8),
        )
        assert (ok, msg) == (False, "ここではできない。")

    def test_missing_current_spot_is_rejected(self, svc, obj) -> None:
        """現在地が渡っていなければ拒否する (配線漏れを表に出す)。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.AT_SPOT_IS,
            required_spot_id=SpotId.create(7),
        )
        ok, _ = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_spot_id=None,
        )
        assert ok is False

    def test_missing_required_spot_is_rejected(self, svc, obj) -> None:
        """required_spot を書き忘れた宣言は成立させない。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.AT_SPOT_IS,
        )
        ok, _ = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_spot_id=SpotId.create(7),
        )
        assert ok is False


class TestAtSpotIsNot:
    """AT_SPOT_IS_NOT: 行為者の現在地が required_spot_id でなければ成立。"""

    def test_other_spot_passes(self, svc, obj) -> None:
        """禁止された場所以外なら成立する (「聖域では争えない」の表現)。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.AT_SPOT_IS_NOT,
            required_spot_id=SpotId.create(7),
        )
        ok, msg = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_spot_id=SpotId.create(8),
        )
        assert (ok, msg) == (True, None)

    def test_forbidden_spot_is_rejected(self, svc, obj) -> None:
        """禁止された場所では拒否する。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.AT_SPOT_IS_NOT,
            required_spot_id=SpotId.create(7),
            failure_message="ここは聖域だ。",
        )
        ok, msg = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_spot_id=SpotId.create(7),
        )
        assert (ok, msg) == (False, "ここは聖域だ。")


class TestTargetPlayerStateIs:
    """TARGET_PLAYER_STATE_IS: 対象プレイヤーの自由 state を判定する。

    ``PLAYER_STATE_IS`` は行為者しか見ない。「crew だけ殺せる」「まだ印が
    無い相手だけ」を書くには対象側を見る条件が要る。
    """

    def test_matching_target_state_passes(self, svc, obj) -> None:
        """対象の state が required_state と全キー一致すれば成立する。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_PLAYER_STATE_IS,
            required_state={"role": "crew"},
        )
        ok, msg = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            target_player_status=_status(2, {"role": "crew"}),
        )
        assert (ok, msg) == (True, None)

    def test_different_target_state_is_rejected(self, svc, obj) -> None:
        """対象の state が違えば拒否する。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_PLAYER_STATE_IS,
            required_state={"role": "crew"},
            failure_message="その相手は同じ側の人間だ。",
        )
        ok, msg = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            target_player_status=_status(2, {"role": "hunter"}),
        )
        assert (ok, msg) == (False, "その相手は同じ側の人間だ。")

    def test_acting_player_state_is_not_consulted(self, svc, obj) -> None:
        """行為者の state が一致していても、対象が違えば拒否する。

        ``PLAYER_STATE_IS`` と取り違えて配線すると、自分の役割を見て
        「誰でも殺せる」状態になる。両者を明確に分ける。
        """
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_PLAYER_STATE_IS,
            required_state={"role": "crew"},
        )
        ok, _ = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            acting_player_status=_status(1, {"role": "crew"}),
            target_player_status=_status(2, {"role": "hunter"}),
        )
        assert ok is False

    def test_missing_target_status_is_rejected(self, svc, obj) -> None:
        """対象が渡っていなければ拒否する (物体 interaction に書いた場合)。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_PLAYER_STATE_IS,
            required_state={"role": "crew"},
        )
        ok, _ = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            target_player_status=None,
        )
        assert ok is False


class TestEveryConditionTypeHasABranch:
    """全 InteractionConditionTypeEnum メンバに評価分岐があること。

    ``_evaluate_condition`` の最終行は未対応の条件を「未対応の前提条件です」
    で落とす。enum に値を足して分岐を書き忘れると、**その条件を使う
    interaction は永久に実行不能**になる。しかも失敗文を書いていれば
    シナリオ作者の文言に隠れて、原因が見えないまま「なぜか一度も成功
    しない」として表れる。

    ここでは分岐の有無だけを見る。判定内容の正しさは各条件のテストが持つ。
    """

    _UNHANDLED = "未対応の前提条件です"

    @pytest.mark.parametrize(
        "condition_type",
        list(InteractionConditionTypeEnum),
        ids=lambda t: t.value,
    )
    def test_condition_type_is_not_unhandled(self, svc, obj, condition_type) -> None:
        """どの条件も「未対応」で落ちない (必要値が欠けた拒否は許容)。"""
        cond = InteractionCondition(condition_type=condition_type)
        _, msg = svc._evaluate_condition(
            cond, obj, frozenset(), owned_item_spec_counts={},
        )
        assert msg != self._UNHANDLED, (
            f"{condition_type.value} に評価分岐がありません。"
            "この条件を使う interaction は永久に実行不能になります。"
        )
