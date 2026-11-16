import argparse
import sys
from difflib import get_close_matches
from typing import get_args

from pydantic import ValidationError

from src.models.requests import ClientRequest, Trigger

TRIGGERS = get_args(Trigger)


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
    return 0


if __name__ == "__main__":
    sys.exit(main())
