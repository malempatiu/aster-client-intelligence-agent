# Client resolver for Aster Intelligence.

## Objective

Resolve a sales representative's free-text client input into a canonical client record.

## Input

Accept:
- Client name.
- Client ID.

## Matching behaviour

Implement these matching strategies in order:

1. Exact client ID match.
2. Exact client name match.
3. Case-insensitive and whitespace-normalised name match.
4. Conservative fuzzy matching for suggestions.

Do not automatically select an ambiguous client.

Use a deterministic matching method and document its thresholds. Standard-library string similarity functionality is sufficient; do not add a fuzzy-matching dependency.

Return one of these statuses:

- resolved
- ambiguous
- not_found

## Structured output

Create or reuse a Pydantic ClientResolution model.

It should contain:
- Input value.
- Resolution status.
- Canonical client ID when resolved.
- Canonical client name when resolved.
- Match type.
- Candidate matches where relevant.
- Match confidence or similarity score where applicable.

Do not invent clients or client IDs.

## CLI integration

Update the existing CLI so that after ClientRequest validation:

1. It invokes the client resolver.
2. It displays the canonical client ID and name when resolved.
3. It displays useful candidate suggestions when ambiguous.
4. It exits with a clear error when no client is found.

Do not implement the planner or orchestrator yet.

## Tests

Test:
1. Exact client ID.
2. Exact client name.
3. Case-insensitive name.
4. Leading and trailing whitespace.
5. Unique normalised match.
6. Ambiguous name.
7. Unknown client.
8. Empty input.
9. Fuzzy-match suggestions.
10. No automatic resolution of an ambiguous fuzzy match.

Use test fixtures or a temporary SQLite database where appropriate. Also run an integration smoke test against the supplied read-only database.

After implementation:
- Run pytest.
- Run Ruff.
- Demonstrate resolution of Halden Bet.
- Demonstrate resolution of C009.
- Demonstrate an unknown client.
- Report all modified files and test results.

Do not implement client profile retrieval in this task.