from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.models import ResolverResult, ServiceAResult, ServiceBResult, UnifiedResult


def _pick_recent(a_value, b_value, a_time: Optional[datetime], b_time: Optional[datetime]):
    if a_value and b_value:
        if a_time and b_time:
            return b_value if b_time >= a_time else a_value
        return a_value
    return a_value or b_value


def merge_results(search_type: str, resolver: ResolverResult, a: Optional[ServiceAResult], b: Optional[ServiceBResult]) -> UnifiedResult:
    a = a or ServiceAResult()
    b = b or ServiceBResult()

    phone = _pick_recent(a.phone, b.phone, a.updated_at, b.updated_at)
    display_name = _pick_recent(a.display_name, b.display_name, a.updated_at, b.updated_at)

    counters = dict(a.counters)
    counters.update(b.counters)

    history = sorted(set(a.history + b.history))
    tags = sorted(set(a.tags + b.tags))

    important_values = [resolver.canonical_id, resolver.created_at, phone, display_name, tags, counters, history]
    confidence = min(100, 30 + sum(10 for val in important_values if val))

    return UnifiedResult(
        search_type=search_type,
        identifier_input=resolver.normalized_identifier,
        canonical_id=resolver.canonical_id,
        created_at=resolver.created_at,
        phone=phone,
        display_name=display_name,
        tags=tags,
        counters=counters,
        history=history,
        notes="Alcune informazioni potrebbero non essere disponibili" if not (a.id and b.id) else "",
        confidence=confidence,
    )
