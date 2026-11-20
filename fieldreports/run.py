"""One pipeline run: validate, build the reports that changed, record everything in the run log.

  python -m fieldreports.run --input data/submissions.json --out out [--today 2026-11-18] [--dry-run]

Safe to run again: a report is rebuilt only when its submissions changed (a late entry gives revision 2), and the
run log (out/runlog.jsonl, append-only) says what each run did. Exit code 0 = clean, 2 = finished with exceptions
for a person, 1 = could not run.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from .report import fingerprint, group, render, write
from .validate import check, load_reference

ROOT = Path(__file__).resolve().parents[1]


def last_fingerprints(runlog: Path) -> dict[str, dict]:
    """The latest report state per project/date from earlier runs."""
    state: dict[str, dict] = {}
    if runlog.exists():
        for line in runlog.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            for r in entry.get("reports", []):
                state[r["key"]] = r
    return state


def run(submissions: list[dict], reference: Path, out: Path, today: date, dry_run: bool = False) -> dict:
    projects, assignments = load_reference(reference)
    checked = check(submissions, projects, assignments, today)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    runlog = out / "runlog.jsonl"
    before = last_fingerprints(runlog)
    reports = []
    for (project_id, shift_date), items in sorted(group(checked).items()):
        key, fp = f"{project_id}/{shift_date}", fingerprint(items)
        previous = before.get(key)
        if previous and previous["fingerprint"] == fp:
            continue  # nothing new for this report
        revision = previous["revision"] + 1 if previous else 1
        path = None
        if not dry_run:
            path = write(out, project_id, shift_date, revision,
                         render(projects[project_id], shift_date, items, revision, run_id))
        reports.append({"key": key, "fingerprint": fp, "revision": revision,
                        "submissions": sorted(c.submission["id"] for c in items), "file": path and path.name})
    exceptions = [{"id": c.submission.get("id"), "errors": c.errors} for c in checked if not c.ok]
    warnings = [{"id": c.submission.get("id"), "warnings": c.warnings} for c in checked if c.ok and c.warnings]
    entry = {"run_id": run_id, "dry_run": dry_run, "received": len(submissions),
             "accepted": sum(c.ok for c in checked), "reports": reports, "exceptions": exceptions,
             "warnings": warnings}
    if not dry_run:
        out.mkdir(parents=True, exist_ok=True)
        with open(runlog, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    return entry


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=ROOT / "data" / "submissions.json")
    ap.add_argument("--reference", type=Path, default=ROOT / "data", help="folder with projects.csv, assignments.csv")
    ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--today", type=date.fromisoformat, default=date.today())
    ap.add_argument("--dry-run", action="store_true", help="validate and plan, write nothing")
    args = ap.parse_args(argv)
    try:
        submissions = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"Could not read {args.input}: {e}", file=sys.stderr)
        return 1
    entry = run(submissions, args.reference, args.out, args.today, args.dry_run)
    print(f"Run {entry['run_id']}: {entry['received']} received, {entry['accepted']} accepted, "
          f"{len(entry['reports'])} report(s) {'planned' if args.dry_run else 'written'}.")
    for r in entry["reports"]:
        print(f"  {r['key']} rev {r['revision']}: {', '.join(r['submissions'])}")
    for x in entry["exceptions"]:
        print(f"  EXCEPTION {x['id']}: {'; '.join(x['errors'])}")
    for w in entry["warnings"]:
        print(f"  warning {w['id']}: {'; '.join(w['warnings'])}")
    return 2 if entry["exceptions"] else 0


if __name__ == "__main__":
    sys.exit(main())
