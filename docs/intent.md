# Intent: Aster Client Intelligence Agent - Working Prototype

## Problem

Aster Vale Sports Data is a fictional company that sells sports data products to business clients: live data feeds,
odds, streaming, visualisation widgets, fan analytics and integrity monitoring. Its clients include sportsbooks,
broadcasters, leagues, clubs and fantasy apps.

Before a renewal, an important meeting or a growth conversation, a sales rep asks a sales business analyst for
client intelligence: how consumption is trending, which products the client could add, where the contract and
renewal stand, what support issues they have had, and what was said in recent meetings. The analyst pulls data
from several systems, works through it and writes it up. This often takes weeks, and meetings arranged at short
notice can happen before the analysis is ready.

We are replacing that manual process with an agent.

## Proposed outcome

A working prototype of a client intelligence agent with trustworthy cited client briefing in one click. 
Given a client and a trigger, it should gather evidence from the starter data(sqlite), analyse it, and produce a short briefing for the sales rep in which every claim is grounded in the data and cited.

## Must-haves (from the candidate brief)

These are non-negotiable. Everything else in this document refines them.

1. **One command** takes a client (name or ID) and a trigger, and writes a briefing (Markdown) plus an evidence file containing the tool outputs it used.
2. **Deterministic tools** covering at least:
   - contract and renewal status
   - usage trends
   - white-space: products the client does not hold, with evidence for why they might fit
   - support summary
   - meeting notes
3. **A planning step** that chooses analyses and emphasis for each trigger, driven by configuration (our choice, see 7.3), not by code for particular clients.
4. **A writer** that cites a source for every figure and claim, and **a verifier** that checks every number in the briefing appears in the evidence and every claim has a citation. We must decide what happens when the check fails and explain why (see section 8).
5. **Honest data handling:** duplicates, missing months, short histories and conflicts between sources are detected and shown in a "Data gaps and confidence" section, not hidden.
6. **A short evaluation:** run at least 3 clients × 2 triggers, include an automated check for numbers in a briefing that do not appear in the tool outputs, and report what we found, including failures (see section 12).

## Who it is for

- **Primary user**: a sales rep (account owner) who is short of time and needs to walk into a conversation prepared. They will not read evidence files unless something looks wrong, so the briefing must be short (about one page), lead with what matters, and end with concrete next steps.

- **Secondary user (the assessors)**: they will run the agent on clients we have not looked at, read the code and README, and ask us to make a small change live (for example, add a trigger).

## 4. What we are building
 
A working prototype with this flow:
 
```
client (name/ID) + trigger (+ optional rep context)
   -> resolve client            (code)
   -> plan analyses             (config-driven, per trigger)
   -> run deterministic tools   (SQL/pandas, no LLM)
   -> aggregate evidence        (code)  -> evidence.json
   -> write briefing            (LLM, evidence only, citations required)
   -> verify                    (code first, LLM semantic check second)
   -> repair once, then remove or flag what still fails
   -> briefing.md + evidence.json + trace
```
Keep it as simple as works. The number of agents is not counted; clarity of jobs is.

## 5. Inputs
 
**Request:** client (ID such as `C001`, or a name as a rep would type it, possibly shorter or informal), trigger, optional free-text context from the rep.
 
**Triggers (must support all four):**
 
| Trigger | The rep is asking |
|---|---|
| `renewal` | The contract is coming up for renewal. What is the position and what should I propose? |
| `meeting_prep` | I am meeting the client soon. What do I need to know? |
| `upsell` | Where can we grow this account (more volume or new products)? |
| `at_risk` | Is this account at risk, why, and what should I do? |


**Data (starter_pack, synthetic, extracted 2026-11-01, which is "today"):**

| File | What it holds |
|---|---|
| `clients.csv` | 25 client accounts: segment, country, account owner, tier |
| `products.csv` | Product catalogue (8 products), usage units, typical segments, products often bought together |
| `contracts.csv` | Contract headers: dates, term, auto-renew, notice period, ARR, status |
| `contract_lines.csv` | Products on each contract, annual fee and included monthly volume |
| `usage_monthly.csv` | Monthly consumption per client and product, November 2024 to October 2026 |
| `support_tickets.csv` | Support tickets with priority, category, dates and satisfaction score |
| `crm_opportunities.csv` | Renewal, upsell and cross-sell opportunities from the CRM |
| `meeting_notes/` + `meeting_notes_index.csv` | Free-text notes from account meetings (only some clients have notes) |
| `client_intel.db` | SQLite database with all of the above as tables (plus `meeting_notes` with the full text) |
| `data_dictionary.md` | Column-level definitions. Read this first. |
| `tool_catalogue.md` | Descriptions of the analyses an analyst runs today, written as tool contracts you can implement |
| `sample_requests.json` | Example requests a sales rep might send |

The data dictionary is the authoritative reference for interpreting the datasets. 

Where the data dictionary and tool catalogue leave ambiguity, document the ambiguity and choose a conservative, explicit implementation.

**Main Data Source - starter_pack/client_intel.db** 

SQLite is the only runtime source of business data.

- Do not use CSV files for application data retrieval.

- Open the database in read-only mode where possible.

- Do not modify the original database.

- Use parameterised SQL queries.

- Preserve source primary keys for evidence and citations.

Explicitly convert TEXT columns into appropriate dates and numeric types.

Use SQL for data retrieval and aggregations, and Python for business calculations and analysis.

**Data-quality rules**

The system must explicitly identify:

- Duplicate records.

- Missing months.

- Incomplete historical periods.

- Missing values.

- Invalid or inconsistent dates.

- Conflicting contract information.

- Conflicting CRM information.

- Usage records without corresponding contract lines.

- Contract lines without matching product catalogue entries.

- Meeting-note availability gaps.

- Incomplete support satisfaction information.

Never silently clean or discard records without documenting the treatment.

Never assume that:

- Missing consumption means zero consumption.

- Missing satisfaction scores mean zero satisfaction.

- Missing meeting notes mean there were no client meetings.

- An absent CRM opportunity means no commercial interest exists.

- A product absent from a contract is necessarily unused.

- Conflicting sources can be resolved through guesswork.

Where records are duplicated, establish an explicit policy based on the data dictionary. Do not automatically sum duplicates.

Where records conflict, retain the relevant source information and flag the discrepancy.

Every briefing must contain a Data Gaps and Confidence section.

## 6. Outputs
 
Per run, in `outputs/<client_id>_<trigger>_<timestamp>/`:
 
| File | Content |
|---|---|
| `briefing.md` | Final rep-facing briefing (Markdown, about one page) |
| `briefing.cited.md` | Writer output with `[fact_id]` citations, kept for verification |
| `evidence.json` | All tool outputs used, plan, indexes, and the source rows cited |
| `plan.json` | What the planner chose and why, including skipped sections |
| `writer_package.txt` | Exact text sent to the writer |
| `verification*.json` | Verifier report per attempt |
| `trace.json` | Steps, tool calls, time, tokens, cost |
 
A useful briefing typically covers some of: headline, account snapshot, contract and renewal position, usage trends, growth opportunities, support health, relationship context from notes, risks, talking points and questions to ask, next steps, and a **Data gaps and confidence** section. Which of these appear, and in what order, is decided per trigger.

## 7. The three things that matter most
 
### 7.1 It is general
- Works for any of the 25 clients and any of the four triggers.
- No logic written for a specific client, segment or case. No client IDs or names in code.
- Behaviour differs only through config, parameters or data.
- It will be run on clients we have not looked at.
### 7.2 The numbers are right
- Every figure comes from code or SQL tools, never from the language model. This includes percentages, counts and date differences.
- The model plans, interprets and writes.
- When data is missing, sparse or inconsistent, the briefing says so instead of filling the gap.
### 7.3 It is orchestrated
- Work is broken into steps with clear jobs: for example planner, deterministic tools, writer, verifier.
- Planning is driven by configuration, not by code for particular clients or triggers. A YAML plan per trigger chooses the analyses, the sections and their order, and what to emphasise. It does not need an LLM. Data availability can still cause a section to be skipped (for example, no meeting notes), and `plan.json` records why.

## 8. Decisions

**Interface: CLI only.** "One click" means one command, e.g. `aster brief "<client>" <trigger> [--context "..."]`. There is no web UI.

**Client resolution: never guess.** The client is resolved from an exact ID or a name match. If the name is ambiguous (several candidates) or matches nothing, the run stops without producing a briefing and prints the ranked candidates, so the rep can rerun with an ID. There is no interactive prompt.

**Rep context: emphasis only.** The optional free-text context can change emphasis and which sections lead. It is never treated as evidence, never cited, and never adds analyses. If a statement from it appears in the briefing, it is labelled "per rep".

**Models: configurable.** Model names live in config, with one default model and optional overrides per role (writer, verifier). No model name is hard-coded.

**When verification still fails.** After the single repair attempt:
- numeric claims that still fail are removed from `briefing.md`
- qualitative claims that still fail stay in, marked ⚠ unverified
- every removed or flagged claim is listed in the Data Gaps and Confidence section and recorded in the verification report

*Why:*
- **Repair first.** Most failures are citation or formatting slips (a missing `[fact_id]`, a rounded figure) that one targeted rewrite fixes cheaply. Repairing more than once costs more and can drift away from the evidence.
- **Remove failed numbers.** A rep will quote a figure to the client, so a wrong number does more harm than a missing one. A number we cannot trace to a tool output must not reach the rep.
- **Flag failed qualitative claims.** These are interpretations of cited evidence, and removing them can leave the briefing without the context the rep needs. A visible ⚠ keeps the context while being honest about what we could not verify.

## 9. Constraints

- **Deadline: about one week.** Prefer the simplest design that meets the success criteria.
- Business data comes only from `starter_pack/client_intel.db`, which is opened read-only (see section 5).

## 10. Out of scope

- Authentication, multiple users, and per-rep access control.
- Live integrations with real CRM, billing or support systems. The SQLite snapshot is the only source.
- Sending, emailing or publishing briefings. Output goes to local files only.
- Forecasting or ML models (e.g. predictive churn). Analyses are descriptive trends and explicit rules only.

## 11. What success looks like

The prototype is done when all of these hold:

1. **Coverage:** every combination of the 25 clients and 4 triggers (100 runs) produces a briefing without crashing, including clients with sparse or missing data.
2. **Grounding:** every factual and numeric claim in `briefing.md` maps to a `fact_id` in `evidence.json` and passes verification. Claims that fail are handled as described in section 8, never left in silently.
3. **Live change:** a new trigger can be added in under 15 minutes by editing config and adding a test, with no changes to orchestration code.
4. **Tests:** pytest covers each deterministic tool and each data-quality rule in section 5, run against the real database.
5. **Evaluation delivered:** the evaluation in section 12 has been run and its report is committed, including any failures.

## 12. Evaluation

- **Scope:** at least 3 clients × 2 triggers. Choose clients that differ: at least one with clean data, one with sparse or short history, and one with duplicates or conflicts between sources. Chosen by inspecting the data, never hard-coded.
- **Automated check for unsupported numbers:** a script (and pytest test) that pulls every number out of `briefing.md` and checks that it appears in that run's tool outputs in `evidence.json`. It allows only the rounding and format differences defined in config (e.g. `1,234` vs `1234`, `12.3%` vs `0.123`). Any number it cannot match fails the check. This check runs separately from the in-pipeline verifier and does not trust it.
- **Also recorded per run:** citation coverage, claims repaired, removed or flagged, data gaps surfaced, runtime, tokens and cost (from `trace.json`).
- **Report:** `eval/REPORT.md` with a results table per run, the failures found and their causes, what we fixed, and what we left as known limitations. Failures are reported, not hidden.