"""GameEndCondition が条件型ごとの必須フィールド欠落を構築時に拒むことを保証する。

とくに **分岐を書き忘れた条件型を素通りさせない** ことを見る。以前は最後の
分岐を抜けるとそのまま構築が成功し、新しい条件型は検証なしでインスタンスに
なれた。必須フィールドが空のまま run に入るので、シナリオ作者は「書いたのに
効かない」形の静かな失敗を踏む (#848 と同じ形が生成側に残っていた)。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import (
    GameEndConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    GameEndConditionValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import (
    GameEndCondition,
)


class TestUnknownConditionTypeIsRejected:
    """検証分岐を持たない条件型は構築できない。"""

    def test_condition_type_without_a_validation_branch_raises(self) -> None:
        """``__post_init__`` に分岐が無い条件型を渡すと拒否される。

        enum に値を足して検証分岐を書き忘れた状況を、実在しない条件型を
        差し込んで再現する。素通りするなら必須フィールド無しで構築できて
        しまう。
        """

        class _UnbranchedConditionType:
            """``__post_init__`` のどの分岐にも一致しない条件型の代役。"""

            value = "UNBRANCHED_FOR_TEST"

        with pytest.raises(GameEndConditionValidationException) as exc:
            GameEndCondition(condition_type=_UnbranchedConditionType())  # type: ignore[arg-type]

        assert "未知の終了条件型です" in str(exc.value)

    @pytest.mark.parametrize(
        "condition_type", list(GameEndConditionTypeEnum), ids=lambda t: t.value
    )
    def test_every_declared_condition_type_has_a_validation_branch(
        self, condition_type: GameEndConditionTypeEnum
    ) -> None:
        """宣言済みの全条件型は「未知」で落ちない (必須値欠落での拒否は許容)。

        分岐の有無だけを見る。どのフィールドが必須かは
        ``test_scenario_loader.py`` の必須フィールド表が持つ。
        """
        try:
            GameEndCondition(condition_type=condition_type)
        except GameEndConditionValidationException as exc:
            assert "未知の終了条件型です" not in str(exc), (
                f"{condition_type.value} に検証分岐がありません"
            )


class TestAllPlayerOutcomesResolvedNeedsNoField:
    """ALL_PLAYER_OUTCOMES_RESOLVED は指定する値を持たない。"""

    def test_it_is_constructible_without_any_field(self) -> None:
        """条件型だけで構築できる。

        全対象プレイヤーが終局結果へ確定したかだけを見るので、どこで・何を
        数えるかを条件側に書かない。
        """
        condition = GameEndCondition(
            condition_type=GameEndConditionTypeEnum.ALL_PLAYER_OUTCOMES_RESOLVED
        )

        assert condition.target_spot_id is None
        assert condition.target_flag is None


class TestSpotConditionsRequireATarget:
    """ALL_AT_SPOT / ANY_AT_SPOT は target_spot_id を要る。"""

    @pytest.mark.parametrize(
        "condition_type",
        [GameEndConditionTypeEnum.ALL_AT_SPOT, GameEndConditionTypeEnum.ANY_AT_SPOT],
        ids=lambda t: t.value,
    )
    def test_missing_target_spot_is_rejected(
        self, condition_type: GameEndConditionTypeEnum
    ) -> None:
        """target_spot_id を省くと拒否される。"""
        with pytest.raises(GameEndConditionValidationException) as exc:
            GameEndCondition(condition_type=condition_type)

        assert "target_spot_id が必要です" in str(exc.value)

    @pytest.mark.parametrize(
        "condition_type",
        [GameEndConditionTypeEnum.ALL_AT_SPOT, GameEndConditionTypeEnum.ANY_AT_SPOT],
        ids=lambda t: t.value,
    )
    def test_target_spot_is_accepted(
        self, condition_type: GameEndConditionTypeEnum
    ) -> None:
        """target_spot_id があれば構築できる。"""
        condition = GameEndCondition(
            condition_type=condition_type, target_spot_id=SpotId(1)
        )

        assert condition.target_spot_id == SpotId(1)
