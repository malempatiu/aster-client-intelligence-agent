# Test Action

1. Read @docs/CURRENT_FEATURE.md to understand what was implemented
3. Check if tests already exist for these functions
4. For functions without tests that have testable logic, write unit tests:
   - Create unit tests using pytest
   - Test happy path and error cases
   - Do not write tests just to write them. Use your best judgement
5. Run `uv run pytest` to verify all tests pass
6. Run `uv run ruff check .` for any code formatting and  issues and fix them.
6. Report test coverage for the new feature code