import json
import re

from .config import AUDIENCES, SETTINGS
from . import knowledge, llm

BANNED = [
    "moreover", "furthermore", "in conclusion", "it is worth noting", "fast-paced world",
    "now more than ever", "game-changer", "game changer", "revolutionary", "transform your life",
    "the secret to", "unexpected delight", "prompted me to reflect", "the honest version",
    "longer-horizon", "in that spirit", "hope this email finds you", "hope this finds you",
    "delve", "unlock", "cutting-edge", "i'm reaching out", "i am reaching out", "synergy",
    "science proves", "scientists have proven", "doctors don't want you to know",
    "this changes everything", "cure dementia", "reverse ageing", "reverse aging",
    "miracle cure", "one weird trick", "this one trick",
]
# Claims Albert must never make about himself. He is a clinical neuroscientist and a PhD
# researcher. He is not a doctor, he has no patients, and ambition towards medicine is not a
# qualification. Writing any of this to a journalist or an event organiser is the most expensive
# mistake this tool could make, so it is checked by code rather than left to the model.
FALSE_CREDENTIALS = [
    (r"\b(dr|dr\.|doctor|professor|prof\.?)\s+vamanu\b", "calls him Dr or Professor"),
    (r"\bas an?\s+(doctor|physician|medical doctor|neurologist|neurosurgeon|clinician|"
     r"psychiatrist|clinical psychologist|professor)\b", "describes him as a clinician"),
    (r"\bi\s*(?:'m|\s+am)\s+an?\s+(doctor|physician|medical doctor|neurologist|neurosurgeon|"
     r"clinician|psychiatrist|clinical psychologist|professor)\b", "claims a credential he does not hold"),
    (r"\bmy patients\b", "implies he treats patients"),
    (r"\bi (?:treat|diagnose|prescribe)\b", "implies clinical practice"),
]
US_SPELLINGS = {
    "color": "colour", "behavior": "behaviour", "organize": "organise", "recognize": "recognise",
    "center": "centre", "analyze": "analyse", "optimize": "optimise", "prioritize": "prioritise",
    "favorite": "favourite", "program ": "programme ",
}
CONTRAST_RE = re.compile(
    r"\bnot (just|only|merely)\b[^.]{0,80}\bbut\b|\b(isn't|is not|it's not) about\b[^.]{0,80}\b(it's|it is) about\b",
    re.IGNORECASE,
)


def _system(extra_rules=""):
    return f"""You draft outreach emails that Albert Vamanu will personally read, edit and send from his own
email account. Write in his first person. A real person writing to a real person.

FACTS ABOUT ALBERT (the only facts about him you may use):
{knowledge.facts()}

VOICE:
{knowledge.voice()}

HARD RULES
- Use only the facts above about Albert. Never invent talks, clients, media appearances, numbers,
  testimonials or affiliations. Never imply he represents any institution.
- Use only what the research notes say about the recipient. If the research is thin, write a shorter,
  plainer email rather than faking familiarity. Never claim to be a long-time fan or listener.
- One clear, low-effort ask.
- No sign-off, name or signature: these are added automatically.
- No opt-out line: this is added automatically.
{extra_rules}
Return JSON only: {{"subject": "...", "body": "..."}}"""


def write_pitch(row, feedback=None):
    aud = AUDIENCES[row["audience"]]
    user = f"""Recipient: {row['name']}, {row['role']} at {row['organisation']} ({row['website'] or 'no website'})
Audience type: {aud['label']}
Albert's goal: {aud['goal']}
What he can offer: {aud['offer'].strip()}
Angle guidance: {aud['angle_guidance'].strip()}
The ask: {aud['ask']}
Avoid: {aud['avoid']}
Albert's own notes on this person: {row['notes'] or 'none'}

Research notes (JSON):
{row['research'] or '{}'}

Body: {SETTINGS.get('max_words', 170)} words or fewer, starting with a greeting using their first name.
Subject: under 60 characters, specific to them, no clickbait."""
    if feedback:
        user += f"""

Revise this previous draft following Albert's note: "{feedback}"
Previous subject: {row['subject']}
Previous body:
{row['body']}"""
    out = llm.parse_json(llm.ask(_system(), user, max_tokens=1200))
    return out["subject"].strip(), out["body"].strip()


def write_followup(row, number, feedback=None):
    kind = (
        "a brief, friendly nudge that adds one small new reason to reply (for example a specific "
        "session or episode idea drawn from the research), 40 to 80 words"
        if number == 1 else
        "a short, gracious close-the-loop note, 30 to 60 words, making it easy to say no or to point "
        "him to someone else"
    )
    user = f"""Write follow-up number {number} in the same email thread. It should be {kind}.
Do not repeat the original pitch. Do not guilt-trip or say "just bumping this".
The subject is not needed; return "subject": "" .

Recipient: {row['name']}, {row['role']} at {row['organisation']}
Original subject: {row['subject']}
Original email:
{row['body']}

Research notes (JSON):
{row['research'] or '{}'}"""
    if feedback:
        user += f'\n\nAlbert\'s note for this version: "{feedback}"'
    out = llm.parse_json(llm.ask(_system(), user, max_tokens=800))
    return out["body"].strip()


def footer():
    return "\n\n{}\n{}\n\n{}".format(
        SETTINGS.get("sign_off", "Best wishes,"),
        SETTINGS.get("signature", "").strip(),
        SETTINGS.get("opt_out_line", "").strip(),
    )


def lint(subject, body, max_words=None, check_subject=True):
    """Mechanical voice check. Returns a list of problems (empty list = clean).

    check_subject is False for follow-ups, where the subject is a "Re:" of one
    already approved and its length is not the model's doing.
    """
    text = f"{subject}\n{body}"
    low = text.lower()
    issues = []
    if "\u2014" in text or "\u2013" in text:
        issues.append("contains an em or en dash")
    issues += [f'banned phrase: "{p}"' for p in BANNED if p in low]
    issues += [f"false credential: {why}" for pattern, why in FALSE_CREDENTIALS
               if re.search(pattern, low)]
    issues += [f'US spelling "{us.strip()}" (use "{uk.strip()}")' for us, uk in US_SPELLINGS.items()
               if re.search(r"\b" + re.escape(us), low)]
    if CONTRAST_RE.search(text):
        issues.append('binary contrast ("not X, but Y")')
    if max_words and len(body.split()) > max_words:
        issues.append(f"body is {len(body.split())} words (limit {max_words})")
    if check_subject and len(subject) > 60:
        issues.append(f"subject is {len(subject)} characters (limit 60)")
    if re.search(r"\[[^\]]*\]|\{[^}]*\}", text):
        issues.append("looks like it contains an unfilled placeholder")
    return issues


def draft_with_check(row):
    """Write a pitch, and if it fails the voice check, rewrite once with the problems listed."""
    max_words = SETTINGS.get("max_words", 170)
    subject, body = write_pitch(row)
    issues = lint(subject, body, max_words)
    if issues:
        row["subject"], row["body"] = subject, body
        subject, body = write_pitch(row, feedback="Fix these problems: " + "; ".join(issues))
        issues = lint(subject, body, max_words)
    return subject, body, json.dumps(issues)
