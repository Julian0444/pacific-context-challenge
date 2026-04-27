# QueryTrace — Video Script (English)

**Target length: 4–5 minutes**
**Format: Loom with screen share + camera**

---

## Before recording

- Server running: `python3 -m uvicorn src.main:app --reload`
- Browser open at `http://localhost:8000/app/`
- Clean screen — just the browser, no extra tabs
- App starts at the Query mode empty state (three onboarding cards visible)

---

## INTRO — 30 seconds

> *[Camera on, screen showing empty state]*

"Hi, I'm Julian. I'm going to walk you through QueryTrace, a project I built to solve a real problem in enterprise AI systems: **what documents do you pass to an LLM before it responds, and how do you make sure you're not passing something the user shouldn't see?**"

"QueryTrace isn't a chatbot. It's the layer that decides what goes into an LLM's context window — and it makes every decision visible."

"The simulated scenario is an M&A deal: a private equity fund evaluating the acquisition of a fintech company. There are 16 documents and three access levels — analyst, VP, and partner. Let's see what happens."

---

## PART 1 — Side-by-side mode, Permission Wall (~90 seconds)

> *[Click "Open in Compare →" on the Permission Wall card]*

"I'll start with the screen that shows the project's value the fastest. I'm clicking 'Open in Compare' on the Permission Wall card."

> *[Three columns load]*

"This runs the same search — 'What is Meridian's ARR growth rate' — as an analyst, through three levels of protection."

> *[Point cursor at the No Filters column]*

"On the left, **No Filters**: with no controls in place, the system would hand the LLM every relevant document. See these red labels that say 'blocked in full' — that's the Investment Committee memo, the LP update letter, internal financial models, and a partner-only legal memo. Things a junior analyst **should never see**."

> *[Move to the middle column]*

"In the middle, **Permissions Only**: the system detects that 10 documents require VP or partner level access, and blocks them. The analyst only sees 6."

> *[Move to the right column]*

"On the right, **Full Pipeline**: on top of permissions, it detects that one document has been superseded by a newer version and penalizes its freshness score. Permissions and freshness are two layers that operate in parallel."

> *[Point at an open Decision Trace]*

"Each column has its Decision Trace open — the full breakdown of what was included, what was blocked, and why. This is auditable."

---

## PART 2 — Stale Detection (~45 seconds)

> *[Go back to empty state: click "Query" tab, then "Side-by-side" tab, click the Stale Detection card]*

"Now let's see what happens with a partner — someone with full access."

> *[Three columns load]*

"Zero blocked documents across all three columns — the partner can see everything. But look at the Full Pipeline column: it detected that three documents have been **replaced** by newer versions."

> *[Point at the "⚠ Superseded" badges]*

"These documents still appear, but with a 50% freshness penalty. The LLM sees them, but weighs them less. This isn't an access issue — it's a **context hygiene** issue. A stale document is worse than a blocked one, because the LLM doesn't know the data is outdated."

---

## PART 3 — Query mode + Decision Trace (~60 seconds)

> *[Click "Query" tab, click "Run in Single" on the Permission Wall card]*

"Let's go back to Query mode for the detailed view. I'm running as an analyst with the full pipeline."

> *[Point at the summary bar]*

"At the top: 6 documents included, roughly 675 tokens — that's 33% of the budget. 10 blocked, 1 demoted as stale."

> *[Point at a result card]*

"Each card shows the document title, type, date, an excerpt, and relevance and freshness score bars."

> *[Click "🔒 10 documents blocked by permissions"]*

"If I open the blocked section, I see exactly which documents were filtered and why — 'Requires partner role, you are analyst'. This is what you'd show to compliance."

> *[Click "Decision Trace"]*

"The Decision Trace opens with a natural-language summary — '6 documents included, 10 blocked, your role cannot access VP and partner level materials'. Below that, color-coded chips: green for included, red for blocked, yellow for stale."

---

## PART 4 — Metrics (~30 seconds)

> *[Click "Metrics" tab]*

"To close with hard numbers: the Metrics dashboard runs the full pipeline against 12 test queries."

> *[Point at the green narrative banner]*

"Zero permission violations — across 12 queries, the system never leaked a document to someone who shouldn't see it. Perfect recall — it never missed an expected document."

> *[Point at the metric cards]*

"Permission Violations: 0%. Recall: 1.0. And every row in the table below is reproducible — this isn't a screenshot, it's the `/evals` endpoint responding live."

---

## CLOSING — 20 seconds

> *[Switch back to Side-by-side mode with a three-column view]*

"In summary: QueryTrace solves the problem that LLMs have no concept of who's asking. Security has to happen **before** the prompt, at the context layer. This project implements that layer with role-based permissions, stale document detection, token budgeting, and full decision traceability."

"All the code is in the repo. Thanks for watching."

> *[End]*

---

## Recording tips

1. **Don't read the script word for word** — internalize the ideas and speak naturally. The script is a guide for what to point at and in what order.
2. **Move the cursor slowly** over what you're explaining — viewers follow the cursor.
3. **Don't zoom into code** or talk about FAISS or BM25 — that's for the technical interview, not the Loom.
4. **If you stumble, keep going** — Loom lets you trim afterwards. Better to record in one take and edit than do 15 attempts.
5. **Ideal pacing**: 3 seconds of silence while the screen loads, then talk about what's visible. Don't narrate before it appears.
