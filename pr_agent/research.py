from .config import AUDIENCES, SETTINGS
from . import llm

SYSTEM = """You research one outreach target so that a pitch email can be personalised honestly.
Use web search. Report only what you can verify, with URLs. Be concise.
If you find nothing recent or relevant, say so plainly. Never guess or embellish.

Return JSON only, with these keys:
- "summary": 2-3 sentences on who they are and what they do
- "recent_work": up to 4 items, each {"title", "date", "url", "why_relevant"}
- "hook": one specific, verifiable reason they might care about Albert's work right now ("" if none)
- "fit": "strong", "possible" or "weak"
- "fit_reason": one sentence
- "contact_check": anything suggesting the person has moved role or the contact is out of date ("" if nothing)
- "sources": list of URLs"""


def research(row, facts):
    aud = AUDIENCES[row["audience"]]
    prompt = f"""Target: {row['name']}, {row['role']} at {row['organisation']}
Website: {row['website'] or 'unknown'}
Audience type: {aud['label']}
Albert's goal with this kind of contact: {aud['goal']}
What he can offer: {aud['offer'].strip()}
Albert's notes on this target: {row['notes'] or 'none'}

Look for what this person or organisation has published, covered, programmed or announced in roughly
the last 12 months that relates to brain health, sleep, exercise, sport, head injury, mental health,
wellbeing, ageing, or AI and wellbeing. Then judge the fit.

For context, here is who Albert is:
{facts[:2500]}"""
    blocks = llm.ask(SYSTEM, prompt, max_tokens=2500, web_search=True,
                     max_searches=SETTINGS.get("research_max_searches", 5))
    return llm.parse_json(blocks)
