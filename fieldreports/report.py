"""One HTML report per project per shift date, built only from submissions that passed validation."""
from __future__ import annotations

import hashlib
import html
from collections import defaultdict
from pathlib import Path

from .validate import Checked

STYLE = """body{font:14px/1.45 system-ui,sans-serif;color:#1d1d1b;max-width:960px;margin:24px auto;padding:0 16px}
h1{font-size:20px;margin:0 0 4px}p.meta{color:#5a5955;margin:0 0 16px}table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #e3e2de;vertical-align:top}th{font-weight:600}
.warn{color:#8a4b00}footer{margin-top:20px;color:#5a5955;font-size:12px}"""


def group(checked: list[Checked]) -> dict[tuple[str, str], list[Checked]]:
    groups: dict[tuple[str, str], list[Checked]] = defaultdict(list)
    for c in checked:
        if c.ok:
            groups[(c.submission["project"], c.submission["shift_date"])].append(c)
    return dict(groups)


def fingerprint(items: list[Checked]) -> str:
    """Changes when any submission in the group is added or changed, so a late entry produces a revision."""
    h = hashlib.sha256()
    for c in sorted(items, key=lambda c: c.submission["id"]):
        h.update(repr(sorted(c.submission.items())).encode())
    return h.hexdigest()[:12]


def render(project: dict, shift_date: str, items: list[Checked], revision: int, run_id: str) -> str:
    e = html.escape
    rows = []
    for c in sorted(items, key=lambda c: (c.submission.get("shift", ""), c.submission["technician"])):
        s = c.submission
        notes = "".join(f'<div class="warn">Note: {e(w)}</div>' for w in c.warnings)
        rows.append(f"<tr><td>{e(s.get('shift', ''))}</td><td>{e(s['technician'])}</td><td>{e(str(s['hours']))}</td>"
                    f"<td>{e(s.get('equipment', ''))}</td><td>{e(s['work_done'])}{notes}</td>"
                    f"<td>{e(s.get('issues', ''))}</td></tr>")
    hours = sum(float(c.submission["hours"]) for c in items)
    title = f"{project['site']} - {shift_date}"
    rev = f" (revision {revision})" if revision > 1 else ""
    return (f"<!doctype html><meta charset=utf-8><title>{e(title)}</title><style>{STYLE}</style>"
            f"<h1>{e(title)}{rev}</h1><p class=meta>{e(project['customer'])} · project {e(project['project'])} · "
            f"{len(items)} entries · {hours:g} hours</p><table><tr><th>Shift</th><th>Technician</th><th>Hours</th>"
            f"<th>Equipment</th><th>Work done</th><th>Open issues</th></tr>{''.join(rows)}</table>"
            f"<footer>Built by run {e(run_id)} from submissions {e(', '.join(sorted(c.submission['id'] for c in items)))}."
            f"</footer>")


def write(out: Path, project_id: str, shift_date: str, revision: int, page: str) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{project_id}_{shift_date}_rev{revision}.html"
    path.write_text(page, encoding="utf-8")
    return path
