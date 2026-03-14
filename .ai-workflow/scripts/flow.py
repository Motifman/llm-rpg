#!/usr/bin/env python3
"""Helpers for the lightweight flow-* workflow."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = ROOT / ".ai-workflow"
IDEAS_DIR = WORKFLOW_DIR / "ideas"
FEATURES_DIR = WORKFLOW_DIR / "features"
TEMPLATES_DIR = WORKFLOW_DIR / "templates"
TEMPLATE_FILES = ("IDEA.md", "PLAN.md", "PROGRESS.md", "REVIEW.md", "SUMMARY.md")
VALID_STATUSES = {"idea", "planned", "in_progress", "review", "done", "dropped"}
REQUIRED_FRONTMATTER_KEYS = ("id", "title", "slug", "status", "created_at", "updated_at")
PLAN_PHASE_FIELDS = (
    "Goal",
    "Scope",
    "Dependencies",
    "Parallelizable",
    "Success definition",
    "Notes",
)


def _today() -> str:
    return dt.date.today().isoformat()


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    if not value:
        raise ValueError("slug must not be empty")
    return value


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _parse_frontmatter(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = _read(path)
    if not text.startswith("---\n"):
        return {}
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return {}
    data: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def _has_nonempty_bullet(text: str, label: str) -> bool:
    pattern = rf"(?m)^- {re.escape(label)}:\s*(.+?)\s*$"
    match = re.search(pattern, text)
    return bool(match and match.group(1).strip())


def _has_header(text: str, header: str) -> bool:
    return re.search(rf"(?m)^#{{1,3}} {re.escape(header)}\s*$", text) is not None


def _extract_phase_blocks(plan_text: str) -> list[str]:
    matches = list(re.finditer(r"(?m)^## Phase .+$", plan_text))
    blocks: list[str] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(plan_text)
        blocks.append(plan_text[start:end])
    return blocks


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return True
    placeholders = {
        "none",
        "null",
        "tbd",
        "n/a",
        "what user value are we trying to create?",
        "what is painful, unclear, or missing today?",
        "state the original goal in one concise paragraph.",
        "summarize what was achieved.",
        "main behavior changes",
        "test coverage added or updated",
        "important design decisions",
        "none, or clearly scoped follow-up items",
    }
    return normalized in placeholders


def _validate_iso_date(value: str) -> bool:
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _render_template(name: str, slug: str, title: str, status: str) -> str:
    content = _read(TEMPLATES_DIR / name)
    today = _today()
    branch = f"codex/{slug}"
    return (
        content.replace("feature-example", f"feature-{slug}")
        .replace("Example Feature", title)
        .replace("example-feature", slug)
        .replace("2026-03-15", today)
        .replace("codex/example-feature", branch)
        .replace("status: idea", f"status: {status}", 1)
    )


def new_idea(args: argparse.Namespace) -> int:
    slug = _slugify(args.slug)
    title = args.title or slug.replace("-", " ").title()
    path = IDEAS_DIR / f"{_today()}-{slug}.md"
    if path.exists() and not args.force:
        print(f"idea file already exists: {path}")
        return 1
    content = _render_template("IDEA.md", slug, title, "idea")
    _write(path, content)
    print(path)
    return 0


def init_feature(args: argparse.Namespace) -> int:
    slug = _slugify(args.slug)
    title = args.title or slug.replace("-", " ").title()
    feature_dir = FEATURES_DIR / slug
    if feature_dir.exists() and not args.force:
        print(f"feature directory already exists: {feature_dir}")
        return 1
    feature_dir.mkdir(parents=True, exist_ok=True)
    status_by_file = {
        "IDEA.md": "idea",
        "PLAN.md": "planned",
        "PROGRESS.md": "in_progress",
        "REVIEW.md": "review",
        "SUMMARY.md": "done",
    }
    for name in TEMPLATE_FILES:
        _write(feature_dir / name, _render_template(name, slug, title, status_by_file[name]))
    print(feature_dir)
    return 0


def _feature_dir_from_slug(slug: str) -> Path:
    return FEATURES_DIR / _slugify(slug)


def status(args: argparse.Namespace) -> int:
    if not args.slug:
        feature_dirs = sorted(path for path in FEATURES_DIR.iterdir() if path.is_dir())
        for path in feature_dirs:
            meta = _parse_frontmatter(path / "IDEA.md")
            current = meta.get("status", "unknown")
            print(f"{path.name}: {current}")
        return 0

    feature_dir = _feature_dir_from_slug(args.slug)
    if not feature_dir.exists():
        print(f"feature not found: {feature_dir}")
        return 1

    idea = _parse_frontmatter(feature_dir / "IDEA.md")
    plan = _parse_frontmatter(feature_dir / "PLAN.md")
    progress_exists = (feature_dir / "PROGRESS.md").exists()
    review_exists = (feature_dir / "REVIEW.md").exists()
    summary_exists = (feature_dir / "SUMMARY.md").exists()

    print(f"feature: {feature_dir.name}")
    print(f"idea status: {idea.get('status', 'unknown')}")
    print(f"plan status: {plan.get('status', 'unknown')}")
    print(f"progress file: {'yes' if progress_exists else 'no'}")
    print(f"review file: {'yes' if review_exists else 'no'}")
    print(f"summary file: {'yes' if summary_exists else 'no'}")

    if summary_exists and idea.get("status") == "done":
        print("next: ship or archive this feature")
    elif review_exists:
        print("next: run review or apply review follow-up")
    elif progress_exists:
        print("next: execute next phase and record findings")
    else:
        print("next: complete plan scaffolding")
    return 0


def _check_feature(feature_dir: Path) -> list[str]:
    findings: list[str] = []
    file_paths = {name: feature_dir / name for name in TEMPLATE_FILES}

    for name, path in file_paths.items():
        if not path.exists():
            findings.append(f"missing file: {name}")

    metas = {name: _parse_frontmatter(path) for name, path in file_paths.items()}
    texts = {name: _read(path) if path.exists() else "" for name, path in file_paths.items()}

    idea_meta = metas["IDEA.md"]
    idea_text = texts["IDEA.md"]
    plan_text = texts["PLAN.md"]
    progress_text = texts["PROGRESS.md"]
    review_text = texts["REVIEW.md"]
    summary_text = texts["SUMMARY.md"]

    for name, meta in metas.items():
        for key in REQUIRED_FRONTMATTER_KEYS:
            if key not in meta:
                findings.append(f"{name} missing frontmatter key: {key}")
        status = meta.get("status")
        if status and status not in VALID_STATUSES:
            findings.append(f"{name} has invalid status: {status}")
        for date_key in ("created_at", "updated_at"):
            if date_key in meta and not _validate_iso_date(meta[date_key]):
                findings.append(f"{name} has invalid {date_key}: {meta[date_key]}")

    if idea_meta.get("slug") and idea_meta.get("slug") != feature_dir.name:
        findings.append("IDEA.md slug does not match feature directory name")

    consistency_keys = ("id", "title", "slug")
    baseline = {key: idea_meta.get(key, "") for key in consistency_keys}
    for name, meta in metas.items():
        for key in consistency_keys:
            if meta.get(key) and baseline.get(key) and meta[key] != baseline[key]:
                findings.append(f"{name} {key} does not match IDEA.md")

    if not _has_header(idea_text, "Goal"):
        findings.append("IDEA.md missing Goal section")
    if not _has_header(idea_text, "Code Context"):
        findings.append("IDEA.md missing Code Context section")
    if _looks_like_placeholder(re.search(r"(?s)# Goal\n\n(.+?)(?:\n# |\Z)", idea_text).group(1).strip()) if re.search(r"(?s)# Goal\n\n(.+?)(?:\n# |\Z)", idea_text) else True:
        findings.append("IDEA.md goal is still placeholder or empty")
    if "Question 1" in idea_text or "Question 2" in idea_text:
        findings.append("IDEA.md still contains template open questions")

    if not _has_header(plan_text, "Objective"):
        findings.append("PLAN.md missing Objective section")
    if not _has_header(plan_text, "Success Criteria"):
        findings.append("PLAN.md missing Success Criteria section")
    if not _has_header(plan_text, "Review Standard"):
        findings.append("PLAN.md missing Review Standard section")
    if not _has_header(plan_text, "Change Log"):
        findings.append("PLAN.md missing Change Log section")
    objective_match = re.search(r"(?s)# Objective\n\n(.+?)(?:\n# |\Z)", plan_text)
    if not objective_match or _looks_like_placeholder(objective_match.group(1)):
        findings.append("PLAN.md objective is still placeholder or empty")
    success_bullets = re.findall(r"(?m)^- .+\S$", plan_text.split("# Success Criteria", 1)[1].split("#", 1)[0]) if "# Success Criteria" in plan_text else []
    if len(success_bullets) < 2:
        findings.append("PLAN.md success criteria should contain at least two concrete bullets")

    phase_blocks = _extract_phase_blocks(plan_text)
    if not phase_blocks:
        findings.append("PLAN.md has no phase sections")
    for index, block in enumerate(phase_blocks, start=1):
        for field in PLAN_PHASE_FIELDS:
            if not _has_nonempty_bullet(block, field):
                findings.append(f"PLAN.md phase {index} is missing a non-empty '{field}' entry")

    if not _has_header(progress_text, "Current State"):
        findings.append("PROGRESS.md missing Current State section")
    if not _has_header(progress_text, "Phase Journal"):
        findings.append("PROGRESS.md missing Phase Journal section")
    for label in ("Active phase", "Last completed phase", "Next recommended action"):
        if not _has_nonempty_bullet(progress_text, label):
            findings.append(f"PROGRESS.md missing current state value for '{label}'")
    if "## Phase" not in progress_text:
        findings.append("PROGRESS.md has no phase journal entries")
    journal_blocks = _extract_phase_blocks(progress_text.replace("## Phase", "## Phase"))
    if not journal_blocks:
        journal_blocks = _extract_phase_blocks(progress_text)
    if not journal_blocks:
        journal_blocks = [block for block in re.split(r"(?m)^## Phase \d+\s*$", progress_text) if block.strip()][1:]
    phase_journal_matches = list(re.finditer(r"(?m)^## Phase \d+\s*$", progress_text))
    if not phase_journal_matches:
        findings.append("PROGRESS.md phase journal headings should use '## Phase N'")
    for index, match in enumerate(phase_journal_matches, start=1):
        start = match.start()
        end = phase_journal_matches[index].start() if index < len(phase_journal_matches) else len(progress_text)
        block = progress_text[start:end]
        for field in ("Started", "Completed", "Commit", "Tests", "Findings", "Plan updates"):
            if not _has_nonempty_bullet(block, field):
                findings.append(f"PROGRESS.md phase journal {index} is missing a value for '{field}'")

    if not _has_header(review_text, "Findings"):
        findings.append("REVIEW.md missing Findings section")
    if not _has_header(review_text, "Follow-up"):
        findings.append("REVIEW.md missing Follow-up section")
    for heading in ("Critical", "Major", "Minor"):
        if not _has_header(review_text, heading):
            findings.append(f"REVIEW.md missing {heading} subsection")
    for label in ("Additional phases needed", "Files to revisit", "Decision"):
        if not _has_nonempty_bullet(review_text, label):
            findings.append(f"REVIEW.md missing follow-up value for '{label}'")

    if not _has_header(summary_text, "Outcome"):
        findings.append("SUMMARY.md missing Outcome section")
    if not _has_header(summary_text, "Delivered"):
        findings.append("SUMMARY.md missing Delivered section")
    if not _has_header(summary_text, "Remaining Work"):
        findings.append("SUMMARY.md missing Remaining Work section")
    if not _has_header(summary_text, "Evidence"):
        findings.append("SUMMARY.md missing Evidence section")
    outcome_match = re.search(r"(?s)# Outcome\n\n(.+?)(?:\n# |\Z)", summary_text)
    if not outcome_match or _looks_like_placeholder(outcome_match.group(1)):
        findings.append("SUMMARY.md outcome is still placeholder or empty")
    delivered_bullets = re.findall(r"(?m)^- .+\S$", summary_text.split("# Delivered", 1)[1].split("#", 1)[0]) if "# Delivered" in summary_text else []
    if len(delivered_bullets) < 2:
        findings.append("SUMMARY.md delivered section should contain at least two concrete bullets")
    for label in ("Final relevant test command(s)", "Final review status", "Merge or PR status"):
        if not _has_nonempty_bullet(summary_text, label):
            findings.append(f"SUMMARY.md missing evidence value for '{label}'")

    if idea_meta.get("status") == "done" and not _has_nonempty_bullet(summary_text, "Final review status"):
        findings.append("done feature is missing final review evidence in SUMMARY.md")

    return findings


def doctor(args: argparse.Namespace) -> int:
    if args.slug:
        feature_dirs = [_feature_dir_from_slug(args.slug)]
    else:
        feature_dirs = sorted(path for path in FEATURES_DIR.iterdir() if path.is_dir())

    has_error = False
    for feature_dir in feature_dirs:
        if not feature_dir.exists():
            print(f"feature not found: {feature_dir}")
            has_error = True
            continue
        findings = _check_feature(feature_dir)
        if findings:
            has_error = True
            print(f"[FAIL] {feature_dir.name}")
            for finding in findings:
                print(f"  - {finding}")
        else:
            print(f"[OK] {feature_dir.name}")
    return 1 if has_error else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lightweight flow-* workflow helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_idea_parser = subparsers.add_parser("new-idea", help="Create an idea markdown file")
    new_idea_parser.add_argument("--slug", required=True)
    new_idea_parser.add_argument("--title")
    new_idea_parser.add_argument("--force", action="store_true")
    new_idea_parser.set_defaults(func=new_idea)

    init_feature_parser = subparsers.add_parser("init-feature", help="Create a feature workflow scaffold")
    init_feature_parser.add_argument("--slug", required=True)
    init_feature_parser.add_argument("--title")
    init_feature_parser.add_argument("--force", action="store_true")
    init_feature_parser.set_defaults(func=init_feature)

    status_parser = subparsers.add_parser("status", help="Show feature workflow status")
    status_parser.add_argument("--slug")
    status_parser.set_defaults(func=status)

    doctor_parser = subparsers.add_parser("doctor", help="Detect workflow gaps")
    doctor_parser.add_argument("--slug")
    doctor_parser.set_defaults(func=doctor)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
