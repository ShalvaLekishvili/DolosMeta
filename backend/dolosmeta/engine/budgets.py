"""Cooperative resource budgets shared across parsers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List

from dolosmeta.config import Settings

from .errors import AnalysisTimeout, LimitExceeded


@dataclass
class AnalysisBudget:
    settings: Settings
    started: float = field(default_factory=time.monotonic)
    metadata_records: int = 0
    structure_nodes: int = 0
    decompressed_bytes: int = 0
    limits_applied: List[str] = field(default_factory=list)

    def check(self) -> None:
        if time.monotonic() - self.started > self.settings.max_analysis_seconds:
            raise AnalysisTimeout("analysis exceeded the configured wall-clock limit")

    def claim_records(self, count: int = 1) -> None:
        self.check()
        if count < 0 or self.metadata_records + count > self.settings.max_metadata_records:
            self.note("metadata record limit reached")
            raise LimitExceeded("metadata record limit reached")
        self.metadata_records += count

    def claim_nodes(self, count: int = 1) -> None:
        self.check()
        if count < 0 or self.structure_nodes + count > self.settings.max_structure_nodes:
            self.note("structure node limit reached")
            raise LimitExceeded("structure node limit reached")
        self.structure_nodes += count

    def claim_decompressed(self, count: int) -> None:
        self.check()
        if count < 0 or self.decompressed_bytes + count > self.settings.max_decompressed_bytes:
            self.note("decompression limit reached")
            raise LimitExceeded("decompression limit reached")
        self.decompressed_bytes += count

    def depth(self, value: int) -> None:
        self.check()
        if value > self.settings.max_parser_depth:
            self.note("parser recursion depth limit reached")
            raise LimitExceeded("parser recursion depth limit reached")

    def note(self, message: str) -> None:
        if message not in self.limits_applied:
            self.limits_applied.append(message)

