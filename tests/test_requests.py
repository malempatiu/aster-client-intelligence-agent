from datetime import date

import pytest
from pydantic import ValidationError

from src.main import main
from src.models.requests import ClientRequest


def test_client_is_trimmed():
    assert ClientRequest(client="  Halden Bet ", trigger="at_risk").client == "Halden Bet"


@pytest.mark.parametrize("client", ["", "   "])
def test_blank_client_rejected(client):
    with pytest.raises(ValidationError):
        ClientRequest(client=client, trigger="at_risk")


def test_blank_request_id_rejected():
    with pytest.raises(ValidationError):
        ClientRequest(request_id="  ", client="C009", trigger="upsell")


def test_invalid_trigger_rejected():
    with pytest.raises(ValidationError):
        ClientRequest(client="C009", trigger="churn")


def test_defaults():
    a = ClientRequest(client="C009", trigger="upsell")
    b = ClientRequest(client="C009", trigger="upsell")
    assert a.request_id != b.request_id
    assert a.rep_context is None
    assert a.as_of == date(2026, 11, 1)


def test_cli_success(capsys):
    assert main(["--client", "Halden Bet", "--trigger", "at_risk", "--request-id", "R1"]) == 0
    out = capsys.readouterr().out
    assert "Request validated." in out
    assert "R1" in out


def test_cli_blank_client(capsys):
    assert main(["--client", "  ", "--trigger", "upsell"]) == 2
    assert "--client cannot be empty" in capsys.readouterr().err


def test_cli_invalid_trigger_suggests(capsys):
    assert main(["--client", "Halden Bet", "--trigger", "at_ris"]) == 2
    err = capsys.readouterr().err
    assert "Did you mean 'at_risk'?" in err
    assert "Traceback" not in err


@pytest.mark.parametrize(
    "argv",
    [
        ["--trigger", "upsell"],
        ["--client", "C009"],
        ["--client", "C009", "--trigger", "upsell", "--as-of", "2025-01-01"],
    ],
)
def test_cli_bad_args_exit(argv):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2
