from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class RecipeCandidate:
    url: str
    priority: int = 0

    def __hash__(self):
        return hash(self.url)

    def __eq__(self, other):
        return self.url == other.url if isinstance(other, RecipeCandidate) else self.url == other


@dataclass
class SiteStats:
    site_url: str
    recipes_found: int = 0
    recipes_imported: int = 0
    recipes_rejected: int = 0
    errors: int = 0
    last_run: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)
