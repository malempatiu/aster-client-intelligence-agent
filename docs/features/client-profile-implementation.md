# Client Profile Tool for Aster Intelligence.

Before implementation:
- Read AGENTS.md and TECH_STACK.md.
- Inspect the existing project structure.
- Reuse the SQLite connection utility.
- Reuse existing Pydantic models where appropriate.
- Inspect the actual clients table schema.

## Objective

Create a deterministic tool that retrieves a client's account profile using their canonical client ID.

## Location

Use the existing tools directory and naming conventions.

Recommended module:
src/tools/resolver.py

Avoid duplicating the client_resolver implementation. Extend the existing module only if that is consistent with the project structure.

## Input

The tool accepts:
- client_id

The client ID must already have been resolved by the client resolver.

Do not perform fuzzy matching or client-name resolution inside this tool.

## Database

Use the SQLite clients table.

Retrieve:
- segment
- country
- owner
- customer_since
- tier

Use parameterised SQL queries.

## Output

Create or reuse a Pydantic ClientProfile model.

Return:
- All seven client fields.
- Original source table.
- Source primary key (client_id).
- Any data-quality warnings.

Parse customer_since as a date where valid.

If optional profile information is missing, preserve it as missing and report an appropriate warning. Do not invent or substitute values.

If the supplied client_id does not exist, return a clear not-found result or a documented exception.

## CLI integration

After successful client resolution, invoke the profile tool and display the retrieved client profile in a readable format.

Do not introduce planner or orchestrator functionality yet.

## Tests

Add pytest tests for:

1. Successful profile retrieval.
2. Correct client ID.
3. Correct retrieval of all profile fields.
4. Missing optional profile values.
5. Invalid customer_since date.
6. Unknown client ID.
7. Database errors.
8. Source primary key preservation.

Use a temporary SQLite test database for controlled cases.

Also run an integration test using the supplied read-only database.

## Scope restrictions

Do not:
- Implement contract analysis.
- Implement usage analysis.
- Call an LLM.
- Implement the planner.
- Implement the orchestrator.
- Modify the original database.
- Use CSV files.
