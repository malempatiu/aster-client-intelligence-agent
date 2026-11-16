"""Resolve free-text client input to a canonical client record.

Strategies, applied in order:
1. Exact client ID.
2. Exact client name.
3. Case-insensitive, whitespace-normalised client ID or name.
4. Fuzzy name similarity (difflib.SequenceMatcher ratio on normalised strings).
   Fuzzy matches are suggestions only and never resolve automatically.

A strategy that matches more than one client returns "ambiguous" with candidates.
"""

from difflib import SequenceMatcher
from pathlib import Path

from src.database import DB_PATH, query
from src.models.resolution import ClientCandidate, ClientResolution, MatchType

FUZZY_THRESHOLD = 0.8  # minimum similarity ratio for a suggestion
MAX_SUGGESTIONS = 5


def normalise(value: str) -> str:
    return " ".join(value.split()).casefold()


def resolve_client(value: str, path: Path = DB_PATH) -> ClientResolution:
    text = value.strip()
    if not text:
        return ClientResolution(input=value, status="not_found")

    clients = query("SELECT client_id, client_name FROM clients ORDER BY client_id", path=path)
    norm = normalise(text)

    strategies: list[tuple[MatchType, list[dict]]] = [
        ("client_id", [c for c in clients if c["client_id"] == text]),
        ("exact_name", [c for c in clients if c["client_name"] == text]),
        (
            "normalised_name",
            [c for c in clients if norm in (normalise(c["client_id"]), normalise(c["client_name"]))],
        ),
    ]
    for match_type, matches in strategies:
        if len(matches) == 1:
            return ClientResolution(
                input=value,
                status="resolved",
                client_id=matches[0]["client_id"],
                client_name=matches[0]["client_name"],
                match_type=match_type,
                score=1.0,
            )
        if matches:
            return ClientResolution(
                input=value,
                status="ambiguous",
                match_type=match_type,
                candidates=[ClientCandidate(**c, score=1.0) for c in matches],
            )

    scored = [
        ClientCandidate(**c, score=round(SequenceMatcher(None, norm, normalise(c["client_name"])).ratio(), 3))
        for c in clients
    ]
    suggestions = sorted((c for c in scored if c.score >= FUZZY_THRESHOLD), key=lambda c: -c.score)
    if suggestions:
        return ClientResolution(
            input=value,
            status="ambiguous",
            match_type="fuzzy",
            candidates=suggestions[:MAX_SUGGESTIONS],
        )
    return ClientResolution(input=value, status="not_found")
