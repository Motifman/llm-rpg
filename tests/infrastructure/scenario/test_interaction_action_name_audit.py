"""全シナリオの interaction 名と display_label の監査。

action_name は LLM が実際に tool 引数へ渡す識別子であり、display_label は
その識別子の意味を選択前に説明する文字列である。display_label が空・同一・
未翻訳のままになると、選択画面が裸の action_name に戻り、多義語の誤解を
再発させる。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, NamedTuple

from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

SCENARIO_DIR = Path(__file__).resolve().parents[3] / "data" / "scenarios"


class InteractionAuditEntry(NamedTuple):
    """scenario 内の interaction 1 件を、修正できる位置情報つきで表す。"""

    scenario: str
    location: str
    action_name: Any
    display_label: Any


AMBIGUOUS_BARE_ACTION_NAME_REASONS: Mapping[str, str] = {
    "take": "take care / take a look と衝突し、治療や診察に読まれる",
    "light": "名詞の明かり・形容詞の軽いと同形で、火をつける意味が弱い",
    "search": "何を探すかが名前から分からず、対象違いの再試行を誘う",
    "claim": "日本語話者には苦情の『クレーム』に読まれやすい",
    "clean": "形容詞と同形で、何を掃除するかが名前から分からない",
    "record": "名詞と同形で、何を記録するかが名前から分からない",
    "collect": "gather 系と意味が重なり、何を集めるかが名前から分からない",
    "use": "対象が名前に無く、use_item / interact の判断を曖昧にする",
    "set": "置く・設定する・整えるなど意味が広すぎる",
    "run": "走る・実行するの両方に読め、世界行動か操作かが曖昧になる",
    "check": "確認対象が名前に無く、診察・調査・検査に広く読める",
    "get": "取る・得る・理解するなど意味が広すぎる",
    "make": "作る対象が名前に無く、生成・調理・工作が曖昧になる",
    "hold": "持つ・押さえる・待つなど意味が広すぎる",
}
AMBIGUOUS_BARE_ACTION_NAMES = frozenset(AMBIGUOUS_BARE_ACTION_NAME_REASONS)


def _iter_interactions(raw: Mapping[str, Any], *, scenario: str) -> Iterable[InteractionAuditEntry]:
    """scenario JSON から object / player interaction を位置情報つきで列挙する。"""
    for spot_index, spot in enumerate(raw.get("spots", []) or []):
        if not isinstance(spot, Mapping):
            continue
        spot_id = spot.get("id", f"#{spot_index}")
        interior = spot.get("interior") or {}
        if not isinstance(interior, Mapping):
            continue
        objects = interior.get("objects", []) or []
        for object_index, obj in enumerate(objects):
            if not isinstance(obj, Mapping):
                continue
            object_id = obj.get("id", f"#{object_index}")
            interactions = obj.get("interactions", []) or []
            for interaction_index, interaction in enumerate(interactions):
                if not isinstance(interaction, Mapping):
                    continue
                yield InteractionAuditEntry(
                    scenario=scenario,
                    location=(
                        f"spots[{spot_id!r}].objects[{object_id!r}]"
                        f".interactions[{interaction_index}]"
                    ),
                    action_name=interaction.get("action_name"),
                    display_label=interaction.get("display_label"),
                )

    for index, interaction in enumerate(raw.get("player_interactions", []) or []):
        if not isinstance(interaction, Mapping):
            continue
        yield InteractionAuditEntry(
            scenario=scenario,
            location=f"player_interactions[{index}]",
            action_name=interaction.get("action_name"),
            display_label=interaction.get("display_label"),
        )


def _load_raw_scenarios() -> list[tuple[Path, Mapping[str, Any]]]:
    """data/scenarios/*.json を JSON として読み、監査入力にする。"""
    loaded: list[tuple[Path, Mapping[str, Any]]] = []
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        loaded.append((path, raw))
    return loaded


def _count_action_name_dicts(value: Any) -> int:
    """JSON 全体から action_name キーを持つ dict を再帰的に数える。"""
    if isinstance(value, Mapping):
        count = 1 if "action_name" in value else 0
        return count + sum(_count_action_name_dicts(child) for child in value.values())
    if isinstance(value, list):
        return sum(_count_action_name_dicts(child) for child in value)
    return 0


def find_missing_or_empty_display_labels(
    entries: Iterable[InteractionAuditEntry],
) -> list[InteractionAuditEntry]:
    """display_label が欠落・空白・文字列以外の interaction を返す。"""
    return [
        entry
        for entry in entries
        if not isinstance(entry.display_label, str) or not entry.display_label.strip()
    ]


def find_untranslated_display_labels(
    entries: Iterable[InteractionAuditEntry],
) -> list[InteractionAuditEntry]:
    """display_label が action_name と同一で、意味説明になっていない interaction を返す。"""
    return [
        entry
        for entry in entries
        if isinstance(entry.action_name, str)
        and isinstance(entry.display_label, str)
        and entry.action_name.strip() == entry.display_label.strip()
    ]


def find_ambiguous_bare_action_names(
    entries: Iterable[InteractionAuditEntry],
) -> list[InteractionAuditEntry]:
    """多義語 denylist に一致する裸の action_name を返す。"""
    return [
        entry
        for entry in entries
        if isinstance(entry.action_name, str)
        and entry.action_name.strip() in AMBIGUOUS_BARE_ACTION_NAMES
    ]


def _format_violations(entries: Iterable[InteractionAuditEntry]) -> str:
    """どのファイルのどの action かを修正できる形で表示する。"""
    return "\n".join(
        (
            f"{entry.scenario}: {entry.location}: "
            f"action_name={entry.action_name!r}, display_label={entry.display_label!r}"
        )
        for entry in entries
    )


def _scenario_entries() -> list[InteractionAuditEntry]:
    """全 scenario の interaction を監査 entry として返す。"""
    entries: list[InteractionAuditEntry] = []
    for path, raw in _load_raw_scenarios():
        entries.extend(_iter_interactions(raw, scenario=path.name))
    return entries


class TestScenarioInteractionDisplayLabels:
    """全シナリオで action_name の意味を display_label が選択前に説明することを保証する。"""

    def test_all_interactions_have_non_empty_display_label(self) -> None:
        """display_label 欠落・空白は、裸の action_name 表示へ戻るので許さない。"""
        violations = find_missing_or_empty_display_labels(_scenario_entries())
        assert not violations, _format_violations(violations)

    def test_all_display_labels_are_not_identical_to_action_name(self) -> None:
        """display_label が action_name と同一なら翻訳していないので許さない。"""
        violations = find_untranslated_display_labels(_scenario_entries())
        assert not violations, _format_violations(violations)

    def test_all_scenarios_still_load_after_display_label_audit(self) -> None:
        """監査対象の全シナリオは ScenarioLoader でも読み込める。"""
        for path, _raw in _load_raw_scenarios():
            ScenarioLoader().load_from_file(path)

    def test_explicit_interaction_iterator_matches_recursive_action_name_count(self) -> None:
        """明示的な走査は新しい入れ子を静かに取りこぼすため、再帰数と一致させる。"""
        mismatches: list[str] = []
        for path, raw in _load_raw_scenarios():
            explicit_count = len(list(_iter_interactions(raw, scenario=path.name)))
            recursive_count = _count_action_name_dicts(raw)
            if explicit_count != recursive_count:
                mismatches.append(
                    f"{path.name}: _iter_interactions={explicit_count}, "
                    f"recursive_action_name_dicts={recursive_count}, "
                    f"diff={recursive_count - explicit_count}"
                )

        assert not mismatches, "\n".join(mismatches)

    def test_action_names_do_not_use_ambiguous_bare_verbs(self) -> None:
        """多義語の裸 action_name は名前だけで誤解を作るため、通常監査で落とす。"""
        violations = find_ambiguous_bare_action_names(_scenario_entries())
        assert not violations, _format_violations(violations)


class TestInteractionDisplayLabelAuditMutationFixtures:
    """違反片を直接渡すと監査 helper が落とすことを保証する。"""

    def test_missing_or_empty_display_label_violation_is_reported(self) -> None:
        """display_label 欠落・空白の違反片は、該当位置つきで検出される。"""
        entries = [
            InteractionAuditEntry("bad.json", "spots['room'].objects['box'].interactions[0]", "open_box", ""),
            InteractionAuditEntry("bad.json", "player_interactions[0]", "loot_from_downed", None),
        ]

        violations = find_missing_or_empty_display_labels(entries)

        assert len(violations) == 2
        assert "spots['room'].objects['box']" in _format_violations(violations)
        assert "player_interactions[0]" in _format_violations(violations)

    def test_display_label_equal_to_action_name_violation_is_reported(self) -> None:
        """display_label が action_name と同一の違反片は、未翻訳として検出される。"""
        entries = [
            InteractionAuditEntry("bad.json", "spots['room'].objects['box'].interactions[0]", "open_box", "open_box"),
        ]

        violations = find_untranslated_display_labels(entries)

        assert violations == entries

    def test_ambiguous_bare_action_name_violation_is_reported(self) -> None:
        """多義語 denylist に入る action_name の違反片は検出される。"""
        entries = [
            InteractionAuditEntry("bad.json", "player_interactions[0]", "take", "持ち物を奪う"),
            InteractionAuditEntry("ok.json", "player_interactions[1]", "loot_from_downed", "持ち物を奪う"),
        ]

        violations = find_ambiguous_bare_action_names(entries)

        assert violations == [entries[0]]

    def test_ambiguous_denylist_keeps_seed_words_with_reasons(self) -> None:
        """denylist を空にする退行を、理由つき語彙の存在で検出する。"""
        expected = {
            "take", "light", "search", "claim", "clean", "record", "collect",
            "use", "set", "run", "check", "get", "make", "hold",
        }
        assert set(AMBIGUOUS_BARE_ACTION_NAME_REASONS) == expected
        assert all(reason.strip() for reason in AMBIGUOUS_BARE_ACTION_NAME_REASONS.values())
