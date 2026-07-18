"""看板 (PR-F) — WRITE_PLAYER_TEXT / SHOW_PLAYER_TEXT effect のユニットテスト。

プレイヤーが自由テキストを世界オブジェクトに書き込み、他プレイヤーが後で
examine で読める「看板」primitive の挙動を検証する。

- WRITE_PLAYER_TEXT: interaction_parameters["text"] を object.state へ
  書き手名・tick と共に上書き保存する (v1 は 1 枚のみ保持)。
- SHOW_PLAYER_TEXT: object.state に書かれた内容を
  「『本文』 — 書き手名」形式の message として組み立てる。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    SIGN_TEXT_MAX_LENGTH,
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


def _sign(initial_state: dict | None = None) -> SpotObject:
    return SpotObject(
        object_id=SpotObjectId.create(9),
        name="古い看板",
        description="誰かが書き込めそうな看板。",
        object_type=SpotObjectTypeEnum.SIGN,
        state=dict(initial_state or {}),
        interactions=(),
    )


def _interior_with(obj: SpotObject) -> SpotInterior:
    return SpotInterior((), (obj,), (), ())


class TestWritePlayerTextEffect:
    """WRITE_PLAYER_TEXT: interaction_parameters["text"] を state へ保存する。"""

    def test_書き込むと_本文_書き手名_tick_が_state_に保存される(self) -> None:
        svc = WorldGraphEffectService()
        sign = _sign()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
            parameters={},
        )
        result = svc.apply_effects(
            interior=_interior_with(sign),
            acting_object=sign,
            effects=[effect],
            world_flags=frozenset(),
            current_tick=WorldTick(10),
            interaction_parameters={"text": "北へ行くと水場がある"},
            acting_player_display_name="アリス",
        )
        new_state = result.new_interior.objects[0].state
        assert new_state["sign_text"] == "北へ行くと水場がある"
        assert new_state["sign_author_name"] == "アリス"
        assert new_state["sign_written_tick"] == 10

    def test_2人目が書くと_1人目の内容が上書きされて消える(self) -> None:
        svc = WorldGraphEffectService()
        sign = _sign()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
            parameters={},
        )
        interior = _interior_with(sign)
        first = svc.apply_effects(
            interior=interior,
            acting_object=sign,
            effects=[effect],
            world_flags=frozenset(),
            current_tick=WorldTick(1),
            interaction_parameters={"text": "1人目のメモ"},
            acting_player_display_name="アリス",
        )
        updated_sign = first.new_interior.objects[0]
        second = svc.apply_effects(
            interior=first.new_interior,
            acting_object=updated_sign,
            effects=[effect],
            world_flags=frozenset(),
            current_tick=WorldTick(5),
            interaction_parameters={"text": "2人目のメモ"},
            acting_player_display_name="ボブ",
        )
        new_state = second.new_interior.objects[0].state
        assert new_state["sign_text"] == "2人目のメモ"
        assert new_state["sign_author_name"] == "ボブ"
        assert new_state["sign_written_tick"] == 5

    def test_text_が欠落していると_InteractionNotAllowedException_が投げられ_state_は変わらない(
        self,
    ) -> None:
        """「書いたつもりで書けていない」まま success=true で返る静かな失敗
        (実 run t72 で観測) を避けるため、text 欠落は失敗として本人に返す。
        state を変更する前に例外を投げるので object.state は不変であること
        も併せて保証する。"""
        svc = WorldGraphEffectService()
        sign = _sign()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
            parameters={},
        )
        with pytest.raises(InteractionNotAllowedException) as exc_info:
            svc.apply_effects(
                interior=_interior_with(sign),
                acting_object=sign,
                effects=[effect],
                world_flags=frozenset(),
                current_tick=WorldTick(1),
                interaction_parameters={},
                acting_player_display_name="アリス",
            )
        assert "text" in str(exc_info.value)
        assert "sign_text" not in sign.state

    def test_空文字のtextは_InteractionNotAllowedException_が投げられ_state_は変わらない(
        self,
    ) -> None:
        svc = WorldGraphEffectService()
        sign = _sign()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
            parameters={},
        )
        with pytest.raises(InteractionNotAllowedException):
            svc.apply_effects(
                interior=_interior_with(sign),
                acting_object=sign,
                effects=[effect],
                world_flags=frozenset(),
                current_tick=WorldTick(1),
                interaction_parameters={"text": ""},
                acting_player_display_name="アリス",
            )
        assert "sign_text" not in sign.state

    def test_text_が非文字列だと_InteractionNotAllowedException_が投げられ_state_は変わらない(
        self,
    ) -> None:
        """interact ツールの自由入力は JSON 経由なので数値や配列が渡る余地が
        あり、非文字列も欠落と同じ扱いにする。"""
        svc = WorldGraphEffectService()
        sign = _sign()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
            parameters={},
        )
        with pytest.raises(InteractionNotAllowedException):
            svc.apply_effects(
                interior=_interior_with(sign),
                acting_object=sign,
                effects=[effect],
                world_flags=frozenset(),
                current_tick=WorldTick(1),
                interaction_parameters={"text": 12345},
                acting_player_display_name="アリス",
            )
        assert "sign_text" not in sign.state

    def test_文字数上限を超えると切り詰められ_可視化される(self) -> None:
        svc = WorldGraphEffectService()
        sign = _sign()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
            parameters={},
        )
        long_text = "あ" * (SIGN_TEXT_MAX_LENGTH + 50)
        result = svc.apply_effects(
            interior=_interior_with(sign),
            acting_object=sign,
            effects=[effect],
            world_flags=frozenset(),
            current_tick=WorldTick(1),
            interaction_parameters={"text": long_text},
            acting_player_display_name="アリス",
        )
        new_state = result.new_interior.objects[0].state
        assert len(new_state["sign_text"]) == SIGN_TEXT_MAX_LENGTH
        assert any("切り詰め" in m for m in result.messages)

    def test_display_name_未指定なら既定のフォールバック名が保存される(self) -> None:
        svc = WorldGraphEffectService()
        sign = _sign()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
            parameters={},
        )
        result = svc.apply_effects(
            interior=_interior_with(sign),
            acting_object=sign,
            effects=[effect],
            world_flags=frozenset(),
            current_tick=WorldTick(1),
            interaction_parameters={"text": "誰かが書いた"},
        )
        new_state = result.new_interior.objects[0].state
        assert new_state["sign_author_name"]

    def test_public_observable_effectとして第三者観測に乗る(self) -> None:
        """既定 visibility は PUBLIC_OBSERVABLE (物理オブジェクトへの書き込みは見える)。"""
        svc = WorldGraphEffectService()
        sign = _sign()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
            parameters={},
        )
        result = svc.apply_effects(
            interior=_interior_with(sign),
            acting_object=sign,
            effects=[effect],
            world_flags=frozenset(),
            current_tick=WorldTick(1),
            interaction_parameters={"text": "メモ"},
            acting_player_display_name="アリス",
        )
        assert len(result.public_observable_effects) == 1

    def test_更新後のオブジェクトは看板_3keyがhidden_state_keysに入る(self) -> None:
        """PR-J: examine した本人だけが読める設計を守るため、書き込み確定時に
        sign_text / sign_author_name / sign_written_tick を hidden_state_keys へ
        自動で加える (シナリオ JSON 側の設定に頼らない)。"""
        svc = WorldGraphEffectService()
        sign = _sign()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
            parameters={},
        )
        result = svc.apply_effects(
            interior=_interior_with(sign),
            acting_object=sign,
            effects=[effect],
            world_flags=frozenset(),
            current_tick=WorldTick(1),
            interaction_parameters={"text": "メモ"},
            acting_player_display_name="アリス",
        )
        updated = result.new_interior.objects[0]
        assert updated.hidden_state_keys == {
            "sign_text",
            "sign_author_name",
            "sign_written_tick",
        }

    def test_更新後のvisible_stateには本文_書き手名_tickが含まれない(self) -> None:
        """visible_state() 経由で周囲プレイヤーのプロンプトに本文が乗らない
        ことを current_state_builder レベルの前提として保証する。"""
        svc = WorldGraphEffectService()
        sign = _sign()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
            parameters={},
        )
        result = svc.apply_effects(
            interior=_interior_with(sign),
            acting_object=sign,
            effects=[effect],
            world_flags=frozenset(),
            current_tick=WorldTick(1),
            interaction_parameters={"text": "メモ"},
            acting_player_display_name="アリス",
        )
        updated = result.new_interior.objects[0]
        visible = updated.visible_state()
        assert "sign_text" not in visible
        assert "sign_author_name" not in visible
        assert "sign_written_tick" not in visible

    def test_上書き後もhidden_state_keysが維持される(self) -> None:
        """2人目が書き込んで上書きしても hidden 属性が消えないことを保証する。"""
        svc = WorldGraphEffectService()
        sign = _sign()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
            parameters={},
        )
        first = svc.apply_effects(
            interior=_interior_with(sign),
            acting_object=sign,
            effects=[effect],
            world_flags=frozenset(),
            current_tick=WorldTick(1),
            interaction_parameters={"text": "1人目のメモ"},
            acting_player_display_name="アリス",
        )
        updated_sign = first.new_interior.objects[0]
        second = svc.apply_effects(
            interior=first.new_interior,
            acting_object=updated_sign,
            effects=[effect],
            world_flags=frozenset(),
            current_tick=WorldTick(5),
            interaction_parameters={"text": "2人目のメモ"},
            acting_player_display_name="ボブ",
        )
        updated = second.new_interior.objects[0]
        assert updated.hidden_state_keys == {
            "sign_text",
            "sign_author_name",
            "sign_written_tick",
        }
        assert "sign_text" not in updated.visible_state()

    def test_効果サマリのstate_deltaに本文_書き手名_tickが乗らない(self) -> None:
        """description には「書き込んだ」という行為の可視性は残すが、
        state_delta からは本文相当の 3 key を除外する。"""
        svc = WorldGraphEffectService()
        sign = _sign()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
            parameters={},
        )
        result = svc.apply_effects(
            interior=_interior_with(sign),
            acting_object=sign,
            effects=[effect],
            world_flags=frozenset(),
            current_tick=WorldTick(1),
            interaction_parameters={"text": "水場はここから北"},
            acting_player_display_name="アリス",
        )
        assert len(result.public_observable_effects) == 1
        summary = result.public_observable_effects[0]
        assert "アリス" in summary.description
        assert "書き込んだ" in summary.description
        delta_keys = {entry.key for entry in summary.state_delta}
        assert "sign_text" not in delta_keys
        assert "sign_author_name" not in delta_keys
        assert "sign_written_tick" not in delta_keys


class TestShowPlayerTextEffect:
    """SHOW_PLAYER_TEXT: state から「『本文』 — 書き手名」形式の message を組む。"""

    def test_書かれていれば本文と書き手名がmessageに現れる(self) -> None:
        svc = WorldGraphEffectService()
        sign = _sign({
            "sign_text": "北へ行くと水場がある",
            "sign_author_name": "アリス",
            "sign_written_tick": 3,
        })
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.SHOW_PLAYER_TEXT,
            parameters={},
        )
        result = svc.apply_effects(
            interior=_interior_with(sign),
            acting_object=sign,
            effects=[effect],
            world_flags=frozenset(),
        )
        assert result.messages == ("『北へ行くと水場がある』 — アリス",)

    def test_未記入なら何も書かれていないと表示される(self) -> None:
        svc = WorldGraphEffectService()
        sign = _sign()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.SHOW_PLAYER_TEXT,
            parameters={},
        )
        result = svc.apply_effects(
            interior=_interior_with(sign),
            acting_object=sign,
            effects=[effect],
            world_flags=frozenset(),
        )
        assert result.messages == ("何も書かれていない。",)

    def test_読む行為はstateを変更せず第三者観測effectを積まない(self) -> None:
        svc = WorldGraphEffectService()
        sign = _sign({"sign_text": "メモ", "sign_author_name": "アリス"})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.SHOW_PLAYER_TEXT,
            parameters={},
        )
        result = svc.apply_effects(
            interior=_interior_with(sign),
            acting_object=sign,
            effects=[effect],
            world_flags=frozenset(),
        )
        assert result.new_interior.objects[0].state == {
            "sign_text": "メモ",
            "sign_author_name": "アリス",
        }
        assert result.public_observable_effects == ()
        assert result.hidden_effects == ()


class TestSpotInteractionServicePropagatesSignParams:
    """SpotInteractionService.execute_interaction 経由でも interaction_parameters /
    acting_player_display_name が effect_service まで伝搬することを保証する。"""

    def test_write_action_経由でtextと書き手名がstateに書き込まれる(self) -> None:
        from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
            SpotInteractionService,
        )
        from ai_rpg_world.domain.world_graph.value_object.interaction_def import (
            InteractionDef,
        )

        sign = SpotObject(
            object_id=SpotObjectId.create(9),
            name="古い看板",
            description="d",
            object_type=SpotObjectTypeEnum.SIGN,
            state={},
            interactions=(
                InteractionDef(
                    action_name="write",
                    display_label="書き込む",
                    preconditions=(),
                    effects=(
                        InteractionEffect(
                            effect_type=InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
                            parameters={},
                        ),
                    ),
                ),
            ),
        )
        interior = _interior_with(sign)
        svc = SpotInteractionService()
        result = svc.execute_interaction(
            interior,
            SpotObjectId.create(9),
            "write",
            frozenset(),
            frozenset(),
            interaction_parameters={"text": "気をつけろ"},
            current_tick=WorldTick(7),
            acting_player_display_name="トマ",
        )
        new_state = result.new_interior.objects[0].state
        assert new_state["sign_text"] == "気をつけろ"
        assert new_state["sign_author_name"] == "トマ"
        assert new_state["sign_written_tick"] == 7
