"""The pipeline: a single CSV you can also open in Excel (close it before running commands)."""
import csv
import re
import shutil
import uuid
from datetime import datetime

from .config import AUDIENCES, DATA

PIPELINE = DATA / "pipeline.csv"
FIELDS = [
    "id", "name", "email", "organisation", "role", "audience", "website", "source", "notes",
    "status", "research", "subject", "body", "lint", "draft_id", "thread_id", "queued_at",
    "last_contact", "followups_sent", "followup_draft_id", "added_at", "history",
]
# new -> researched / weak_fit -> drafted -> queued (Gmail draft) -> sent -> replied / booked / declined
# plus: excluded, opted_out
FINAL = {"replied", "booked", "declined", "opted_out", "excluded"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def now():
    return datetime.now().isoformat(timespec="seconds")


def load():
    if not PIPELINE.exists():
        return []
    with open(PIPELINE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in FIELDS:
            r.setdefault(k, "")
            if r[k] is None:
                r[k] = ""
    return rows


def save(rows):
    DATA.mkdir(exist_ok=True)
    if PIPELINE.exists():
        shutil.copy(PIPELINE, PIPELINE.with_suffix(".csv.bak"))
    tmp = PIPELINE.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(PIPELINE)


def log(row, event):
    entries = [e for e in (row.get("history") or "").split(" | ") if e.strip()]
    entries.append(f"{now()} {event}")
    row["history"] = " | ".join(entries)


def find(rows, key):
    key = key.strip().lower()
    return next((r for r in rows if r["id"] == key or r["email"].lower() == key), None)


def import_targets(csv_path):
    rows = load()
    known = {r["email"].lower(): r for r in rows}
    added, problems = 0, []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for i, t in enumerate(csv.DictReader(f), start=2):
            t = {k.strip().lower(): (v or "").strip() for k, v in t.items() if k}
            email = t.get("email", "").lower()
            if not EMAIL_RE.match(email):
                problems.append(f"line {i}: invalid or missing email")
                continue
            if email in known:
                if known[email]["status"] in ("opted_out", "excluded"):
                    problems.append(f"line {i}: {email} has opted out or been excluded, not re-added")
                else:
                    problems.append(f"line {i}: {email} already in pipeline (skipped)")
                continue
            if t.get("audience") not in AUDIENCES:
                problems.append(f"line {i}: audience '{t.get('audience')}' not in config/audiences.yaml")
                continue
            if not t.get("source"):
                problems.append(f"line {i}: no 'source' recorded (needed for GDPR records)")
                continue
            row = {k: "" for k in FIELDS}
            row.update({k: t.get(k, "") for k in
                        ["name", "organisation", "role", "audience", "website", "source", "notes"]})
            row.update(id=uuid.uuid4().hex[:8], email=email, status="new",
                       followups_sent="0", added_at=now())
            log(row, "imported")
            rows.append(row)
            known[email] = row
            added += 1
    save(rows)
    return added, problems
