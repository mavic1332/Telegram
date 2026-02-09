from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class UserProfile:
    identifier: Optional[str] = None
    phone: Optional[str] = None
    registration: Optional[str] = None
    history: List[str] = field(default_factory=list)
    groups: List[str] = field(default_factory=list)
    bot_data: List[str] = field(default_factory=list)


@dataclass
class RawBotResponses:
    botfindinformation: str = ''
    wow_myai: str = ''
    bot_a_wait_until: Optional[str] = None
    bot_a_retry_after: Optional[str] = None
    bot_a_seconds: Optional[float] = None
    bot_b_seconds: Optional[float] = None
    bot_a_phone: Optional[str] = None
    profile: UserProfile = field(default_factory=UserProfile)

    def as_dict(self) -> Dict[str, str]:
        return {
            'bot_a': self.botfindinformation,
            'bot_b': self.wow_myai,
        }


@dataclass
class SearchResult:
    target: str
    lines: List[str]
    elapsed_ms: int
    status: str
    bot_a_seconds: Optional[float]
    bot_b_seconds: Optional[float]
