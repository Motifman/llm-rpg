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
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


def _sign(
    initial_state: dict | None = None,
    *,
    hidden_state_keys: frozenset[str] = frozenset(),
) -> SpotObject:
    return SpotObject(
        object_id=SpotObjectId.create(9),
        name="古い看板",
        description="誰かが書き込めそうな看板。",
        object_type=SpotObjectTypeEnum.SIGN,
        state=dict(initial_state or {}),
        interactions=(),
        hidden_state_keys=hidden_state_keys,
    )


def _interior_with(obj: SpotObject) -> SpotInterior:
    return SpotInterior((), (obj,), (), ())


class TestWritePlayerTextEffect:
    """WRITE_PLAYER_TEXT: interaction_parameters["text"] を state へ保存する。"""

    def test_writing_sign_saves_text_author_and_tick_to_state(self) -> None:
        """書き込むと 本文 書き手名 tick が state に保存される。"""
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

    def test_two_one_removed(self) -> None:
        """2人目が書くと 1人目の内容が上書きされて消える。"""
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

    @pytest.mark.parametrize(
        "parameters",
        [{}, {"text": ""}, {"text": 12345}],
        ids=["missing", "empty", "numeric"],
    )
    @pytest.mark.parametrize(
        "initial_state",
        [{}, {"sign_text": "前の本文", "sign_author_name": "前の作者", "sign_written_tick": 9, "public_label": "木製"}],
        ids=["empty-state", "existing-state"],
    )
    def test_text_missing_interaction_not_allowed_exception_state(
        self,
        parameters: dict,
        initial_state: dict,
    ) -> None:
        """欠落・空文字・数値の本文を拒否し、元の看板の全状態を保持する。

        空看板の元3入力に、以前の内容がある行を加える。確認するのは
        元オブジェクトの非破壊性で、外部保存の原子性ではない。
        """
        svc = WorldGraphEffectService()
        sign = _sign(initial_state)
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
                interaction_parameters=parameters,
                acting_player_display_name="アリス",
            )
        assert "text" in str(exc_info.value)
        assert sign.state == initial_state

    @pytest.mark.parametrize(
        ("long_text", "expected_text"),
        [("あ" * 250, "あ" * 200), ("先" * 199 + "中" + "尾" * 50, "先" * 199 + "中")],
        ids=["original-repeated-text", "distinct-tail"],
    )
    def test_exceeds(self, long_text: str, expected_text: str) -> None:
        """200字を超えた本文は先頭200字を保存し、切り詰めたことを伝える。"""
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
            interaction_parameters={"text": long_text},
            acting_player_display_name="アリス",
        )
        new_state = result.new_interior.objects[0].state
        assert len(new_state["sign_text"]) == 200
        assert new_state["sign_text"] == expected_text
        assert any("切り詰め" in m for m in result.messages)

    def test_display_name_unspecified_default_fallback_saved(self) -> None:
        """display name 未指定なら既定のフォールバック名が保存される。"""
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
        assert new_state["sign_author_name"] == "名無し"

    def test_after_3key_hidden_state_keys(self) -> None:
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

    def test_after_visible_state_text_tick_not_included(self) -> None:
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

    @pytest.mark.parametrize(
        ("initial_state", "initial_hidden", "expected_visible"),
        [
            ({}, frozenset(), {}),
            ({"secret": "封印", "public_label": "木製"}, frozenset({"secret"}), {"public_label": "木製"}),
        ],
        ids=["original-empty-state", "existing-private-and-public"],
    )
    def test_after_hidden_state_keys_preserved(
        self,
        initial_state: dict,
        initial_hidden: frozenset[str],
        expected_visible: dict,
    ) -> None:
        """初回と再書込みで元の値・秘匿キーを保持し、無関係な公開値は隠さない。"""
        svc = WorldGraphEffectService()
        sign = _sign(initial_state, hidden_state_keys=initial_hidden)
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
        expected_hidden = initial_hidden | {
            "sign_text",
            "sign_author_name",
            "sign_written_tick",
        }
        assert updated_sign.state == {
            **initial_state,
            "sign_text": "1人目のメモ",
            "sign_author_name": "アリス",
            "sign_written_tick": 1,
        }
        assert updated_sign.hidden_state_keys == expected_hidden
        assert updated_sign.visible_state() == expected_visible
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
        assert updated.state == {
            **initial_state,
            "sign_text": "2人目のメモ",
            "sign_author_name": "ボブ",
            "sign_written_tick": 5,
        }
        assert updated.hidden_state_keys == expected_hidden
        assert updated.visible_state() == expected_visible
        assert "sign_text" not in updated.visible_state()

    @pytest.mark.parametrize(
        "text",
        ["水場はここから北", "メモ"],
        ids=["original-private-content", "absorbed-public-summary"],
    )
    def test_state_delta_text_tick_not_included(self, text: str) -> None:
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
            interaction_parameters={"text": text},
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

    def test_text_message(self) -> None:
        """書かれていれば本文と書き手名がmessageに現れる。"""
        svc = WorldGraphEffectService()
        sign = _sign(
            {
                "sign_text": "北へ行くと水場がある",
                "sign_author_name": "アリス",
                "sign_written_tick": 3,
            }
        )
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

    def test_displayed(self) -> None:
        """未記入なら何も書かれていないと表示される。"""
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

    def test_line_state_observation_effect(self) -> None:
        """読む行為はstateを変更せず第三者観測effectを積まない。"""
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

    def test_write_action_via_text_state(self) -> None:
        """write action 経由でtextと書き手名がstateに書き込まれる。"""
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
