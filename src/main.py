import argparse
import sys
from difflib import get_close_matches
from typing import get_args

from pydantic import ValidationError

from src.database import DatabaseError
from src.models.profile import ClientProfile
from src.models.requests import ClientRequest, Trigger
from src.tools.client_profile import ClientNotFoundError, get_client_profile
from src.tools.resolver import resolve_client

TRIGGERS = get_args(Trigger)
PROFILE_LABELS = {
    "client_id": "Client ID",
    "client_name": "Name",
    "segment": "Segment",
    "country": "Country",
    "account_owner": "Owner",
    "customer_since": "Customer since",
    "tier": "Tier",
}


class Parser(argparse.ArgumentParser):
    def error(self, message: str):
        self.exit(2, f"Error: {message}\nRun with --help for usage.\n")


def build_parser() -> argparse.ArgumentParser:
    parser = Parser(prog="aster", description="Submit a client intelligence request.")
    parser.add_argument("--client", required=True, help="client name or ID, e.g. 'Halden Bet' or C009")
    parser.add_argument("--trigger", required=True, help=f"one of: {', '.join(TRIGGERS)}")
    parser.add_argument("--context", help="optional free-text context from the sales rep")
    parser.add_argument("--request-id", help="optional request ID (generated if omitted)")
    return parser


def describe(err: dict) -> str:
    field = err["loc"][0]
    if field in ("client", "request_id"):
        return f"--{field.replace('_', '-')} cannot be empty."
    if field == "trigger":
        value = str(err["input"])
        msg = f"'{value}' is not a valid trigger."
        if match := get_close_matches(value, TRIGGERS, n=1):
            msg += f" Did you mean '{match[0]}'?"
        return f"{msg}\nValid triggers: {', '.join(TRIGGERS)}"
    return f"{field}: {err['msg']}"


def print_profile(profile: ClientProfile) -> None:
    print(f"\nClient profile (source: {profile.source_table}.client_id = {profile.source_primary_key})")
    for field, label in PROFILE_LABELS.items():
        value = getattr(profile, field)
        print(f"  {label:<15} {value if value is not None else '-'}")
    for warning in profile.warnings:
        print(f"  Warning: {warning}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fields = {
        "client": args.client,
        "trigger": args.trigger,
        "rep_context": args.context,
        "request_id": args.request_id,
    }
    try:
        request = ClientRequest(**{k: v for k, v in fields.items() if v is not None})
    except ValidationError as e:
        for err in e.errors():
            print(f"Error: {describe(err)}", file=sys.stderr)
        return 2

    print("Request validated.")
    for name, value in request.model_dump().items():
        print(f"  {name:<12} {value if value is not None else '-'}")

    try:
        resolution = resolve_client(request.client)
    except DatabaseError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if resolution.status == "resolved" and resolution.client_id is not None:
        print(f"Client resolved: {resolution.client_id} {resolution.client_name}")
        try:
            profile = get_client_profile(resolution.client_id)
        except (DatabaseError, ClientNotFoundError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        print_profile(profile)
        return 0
    if resolution.status == "ambiguous":
        print(f"Error: '{request.client}' did not match a single client. Did you mean:", file=sys.stderr)
        for c in resolution.candidates:
            print(f"  {c.client_id}  {c.client_name}", file=sys.stderr)
        print("Re-run with the client ID.", file=sys.stderr)
        return 1
    print(f"Error: no client found matching '{request.client}'.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
