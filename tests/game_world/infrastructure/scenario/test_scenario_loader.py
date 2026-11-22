from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ai_rpg_world.game_world.domain.action.common_rule_refusal import CommonRuleRefusalKind
from ai_rpg_world.game_world.domain.action.speech import OrdinaryVoice
from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.flag_conditions import FlagIsRaisedCondition
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.person_conditions import IsAtSpotCondition
from ai_rpg_world.game_world.domain.declaration.time_and_weather import DayPhaseName, NoDayNight, NoWeather
from ai_rpg_world.game_world.domain.declaration.time_and_weather.everyone_awake import EveryoneAwake
from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_type import WeatherType
from ai_rpg_world.game_world.domain.declaration.verb import NoticedOnWaking, ObjectLook
from ai_rpg_world.game_world.domain.declaration.verb.item_name_joiner import ItemNameJoiner
from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw, DesignLocation, ScenarioFile
from ai_rpg_world.game_world.domain.exception.world_design_exception import WorldDesignFlawsException
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople, Unidentified
from ai_rpg_world.game_world.domain.perception import NoTarget
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    DescriptionText,
    DisplayName,
    HitPoints,
    InteractionId,
    ObjectId,
    PassageId,
    PersonId,
    SpotSectionId,
)
from ai_rpg_world.game_world.infrastructure.scenario.character_briefing import CharacterBriefing
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import LoadedScenario, load_scenario

_COMMON = Path(__file__).parent / "data" / "common_for_tests.yaml"

_LIFT_LANDING = """
includes: [common.yaml]
introduction:
  title: 昇降機の乗り場
  text: 坑道の奥で目を覚ました。
  premises: 昇降機は一度しか動かない。
flags:
  generator_running: { meaning: 発電機が動いている, initially_raised: true }
  lift_departed: { meaning: 籠が上がった }
spots:
  lift_landing:
    name: 昇降機の乗り場
    description: 坑道の最も深い所にある昇降機の乗り場。
    atmosphere: { lighting: dark, temperature: cold, ambient_sound: 縦穴を吹き上がる風の音 }
    sections:
      cage:
        name: 昇降機の籠
        capacity: 3
        reachable_objects: [lift_panel]
        access:
          enter_label: 籠に乗り込む
          leave_label: 籠から降りる
          enter_text: 鉄の籠に乗り込んだ。
          leave_text: 籠から降りた。
          entry_condition:
            not: { flag_is_raised: lift_departed }
            failure_text: 籠はもう上がってしまった。
          perceived_as:
            witness: { clear: "{actor}が昇降機の籠に乗り込んだ。" }
    objects:
      lift_panel:
        name: 籠の操作盤
        description: 籠の奥の壁にある操作盤。
        interactions:
          start_lift:
            display_label: 鍵を差して昇降機を動かす
            precondition:
              all_of:
                - not: { flag_is_raised: lift_departed }
                  failure_text: 籠はもう上がってしまった。
                - has_item: { who: actor, item_spec: lift_key, count: 1 }
                  failure_text: 鍵穴に合う鍵を持っていない。
                - flag_is_raised: generator_running
              failure_text: 昇降機は動かない。
            effect:
              raise_flag: lift_departed
            success_text: 籠が大きく揺れ、ゆっくりと縦穴を上がりはじめた。
            perceived_as:
              witness: { clear: "{actor}が昇降機の操作盤に鍵を差し、把手を引いた。" }
              sound: { loudness: very_loud, clear: 鉄の籠が軋みながら上がっていく音がした。, muffled: 遠くで重い鉄の軋む音がした。 }
  shaft_head:
    name: 縦穴の上
    description: 縦穴の上の小屋。
    atmosphere: { lighting: bright }
passages:
  ladder: { name: 古い梯子, description: 縦穴の壁に打ち付けた木の梯子。, ends: [lift_landing, shaft_head], travel_ticks: 3 }
item_specs:
  lift_key: { name: 昇降機の鍵, description: 小さな真鍮の鍵。 }
characters:
  haru:
    appearance: 測量具を背負った年かさの男
    spawn_spot: lift_landing
    initial_items: [lift_key]
    known_facts: 昇降機の鍵は自分が持っている。
    objective: ミオと二人で昇降機に乗る。
    being:
      name: ハル
      first_person: 私
      speech: 落ち着いた常体
      traits: [慎重, 確かめてから動く]
  mio:
    appearance: 小柄な若い女
    spawn_spot: lift_landing
    max_hp: 60
    pack_capacity: 8
    known_facts: 籠には三人しか乗れない。
    objective: ハルと二人で昇降機に乗る。
    being:
      name: ミオ
outcomes:
  rescued: { name: 救出, announcement: "{each_person}は昇降機で外へ出た。" }
  stranded: { name: 取り残された, announcement: "{each_person}は坑道に取り残された。" }
happenings:
  lift_leaves:
    condition: { flag_is_raised: lift_departed }
    once: true
    effect:
      sequence:
        - for_everyone:
            people: { where: { is_in_section: { who: each_person, section: cage } } }
            effect: { set_outcome: { who: each_person, outcome: rescued } }
        - for_everyone:
            people: { where: { not: { is_in_section: { who: each_person, section: cage } } } }
            effect: { set_outcome: { who: each_person, outcome: stranded } }
ending:
  ends_when: all_outcomes_decided
time:
  day_night: null
  weather: null
"""


def _mine(declaration: str, name: str, field: str) -> DesignLocation:
    return DesignLocation(declaration, name, field).in_file(ScenarioFile("mine.yaml"))


def _scenario(tmp_path: Path, text: str) -> Path:
    shutil.copy(_COMMON, tmp_path / "common.yaml")
    path = tmp_path / "mine.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _load(tmp_path: Path, text: str = _LIFT_LANDING) -> LoadedScenario:
    return load_scenario(_scenario(tmp_path, text))


def _flaws(tmp_path: Path, text: str) -> tuple[DesignFlaw, ...]:
    with pytest.raises(WorldDesignFlawsException) as raised:
        _load(tmp_path, text)
    return raised.value.flaws


class TestLoadingTheLiftLanding:
    """load_scenario が、scenario_format.md の昇降機の乗り場を名詞と動詞に分けて WorldDesign にまとめることを保証する。"""

    def test_interaction_written_inside_object_reaches_compose(self, tmp_path: Path) -> None:
        """操作盤の中に書いた操作 start_lift は、操作盤の ObjectInteractionDeclaration として設計図から引ける。"""
        design = _load(tmp_path).design

        interaction = design.interaction_on_object(ObjectId("lift_panel"), InteractionId("start_lift"))

        assert interaction.display_label == DisplayName("鍵を差して昇降機を動かす")

    def test_section_access_written_inside_section_reaches_compose(self, tmp_path: Path) -> None:
        """籠の中に書いた出入りは、籠の SectionAccessDeclaration として設計図から引ける。"""
        design = _load(tmp_path).design

        assert design.section_access(SpotSectionId("cage")).enter_label == DisplayName("籠に乗り込む")

    def test_unwritten_passage_states_are_filled_from_the_common_defaults(self, tmp_path: Path) -> None:
        """状態を書かなかった梯子は、共通の部品の defaults.passage の open の状態 1 つを持つ。"""
        nouns = _load(tmp_path).design.nouns

        ladder = nouns.passage("ladder", DesignLocation("passage", "ladder", ""))

        assert [state.display_name for state in ladder.states] == [DisplayName("開いている")]
        assert ladder.allows(ladder.initial_state)

    def test_people_start_with_world_default_unless_they_override_it(self, tmp_path: Path) -> None:
        """体力と荷を書かない haru は世界の既定 (100、20)、書いた mio はその値 (60、8) で始まる。"""
        people = {person.person: person for person in _load(tmp_path).design.initial_world().people}

        assert (people[PersonId("haru")].hp, people[PersonId("haru")].pack_capacity) == (
            HitPoints(100, 100),
            Capacity(20),
        )
        assert (people[PersonId("mio")].hp, people[PersonId("mio")].pack_capacity) == (HitPoints(60, 60), Capacity(8))

    def test_unwritten_sound_is_filled_with_default_text_and_warned(self, tmp_path: Path) -> None:
        """籠の出入りに音の文を書かないと、共通の部品の既定の文で埋め、その場所の DesignWarning を残す。"""
        loaded = _load(tmp_path)

        assert _mine("section", "cage", "access.perceived_as.sound") in [
            warning.location for warning in loaded.warnings
        ]


class TestWhatEachPersonBringsIn:
    """load_scenario が、登場人物の人柄・立場・目的と全員に同じ前提を、世界の宣言の外へ新しい形で返すことを保証する (D2222)。"""

    def test_being_is_read_by_persona_fields_with_lists_as_tuples(self, tmp_path: Path) -> None:
        """haru の being: は人柄の欄ごとに beings に返り、traits は書いた順の tuple になる。書かなかった欄は含まれない。"""
        loaded = _load(tmp_path)

        assert dict(loaded.beings[PersonId("haru")]) == {
            "name": "ハル",
            "first_person": "私",
            "speech": "落ち着いた常体",
            "traits": ("慎重", "確かめてから動く"),
        }
        assert dict(loaded.beings[PersonId("mio")]) == {"name": "ミオ"}

    def test_every_persona_field_is_read(self, tmp_path: Path) -> None:
        """mio の being: に人柄の 7 つの欄をすべて書くと、文の欄は文のまま、一覧の欄は tuple で beings に返る。"""
        text = _LIFT_LANDING.replace(
            "      name: ミオ\n",
            "      name: ミオ\n"
            "      first_person: あたし\n"
            "      speech: 気さくな常体\n"
            "      traits: [元気]\n"
            "      values: [仲間]\n"
            "      fears: [暗がり, 狭い所]\n"
            "      background: 調査隊の若い隊員。\n",
            1,
        )

        assert dict(_load(tmp_path, text).beings[PersonId("mio")]) == {
            "name": "ミオ",
            "first_person": "あたし",
            "speech": "気さくな常体",
            "traits": ("元気",),
            "values": ("仲間",),
            "fears": ("暗がり", "狭い所"),
            "background": "調査隊の若い隊員。",
        }

    def test_known_facts_and_objective_are_returned_as_briefing(self, tmp_path: Path) -> None:
        """haru の known_facts と objective は、briefings の CharacterBriefing として返る。"""
        loaded = _load(tmp_path)

        assert loaded.briefings[PersonId("haru")] == CharacterBriefing(
            known_facts=DescriptionText("昇降機の鍵は自分が持っている。"),
            objective=DescriptionText("ミオと二人で昇降機に乗る。"),
        )

    def test_omitted_premises_are_read_as_none(self, tmp_path: Path) -> None:
        """introduction に premises を書かないと、WorldIntroduction.premises は None になり、案内に前提の行は出ない。"""
        text = _LIFT_LANDING.replace("  premises: 昇降機は一度しか動かない。\n", "", 1)

        assert _load(tmp_path, text).design.introduction.premises is None

    def test_title_is_read_into_world_introduction(self, tmp_path: Path) -> None:
        """introduction.title は、WorldIntroduction.title として設計図から引ける。"""
        assert _load(tmp_path).design.introduction.title == DisplayName("昇降機の乗り場")

    def test_premises_are_read_into_world_introduction(self, tmp_path: Path) -> None:
        """introduction.premises は、WorldIntroduction.premises として設計図から引ける。"""
        introduction = _load(tmp_path).design.introduction

        assert introduction.premises == DescriptionText("昇降機は一度しか動かない。")

    def test_world_map_is_hidden_unless_the_introduction_shows_it(self, tmp_path: Path) -> None:
        """introduction に show_world_map を書かないと、設計図は地図の文を返さない。"""
        assert _load(tmp_path).design.world_map_text() is None

    def test_show_world_map_puts_every_place_on_the_map(self, tmp_path: Path) -> None:
        """introduction に show_world_map: true を書くと、設計図は場所ごとの行を地図の文として返す。"""
        text = _LIFT_LANDING.replace(
            "  premises: 昇降機は一度しか動かない。\n",
            "  premises: 昇降機は一度しか動かない。\n  show_world_map: true\n",
            1,
        )

        world_map = _load(tmp_path, text).design.world_map_text()

        assert world_map is not None and world_map.startswith("  昇降機の乗り場 (暗い)")

    def test_show_world_map_that_is_not_true_or_false_is_a_flaw(self, tmp_path: Path) -> None:
        """show_world_map に真偽でない値を書くと、その欄の場所を付けた DesignFlaw になる。"""
        text = _LIFT_LANDING.replace(
            "  premises: 昇降機は一度しか動かない。\n",
            "  premises: 昇降機は一度しか動かない。\n  show_world_map: yes please\n",
            1,
        )

        assert _mine("world", "world", "introduction.show_world_map") in [
            flaw.location for flaw in _flaws(tmp_path, text)
        ]

    @pytest.mark.parametrize(
        ("old", "new", "location"),
        [
            (
                "      speech: 落ち着いた常体\n",
                "      persona: 慎重な隊長。\n",
                _mine("character", "haru", "being.persona"),
            ),
            (
                "      speech: 落ち着いた常体\n",
                "      objective: 外へ出る。\n",
                _mine("character", "haru", "being.objective"),
            ),
            (
                "  premises: 昇降機は一度しか動かない。\n",
                "  objective: 外へ出る。\n",
                _mine("world", "world", "introduction.objective"),
            ),
        ],
    )
    def test_old_shape_is_a_flaw(self, tmp_path: Path, old: str, new: str, location: DesignLocation) -> None:
        """古い形の being.persona・being.objective・introduction.objective を書くと、その欄の場所を付けた DesignFlaw になる。"""
        assert location in [flaw.location for flaw in _flaws(tmp_path, _LIFT_LANDING.replace(old, new, 1))]

    @pytest.mark.parametrize(
        ("removed", "location"),
        [
            ("    known_facts: 籠には三人しか乗れない。\n", _mine("character", "mio", "known_facts")),
            ("    objective: ハルと二人で昇降機に乗る。\n", _mine("character", "mio", "objective")),
            ("    being:\n      name: ミオ\n", _mine("character", "mio", "being")),
        ],
    )
    def test_unwritten_briefing_or_being_is_a_flaw(
        self, tmp_path: Path, removed: str, location: DesignLocation
    ) -> None:
        """mio の known_facts・objective・being: のどれかを書かないと、その欄の場所を付けた DesignFlaw になる。"""
        assert location in [flaw.location for flaw in _flaws(tmp_path, _LIFT_LANDING.replace(removed, "", 1))]

    @pytest.mark.parametrize(
        ("old", "new", "location"),
        [
            ("      name: ミオ\n", "      first_person: あたし\n", _mine("character", "mio", "being.name")),
            ("      name: ミオ\n", '      name: "  "\n', _mine("character", "mio", "being.name")),
            (
                "      traits: [慎重, 確かめてから動く]\n",
                "      traits: 慎重\n",
                _mine("character", "haru", "being.traits"),
            ),
            (
                "      traits: [慎重, 確かめてから動く]\n",
                '      traits: [慎重, " "]\n',
                _mine("character", "haru", "being.traits[1]"),
            ),
            ("      first_person: 私\n", '      first_person: " "\n', _mine("character", "haru", "being.first_person")),
            ("    being:\n      name: ミオ\n", "    being: ミオ\n", _mine("character", "mio", "being")),
        ],
    )
    def test_being_that_cannot_become_persona_is_a_flaw(
        self, tmp_path: Path, old: str, new: str, location: DesignLocation
    ) -> None:
        """name の無い being:、空白だけの name・first_person・traits の項目、一覧でない traits、地図でない being: は、その欄の場所を付けた DesignFlaw になる。"""
        assert location in [flaw.location for flaw in _flaws(tmp_path, _LIFT_LANDING.replace(old, new, 1))]


class TestIncludes:
    """シナリオが includes: の共通の部品を行ごとに書き換えられることを保証する。"""

    def test_one_refusal_text_is_rewritten_and_the_rest_kept(self, tmp_path: Path) -> None:
        """断りの文の busy だけをシナリオで書き換えると、busy は書き換えた文、too_tired は共通の部品の文になる。"""
        text = _LIFT_LANDING + "refusal_texts:\n  common_rules:\n    busy: 今はそれどころではない。\n"

        texts = _load(tmp_path, text).design.refusal_texts.common_rules

        assert texts[CommonRuleRefusalKind.BUSY] == TextWithUnassignedPeople("今はそれどころではない。")
        assert texts[CommonRuleRefusalKind.TOO_TIRED] == TextWithUnassignedPeople("疲れて動けない。")


class TestSpeechAndArrivalPerceptions:
    """built_in_action_perceptions の whisper・speak・shout・arrival が、声の大きさごとの欄と着いた側の欄に読まれることを保証する。"""

    def test_speak_is_read_as_ordinary_voice(self, tmp_path: Path) -> None:
        """シナリオで speak の見た人の文を書き換えると、その文が OrdinaryVoice の知覚になる。"""
        text = (
            _LIFT_LANDING + 'built_in_action_perceptions:\n  speak:\n    witness: { clear: "{actor}が口を開いた。" }\n'
        )

        perceptions = _load(tmp_path, text).design.built_in_action_perceptions

        assert perceptions.speech(OrdinaryVoice()).witness.clear == TextWithUnassignedPeople("{actor}が口を開いた。")

    def test_missing_shout_without_include_is_a_flaw(self, tmp_path: Path) -> None:
        """取り込んだ共通の部品にもシナリオにも shout が無いと、その欄の場所を付けた DesignFlaw になる。"""
        path = _scenario(tmp_path, _LIFT_LANDING)
        common = tmp_path / "common.yaml"
        common.write_text(common.read_text(encoding="utf-8").replace("  shout: *quiet\n", ""), encoding="utf-8")

        with pytest.raises(WorldDesignFlawsException) as raised:
            load_scenario(path)

        assert [flaw.location for flaw in raised.value.flaws] == [
            DesignLocation("world", "world", "built_in_action_perceptions.shout").in_file(ScenarioFile("common.yaml"))
        ]

    def test_arrival_naming_origin_and_whisper_naming_target_load(self, tmp_path: Path) -> None:
        """arrival の文に {origin}、whisper の文に {target} を書いても、DesignFlaw を出さずに読み込める。"""
        text = _LIFT_LANDING + (
            "built_in_action_perceptions:\n"
            '  arrival:\n    witness: { clear: "{actor}が{origin}から来た。" }\n'
            '  whisper:\n    witness: { clear: "{actor}が{target}に耳打ちした。" }\n'
        )

        perceptions = _load(tmp_path, text).design.built_in_action_perceptions

        assert perceptions.arrival.witness.clear == TextWithUnassignedPeople("{actor}が{origin}から来た。")
        assert perceptions.whisper.witness.clear == TextWithUnassignedPeople("{actor}が{target}に耳打ちした。")

    def test_speak_naming_target_is_a_flaw(self, tmp_path: Path) -> None:
        """speak の文に、ふつうの声では埋まらない {target} を書くと、組み込みの行為の知覚の表の DesignFlaw になる。"""
        text = (
            _LIFT_LANDING
            + 'built_in_action_perceptions:\n  speak:\n    witness: { clear: "{actor}が{target}に話した。" }\n'
        )

        flaws = _flaws(tmp_path, text)

        assert [flaw.location.field for flaw in flaws] == ["built_in_action_perceptions"]
        assert "speak" in flaws[0].reason

    def test_arrival_with_announcement_is_a_flaw_naming_arrival(self, tmp_path: Path) -> None:
        """arrival の行に世界の知らせ (announcement) を書くと、組み込みの行為の知覚の表の DesignFlaw になり、理由に arrival が出る。"""
        text = _LIFT_LANDING + (
            "built_in_action_perceptions:\n"
            "  arrival:\n"
            '    witness: { clear: "{actor}が来た。" }\n'
            "    announcement: { audience: { where: { all_of: [] } }, text: 誰かが来た。, salience: notable }\n"
        )

        flaws = _flaws(tmp_path, text)

        assert [flaw.location.field for flaw in flaws] == ["built_in_action_perceptions"]
        assert "arrival" in flaws[0].reason

    def test_item_joiner_is_read_from_the_common_part(self, tmp_path: Path) -> None:
        """取り込んだ共通の部品の item_joiner が、品物の呼び名をつなぐ言葉になる。"""
        perceptions = _load(tmp_path).design.built_in_action_perceptions

        assert perceptions.item_joiner == ItemNameJoiner("と")

    def test_missing_item_joiner_is_a_flaw(self, tmp_path: Path) -> None:
        """共通の部品にもシナリオにも item_joiner が無いと、その欄の場所を付けた DesignFlaw になる。"""
        path = _scenario(tmp_path, _LIFT_LANDING)
        common = tmp_path / "common.yaml"
        common.write_text(common.read_text(encoding="utf-8").replace("  item_joiner: と\n", ""), encoding="utf-8")

        with pytest.raises(WorldDesignFlawsException) as raised:
            load_scenario(path)

        assert [flaw.location for flaw in raised.value.flaws] == [
            DesignLocation("world", "world", "built_in_action_perceptions.item_joiner").in_file(
                ScenarioFile("common.yaml")
            )
        ]


class TestSurroundingsTexts:
    """場面と知らせの文 (surroundings_texts) が、共通の部品から読まれ、書き換えと欠けと穴の誤りが読み込みで扱われることを保証する。"""

    def test_scenario_overrides_one_text_of_the_common_part(self, tmp_path: Path) -> None:
        """シナリオが waking だけを書くと、その文に置き換わり、ほかの文は共通の部品のまま残る。"""
        text = _LIFT_LANDING + "surroundings_texts:\n  waking: はっと目を開けた。\n"

        texts = _load(tmp_path, text).design.surroundings_texts

        assert (texts.waking.template, texts.darkening.template) == ("はっと目を開けた。", "辺りが暗くなった。")

    def test_scenario_joiner_joins_the_listed_people(self, tmp_path: Path) -> None:
        """シナリオが joiner に「と」を書くと、場面に並ぶ人の穴が「と」でつながる。"""
        text = _LIFT_LANDING + "surroundings_texts:\n  joiner: と\n"

        texts = _load(tmp_path, text).design.surroundings_texts
        listed = texts.scene_as_seen(people=(Unidentified(), Unidentified()), bodies=()).template

        assert listed == "ここには{person_1}と{person_2}がいる。"

    def test_missing_text_is_a_flaw_naming_the_field(self, tmp_path: Path) -> None:
        """共通の部品にもシナリオにも darkening が無いと、surroundings_texts.darkening の場所を付けた DesignFlaw になる。"""
        path = _scenario(tmp_path, _LIFT_LANDING)
        common = tmp_path / "common.yaml"
        common.write_text(
            common.read_text(encoding="utf-8").replace("  darkening: 辺りが暗くなった。\n", ""), encoding="utf-8"
        )

        with pytest.raises(WorldDesignFlawsException) as raised:
            load_scenario(path)

        assert [flaw.location for flaw in raised.value.flaws] == [
            DesignLocation("world", "world", "surroundings_texts.darkening").in_file(ScenarioFile("common.yaml"))
        ]

    def test_wrong_hole_is_a_flaw(self, tmp_path: Path) -> None:
        """people_here に {people} ではなく {actor} を書くと、surroundings_texts の DesignFlaw になり、理由に people_here が出る。"""
        text = _LIFT_LANDING + 'surroundings_texts:\n  people_here: "{actor}がいる。"\n'

        flaws = _flaws(tmp_path, text)

        assert [flaw.location.field for flaw in flaws] == ["surroundings_texts"]
        assert "people_here" in flaws[0].reason


class TestBriefingHeadings:
    """入るときの案内の見出し (briefing_headings) が、共通の部品から読まれ、欠けと誤りが読み込みで DesignFlaw になることを保証する。"""

    def test_scenario_overrides_one_heading_of_the_common_part(self, tmp_path: Path) -> None:
        """シナリオが premises だけを書くと、その見出しに置き換わり、ほかの見出しは共通の部品のまま残る。"""
        text = _LIFT_LANDING + "briefing_headings:\n  premises: この村の決まり\n"

        headings = _load(tmp_path, text).design.briefing_headings

        assert (headings.premises, headings.title, headings.world_map) == (
            "この村の決まり",
            "- 舞台のタイトル: {title}",
            "【この場所の造り】",
        )

    def test_missing_line_is_a_flaw_naming_the_field(self, tmp_path: Path) -> None:
        """共通の部品にもシナリオにも world_map が無いと、briefing_headings.world_map の場所を付けた DesignFlaw になる。"""
        path = _scenario(tmp_path, _LIFT_LANDING)
        common = tmp_path / "common.yaml"
        common.write_text(
            common.read_text(encoding="utf-8").replace("  world_map: 【この場所の造り】\n", ""), encoding="utf-8"
        )

        with pytest.raises(WorldDesignFlawsException) as raised:
            load_scenario(path)

        assert [flaw.location for flaw in raised.value.flaws] == [
            DesignLocation("world", "world", "briefing_headings.world_map").in_file(ScenarioFile("common.yaml"))
        ]

    @pytest.mark.parametrize(
        "line",
        ['  title: "- 題名"\n', '  premises: "【前提】"\n', "  sequel: 続き\n"],
        ids=["title_without_value", "brackets", "unknown_key"],
    )
    def test_malformed_headings_are_a_flaw(self, tmp_path: Path, line: str) -> None:
        """題名を書かない題名の行・【】を含む見出し・知らない鍵は、briefing_headings の場所の DesignFlaw になる。"""
        flaws = _flaws(tmp_path, _LIFT_LANDING + "briefing_headings:\n" + line)

        assert [flaw.location.field.split(".")[0] for flaw in flaws] == ["briefing_headings"]


class TestBuiltInTargetTexts:
    """built_in_action_perceptions の相手が見る文 (target) を、相手のいる行為にだけ書けることを保証する。"""

    def test_tend_text_noticed_on_waking_is_read_into_the_declaration(self, tmp_path: Path) -> None:
        """介抱の行の target に noticed_later を書くと、倒れていた相手が目が覚めてから気づく文として宣言に入る。"""
        text = _LIFT_LANDING + (
            "rules:\n  tend: { revive_hp_rate: 0.6 }\n"
            "built_in_action_perceptions:\n"
            '  tend:\n    witness: { clear: "{actor}が{target}を介抱している。" }\n'
            '    target: { noticed_later: "{actor}が介抱してくれたようだ。" }\n'
        )

        tend = _load(tmp_path, text).design.built_in_action_perceptions.by_kind[ActionKind.TEND]

        assert tend.target == NoticedOnWaking(TextWithUnassignedPeople("{actor}が介抱してくれたようだ。"))

    def test_tend_target_with_clear_is_a_flaw_at_that_field(self, tmp_path: Path) -> None:
        """介抱の行の target に、倒れている相手には届かない clear を書くと、その欄の場所を付けた DesignFlaw になる。"""
        text = _LIFT_LANDING + (
            "rules:\n  tend: { revive_hp_rate: 0.6 }\n"
            "built_in_action_perceptions:\n"
            '  tend:\n    witness: { clear: "{actor}が{target}を介抱している。" }\n'
            '    target: { clear: "{actor}があなたを介抱している。", noticed_later: "{actor}が介抱してくれたようだ。" }\n'
        )

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [
            _mine("world", "world", "built_in_action_perceptions.tend.target.clear")
        ]

    def test_tend_without_target_text_is_not_noticed_and_not_warned(self, tmp_path: Path) -> None:
        """介抱の行に target を書かないと、既定の文で埋めずに気づかない (NoTarget) ことになり、DesignWarning も残さない。"""
        text = _LIFT_LANDING + (
            "rules:\n  tend: { revive_hp_rate: 0.6 }\n"
            "built_in_action_perceptions:\n"
            '  tend:\n    witness: { clear: "{actor}が{target}を介抱している。" }\n    sound: null\n'
        )

        loaded = _load(tmp_path, text)

        assert loaded.design.built_in_action_perceptions.by_kind[ActionKind.TEND].target == NoTarget()
        assert [w for w in loaded.warnings if w.location.field.startswith("built_in_action_perceptions.tend")] == []

    @pytest.mark.parametrize(
        "action",
        [
            "interact_with_object",
            "interact_with_carried_item",
            "interact_with_person",
            "enter_section",
            "leave_section",
            "attack_monster",
        ],
    )
    def test_action_not_in_the_table_is_a_flaw(self, tmp_path: Path, action: str) -> None:
        """組み込みの行為の表に書けない行為 (操作、区画の出入り、モンスターへの攻撃) を書くと、素の例外ではなく表の場所を付けた DesignFlaw になる。"""
        text = (
            _LIFT_LANDING
            + f'built_in_action_perceptions:\n  {action}:\n    witness: {{ clear: "{{actor}}が動いた。" }}\n'
        )

        assert [flaw.location.field for flaw in _flaws(tmp_path, text)] == ["built_in_action_perceptions"]

    def test_travel_target_text_is_a_flaw_at_that_field(self, tmp_path: Path) -> None:
        """相手のいない移動の行に target の文を書くと、その欄の場所を付けた DesignFlaw になる。"""
        text = _LIFT_LANDING + (
            'built_in_action_perceptions:\n  travel:\n    target: { clear: "{actor}があなたから離れた。" }\n'
        )

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [
            _mine("world", "world", "built_in_action_perceptions.travel.target")
        ]


class TestFlawsWhileLoading:
    """読み込みの誤りが、素の例外ではなく場所つきの DesignFlaw にまとまることを保証する。"""

    def test_node_with_two_kinds_is_a_flaw_at_that_node(self, tmp_path: Path) -> None:
        """出来事の条件に種類の鍵を 2 つ書くと、その条件の場所を付けた DesignFlaw になる。"""
        text = _LIFT_LANDING.replace(
            "    condition: { flag_is_raised: lift_departed }\n",
            "    condition: { flag_is_raised: lift_departed, is_down: actor }\n",
        )

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [_mine("happening", "lift_leaves", "condition")]

    def test_three_mistakes_are_all_collected(self, tmp_path: Path) -> None:
        """綴り違いの列挙、知らない種類、宣言の無い品物の 3 か所を書き間違えると、3 つとも集めて 1 つの例外で投げる。"""
        text = (
            _LIFT_LANDING.replace("lighting: bright", "lighting: brigth")
            .replace("raise_flag: lift_departed", "raise_flags: lift_departed")
            .replace("initial_items: [lift_key]", "initial_items: [lift_kye]")
        )

        assert sorted(str(flaw.location) for flaw in _flaws(tmp_path, text)) == sorted(
            [
                str(_mine("spot", "shaft_head", "atmosphere.lighting")),
                str(_mine("object", "lift_panel", "interactions.start_lift.effect.raise_flags")),
                str(_mine("character", "haru", "initial_items[0]")),
            ]
        )

    def test_passage_keeps_its_written_name_and_description(self, tmp_path: Path) -> None:
        """梯子に書いた name と description は、そのまま梯子の PassageDeclaration に入る。"""
        nouns = _load(tmp_path).design.nouns

        ladder = nouns.passage("ladder", DesignLocation("passage", "ladder", ""))

        assert ladder.name == DisplayName("古い梯子")
        assert ladder.description == DescriptionText("縦穴の壁に打ち付けた木の梯子。")

    def test_passage_without_name_is_a_flaw_not_filled_from_defaults(self, tmp_path: Path) -> None:
        """梯子の name を書き忘れると、共通の部品で埋めずに、その欄の場所を付けた DesignFlaw になる。"""
        text = _LIFT_LANDING.replace("name: 古い梯子, ", "")

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [_mine("passage", "ladder", "name")]

    def test_missing_required_field_is_a_flaw_not_key_error(self, tmp_path: Path) -> None:
        """操作の success_text を書き忘れても KeyError を出さず、その欄の場所を付けた DesignFlaw になる。"""
        text = _LIFT_LANDING.replace("            success_text: 籠が大きく揺れ、ゆっくりと縦穴を上がりはじめた。\n", "")

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [
            _mine("object", "lift_panel", "interactions.start_lift.success_text")
        ]

    def test_duplicated_key_is_a_flaw(self, tmp_path: Path) -> None:
        """同じ名前の場所を 2 回書くと、その場所の DesignFlaw になる。"""
        text = _LIFT_LANDING.replace("  shaft_head:\n", "  lift_landing:\n    name: もう一つ\n  shaft_head:\n", 1)

        assert _mine("spot", "lift_landing", "") in [flaw.location for flaw in _flaws(tmp_path, text)]

    def test_unknown_field_is_a_flaw(self, tmp_path: Path) -> None:
        """宣言に無い欄 (綴り違いの descripton) を書くと、その欄の場所を付けた DesignFlaw になる。"""
        text = _LIFT_LANDING.replace("description: 縦穴の上の小屋。", "descripton: 縦穴の上の小屋。")

        assert _mine("spot", "shaft_head", "descripton") in [flaw.location for flaw in _flaws(tmp_path, text)]

    def test_adding_to_a_flag_key_is_a_flaw_at_that_effect(self, tmp_path: Path) -> None:
        """旗の状態の鍵 (操作盤の通電) に数を足す効果を書くと、遊ぶ前の読み込みで、その効果の場所を付けた DesignFlaw になる。"""
        text = _LIFT_LANDING.replace(
            "        description: 籠の奥の壁にある操作盤。\n",
            "        description: 籠の奥の壁にある操作盤。\n"
            "        state_keys: { powered: { kind: flag, initial: false } }\n",
        ).replace(
            "              raise_flag: lift_departed\n",
            "              sequence:\n"
            "                - raise_flag: lift_departed\n"
            "                - add_to_object_count: { key: lift_panel.powered, amount: 1 }\n",
        )

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [
            _mine("object", "lift_panel", "interactions.start_lift.effect.sequence[1].add_to_object_count")
        ]

    def test_counting_a_flag_key_in_a_condition_is_a_flaw_at_that_condition(self, tmp_path: Path) -> None:
        """旗の状態の鍵 (操作盤の通電) を数として比べる条件を書くと、読み込みで、その条件の場所を付けた DesignFlaw になる。"""
        text = _LIFT_LANDING.replace(
            "        description: 籠の奥の壁にある操作盤。\n",
            "        description: 籠の奥の壁にある操作盤。\n"
            "        state_keys: { powered: { kind: flag, initial: false } }\n",
        ).replace(
            "    condition: { flag_is_raised: lift_departed }\n",
            "    condition: { object_count_at_least: { key: lift_panel.powered, count: 1 } }\n",
        )

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [
            _mine("happening", "lift_leaves", "condition.object_count_at_least")
        ]


class TestBrokenShapesStayDesignFlaws:
    """形の崩れた YAML でも、素の例外ではなく DesignFlaw にまとまることを保証する。"""

    @pytest.mark.parametrize(
        ("broken", "location"),
        [
            ("spots:\n", _mine("world", "world", "spots")),
            ("groupings: [team]\n", _mine("world", "world", "groupings")),
        ],
    )
    def test_top_level_map_that_is_not_a_map_is_a_flaw(
        self, tmp_path: Path, broken: str, location: DesignLocation
    ) -> None:
        """名前で指す宣言の欄を空や一覧にすると、その欄の場所を付けた DesignFlaw になる。"""
        text = (
            "includes: [common.yaml]\n"
            "introduction: { title: 坑道, text: 目覚めた。, premises: 出る。 }\n"
            "ending: { ends_when: all_outcomes_decided }\n"
            "time: { day_night: null, weather: null }\n" + broken
        )

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [location]

    def test_objects_left_empty_inside_spot_is_a_flaw(self, tmp_path: Path) -> None:
        """場所の objects: の中身をすべて消して空にすると、その欄の場所を付けた DesignFlaw になる。"""
        text = _LIFT_LANDING.replace(
            "    atmosphere: { lighting: bright }\n", "    atmosphere: { lighting: bright }\n    objects:\n"
        )

        assert _mine("spot", "shaft_head", "objects") in [flaw.location for flaw in _flaws(tmp_path, text)]

    def test_recursive_anchor_is_a_flaw(self, tmp_path: Path) -> None:
        """自分を含むアンカー (&a [*a]) を書くと、無限に辿らず DesignFlaw になる。"""
        flaws = _flaws(tmp_path, _LIFT_LANDING + "loop: &a [*a]\n")

        assert flaws

    def test_number_key_is_a_flaw(self, tmp_path: Path) -> None:
        """名前に数を書くと (1 と '1' が黙って重ならないよう) その場所の DesignFlaw になる。"""
        text = _LIFT_LANDING.replace(
            "  lift_departed: { meaning: 籠が上がった }\n",
            "  lift_departed: { meaning: 籠が上がった }\n  1: { meaning: 数 }\n",
        )

        assert _mine("world", "world", "flags") in [flaw.location for flaw in _flaws(tmp_path, text)]

    def test_target_text_on_object_interaction_is_a_flaw(self, tmp_path: Path) -> None:
        """相手のいない物の操作に、された人の文 target を書くと、誰にも届かない文として DesignFlaw になる。"""
        text = _LIFT_LANDING.replace(
            '              witness: { clear: "{actor}が昇降機の操作盤に鍵を差し、把手を引いた。" }\n',
            '              witness: { clear: "{actor}が昇降機の操作盤に鍵を差し、把手を引いた。" }\n'
            "              target: { clear: 誰か。 }\n",
        )

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [
            _mine("object", "lift_panel", "interactions.start_lift.perceived_as.target")
        ]

    def test_same_flaw_is_reported_once(self, tmp_path: Path) -> None:
        """場所に知らない欄を 1 つ書くと、名詞と動詞の両方で読んでも誤りは 1 つだけ出る。"""
        text = _LIFT_LANDING.replace("description: 縦穴の上の小屋。", "description: 縦穴の上の小屋。\n    foo: 1")

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [_mine("spot", "shaft_head", "foo")]

    def test_include_not_in_utf8_is_a_flaw_at_its_place(self, tmp_path: Path) -> None:
        """UTF-8 でない共通の部品は、includes のその位置の DesignFlaw になる。"""
        path = _scenario(
            tmp_path, _LIFT_LANDING.replace("includes: [common.yaml]", "includes: [common.yaml, broken.yaml]")
        )
        (tmp_path / "broken.yaml").write_bytes("rules: 規則".encode("shift_jis"))

        with pytest.raises(WorldDesignFlawsException) as raised:
            load_scenario(path)

        assert [flaw.location for flaw in raised.value.flaws] == [_mine("world", "world", "includes[1]")]


class TestSkippingWhatPointsAtUnreadable:
    """読めなかった名詞を指す宣言を飛ばしても、元の誤りは捨てずに 1 件だけ出すことを保証する。"""

    def test_happening_reading_unreadable_flag_is_skipped_but_flag_flaw_remains(self, tmp_path: Path) -> None:
        """旗 lift_departed の意味に数を書くと、旗の誤りだけが 1 件出て、その旗を見る出来事や操作の「宣言が無い」は出ない。"""
        text = _LIFT_LANDING.replace("lift_departed: { meaning: 籠が上がった }", "lift_departed: { meaning: 5 }")

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [_mine("flag", "lift_departed", "meaning")]

    def test_passage_pointing_at_unreadable_spot_is_left_out_without_its_own_flaw(self, tmp_path: Path) -> None:
        """縦穴の上の明るさを綴り違えると、その場所の誤りだけが出て、そこへ続く梯子の「場所が無い」は出ない。"""
        text = _LIFT_LANDING.replace("lighting: bright", "lighting: brigth")

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [
            _mine("spot", "shaft_head", "atmosphere.lighting")
        ]

    def test_written_states_are_not_mixed_with_default_open(self, tmp_path: Path) -> None:
        """states を書いた梯子は、共通の部品の既定の open を混ぜず、書いた状態だけを持つ。"""
        text = _LIFT_LANDING.replace(
            "  ladder: { name: 古い梯子, description: 縦穴の壁に打ち付けた木の梯子。, ends: [lift_landing, shaft_head], travel_ticks: 3 }",
            "  ladder:\n"
            "    name: 古い梯子\n"
            "    description: 縦穴の壁に打ち付けた木の梯子。\n"
            "    ends: [lift_landing, shaft_head]\n"
            "    travel_ticks: 3\n"
            "    states: { shut: { display_name: 閉じている, traversable: false, sound_loss: 20 } }\n"
            "    initial_state: shut",
        )

        ladder = _load(tmp_path, text).design.nouns.passage("ladder", DesignLocation("passage", "ladder", ""))

        assert [state.name.value for state in ladder.states] == ["shut"]


class TestTimeMustBeWritten:
    """天候と昼夜は「無い」ことも null で書かせ、書き忘れを「無い」として通さないことを保証する。"""

    def test_null_weather_and_day_night_mean_none(self, tmp_path: Path) -> None:
        """weather: null と day_night: null を書けば、天候も昼夜も無い世界になる。"""
        design = _load(tmp_path).design

        assert (design.weather, design.day_night) == (NoWeather(), NoDayNight())

    @pytest.mark.parametrize(
        ("written", "missing"),
        [
            ("time:\n  day_night: null\n  weather: null\n", None),
            ("time:\n  day_night: null\n", "time.weather"),
            ("time:\n  weather: null\n", "time.day_night"),
        ],
    )
    def test_forgetting_weather_or_day_night_is_a_flaw(self, tmp_path: Path, written: str, missing: str | None) -> None:
        """time: を書かないか、その中の weather か day_night を書き忘れると、その欄の場所の DesignFlaw になる。"""
        text = (
            _LIFT_LANDING.replace(written, "")
            if missing is None
            else _LIFT_LANDING.replace("time:\n  day_night: null\n  weather: null\n", written)
        )

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [_mine("world", "world", missing or "time")]


class TestFlawsNameTheirFile:
    """誤りの場所が、シナリオか、取り込んだどの共通の部品かを持ち、文にもファイルの名前が出ることを保証する。"""

    def test_mistake_inside_include_names_the_include(self, tmp_path: Path) -> None:
        """共通の部品の規則の疲れの上限に文を書くと、その誤りは共通の部品 common.yaml の場所になり、文の先頭に common.yaml が付く。"""
        path = _scenario(tmp_path, _LIFT_LANDING)
        common = tmp_path / "common.yaml"
        common.write_text(
            common.read_text(encoding="utf-8").replace(
                "limit: 100\n    levels: [{ starts_at: 0, name: 元気 }]",
                "limit: たくさん\n    levels: [{ starts_at: 0, name: 元気 }]",
            ),
            encoding="utf-8",
        )

        with pytest.raises(WorldDesignFlawsException) as raised:
            load_scenario(path)

        (flaw,) = raised.value.flaws
        assert flaw.location == DesignLocation("world", "world", "rules.fatigue.limit").in_file(
            ScenarioFile("common.yaml")
        )
        assert str(flaw).startswith("common.yaml: ")

    def test_field_the_scenario_overrides_names_the_scenario(self, tmp_path: Path) -> None:
        """シナリオが共通の部品の疲れの上限だけを書き換えて間違えると、その誤りはシナリオ mine.yaml の場所になる。"""
        text = _LIFT_LANDING + "rules:\n  fatigue:\n    limit: たくさん\n"

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [_mine("world", "world", "rules.fatigue.limit")]

    def test_mistake_in_a_filled_default_names_the_defaults(self, tmp_path: Path) -> None:
        """共通の部品の defaults.flag の initially_raised を文にすると、その既定で埋めた旗の誤りは、旗ではなく common.yaml の defaults の場所になる。"""
        path = _scenario(tmp_path, _LIFT_LANDING)
        common = tmp_path / "common.yaml"
        common.write_text(
            common.read_text(encoding="utf-8").replace(
                "flag: { initially_raised: false }", "flag: { initially_raised: いいえ }"
            ),
            encoding="utf-8",
        )

        with pytest.raises(WorldDesignFlawsException) as raised:
            load_scenario(path)

        assert [flaw.location for flaw in raised.value.flaws] == [
            DesignLocation("world", "world", "defaults.flag.initially_raised").in_file(ScenarioFile("common.yaml"))
        ]

    def test_flaw_found_by_compose_names_the_file_of_its_declaration(self, tmp_path: Path) -> None:
        """宣言の無い出来事を読む出来事 rumble の誤りは compose が見つけ、rumble を書いたシナリオ mine.yaml の場所になる。"""
        text = _LIFT_LANDING.replace(
            "happenings:\n",
            "happenings:\n"
            "  rumble:\n"
            "    condition: { happening_has_fired: landslide }\n"
            "    once: true\n"
            "    effect: no_effect\n",
        )

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [_mine("happening", "rumble", "condition")]


class TestFilesAcrossSeveralIncludes:
    """宣言を共通の部品とシナリオに分けて書いたときも、誤りがそれを書いたファイルを指すことを保証する。"""

    def test_missing_field_in_a_replaced_list_names_the_scenario(self, tmp_path: Path) -> None:
        """シナリオが疲れの段階の一覧を置き換え、その中の starts_at を書き忘れると、共通の部品ではなく mine.yaml を指す。"""
        text = _LIFT_LANDING + "rules:\n  fatigue:\n    levels: [{ name: 元気 }]\n"

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [
            _mine("world", "world", "rules.fatigue.levels[0].starts_at")
        ]

    def test_compose_flaw_in_an_included_interaction_names_that_include(self, tmp_path: Path) -> None:
        """parts.yaml に書いた操作の前提が宣言の無い出来事を読むと、シナリオが同じ物の説明だけを書き換えていても、誤りは parts.yaml を指す。"""
        parts = (
            "happenings:\n"
            "  rumble:\n"
            "    condition: { tick_at_least: 1 }\n"
            "    once: true\n"
            "    effect: no_effect\n"
            "spots:\n"
            "  lift_landing:\n"
            "    objects:\n"
            "      lift_panel:\n"
            "        interactions:\n"
            "          start_lift:\n"
            "            precondition: { happening_has_fired: ghost, failure_text: 動かない。 }\n"
        )
        text = _LIFT_LANDING.replace("includes: [common.yaml]", "includes: [common.yaml, parts.yaml]").replace(
            "            precondition:\n"
            "              all_of:\n"
            "                - not: { flag_is_raised: lift_departed }\n"
            "                  failure_text: 籠はもう上がってしまった。\n"
            "                - has_item: { who: actor, item_spec: lift_key, count: 1 }\n"
            "                  failure_text: 鍵穴に合う鍵を持っていない。\n"
            "                - flag_is_raised: generator_running\n"
            "              failure_text: 昇降機は動かない。\n",
            "",
        )
        path = _scenario(tmp_path, text)
        (tmp_path / "parts.yaml").write_text(parts, encoding="utf-8")

        with pytest.raises(WorldDesignFlawsException) as raised:
            load_scenario(path)

        assert [flaw.location.file for flaw in raised.value.flaws] == [ScenarioFile("parts.yaml")]

    def test_compose_warning_names_the_file_of_its_declaration(self, tmp_path: Path) -> None:
        """立てるだけで誰も見ない旗 bell の警告は、bell を宣言したシナリオ mine.yaml を指す。"""
        text = _LIFT_LANDING.replace(
            "  lift_departed: { meaning: 籠が上がった }\n",
            "  lift_departed: { meaning: 籠が上がった }\n  bell: { meaning: 鐘が鳴った }\n",
        ).replace(
            "              raise_flag: lift_departed\n",
            "              sequence: [{ raise_flag: lift_departed }, { raise_flag: bell }]\n",
        )

        warnings = _load(tmp_path, text).warnings

        assert _mine("flag", "bell", "flag_id") in [warning.location for warning in warnings]


class TestFormatDocumentExamples:
    """scenario_format.md に載せた例が、そのまま読み込めることを保証する。"""

    def test_beast_happening_example_loads(self, tmp_path: Path) -> None:
        """獣を出来事に置き換えた例 (北の坑道にいる人に痛手を与え、物音で知らせる) は、知らせの salience を共通の部品で埋めて読める。"""
        text = (
            _LIFT_LANDING.replace(
                "  shaft_head:\n",
                "  north_tunnel:\n    name: 北の坑道\n    description: 暗い坑道。\n    atmosphere: { lighting: dark }\n"
                "  shaft_head:\n",
            )
            .replace(
                "  lift_departed: { meaning: 籠が上がった }\n",
                "  lift_departed: { meaning: 籠が上がった }\n  beast_north_awake: { meaning: 獣が目覚めた }\n",
            )
            .replace(
                "happenings:\n",
                "happenings:\n"
                "  beast_north_attacks:\n"
                "    condition:\n"
                "      all_of:\n"
                "        - flag_is_raised: beast_north_awake\n"
                "        - people_count_at_least:\n"
                "            people: { where: { is_at_spot: { who: each_person, spot: north_tunnel } } }\n"
                "            count: 1\n"
                "      failure_text: 北の坑道は静かだ。\n"
                "    once: false\n"
                "    effect:\n"
                "      for_everyone:\n"
                "        people: { where: { is_at_spot: { who: each_person, spot: north_tunnel } } }\n"
                "        effect: { damage: { who: each_person, amount: 8 } }\n"
                "    notice:\n"
                "      sound_from: { spot: north_tunnel, sound: { loudness: very_loud, clear: 暗がりから何かが唸った。, muffled: 坑道の奥で唸り声がした。 } }\n"
                "  wake_beast:\n"
                "    condition: { tick_at_least: 10 }\n"
                "    once: true\n"
                "    effect: { raise_flag: beast_north_awake }\n",
            )
        )

        happenings = _load(tmp_path, text).design.happenings()

        assert "beast_north_attacks" in [happening.happening_id.value for happening in happenings]

    def test_notice_naming_a_person_is_a_flaw_at_that_notice(self, tmp_path: Path) -> None:
        """出来事 bell の世界の知らせの文に {each_person} を書くと、その知らせ (notice.announcement_to) を場所とし、理由にプレースホルダーの名前が出る DesignFlaw になる。"""
        text = _LIFT_LANDING.replace(
            "happenings:\n",
            "happenings:\n"
            "  bell:\n"
            "    condition: { tick_at_least: 3 }\n"
            "    once: true\n"
            "    effect: no_effect\n"
            "    notice:\n"
            '      announcement_to: { audience: { where: { all_of: [] } }, text: "{each_person}は鐘を聞いた。" }\n',
        )

        flaws = _flaws(tmp_path, text)

        assert [
            (flaw.location.declaration, flaw.location.name, flaw.location.field, "each_person" in flaw.reason)
            for flaw in flaws
        ] == [("happening", "bell", "notice.announcement_to", True)]


class TestHappeningsReadingThemselves:
    """出来事が自分を読む条件を書けることを保証する。"""

    def test_happening_repeating_after_its_last_firing_loads(self, tmp_path: Path) -> None:
        """最後に起きてから 5 tick 経つと繰り返す出来事 rumble は、自分を指す条件のまま読み込める。"""
        text = _LIFT_LANDING.replace(
            "happenings:\n",
            "happenings:\n"
            "  rumble:\n"
            "    condition: { ticks_since_happening_at_least: { happening: rumble, ticks: 5 } }\n"
            "    once: false\n"
            "    effect: no_effect\n",
        )

        happenings = _load(tmp_path, text).design.happenings()

        assert "rumble" in [happening.happening_id.value for happening in happenings]


def test_passage_id_is_declared_by_its_key(tmp_path: Path) -> None:
    """通路の名前は地図の鍵から取る。"""
    nouns = _load(tmp_path).design.nouns

    assert nouns.passage("ladder", DesignLocation("passage", "ladder", "")).passage_id == PassageId("ladder")


_PANEL_DESCRIPTION = "        description: 籠の奥の壁にある操作盤。\n"


def _with_panel_looks(looks: str) -> str:
    return _LIFT_LANDING.replace(_PANEL_DESCRIPTION, _PANEL_DESCRIPTION + looks, 1)


class TestObjectLooks:
    """load_scenario が、物の中に書いた looks を、書いた順の ObjectLook を持つその物の見え方の宣言にすることを保証する。"""

    def test_written_looks_are_kept_in_order(self, tmp_path: Path) -> None:
        """操作盤に籠が上がったときと発電機が動いているときの見え方を書くと、その順の条件と文を持つ。"""
        text = _with_panel_looks(
            "        looks:\n"
            "          - { when: { flag_is_raised: lift_departed }, text: 鍵穴の鍵は抜かれている }\n"
            "          - { when: { flag_is_raised: generator_running }, text: 小さな灯りがともっている }\n"
        )

        design = _load(tmp_path, text).design
        nouns = design.nouns

        assert design.looks_of(ObjectId("lift_panel")).looks == (
            ObjectLook(
                when=FlagIsRaisedCondition(
                    flag=nouns.flag("lift_departed", DesignLocation("flag", "lift_departed", "")), failure_text=NoText()
                ),
                text=DescriptionText("鍵穴の鍵は抜かれている"),
            ),
            ObjectLook(
                when=FlagIsRaisedCondition(
                    flag=nouns.flag("generator_running", DesignLocation("flag", "generator_running", "")),
                    failure_text=NoText(),
                ),
                text=DescriptionText("小さな灯りがともっている"),
            ),
        )

    def test_unwritten_looks_are_empty(self, tmp_path: Path) -> None:
        """looks を書かない操作盤は、見え方を 1 つも持たない。"""
        design = _load(tmp_path).design

        assert design.looks_of(ObjectId("lift_panel")).looks == ()

    def test_look_reading_the_actor_is_a_flaw_of_that_look(self, tmp_path: Path) -> None:
        """見え方の条件が行う人 (actor) を読むと、その物の looks[0] の DesignFlaw で読み込みが止まる。"""
        text = _with_panel_looks(
            "        looks:\n          - { when: { is_down: { who: actor } }, text: 誰かが倒れている }\n"
        )

        flaws = _flaws(tmp_path, text)

        assert [flaw.location for flaw in flaws] == [_mine("object_looks", "lift_panel", "looks[0]")]

    def test_look_reading_an_undeclared_flag_is_a_flaw(self, tmp_path: Path) -> None:
        """見え方の条件が宣言に無い旗を読むと、読み込みは DesignFlaw で止まる。"""
        text = _with_panel_looks(
            "        looks:\n          - { when: { flag_is_raised: no_such_flag }, text: 何かが変わった }\n"
        )

        flaws = _flaws(tmp_path, text)

        assert len(flaws) == 1
        assert "no_such_flag" in flaws[0].reason


_DAY_NIGHT = """time:
  day_night:
    ticks_per_day: 48
    starts_at: 0
    phases:
      predawn: { display: 未明, begins_at: 0, dark: true, announcement: 夜明け前の、いちばん冷える時刻になった。 }
      morning:
        display: 朝
        begins_at: 12
        dark: false
        announcement: 空が白み、朝になった。
        audience: AUDIENCE
  weather: null
"""


def _with_morning_audience(audience: str) -> str:
    return _LIFT_LANDING.replace(
        "time:\n  day_night: null\n  weather: null\n", _DAY_NIGHT.replace("AUDIENCE", audience)
    )


class TestDayPhaseAudience:
    """時間帯の知らせの届く相手 (audience) を、人の選び方か everyone_awake で読み、書かなければ共通の部品の既定で起きている全員にすることを保証する。"""

    def test_display_is_read_as_the_phase_display_name(self, tmp_path: Path) -> None:
        """時間帯の display は、場面の時刻帯に出す表示名として読まれる。"""
        design = _load(tmp_path, _with_morning_audience("everyone_awake")).design

        assert design.day_night.phase_named(DayPhaseName("predawn")).display_name == DisplayName("未明")

    def test_phase_without_display_is_a_flaw(self, tmp_path: Path) -> None:
        """時間帯に display を書かないと、その時間帯の場所を付けた DesignFlaw になる。識別子を場面に出さないため。"""
        text = _with_morning_audience("everyone_awake").replace("display: 未明, ", "", 1)

        assert any("predawn" in str(flaw.location) for flaw in _flaws(tmp_path, text))

    def test_phase_without_audience_reaches_everyone_awake(self, tmp_path: Path) -> None:
        """audience を書かない夜明け前は、共通の部品の既定で、起きている全員 (EveryoneAwake) に届く。"""
        design = _load(tmp_path, _with_morning_audience("everyone_awake")).design

        assert design.day_night.phase_named(DayPhaseName("predawn")).audience == EveryoneAwake()

    def test_written_audience_is_read_as_a_people_selection(self, tmp_path: Path) -> None:
        """朝の audience に乗り場にいる人の選び方を書くと、その条件で人を選ぶ PeopleSelection として読む。"""
        written = "{ where: { is_at_spot: { who: each_person, spot: lift_landing } } }"
        design = _load(tmp_path, _with_morning_audience(written)).design

        audience = design.day_night.phase_named(DayPhaseName("morning")).audience
        assert isinstance(audience, PeopleSelection)
        assert isinstance(audience.where, IsAtSpotCondition)

    @pytest.mark.parametrize(
        "written",
        ["everyone", "{ where: { is_at_spot: { who: each_person, spot: nowhere } } }", "{ whom: { all_of: [] } }"],
        ids=["知らない言葉", "宣言に無い場所", "知らない欄"],
    )
    def test_mistaken_audience_stops_loading(self, tmp_path: Path, written: str) -> None:
        """朝の audience に、everyone_awake でも人の選び方でもないものや、宣言に無い場所を書くと、読み込みで DesignFlaw になって止まる。"""
        flaws = _flaws(tmp_path, _with_morning_audience(written))

        assert flaws
        assert all("phases.morning.audience" in str(flaw) for flaw in flaws)

    def test_audience_referring_to_an_actor_stops_loading(self, tmp_path: Path) -> None:
        """朝の audience で行った人 (actor) を選ぶと、行った人のいない時間帯なので、time.day_night.phases.morning.audience の DesignFlaw になる。"""
        flaws = _flaws(tmp_path, _with_morning_audience("{ where: { is_down: { who: actor } } }"))

        assert [flaw.location for flaw in flaws] == [_mine("world", "world", "time.day_night.phases.morning.audience")]


class TestWorldWords:
    """明るさ・気温・天候の言葉 (world_words) が共通の部品から読まれ、欠けと誤りが読み込みで DesignFlaw になることを保証する。"""

    def test_scenario_overrides_one_weather_word(self, tmp_path: Path) -> None:
        """シナリオが雪の言葉だけを書くと、その言葉に置き換わり、ほかの言葉は共通の部品のまま残る。"""
        text = _LIFT_LANDING + "world_words:\n  weather: { snow: 粉雪 }\n"

        words = _load(tmp_path, text).design.world_words

        assert (words.weather[WeatherType.SNOW], words.weather[WeatherType.RAIN]) == ("粉雪", "雨")

    def test_unknown_weather_is_a_flaw(self, tmp_path: Path) -> None:
        """天候の言葉に宣言に無い天候を書くと、その欄の場所を付けた DesignFlaw になる。"""
        text = _LIFT_LANDING + "world_words:\n  weather: { hail: 雹 }\n"

        assert any("hail" in str(flaw.location) for flaw in _flaws(tmp_path, text))

    def test_blank_word_is_a_flaw(self, tmp_path: Path) -> None:
        """言葉を空にすると、MissingWorldWordException が読み込みの DesignFlaw として集まる。"""
        text = _LIFT_LANDING + "world_words:\n  lighting: { dark: ' ' }\n"

        assert any("world_words" in str(flaw.location) for flaw in _flaws(tmp_path, text))
