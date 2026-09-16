"""Shared configuration for file-system tools."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class FileToolConfig:
    """Configuration shared by every file-system tool.

    - ``allowed_roots``: directories the tool is permitted to operate inside.
      An empty tuple (the default) means *all* file operations are rejected —
      a fail-closed policy.
    - ``read_max_bytes``: maximum number of bytes a read-type tool will accept.
    - ``write_max_bytes``: maximum number of bytes a write-type tool will accept
      (for both the content payload and the resulting file).
    - ``max_search_results``: hard cap on the number of search matches
      returned regardless of the caller-requested limit.
    """

    allowed_roots: tuple[Path, ...] = ()
    read_max_bytes: int = 65_536
    write_max_bytes: int = 65_536
    max_search_results: int = 50