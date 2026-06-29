import re
from typing import Any

from config import Settings


def _parse_database_url(url: str) -> dict[str, Any]:
    """Extract connection params from SQLAlchemy database URL.
    Handles both asyncpg and psycopg2 URL formats."""
    pattern = r"postgresql(?:\+asyncpg)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)"
    match = re.match(pattern, url)
    if not match:
        raise ValueError(f"Cannot parse database URL: {url}")
    return {
        "user": match.group(1),
        "password": match.group(2),
        "host": match.group(3),
        "port": int(match.group(4)),
        "dbname": match.group(5),
    }


def create_age_graph(settings: Settings) -> Any:
    """Create AGEGraph connection to the AGE database container.
    Wraps in AgeGraphWrapper for GraphCypherQAChain compatibility.
    """
    from langchain_community.graphs.age_graph import AGEGraph

    from graph.age_wrapper import AgeGraphWrapper

    conf = _parse_database_url(settings.age_database_url)
    age = AGEGraph(graph_name="doc_graph", conf=conf, create=True)
    return AgeGraphWrapper(age)


_cached_age_graph: Any | None = None


def get_age_graph(settings: Settings) -> Any:
    """Return cached AGE graph connection with health check + reconnect."""
    global _cached_age_graph

    if _cached_age_graph is None:
        _cached_age_graph = create_age_graph(settings)
        return _cached_age_graph

    try:
        _cached_age_graph.query("RETURN 1", {})
    except Exception:
        _cached_age_graph = create_age_graph(settings)

    return _cached_age_graph
