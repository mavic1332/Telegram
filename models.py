from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class RawBotResponses:
    botfindinformation: str = ''
    wow_myai: str = ''
    bot_a_wait_until: Optional[str] = None

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
