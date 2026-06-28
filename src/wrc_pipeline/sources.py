"""Definition of the WRC "bodies" (the filters on the left of the search page).

These IDs were confirmed by inspecting the live search form. Each body maps to
the ``body=`` query-string parameter accepted by the search endpoint, e.g.::

    /en/search/?decisions=1&from=01/01/2024&to=31/01/2024&body=15376&pageNumber=1
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Body:
    """A tribunal/commission whose decisions we scrape."""

    key: str           # stable slug used in config + storage paths
    site_id: int       # value of the `body=` query parameter
    display_name: str  # human-readable name (stored in metadata)


# Order roughly matches the website's left-hand list.
BODIES: dict[str, Body] = {
    b.key: b
    for b in (
        Body("workplace_relations_commission", 15376, "Workplace Relations Commission"),
        Body("labour_court", 3, "Labour Court"),
        Body("equality_tribunal", 1, "Equality Tribunal"),
        Body("employment_appeals_tribunal", 2, "Employment Appeals Tribunal"),
    )
}


def resolve_bodies(keys: list[str]) -> list[Body]:
    """Resolve config body keys to :class:`Body` objects (all bodies if empty)."""
    if not keys:
        return list(BODIES.values())
    try:
        return [BODIES[k] for k in keys]
    except KeyError as exc:  # pragma: no cover - defensive, surfaces config typos
        raise ValueError(
            f"Unknown body {exc.args[0]!r}. Valid keys: {sorted(BODIES)}"
        ) from exc
