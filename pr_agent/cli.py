import argparse
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from collections import Counter
from datetime import date, datetime

from .config import AUDIENCES, SETTINGS
from . import knowledge, pitch, tracker

RULE = "-" * 72


# ---------- helpers ----------

def _gmail():
    from . import gmail_client  # imported lazily so research/draft work without Google set up
    return gmail_client


def _edit_in_editor(subject, body):
    editor = os.environ.get("EDITOR") or ("notepad" if sys.platform.startswith("win") else "nano")
    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(f"Subject: {subject}\n\n{body}\n")
        path = f.name
    subprocess.call([editor, path])
    text = open(path, encoding="utf-8").read()
    os.unlink(path)
    first, _, rest = text.partition("\n")
    if first.lower().startswith("subject:"):
        return first[8:].strip(), rest.strip()
    return subject, text.strip()


def _days_since(iso):
    if not iso:
        return 0
    return (datetime.now() - datetime.fromisoformat(iso)).days


def _show(row, subject, body, issues):
    research = {}
    try:
        research = json.loads(row["research"] or "{}")
    except json.JSONDecodeError:
        pass
    print("\n" + RULE)
    print(f"{row['name']}  <{row['email']}>")
    print(f"{row['role']}, {row['organisation']}  |  {AUDIENCES[row['audience']]['label']}")
    if research:
        print(f"Fit: {research.get('fit', '?')}  ({research.get('fit_reason', '')})")
        if research.get("hook"):
            print(f"Hook: {research['hook']}")
        if research.get("contact_check"):
            print(f"CONTACT CHECK: {research['contact_check']}")
        for src in research.get("sources", [])[:4]:
            print(f"  source: {src}")
    print(RULE)
    print(f"Subject: {subject}\n")
    print(body + pitch.footer())
    print(RULE)
    if issues:
        print("Voice check: " + "; ".join(issues))
    else:
        print("Voice check: clean")
    print(f"Words in body: {len(body.split())}")


# ---------- commands ----------

def cmd_import(args):
    added, problems = tracker.import_targets(args.csv)
    print(f"Added {added} target(s).")
    for p in problems:
        print("  " + p)


def cmd_research(args):
    from . import research
    rows = tracker.load()
    todo = [r for r in rows if r["status"] == "new"][: args.limit]
    if not todo:
        print("Nothing to research. Import targets first.")
        return
    facts = knowledge.facts()
    for r in todo:
        print(f"Researching {r['name']} ({r['organisation']})...", flush=True)
        try:
            notes = research.research(r, facts)
        except Exception as e:  # keep going on individual failures
            print(f"  failed: {e}")
            continue
        r["research"] = json.dumps(notes, ensure_ascii=False)
        fit = notes.get("fit", "possible")
        r["status"] = "weak_fit" if fit == "weak" else "researched"
        tracker.log(r, f"researched (fit: {fit})")
        tracker.save(rows)
        print(f"  fit: {fit}. {notes.get('fit_reason', '')}")


def cmd_draft(args):
    rows = tracker.load()
    statuses = {"researched", "weak_fit"} if args.include_weak else {"researched"}
    todo = [r for r in rows if r["status"] in statuses][: args.limit]
    if not todo:
        print("Nothing to draft. Run 'research' first.")
        return
    for r in todo:
        print(f"Drafting for {r['name']}...", flush=True)
        try:
            r["subject"], r["body"], r["lint"] = pitch.draft_with_check(r)
        except Exception as e:
            print(f"  failed: {e}")
            continue
        r["status"] = "drafted"
        tracker.log(r, "pitch drafted")
        tracker.save(rows)
        issues = json.loads(r["lint"])
        print("  ready for review" + (f" (voice check: {'; '.join(issues)})" if issues else ""))


def _review_loop(row, subject, body, max_words, regenerate, check_subject=True):
    """Shared approve/edit/rewrite loop. Returns (action, subject, body)."""
    while True:
        issues = pitch.lint(subject, body, max_words, check_subject=check_subject)
        _show(row, subject, body, issues)
        choice = input("[a]pprove to Gmail drafts  [e]dit  [r]ewrite with a note  [s]kip  [x] exclude  [q]uit > ").strip().lower()
        if choice == "a":
            if issues and input("Voice check found problems. Approve anyway? [y/N] ").strip().lower() != "y":
                continue
            return "approve", subject, body
        if choice == "e":
            subject, body = _edit_in_editor(subject, body)
        elif choice == "r":
            note = input("What should change? > ").strip()
            if note:
                print("Rewriting...", flush=True)
                subject, body = regenerate(subject, body, note)
        elif choice in ("s", "x", "q"):
            return {"s": "skip", "x": "exclude", "q": "quit"}[choice], subject, body


def cmd_review(args):
    gm = _gmail()
    rows = tracker.load()
    todo = [r for r in rows if r["status"] == "drafted"]
    if not todo:
        print("Nothing to review. Run 'draft' first.")
        return
    cap = SETTINGS.get("max_new_pitches_per_day", 15)
    today = date.today().isoformat()
    queued_today = sum(1 for r in rows if r["queued_at"].startswith(today))
    svc = gm.service()
    sender = SETTINGS.get("from_address") or None

    for r in todo:
        if queued_today >= cap:
            print(f"\nDaily limit of {cap} new pitches reached. The rest will wait until tomorrow.")
            break

        def regenerate(subject, body, note, r=r):
            r["subject"], r["body"] = subject, body
            return pitch.write_pitch(r, feedback=note)

        action, subject, body = _review_loop(r, r["subject"], r["body"],
                                             SETTINGS.get("max_words", 170), regenerate)
        r["subject"], r["body"] = subject, body
        if action == "approve":
            draft_id, thread_id = gm.create_draft(svc, r["email"], subject, body + pitch.footer(), sender)
            r.update(draft_id=draft_id, thread_id=thread_id, status="queued", queued_at=tracker.now())
            tracker.log(r, "approved, saved to Gmail drafts")
            queued_today += 1
            print("Saved to Gmail drafts. Open Gmail, give it a last read, and press send.")
        elif action == "exclude":
            r["status"] = "excluded"
            tracker.log(r, "excluded at review")
        tracker.save(rows)
        if action == "quit":
            break


def _sync(gm, svc, rows):
    me = gm.my_address(svc)
    changes = 0
    for r in rows:
        if not r["thread_id"] or r["status"] not in ("queued", "sent"):
            continue
        st = gm.thread_state(svc, r["thread_id"], me)
        if st is None:
            continue
        if st["replied"]:
            r["status"] = "replied"
            tracker.log(r, "reply detected")
            print(f"Reply detected: {r['name']} ({r['organisation']}). Read it and update with 'mark'.")
            changes += 1
        elif st["sent"]:
            if r["status"] == "queued":
                r["status"] = "sent"
                tracker.log(r, "sent")
                changes += 1
            if st["last_sent"] and st["last_sent"] != r["last_contact"]:
                r["last_contact"] = st["last_sent"]
        r["_last_message_id"] = st["last_message_id"] or ""
    tracker.save(rows)
    return changes


def cmd_sync(args):
    gm = _gmail()
    rows = tracker.load()
    changes = _sync(gm, gm.service(), rows)
    print(f"Sync complete. {changes} update(s).")


def cmd_followups(args):
    gm = _gmail()
    svc = gm.service()
    rows = tracker.load()
    _sync(gm, svc, rows)
    days = SETTINGS.get("followup_days", [7, 14])
    max_f = SETTINGS.get("max_followups", 2)
    sender = SETTINGS.get("from_address") or None

    due = []
    for r in rows:
        if r["status"] != "sent":
            continue
        n = int(r["followups_sent"] or 0)
        if n >= max_f or _days_since(r["last_contact"]) < days[min(n, len(days) - 1)]:
            continue
        if gm.draft_exists(svc, r["followup_draft_id"]):
            continue  # a follow-up is already waiting in Gmail drafts
        due.append(r)
    if not due:
        print("No follow-ups due.")
        return

    for r in due:
        n = int(r["followups_sent"] or 0) + 1
        print(f"\nWriting follow-up {n} for {r['name']}...", flush=True)
        body = pitch.write_followup(r, n)
        subject = r["subject"] if r["subject"].lower().startswith("re:") else f"Re: {r['subject']}"

        def regenerate(subject, body, note, r=r, n=n):
            return subject, pitch.write_followup(r, n, feedback=note)

        action, subject, body = _review_loop(r, subject, body, 90, regenerate, check_subject=False)
        if action == "approve":
            draft_id, _ = gm.create_draft(svc, r["email"], subject, body + pitch.footer(), sender,
                                          thread_id=r["thread_id"],
                                          in_reply_to=r.get("_last_message_id") or None)
            r["followups_sent"] = str(n)
            r["followup_draft_id"] = draft_id
            tracker.log(r, f"follow-up {n} saved to Gmail drafts")
            print("Follow-up saved to Gmail drafts, in the same thread.")
        elif action == "exclude":
            r["status"] = "excluded"
            tracker.log(r, "excluded at follow-up")
        tracker.save(rows)
        if action == "quit":
            break


def cmd_status(args):
    rows = tracker.load()
    if not rows:
        print("Pipeline is empty.")
        return
    counts = Counter(r["status"] for r in rows)
    order = ["new", "researched", "weak_fit", "drafted", "queued", "sent", "replied",
             "booked", "declined", "opted_out", "excluded"]
    print("Pipeline")
    for s in order + sorted(set(counts) - set(order)):
        if counts.get(s):
            print(f"  {s:<11} {counts[s]}")
    by_aud = Counter((r["audience"], r["status"]) for r in rows)
    print("\nBy audience")
    for aud in sorted({r["audience"] for r in rows}):
        parts = ", ".join(f"{s} {c}" for (a, s), c in sorted(by_aud.items()) if a == aud)
        print(f"  {aud}: {parts}")
    replied = [r for r in rows if r["status"] == "replied"]
    if replied:
        print("\nNeeds your attention (replied):")
        for r in replied:
            print(f"  {r['id']}  {r['name']}, {r['organisation']}")
    queued = [r for r in rows if r["status"] == "queued"]
    if queued:
        print(f"\n{len(queued)} approved draft(s) are waiting in Gmail for you to send.")


def cmd_check(args):
    """Confirm the setup is complete before the first real run."""
    from .config import MODEL, ROOT

    blockers, warnings = [], []
    print(f"Python        {sys.version.split()[0]}")
    print(f"Model         {MODEL}")
    print(f"Audiences     {len(AUDIENCES)} configured: {', '.join(sorted(AUDIENCES))}")

    if (os.getenv("ANTHROPIC_API_KEY") or "").strip():
        print("Anthropic key found in the environment or .env")
    else:
        blockers.append("No ANTHROPIC_API_KEY. Copy .env.example to .env and paste your key.")

    if (ROOT / "token.json").exists():
        print("Gmail         authorised (token.json present)")
    elif (ROOT / "credentials.json").exists():
        print("Gmail         credentials.json present, you will be asked to authorise on first review")
    else:
        blockers.append("No credentials.json. See README, 'Connect Gmail'. "
                        "Research and draft still work without it.")

    facts = knowledge.facts()
    todos = sum(1 for line in (knowledge.KNOWLEDGE / "profile.md").read_text(encoding="utf-8").splitlines()
                if "TODO" in line) if (knowledge.KNOWLEDGE / "profile.md").exists() else 0
    if not facts:
        blockers.append("knowledge/profile.md has no usable facts. The agent has nothing true to say.")
    else:
        print(f"Knowledge     {len(facts.split())} words the agent may use"
              + (f", {todos} TODO line(s) still ignored" if todos else ""))
    if todos:
        warnings.append(f"{todos} TODO line(s) in knowledge/profile.md are ignored until you fill them in.")

    if not SETTINGS.get("signature", "").strip():
        warnings.append("No signature in config/settings.yaml.")
    if not SETTINGS.get("opt_out_line", "").strip():
        warnings.append("No opt_out_line in config/settings.yaml.")

    rows = tracker.load()
    print(f"Pipeline      {len(rows)} contact(s) in data/pipeline.csv"
          if rows else "Pipeline      empty, import a CSV to begin")

    for w in warnings:
        print(f"\nWorth fixing: {w}")
    for b in blockers:
        print(f"\nNot ready:    {b}")
    if not blockers:
        print("\nReady. Next: python run.py import data/your_targets.csv")
    sys.exit(1 if blockers else 0)


def cmd_mark(args):
    rows = tracker.load()
    r = tracker.find(rows, args.who)
    if not r:
        print("No match. Use the id from 'status' or the email address.")
        return
    r["status"] = args.status
    tracker.log(r, f"marked {args.status}" + (f": {args.note}" if args.note else ""))
    tracker.save(rows)
    print(f"{r['name']} marked as {args.status}.")


def cmd_show(args):
    rows = tracker.load()
    r = tracker.find(rows, args.who)
    if not r:
        print("No match.")
        return
    for k in tracker.FIELDS:
        if r.get(k):
            print(f"{k}:\n{textwrap.indent(str(r[k]), '  ')}")


def main():
    p = argparse.ArgumentParser(prog="pr-agent", description="Bodies Brains and Minds PR agent (draft-only).")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("import", help="add targets from a CSV")
    s.add_argument("csv")
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("research", help="web-research new targets")
    s.add_argument("--limit", type=int, default=10)
    s.set_defaults(func=cmd_research)

    s = sub.add_parser("draft", help="write pitches for researched targets")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--include-weak", action="store_true", help="also draft for weak-fit targets")
    s.set_defaults(func=cmd_draft)

    sub.add_parser("review", help="approve, edit or reject pitches; approved ones go to Gmail drafts").set_defaults(func=cmd_review)
    sub.add_parser("sync", help="check Gmail for sent emails and replies").set_defaults(func=cmd_sync)
    sub.add_parser("followups", help="draft follow-ups that are due").set_defaults(func=cmd_followups)
    sub.add_parser("status", help="pipeline summary").set_defaults(func=cmd_status)
    sub.add_parser("check", help="confirm keys, Gmail and knowledge are set up").set_defaults(func=cmd_check)

    s = sub.add_parser("mark", help="update a contact's status by hand")
    s.add_argument("who", help="id or email")
    s.add_argument("status", choices=["booked", "declined", "opted_out", "replied", "excluded", "sent"])
    s.add_argument("--note", default="")
    s.set_defaults(func=cmd_mark)

    s = sub.add_parser("show", help="show everything stored for one contact")
    s.add_argument("who", help="id or email")
    s.set_defaults(func=cmd_show)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
