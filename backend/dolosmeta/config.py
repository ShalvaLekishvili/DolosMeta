"""Configuration loaded exclusively from local environment variables."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple


def _integer(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("{} must be an integer".format(name)) from exc
    if value < minimum:
        raise ValueError("{} must be at least {}".format(name, minimum))
    return value


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    temp_dir: Path
    max_upload_bytes: int
    upload_retention_seconds: int
    max_metadata_block_bytes: int
    max_string_scan_bytes: int
    max_decompressed_bytes: int
    max_archive_entries: int
    max_parser_depth: int
    max_metadata_records: int
    max_structure_nodes: int
    max_strings: int
    max_analysis_seconds: int
    max_hex_length: int
    max_batch_files: int
    enable_pdf: bool
    enable_archive: bool
    enable_executable: bool
    allowed_origins: Tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        configured_tmp = os.getenv("TEMP_DIR")
        temp_dir = (
            Path(configured_tmp).expanduser().resolve()
            if configured_tmp
            else Path(tempfile.gettempdir()).resolve() / "dolosmeta"
        )
        origins = tuple(
            item.strip()
            for item in os.getenv(
                "CORS_ORIGINS",
                "http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:8080,http://localhost:8080",
            ).split(",")
            if item.strip()
        )
        return cls(
            app_name=os.getenv("APP_NAME", "DolosMeta"),
            app_env=os.getenv("APP_ENV", "development"),
            temp_dir=temp_dir,
            max_upload_bytes=_integer("MAX_UPLOAD_SIZE_MB", 250) * 1024 * 1024,
            upload_retention_seconds=_integer("UPLOAD_RETENTION_MINUTES", 15) * 60,
            max_metadata_block_bytes=_integer("MAX_METADATA_BLOCK_MB", 32) * 1024 * 1024,
            max_string_scan_bytes=_integer("MAX_STRING_SCAN_MB", 64) * 1024 * 1024,
            max_decompressed_bytes=_integer("MAX_DECOMPRESSED_SIZE_MB", 500) * 1024 * 1024,
            max_archive_entries=_integer("MAX_ARCHIVE_ENTRIES", 10_000),
            max_parser_depth=_integer("MAX_PARSER_RECURSION_DEPTH", 32),
            max_metadata_records=_integer("MAX_METADATA_RECORDS", 20_000),
            max_structure_nodes=_integer("MAX_STRUCTURE_NODES", 20_000),
            max_strings=_integer("MAX_EXTRACTED_STRINGS", 5_000),
            max_analysis_seconds=_integer("MAX_ANALYSIS_SECONDS", 45),
            max_hex_length=_integer("MAX_HEX_RANGE_BYTES", 65_536),
            max_batch_files=_integer("MAX_BATCH_FILES", 20),
            enable_pdf=_boolean("ENABLE_PDF_ANALYSIS", True),
            enable_archive=_boolean("ENABLE_ARCHIVE_ANALYSIS", True),
            enable_executable=_boolean("ENABLE_EXECUTABLE_ANALYSIS", True),
            allowed_origins=origins,
        )


settings = Settings.from_env()

