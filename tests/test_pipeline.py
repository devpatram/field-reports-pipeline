import json
from datetime import date
from pathlib import Path

from fieldreports.report import fingerprint, group
from fieldreports.run import main, run
from fieldreports.validate import check, load_reference

ROOT = Path(__file__).resolve().parents[1]
SUBMISSIONS = json.loads((ROOT / "data" / "submissions.json").read_text())
PROJECTS, ASSIGNMENTS = load_reference(ROOT / "data")


def by_id(checked):
    return {c.submission["id"]: c for c in reversed(checked)}  # first occurrence wins


def test_errors_stop_a_submission_and_warnings_do_not():
    checked = check(SUBMISSIONS, PROJECTS, ASSIGNMENTS, date(2026, 11, 18))
    c = by_id(checked)
    assert c["S-1001"].ok and not c["S-1001"].warnings
    assert c["S-1004"].errors == ["project 700999 is not in the project list"]
    assert c["S-1008"].errors == ["missing work_done"]
    assert c["S-1007"].ok and "not assigned" in c["S-1007"].warnings[0]
    assert c["S-1006"].ok and c["S-1006"].warnings[0].startswith("late")
    assert checked[-1].errors == ["duplicate of an earlier submission S-1002"]


def test_future_dates_and_bad_hours():
    s = dict(SUBMISSIONS[0], id="X", shift_date="2026-12-01", hours="ten")
    errors = check([s], PROJECTS, ASSIGNMENTS, date(2026, 11, 18))[0].errors
    assert "shift date 2026-12-01 is in the future" in errors and "hours 'ten' is not a number" in errors


def test_one_group_per_project_and_date_from_valid_submissions_only():
    groups = group(check(SUBMISSIONS, PROJECTS, ASSIGNMENTS, date(2026, 11, 18)))
    assert sorted(groups) == [("700101", "2026-11-16"), ("700205", "2026-11-16"), ("700311", "2026-11-16")]
    assert sorted(c.submission["id"] for c in groups[("700101", "2026-11-16")]) == ["S-1001", "S-1002", "S-1006"]


def test_rerun_is_idempotent_and_a_late_entry_makes_a_revision(tmp_path):
    early = [s for s in SUBMISSIONS if s["id"] != "S-1006"]
    first = run(early, ROOT / "data", tmp_path, date(2026, 11, 17))
    assert [r["revision"] for r in first["reports"]] == [1, 1, 1]
    again = run(early, ROOT / "data", tmp_path, date(2026, 11, 17))
    assert again["reports"] == []  # nothing changed, nothing rebuilt
    late = run(SUBMISSIONS, ROOT / "data", tmp_path, date(2026, 11, 18))
    assert [(r["key"], r["revision"]) for r in late["reports"]] == [("700101/2026-11-16", 2)]
    assert (tmp_path / "700101_2026-11-16_rev2.html").exists()
    assert len((tmp_path / "runlog.jsonl").read_text().splitlines()) == 3


def test_dry_run_writes_nothing(tmp_path):
    entry = run(SUBMISSIONS, ROOT / "data", tmp_path, date(2026, 11, 18), dry_run=True)
    assert entry["reports"] and list(tmp_path.iterdir()) == []


def test_report_escapes_text_and_lists_its_sources(tmp_path):
    s = dict(SUBMISSIONS[0], id="S-9", work_done="<script>alert(1)</script> replaced belt")
    run([s], ROOT / "data", tmp_path, date(2026, 11, 18))
    page = next(tmp_path.glob("*.html")).read_text()
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "from submissions S-9" in page


def test_fingerprint_changes_when_a_submission_changes():
    checked = check(SUBMISSIONS[:2], PROJECTS, ASSIGNMENTS, date(2026, 11, 18))
    edited = check([SUBMISSIONS[0], dict(SUBMISSIONS[1], hours=11)], PROJECTS, ASSIGNMENTS, date(2026, 11, 18))
    assert fingerprint(checked) != fingerprint(edited)


def test_exit_codes(tmp_path):
    assert main(["--out", str(tmp_path), "--today", "2026-11-18"]) == 2  # exceptions for a person
    clean = tmp_path / "clean.json"
    clean.write_text(json.dumps(SUBMISSIONS[:2]))
    assert main(["--input", str(clean), "--out", str(tmp_path / "c"), "--today", "2026-11-18"]) == 0
    assert main(["--input", str(tmp_path / "missing.json"), "--out", str(tmp_path)]) == 1
