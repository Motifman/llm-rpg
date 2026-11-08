from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ai_rpg_world.game_world.domain.action.common_rule_refusal import CommonRuleRefusalKind
from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw, DesignLocation
from ai_rpg_world.game_world.domain.exception.world_design_exception import WorldDesignFlawsException
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    DisplayName,
    HitPoints,
    InteractionId,
    ObjectId,
    PassageId,
    PersonId,
    SpotSectionId,
)
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import LoadedScenario, load_scenario

_COMMON = Path(__file__).parent / "data" / "common_for_tests.yaml"

_LIFT_LANDING = """
includes: [common.yaml]
introduction:
  text: 坑道の奥で目を覚ました。
  objective: 昇降機で外へ出る。
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
  ladder: { ends: [lift_landing, shaft_head], travel_ticks: 3 }
item_specs:
  lift_key: { name: 昇降機の鍵, description: 小さな真鍮の鍵。 }
characters:
  haru:
    appearance: 測量具を背負った年かさの男
    spawn_spot: lift_landing
    initial_items: [lift_key]
    being:
      name: ハル
      first_person: 私
  mio:
    appearance: 小柄な若い女
    spawn_spot: lift_landing
    max_hp: 60
    pack_capacity: 8
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
"""


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

    def test_being_is_returned_apart_from_the_world(self, tmp_path: Path) -> None:
        """haru の being: は世界の宣言には入らず、人柄の地図のまま beings に返る。being の無い mio は含まれない。"""
        loaded = _load(tmp_path)

        assert dict(loaded.beings) == {PersonId("haru"): {"name": "ハル", "first_person": "私"}}

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

        assert DesignLocation("section", "cage", "access.perceived_as.sound") in [
            warning.location for warning in loaded.warnings()
        ]


class TestIncludes:
    """シナリオが includes: の共通の部品を行ごとに書き換えられることを保証する。"""

    def test_one_refusal_text_is_rewritten_and_the_rest_kept(self, tmp_path: Path) -> None:
        """断りの文の busy だけをシナリオで書き換えると、busy は書き換えた文、too_tired は共通の部品の文になる。"""
        text = _LIFT_LANDING + "refusal_texts:\n  common_rules:\n    busy: 今はそれどころではない。\n"

        texts = _load(tmp_path, text).design.refusal_texts.common_rules

        assert texts[CommonRuleRefusalKind.BUSY] == TextWithUnassignedPeople("今はそれどころではない。")
        assert texts[CommonRuleRefusalKind.TOO_TIRED] == TextWithUnassignedPeople("疲れて動けない。")


class TestFlawsWhileLoading:
    """読み込みの誤りが、素の例外ではなく場所つきの DesignFlaw にまとまることを保証する。"""

    def test_node_with_two_kinds_is_a_flaw_at_that_node(self, tmp_path: Path) -> None:
        """出来事の条件に種類の鍵を 2 つ書くと、その条件の場所を付けた DesignFlaw になる。"""
        text = _LIFT_LANDING.replace(
            "    condition: { flag_is_raised: lift_departed }\n",
            "    condition: { flag_is_raised: lift_departed, is_down: actor }\n",
        )

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [
            DesignLocation("happening", "lift_leaves", "condition")
        ]

    def test_three_mistakes_are_all_collected(self, tmp_path: Path) -> None:
        """綴り違いの列挙、知らない種類、宣言の無い品物の 3 か所を書き間違えると、3 つとも集めて 1 つの例外で投げる。"""
        text = (
            _LIFT_LANDING.replace("lighting: bright", "lighting: brigth")
            .replace("raise_flag: lift_departed", "raise_flags: lift_departed")
            .replace("initial_items: [lift_key]", "initial_items: [lift_kye]")
        )

        assert sorted(str(flaw.location) for flaw in _flaws(tmp_path, text)) == sorted(
            [
                str(DesignLocation("spot", "shaft_head", "atmosphere.lighting")),
                str(DesignLocation("object", "lift_panel", "interactions.start_lift.effect.raise_flags")),
                str(DesignLocation("character", "haru", "initial_items[0]")),
            ]
        )

    def test_missing_required_field_is_a_flaw_not_key_error(self, tmp_path: Path) -> None:
        """操作の success_text を書き忘れても KeyError を出さず、その欄の場所を付けた DesignFlaw になる。"""
        text = _LIFT_LANDING.replace("            success_text: 籠が大きく揺れ、ゆっくりと縦穴を上がりはじめた。\n", "")

        assert [flaw.location for flaw in _flaws(tmp_path, text)] == [
            DesignLocation("object", "lift_panel", "interactions.start_lift.success_text")
        ]

    def test_duplicated_key_is_a_flaw(self, tmp_path: Path) -> None:
        """同じ名前の場所を 2 回書くと、その場所の DesignFlaw になる。"""
        text = _LIFT_LANDING.replace("  shaft_head:\n", "  lift_landing:\n    name: もう一つ\n  shaft_head:\n", 1)

        assert DesignLocation("spot", "lift_landing", "") in [flaw.location for flaw in _flaws(tmp_path, text)]

    def test_unknown_field_is_a_flaw(self, tmp_path: Path) -> None:
        """宣言に無い欄 (綴り違いの descripton) を書くと、その欄の場所を付けた DesignFlaw になる。"""
        text = _LIFT_LANDING.replace("description: 縦穴の上の小屋。", "descripton: 縦穴の上の小屋。")

        assert DesignLocation("spot", "shaft_head", "descripton") in [flaw.location for flaw in _flaws(tmp_path, text)]


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
