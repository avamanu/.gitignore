# Bodies Brains and Minds PR agent (Phase 1)

A draft-only publicity assistant. It researches each contact, writes a personalised pitch in your
voice, and shows it to you. Approved pitches are saved as **Gmail drafts**. You press send yourself.
The tool has no permission to send email.

```
targets.csv -> import -> research -> draft -> review -> Gmail drafts -> you send -> sync -> followups
```

## 1. One-time setup (about 30 minutes)

**Python.** Install Python 3.10 or newer. In this folder:

```
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Anthropic key.** Copy `.env.example` to `.env` and paste your API key from console.anthropic.com.
Web search must be enabled for your organisation in the Console (Settings, then Privacy / tools).

**Connect Gmail.**
1. Go to console.cloud.google.com and create a project (e.g. "BBM PR agent").
2. APIs and Services, Library: enable **Gmail API**.
3. OAuth consent screen: choose External, fill in the basics, add your own Gmail address as a **test user**.
4. Credentials, Create credentials, OAuth client ID, application type **Desktop app**.
5. Download the JSON, rename it `credentials.json`, put it in this folder.

The first time you run `review`, a browser window asks you to allow access. A `token.json` file is
saved so you are not asked again. Keep `credentials.json`, `token.json` and `.env` private.

**Your knowledge base.** Open `knowledge/profile.md` and fill in the TODO lines (past talks, formats,
links, testimonials). Lines with TODO are ignored, so the agent can never mention something you have
not confirmed. Anything you add here is fair game for pitches, so keep it true.

**Your strategy.** `config/audiences.yaml` holds what you offer, the angle and the ask for each audience.
`config/settings.yaml` holds your signature, opt-out line, daily limit and follow-up timings.

**Check the setup.** When you think you are done:

```
python run.py check
```

It confirms your key, your Gmail files, your knowledge base and your config, and tells you what is
still missing. It never contacts anyone.

## 2. Add targets

Copy `data/targets_template.csv`, replace the example row, and fill in:

| column | notes |
|---|---|
| name, email, organisation, role | as found |
| audience | one of: podcasts, journalists, events, corporate_wellbeing, councils, universities_sport |
| website | show, publication or organisation page |
| source | **where you found the contact**, e.g. "Contact page, checked Sept 2026". Required: it is your GDPR record |
| notes | anything you know that helps the pitch |

```
python run.py import data/my_podcasts.csv
```

Duplicates are skipped, so you can import new lists over time.

## 3. The daily routine (about 20 minutes)

```
python run.py research --limit 10    # web research, fit score, hook, sources
python run.py draft --limit 10       # writes pitches, auto-checks voice, rewrites once if needed
python run.py review                 # you decide, one by one
```

In `review` you see the research, sources, the full email with signature, and a voice check
(dashes, US spellings, banned phrases, binary contrasts, word count). Then:

- **a** approve: saved to Gmail drafts
- **e** edit in a text editor
- **r** rewrite with a note, e.g. "shorter, lead with the concussion angle"
- **s** skip for now, **x** exclude permanently, **q** quit

Then open Gmail, give each draft a final read, and send.

## 4. Replies and follow-ups

```
python run.py sync          # detects sent emails and replies
python run.py followups     # drafts follow-ups due at 7 and 14 days, in the same thread
python run.py status        # pipeline summary and who needs attention
python run.py mark jane@example.com booked --note "Episode recording 12 Oct"
python run.py show jane@example.com
```

Statuses you can set with `mark`: booked, declined, opted_out, replied, excluded, sent.
Anyone marked `opted_out` or `excluded` is never contacted again, and re-importing them is blocked.
Note that an out-of-office auto-reply counts as a reply, so check before marking.

Everything lives in `data/pipeline.csv`, which you can open in Excel (close it before running commands).
A backup `pipeline.csv.bak` is written before every save.

## Checking the code still works

```
pip install -r requirements-dev.txt
pytest
```

The tests run offline. They cover the pipeline file, the import rules including the opt-out block,
and the voice check. No API key, no Gmail, no emails.

## Guardrails built in

- No send permission. Every email passes through your eyes twice (review, then Gmail).
- The agent may only use facts in `knowledge/`, and only research it can source.
- Signature and opt-out line are added by code, never by the model.
- Daily cap on new pitches (default 15) to protect your domain's reputation.
- A `source` is required for every contact.
- Maximum two follow-ups, then it stops.

## Using it well

- Start with one audience and 30 pitches. Look at which ones get replies before scaling.
- Rewrite the `angle_guidance` in `audiences.yaml` as you learn what works. That file is your playbook.
- UK rules (PECR and UK GDPR) are friendlier to emailing people at organisations about something relevant
  to their role than to emailing individuals or sole traders. Check the ICO's direct marketing guidance
  if you are unsure about a list.

## Model and costs

The model is set in `config/settings.yaml` (or `PR_AGENT_MODEL` in `.env`). Research uses web search,
billed per search on top of tokens, and is capped at 5 searches per contact. Expect a few pence per
contact, but check current pricing in the Anthropic Console.
