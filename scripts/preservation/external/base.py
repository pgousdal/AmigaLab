from __future__ import annotations

from abc import ABC, abstractmethod
from .models import ExternalItem, ExternalSource


class ExternalProvider(ABC):
    @abstractmethod
    def inspect(self, source: ExternalSource, *, page_size: int = 50, page: int = 1) -> tuple[dict[str, object], tuple[ExternalItem, ...], bool]:
        """Return collection metadata, normalized items, and completion flag."""
