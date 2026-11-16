# CLI input and request validation for Aster Intelligence.

# Objective

Allow a sales representative to submit a client intelligence request through the command line and validate it before passing it to the application.

# Technology

- Python 3.12
- argparse for CLI argument parsing
- Pydantic v2 for request validation

# CLI inputs

### Required:

- --client: client name or client ID
- --trigger: requested business trigger

### Optional:

- --context: free-text context from the sales representative

### Supported triggers:

- renewal

- meeting_prep

- upsell

- at_risk

## Pydantic model

Create a ClientRequest model in the src/models/requests.py module

### The model should contain:

- request_id

- client

- trigger

- rep_context

- as_of

### Validation rules:

- Client is required and cannot be empty or whitespace.

- Trim unnecessary whitespace from client names and IDs.

- Trigger must be one of the four supported values.

- Rep context is optional.

- Request ID is optional. Generate a unique ID if not supplied.

- Use 2026-11-01 as the fixed reporting date.

- Do not allow the user to override the reporting date through the CLI.


## CLI behaviour

### The application must accept commands such as:

- uv run -m src.main --client "Halden Bet" --trigger at_risk

- uv run -m src.main --client C009 --trigger upsell

- uv run -m src.main --client "Corvane Media" --trigger upsell --context "Meeting their head of digital next week"

- uv run -m src.main --client "Halden Bet" --trigger at_risk

### The CLI should:

- Display helpful usage information.

- Display clear validation errors.

- Exit gracefully when required arguments are missing.

- Return a clear indication when validation succeeds.

- Display the validated request in a readable format.

## Scope restrictions

This feature must ONLY implement CLI input and request validation.