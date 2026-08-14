from __future__ import annotations

from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.service.effect_application.context import (
    EffectApplicationState,
)
from ai_rpg_world.domain.world_graph.service.effect_application.object_target import (
    resolve_target_object,
)
from ai_rpg_world.domain.world_graph.service.effect_application.registry import (
    EffectHandlerFn,
)
from ai_rpg_world.domain.world_graph.service.effect_application.visibility import (
    resolve_visibility,
    state_delta_entries,
)
from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
    AppliedEffectKind,
    AppliedEffectSummary,
)
from ai_rpg_world.domain.world_graph.value_object.cross_domain_effect_spec import (
    RoomOccupancyDisplaySpec,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)

# PR-F (#710 後続): 看板 (WRITE_PLAYER_TEXT / SHOW_PLAYER_TEXT) が使う
# object.state key と文字数上限。「静かな失敗」を避けるため、上限超過は
# 切り詰め + messages への可視化とセットで扱う (定数化して仕様として明示する)。
SIGN_TEXT_MAX_LENGTH = 200
SIGN_TEXT_STATE_KEY = "sign_text"
SIGN_AUTHOR_STATE_KEY = "sign_author_name"
SIGN_WRITTEN_TICK_STATE_KEY = "sign_written_tick"

# PR-J (#714 後続): 「書き込みは公開、内容は examine (SHOW_PLAYER_TEXT) した
# 本人だけが読める」という看板の設計を、visible_state() / state_delta の
# 両方で実際に守るための hidden key 集合。WRITE_PLAYER_TEXT がこの 3 key を
# 書いた時点で自分で hidden_state_keys へ加える (シナリオ JSON の設定漏れに
# 依存しない)。
SIGN_HIDDEN_STATE_KEYS = frozenset(
    {SIGN_TEXT_STATE_KEY, SIGN_AUTHOR_STATE_KEY, SIGN_WRITTEN_TICK_STATE_KEY}
)


def apply_show_message(effect: InteractionEffect, ctx: EffectApplicationState) -> None:
    msg = effect.parameters.get("message")
    if isinstance(msg, str):
        ctx.messages.append(msg)


def apply_show_room_occupancy(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    ctx.room_occupancy_display_specs.append(RoomOccupancyDisplaySpec())


def apply_write_player_text(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    p = effect.parameters
    visibility = resolve_visibility(effect)
    text_param_key = p.get("text_param_key", "text")
    params_in = ctx.interaction_parameters or {}
    raw_text = params_in.get(text_param_key)
    if not isinstance(raw_text, str) or raw_text == "":
        raise InteractionNotAllowedException(
            f"何を書くか {text_param_key} パラメータで指定してください。"
        )
    target = resolve_target_object(ctx.interior, ctx.acting_object, p)
    if target is None:
        return
    text = raw_text
    truncated = len(text) > SIGN_TEXT_MAX_LENGTH
    if truncated:
        text = text[:SIGN_TEXT_MAX_LENGTH]
    author_name = ctx.acting_player_display_name or "名無し"
    before_state = dict(target.state)
    new_state = dict(target.state)
    new_state[SIGN_TEXT_STATE_KEY] = text
    new_state[SIGN_AUTHOR_STATE_KEY] = author_name
    new_state[SIGN_WRITTEN_TICK_STATE_KEY] = (
        int(ctx.current_tick.value) if ctx.current_tick is not None else None
    )
    updated_target = target.with_state(new_state).with_additional_hidden_state_keys(
        SIGN_HIDDEN_STATE_KEYS
    )
    ctx.replace_object(updated_target)
    if truncated:
        ctx.messages.append(
            f"本文が{SIGN_TEXT_MAX_LENGTH}字を超えていたため切り詰めました。"
        )
    ctx.messages.append(f"{updated_target.name} に書き込んだ。")
    ctx.summaries.append(
        AppliedEffectSummary(
            kind=AppliedEffectKind.SPOT_OBJECT_STATE_CHANGE,
            visibility=visibility,
            description=f"{updated_target.name} に {author_name} が書き込んだ",
            target_ref=updated_target.name,
            state_delta=state_delta_entries(
                before_state, new_state, exclude_keys=SIGN_HIDDEN_STATE_KEYS
            ),
        )
    )


def apply_show_player_text(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    p = effect.parameters
    target = resolve_target_object(ctx.interior, ctx.acting_object, p)
    if target is None:
        return
    text = target.state.get(SIGN_TEXT_STATE_KEY)
    if not isinstance(text, str) or text == "":
        ctx.messages.append(p.get("empty_message", "何も書かれていない。"))
        return
    author_name = target.state.get(SIGN_AUTHOR_STATE_KEY) or "名無し"
    ctx.messages.append(f"『{text}』 — {author_name}")


def build_message_handlers() -> dict[InteractionEffectTypeEnum, EffectHandlerFn]:
    return {
        InteractionEffectTypeEnum.SHOW_MESSAGE: apply_show_message,
        InteractionEffectTypeEnum.SHOW_ROOM_OCCUPANCY: apply_show_room_occupancy,
        InteractionEffectTypeEnum.WRITE_PLAYER_TEXT: apply_write_player_text,
        InteractionEffectTypeEnum.SHOW_PLAYER_TEXT: apply_show_player_text,
    }
