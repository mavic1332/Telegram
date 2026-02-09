from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ResolverResult(BaseModel):
    canonical_id: str
    created_at: Optional[datetime] = None
    normalized_identifier: str
    notes_min: Optional[str] = None


class BaseServiceResult(BaseModel):
    id: Optional[str] = None
    phone: Optional[str] = None
    display_name: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    history: List[str] = Field(default_factory=list)
    counters: Dict[str, int] = Field(default_factory=dict)
    extra: Dict[str, str] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None


class ServiceAResult(BaseServiceResult):
    pass


class ServiceBResult(BaseServiceResult):
    pass


class UnifiedResult(BaseModel):
    search_type: str
    identifier_input: str
    canonical_id: str
    created_at: Optional[datetime] = None
    phone: Optional[str] = None
    display_name: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    counters: Dict[str, int] = Field(default_factory=dict)
    history: List[str] = Field(default_factory=list)
    notes: str = ""
    confidence: int = 0
