from datetime import datetime, timezone

from app.merge import merge_results
from app.models import ResolverResult, ServiceAResult, ServiceBResult


def test_merge_prefers_recent_and_unions():
    resolver = ResolverResult(canonical_id="CID-1", created_at=datetime.now(timezone.utc), normalized_identifier="@u")
    a = ServiceAResult(display_name="Nome A", phone="+391", tags=["a"], history=["h1"], counters={"x": 1})
    b = ServiceBResult(display_name="Nome B", phone="+392", tags=["b"], history=["h1", "h2"], counters={"y": 2})
    merged = merge_results("Telegram", resolver, a, b)
    assert merged.canonical_id == "CID-1"
    assert set(merged.tags) == {"a", "b"}
    assert merged.counters["x"] == 1
    assert merged.counters["y"] == 2
    assert merged.history == ["h1", "h2"]
