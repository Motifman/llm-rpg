"""退役した当たり判定の値をスキル定義や本番経路へ再導入しない。"""

import ast
from dataclasses import fields
from pathlib import Path

from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec

_ROOT = Path(__file__).resolve().parents[2]
_REMOVED_MODULES = {
    "domain/combat/value_object/hit_box_shape.py",
    "domain/combat/value_object/hit_box_velocity.py",
    "domain/combat/value_object/hit_effect.py",
    "domain/combat/exception/combat_exceptions.py",
    "domain/skill/value_object/skill_hit_pattern.py",
}
_REMOVED_NAMES = {
    "HitBoxShape",
    "RelativeCoordinate",
    "HitBoxVelocity",
    "HitEffect",
    "HitEffectType",
    "SkillHitPattern",
    "SkillHitTimelineSegment",
    "SkillHitPatternType",
    "HitBoxValidationException",
    "HitEffectValidationException",
    "SkillHitPatternValidationException",
    "SkillRotationAngleUnsupportedException",
    "CombatDomainException",
}


def test_legacy_modules_are_absent() -> None:
    """旧当たり判定の値・命中パターン・専用例外のモジュールは存在しない。"""
    assert not [path for path in _REMOVED_MODULES if (_ROOT / "src/ai_rpg_world" / path).exists()]


def test_source_has_no_legacy_symbols_or_dynamic_imports() -> None:
    """srcの宣言・参照・再公開・動的import用文字列に削除した型やモジュールが残らない。"""
    forbidden = _REMOVED_NAMES | {Path(p).stem for p in _REMOVED_MODULES}
    found = []
    for path in (_ROOT / "src").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            values = [getattr(node, attr, "") for attr in ("name", "id", "attr", "module")]
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                values.append(node.value)
            if any(value and set(value.split(".")) & forbidden for value in values):
                found.append(f"{path.relative_to(_ROOT)}:{node.lineno}")
    assert not found
    assert not any(name in (_ROOT / "pyproject.toml").read_text() for name in _REMOVED_NAMES)


def test_skill_spec_has_no_hit_fields() -> None:
    """SkillSpecは旧当たり判定の形・速度・追加効果を保持しない。"""
    assert not {"hit_pattern", "hit_effects"} & {field.name for field in fields(SkillSpec)}
