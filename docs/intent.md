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

## Who it is for

- **Primary user**: a sales rep (account owner) who is short of time and needs to walk into a conversation prepared. They will not read evidence files unless something looks wrong, so the briefing must be short (about one page), lead with what matters, and end with concrete next steps.

- **Secondary user (the assessors)**: they will run the agent on clients we have not looked at, read the code and README, and ask us to make a small change live (for example, add a trigger).

## 4. What we are building
 
A working prototype with this flow:
 
```
client (name/ID) + trigger (+ optional rep context)
   -> resolve client            (code)
   -> plan analyses             (config, optional light LLM adjustment)
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
- Planning is driven by configuration or model reasoning, not by code for particular clients or triggers.