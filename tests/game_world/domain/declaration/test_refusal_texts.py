from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.action.common_rule_refusal import (
    ActorCannotAct,
    Busy,
    CommonRuleRefusalKind,
    NoOneFoundInTheDark,
    NotAllowedInThisStage,
    NotTogether,
    OutOfReach,
    TooTired,
)
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.declaration.refusal_texts import RefusalTexts
from ai_rpg_world.game_world.domain.exception.action_exception import (
    BlankRefusalCodeException,
    MissingCommonRuleRefusalTextException,
    UnknownPersonInRefusalTextException,
)
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import SectionFullException
from ai_rpg_world.game_world.domain.people import TextAboutPeople, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import PersonId

ALICE = PersonId("alice")
HIDDEN = TextWithUnassignedPeople("今はできない。")


def _common_rules(**overrides: str) -> dict[CommonRuleRefusalKind, TextWithUnassignedPeople]:
    texts = {kind: TextWithUnassignedPeople(f"{kind.name} のためできない。") for kind in CommonRuleRefusalKind}
    for name, text in overrides.items():
        texts[CommonRuleRefusalKind[name]] = TextWithUnassignedPeople(text)
    return texts


class TestCommonRuleKinds:
    """共通の決まりの断りの型が、断りの文の表を引く種類を自分で答えることを保証する。"""

    @pytest.mark.parametrize(
        ("refusal", "kind"),
        [
            (ActorCannotAct(), CommonRuleRefusalKind.ACTOR_CANNOT_ACT),
            (Busy(), CommonRuleRefusalKind.BUSY),
            (NotTogether(), CommonRuleRefusalKind.NOT_TOGETHER),
            (OutOfReach(), CommonRuleRefusalKind.OUT_OF_REACH),
            (TooTired(), CommonRuleRefusalKind.TOO_TIRED),
            (NotAllowedInThisStage(), CommonRuleRefusalKind.NOT_ALLOWED_IN_THIS_STAGE),
            (NoOneFoundInTheDark(), CommonRuleRefusalKind.NO_ONE_FOUND_IN_THE_DARK),
        ],
        ids=lambda value: type(value).__name__,
    )
    def test_each_refusal_answers_its_kind(self, refusal: object, kind: CommonRuleRefusalKind) -> None:
        """断りの型ごとに、対応する CommonRuleRefusalKind を kind() で答える。"""
        assert refusal.kind() is kind  # type: ignore[attr-defined]


class TestRefusalTexts:
    """RefusalTexts が、共通の決まりの断りの文を、行った人を当てた TextAboutPeople で返すことを保証する。"""

    def test_text_for_common_rule_assigns_the_actor(self) -> None:
        """{actor} を書いた文は、行った人の PersonId を当てた TextAboutPeople で返る。"""
        texts = RefusalTexts(common_rules=_common_rules(BUSY="{actor}は手が離せない。"), world_state={}, hidden=HIDDEN)

        assert texts.common_rule_text(Busy(), ALICE) == TextAboutPeople(
            TextWithUnassignedPeople("{actor}は手が離せない。"), {"actor": ALICE}
        )

    def test_text_without_placeholder_assigns_no_one(self) -> None:
        """人を書いていない文は、誰も当てずにそのまま返る。"""
        texts = RefusalTexts(
            common_rules=_common_rules(TOO_TIRED="疲れすぎて動けない。"), world_state={}, hidden=HIDDEN
        )

        assert texts.common_rule_text(TooTired(), ALICE) == TextAboutPeople(
            TextWithUnassignedPeople("疲れすぎて動けない。"), {}
        )

    def test_missing_common_rule_text_raises(self) -> None:
        """共通の決まりの種類のうち 1 つでも文が無いと、作るときに MissingCommonRuleRefusalTextException を投げる。"""
        common_rules = _common_rules()
        del common_rules[CommonRuleRefusalKind.OUT_OF_REACH]

        with pytest.raises(MissingCommonRuleRefusalTextException):
            RefusalTexts(common_rules=common_rules, world_state={}, hidden=HIDDEN)

    @pytest.mark.parametrize("where", ["common_rules", "world_state", "hidden"])
    def test_person_other_than_actor_raises(self, where: str) -> None:
        """どの文にも {actor} 以外の人 ({target} など) を書くと、作るときに UnknownPersonInRefusalTextException を投げる。"""
        bad = TextWithUnassignedPeople("{target}が遠い。")
        common_rules = _common_rules()
        world_state = {RefusalCode("GAME_WORLD.WHEREABOUTS.SECTION_FULL"): TextWithUnassignedPeople("満員だ。")}
        hidden = HIDDEN
        if where == "common_rules":
            common_rules[CommonRuleRefusalKind.NOT_TOGETHER] = bad
        elif where == "world_state":
            world_state[RefusalCode("GAME_WORLD.WHEREABOUTS.SECTION_FULL")] = bad
        else:
            hidden = bad

        with pytest.raises(UnknownPersonInRefusalTextException):
            RefusalTexts(common_rules=common_rules, world_state=world_state, hidden=hidden)


class TestRefusalCode:
    """RefusalCode が、集約の投げたドメイン例外の error_code を包むことを保証する。"""

    def test_of_exception_wraps_its_error_code(self) -> None:
        """ドメイン例外から作ると、その例外の error_code を持つ。"""
        assert RefusalCode.of(SectionFullException("cage is full")) == RefusalCode(SectionFullException.error_code)

    @pytest.mark.parametrize("value", ["", "  "])
    def test_blank_code_raises(self, value: str) -> None:
        """空や空白だけの文字列から作ると BlankRefusalCodeException を投げる。"""
        with pytest.raises(BlankRefusalCodeException):
            RefusalCode(value)
