"""Read-only source adapters."""

from .adapters import DirectoryAdapter, IsoAdapter, TarAdapter, ZipAdapter, adapter_for

__all__ = ["DirectoryAdapter", "IsoAdapter", "TarAdapter", "ZipAdapter", "adapter_for"]
