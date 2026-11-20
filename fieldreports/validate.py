"""Checks every submission before it can reach a report.

Errors stop a submission (it goes to the exceptions list for a person). Warnings let it through but are printed in
the report and the run log, so nothing is fixed silently.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

REQUIRED = ("id", "submitted_at", "project", "technician", "shift_date", "hours", "work_done")
LATE_AFTER = timedelta(hours=24)  # after the end of the shift date
ASSIGNMENT_SLACK = timedelta(days=3)  # crews often start a day or two before the paperwork does
MAX_HOURS = 16


@dataclass
class Checked:
    submission: dict
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def load_reference(folder: str | Path) -> tuple[dict, list[dict]]:
    folder = Path(folder)
    with open(folder / "projects.csv", newline="", encoding="utf-8") as f:
        projects = {r["project"]: r for r in csv.DictReader(f)}
    with open(folder / "assignments.csv", newline="", encoding="utf-8") as f:
        assignments = list(csv.DictReader(f))
    return projects, assignments


def assigned(technician: str, project: str, day: date, assignments: list[dict]) -> bool:
    for a in assignments:
        if a["technician"] == technician and a["project"] == project:
            start, end = date.fromisoformat(a["start"]), date.fromisoformat(a["end"])
            if start - ASSIGNMENT_SLACK <= day <= end + ASSIGNMENT_SLACK:
                return True
    return False


def check(submissions: list[dict], projects: dict, assignments: list[dict], today: date) -> list[Checked]:
    out, seen = [], {}
    for s in submissions:
        c = Checked(s)
        missing = [k for k in REQUIRED if not str(s.get(k, "")).strip()]
        if missing:
            c.errors.append(f"missing {', '.join(missing)}")
        if s.get("id") in seen:
            # Same ID twice: a double tap on Submit. Keep the first, drop the rest.
            c.errors.append(f"duplicate of an earlier submission {s['id']}")
        seen.setdefault(s.get("id"), True)
        if s.get("project") and s["project"] not in projects:
            c.errors.append(f"project {s['project']} is not in the project list")
        try:
            day = date.fromisoformat(s.get("shift_date", ""))
            if day > today:
                c.errors.append(f"shift date {day} is in the future")
            elif s.get("project") in projects and s.get("technician") and \
                    not assigned(s["technician"], s["project"], day, assignments):
                c.warnings.append(f"{s['technician']} is not assigned to {s['project']} on {day}")
            submitted = datetime.fromisoformat(s.get("submitted_at", ""))
            if submitted > datetime.combine(day + timedelta(days=1), datetime.min.time()) + LATE_AFTER:
                c.warnings.append(f"late: submitted {submitted:%Y-%m-%d %H:%M} for {day}")
        except ValueError:
            c.errors.append("shift_date or submitted_at is not a date")
        try:
            if not 0 < float(s.get("hours", 0)) <= MAX_HOURS:
                c.warnings.append(f"hours {s.get('hours')} outside 0 to {MAX_HOURS}")
        except (TypeError, ValueError):
            c.errors.append(f"hours '{s.get('hours')}' is not a number")
        out.append(c)
    return out
