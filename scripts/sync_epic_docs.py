#!/usr/bin/env python3
"""
Keep sprint tracking aligned with planning docs.

  python scripts/sync_epic_docs.py pre-commit   # generate + check + git add docs (used by pre-commit; you should not need to run this by hand)
  python scripts/sync_epic_docs.py ci-verify    # generate, fail if docs differ from repo, then check (used by CI)
  python scripts/sync_epic_docs.py check        # sprint-status vs epics.md only
  python scripts/sync_epic_docs.py generate     # refresh auto block + header date (for debugging)

epics.md only lists epics 9–14 in this repo; epics 1–8 are validated in sprint only.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPRINT = ROOT / ".bmad-outputs/implementation-artifacts/sprint-status.yaml"
EPICS_MD = ROOT / ".bmad-outputs/planning-artifacts/epics.md"
DOCS_VIEW = ROOT / "docs/epics-and-stories.md"

MARK_BEGIN = "<!-- sync-epic-docs:begin -->"
MARK_END = "<!-- sync-epic-docs:end -->"

STATUS_FR = {
    "done": "terminé",
    "backlog": "backlog",
    "in-progress": "en cours",
    "ready-for-dev": "prêt pour dev",
    "review": "revue",
    "optional": "optionnel",
}


def parse_sprint_status(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_section = False
    out: dict[str, str] = {}
    for line in lines:
        if line.strip() == "development_status:":
            in_section = True
            continue
        if not in_section:
            continue
        if not line.startswith("  ") or line.startswith("  #"):
            continue
        m = re.match(r"^  ([a-zA-Z0-9_-]+):\s*(.+)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def sprint_meta_last_updated(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("last_updated:"):
            return line.split(":", 1)[1].strip()
    return None


def parse_epics_md_plan(path: Path) -> tuple[set[str], set[tuple[int, int]]]:
    """Epic numbers and (epic, story) pairs from ### Epic / #### Story headings."""
    text = path.read_text(encoding="utf-8")
    epics = set(re.findall(r"^### Epic (\d+):", text, re.MULTILINE))
    stories = re.findall(r"^#### Story (\d+)\.(\d+):", text, re.MULTILINE)
    pairs = {(int(a), int(b)) for a, b in stories}
    return epics, pairs


def sprint_story_keys(status: dict[str, str]) -> dict[int, list[tuple[str, str]]]:
    """epic_num -> [(full_key, status), ...] for keys like 13-1-foo."""
    by_epic: dict[int, list[tuple[str, str]]] = {}
    for key, st in status.items():
        m = re.match(r"^(\d+)-(\d+)-", key)
        if not m:
            continue
        e, s = int(m.group(1)), int(m.group(2))
        by_epic.setdefault(e, []).append((key, st))
    for e in by_epic:
        by_epic[e].sort(key=lambda x: x[0])
    return by_epic


def epic_keys_status(status: dict[str, str]) -> dict[int, str]:
    out: dict[int, str] = {}
    for key, st in status.items():
        m = re.match(r"^epic-(\d+)$", key)
        if m:
            out[int(m.group(1))] = st
    return out


def retro_keys_status(status: dict[str, str]) -> dict[int, str]:
    out: dict[int, str] = {}
    for key, st in status.items():
        m = re.match(r"^epic-(\d+)-retrospective$", key)
        if m:
            out[int(m.group(1))] = st
    return out


def check() -> list[str]:
    errors: list[str] = []
    status = parse_sprint_status(SPRINT)
    epics_in_md, stories_in_md = parse_epics_md_plan(EPICS_MD)
    stories_by_epic = sprint_story_keys(status)

    for n_str in sorted(epics_in_md, key=int):
        n = int(n_str)
        ek = f"epic-{n}"
        if ek not in status:
            errors.append(f"epics.md has ### Epic {n}: but sprint-status missing key {ek}")

    for n_str in sorted(epics_in_md, key=int):
        n = int(n_str)
        for key, _st in stories_by_epic.get(n, []):
            parts = key.split("-")
            if len(parts) >= 2 and parts[1].isdigit():
                sn = int(parts[1])
                if (n, sn) not in stories_in_md:
                    errors.append(
                        f"sprint has {key} but epics.md has no #### Story {n}.{sn}: (Epic {n} is in epics.md)"
                    )

    for n_str in sorted(epics_in_md, key=int):
        n = int(n_str)
        for a, b in sorted((s for s in stories_in_md if s[0] == n), key=lambda x: (x[0], x[1])):
            expected_prefix = f"{n}-{b}-"
            if not any(k.startswith(expected_prefix) for k, _ in stories_by_epic.get(n, [])):
                errors.append(
                    f"epics.md has #### Story {a}.{b}: but sprint-status has no story key starting with {expected_prefix!r}"
                )

    # Retrospective keys: if epic in epics.md, expect epic-N-retrospective in sprint (already true if we sync)
    for n_str in sorted(epics_in_md, key=int):
        n = int(n_str)
        rk = f"epic-{n}-retrospective"
        if rk not in status:
            errors.append(f"epics.md lists Epic {n}; sprint-status should include {rk} (optional/done)")

    return errors


def build_table(status: dict[str, str]) -> str:
    epic_st = epic_keys_status(status)
    retro_st = retro_keys_status(status)
    stories_by_epic = sprint_story_keys(status)
    lines = [
        "",
        "### État des épiques et stories (généré automatiquement)",
        "",
        "Source : `.bmad-outputs/implementation-artifacts/sprint-status.yaml`.",
        "Mis à jour automatiquement au commit (hook Git `scripts/git-hooks/` ou outil pre-commit) ; la CI échoue si ce bloc est obsolète.",
        "",
        "| Épique | Statut | Rétro | Stories |",
        "|--------|--------|-------|---------|",
    ]
    for n in sorted(epic_st.keys()):
        es = epic_st[n]
        rs = retro_st.get(n, "—")
        rs_fr = STATUS_FR.get(rs, rs)
        es_fr = STATUS_FR.get(es, es)
        sk = stories_by_epic.get(n, [])
        if sk:
            parts = [f"`{k}` {STATUS_FR.get(s, s)}" for k, s in sk]
            scell = "<br>".join(parts)
        else:
            scell = "—"
        lines.append(f"| {n} | {es_fr} | {rs_fr} | {scell} |")
    lines.append("")
    return "\n".join(lines)


def generate() -> None:
    status = parse_sprint_status(SPRINT)
    block = MARK_BEGIN + "\n" + build_table(status) + MARK_END + "\n"
    text = DOCS_VIEW.read_text(encoding="utf-8")
    lu = sprint_meta_last_updated(SPRINT)
    if lu:
        text = re.sub(
            r"^(\*\*Dernière mise à jour :\*\*)\s+.*$",
            rf"\1 {lu}",
            text,
            count=1,
            flags=re.MULTILINE,
        )

    if MARK_BEGIN in text and MARK_END in text:
        pattern = re.compile(
            re.escape(MARK_BEGIN) + r".*?" + re.escape(MARK_END),
            re.DOTALL,
        )
        text = pattern.sub(block.strip(), text)
    else:
        if not text.endswith("\n"):
            text += "\n"
        text = text.rstrip() + "\n\n---\n\n" + block

    DOCS_VIEW.write_text(text, encoding="utf-8")
    print(f"Updated {DOCS_VIEW.relative_to(ROOT)}")


def _run_check_or_exit() -> None:
    errs = check()
    if errs:
        print("sync_epic_docs check failed:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)


def pre_commit() -> None:
    """Regenerate docs view, validate, stage for the current commit."""
    generate()
    _run_check_or_exit()
    r = subprocess.run(
        ["git", "add", "docs/epics-and-stories.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(
            "sync_epic_docs: git add failed (is this a git work tree?):",
            r.stderr or r.stdout,
            file=sys.stderr,
        )
        sys.exit(r.returncode)


def ci_verify() -> None:
    """CI: regenerated doc must match committed file; then structural check."""
    generate()
    r = subprocess.run(
        ["git", "diff", "--exit-code", "--", "docs/epics-and-stories.md"],
        cwd=ROOT,
    )
    if r.returncode != 0:
        print(
            "docs/epics-and-stories.md is out of sync with sprint-status.yaml.",
            "Run `pre-commit run --all-files` locally or commit after the hook updates the doc.",
            file=sys.stderr,
            sep="\n",
        )
        sys.exit(1)
    _run_check_or_exit()
    print("sync_epic_docs ci-verify OK")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "command",
        choices=("check", "generate", "pre-commit", "ci-verify"),
        nargs="?",
        default="check",
    )
    args = p.parse_args()

    if args.command == "generate":
        generate()
        return
    if args.command == "pre-commit":
        pre_commit()
        return
    if args.command == "ci-verify":
        ci_verify()
        return

    _run_check_or_exit()
    print("sync_epic_docs check OK (sprint-status vs epics.md for epics present in epics.md)")


if __name__ == "__main__":
    main()
