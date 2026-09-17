from pr_agent import tracker

from .conftest import write_csv

GOOD = "Jane Example,jane@example.com,Example FM,Host,podcasts,https://example.com,Contact page,notes"


def test_imports_a_valid_row(pipeline):
    added, problems = tracker.import_targets(write_csv(pipeline / "t.csv", GOOD))
    assert (added, problems) == (1, [])
    row = tracker.load()[0]
    assert row["email"] == "jane@example.com"
    assert row["status"] == "new"
    assert row["followups_sent"] == "0"
    assert row["id"]


def test_rejects_bad_rows_and_explains_why(pipeline):
    added, problems = tracker.import_targets(write_csv(
        pipeline / "t.csv",
        "No Email,nope,Org,Editor,journalists,,Contact page,",
        "No Source,ns@example.com,Org,Editor,journalists,,,",
        "Bad Audience,ba@example.com,Org,Editor,not_an_audience,,Contact page,",
    ))
    assert added == 0
    assert "invalid or missing email" in problems[0]
    assert "source" in problems[1]
    assert "not in config/audiences.yaml" in problems[2]


def test_duplicate_email_is_skipped(pipeline):
    csv_path = write_csv(pipeline / "t.csv", GOOD)
    tracker.import_targets(csv_path)
    added, problems = tracker.import_targets(csv_path)
    assert added == 0
    assert "already in pipeline" in problems[0]
    assert len(tracker.load()) == 1


def test_opted_out_contact_is_never_re_added(pipeline):
    csv_path = write_csv(pipeline / "t.csv", GOOD)
    tracker.import_targets(csv_path)
    rows = tracker.load()
    rows[0]["status"] = "opted_out"
    tracker.save(rows)

    added, problems = tracker.import_targets(csv_path)
    assert added == 0
    assert "opted out" in problems[0]
    assert tracker.load()[0]["status"] == "opted_out"


def test_history_entries_stay_separated(pipeline):
    row = {"history": ""}
    tracker.log(row, "imported")
    tracker.log(row, "researched")
    assert row["history"].count(" | ") == 1
    first, second = row["history"].split(" | ")
    assert first.endswith("imported") and second.endswith("researched")


def test_save_keeps_a_backup_of_the_previous_pipeline(pipeline):
    tracker.import_targets(write_csv(pipeline / "t.csv", GOOD))
    rows = tracker.load()
    rows[0]["status"] = "booked"
    tracker.save(rows)
    assert (pipeline / "pipeline.csv.bak").exists()
    assert "new" in (pipeline / "pipeline.csv.bak").read_text()
    assert tracker.load()[0]["status"] == "booked"


def test_find_matches_id_or_email(pipeline):
    tracker.import_targets(write_csv(pipeline / "t.csv", GOOD))
    rows = tracker.load()
    assert tracker.find(rows, "JANE@example.com") is rows[0]
    assert tracker.find(rows, rows[0]["id"]) is rows[0]
    assert tracker.find(rows, "nobody@example.com") is None
