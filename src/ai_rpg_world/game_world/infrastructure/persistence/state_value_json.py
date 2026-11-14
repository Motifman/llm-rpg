from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ChoiceName,
    ChoiceValue,
    CountValue,
    FlagValue,
    NothingWritten,
    StateValue,
    StockValue,
    TextBody,
    WrittenText,
)
from ai_rpg_world.game_world.domain.value_object import Count, StateKeyId
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    JsonUnion,
    JsonUnionMember,
    exact_fields,
    json_bool,
    json_int,
    json_str,
    person_id_from_json,
    world_tick_from_json,
)


def _flag_from_json(raw: object) -> FlagValue:
    return FlagValue(json_bool(exact_fields(raw, ("raised",))["raised"]))


def _count_from_json(raw: object) -> CountValue:
    return CountValue(count_from_json(exact_fields(raw, ("count",))["count"]))


def _choice_from_json(raw: object) -> ChoiceValue:
    return ChoiceValue(ChoiceName(json_str(exact_fields(raw, ("choice",))["choice"])))


def _stock_from_json(raw: object) -> StockValue:
    return StockValue(count_from_json(exact_fields(raw, ("amount",))["amount"]))


def _written_from_json(raw: object) -> WrittenText:
    fields = exact_fields(raw, ("body", "author", "written_at"))
    return WrittenText(
        body=TextBody(json_str(fields["body"])),
        author=person_id_from_json(fields["author"]),
        written_at=world_tick_from_json(fields["written_at"]),
    )


STATE_VALUE: JsonUnion[StateValue] = JsonUnion(
    JsonUnionMember("flag_value", FlagValue, lambda value: {"raised": value.raised}, _flag_from_json),
    JsonUnionMember("count_value", CountValue, lambda value: {"count": value.count.value}, _count_from_json),
    JsonUnionMember("choice_value", ChoiceValue, lambda value: {"choice": value.choice.value}, _choice_from_json),
    JsonUnionMember("stock_value", StockValue, lambda value: {"amount": value.amount.value}, _stock_from_json),
    JsonUnionMember(
        "written_text",
        WrittenText,
        lambda value: {"body": value.body.value, "author": value.author.value, "written_at": value.written_at.value},
        _written_from_json,
    ),
    JsonUnionMember.fieldless("nothing_written", NothingWritten()),
)


def count_from_json(raw: object) -> Count:
    return Count(json_int(raw))


def state_key_from_json(raw: object) -> StateKeyId:
    return StateKeyId(json_str(raw))
