# Metadata model

DolosMeta returns one strict, versioned `AnalysisResult` from its engine, API,
CLI JSON mode, and JSON exporter. Parser-specific records are preserved while a
separate normalized layer gives clients stable concepts across formats.

## Versioning

Every result contains:

- `analysis_version`: the analysis/report format version;
- `schema_version`: the public model version;
- `engine`: engine name and implementation version;
- `parsers`: every parser run, its version, status, record count, and warning
  count;
- `parser`: the primary parser summary for compact clients.

Additive optional fields may appear within a compatible schema version. A
rename, removal, type change, or semantic change requires a new schema version.
Clients should ignore unknown additive properties only after validating the
declared schema version.

## Top-level shape

```json
{
  "id": "analysis-id",
  "analysis_version": "1.0",
  "schema_version": "1.0",
  "state": "complete",
  "created_at": "2026-08-20T14:31:20Z",
  "expires_at": "2026-08-20T14:46:20Z",
  "engine": {"name": "DolosMeta Engine", "version": "1.0.0"},
  "file": {},
  "hashes": {},
  "metrics": {},
  "metadata": [],
  "normalized": {},
  "structure": [],
  "strings": [],
  "timeline": [],
  "artifacts": [],
  "privacy": {},
  "forensics": {},
  "parsers": [],
  "parser": {},
  "limits_applied": []
}
```

`state` distinguishes a complete result from a partial or failed specialized
parse. Even a partial result should retain safely computed generic properties
and parser warnings.

## File identity

`file` records supplied and detected identity separately:

```json
{
  "name": "holiday.png",
  "size": 4821190,
  "extension": "png",
  "declared_mime": "image/png",
  "mime": "image/jpeg",
  "detected_format": "JPEG",
  "signature": "JPEG SOI",
  "signature_match": false,
  "magic_hex": "ffd8ffe1001c457869660000",
  "binary": true,
  "upload_session_created": "2026-08-20T14:31:20Z"
}
```

`name` is display data. It is not a storage path. `mime` and `detected_format`
come from content detection; `declared_mime` and `extension` are untrusted
upload claims. `signature_match` can be `null` when there is no meaningful
extension comparison.

## Fingerprints and metrics

`hashes` contains lowercase hexadecimal SHA-256, SHA-512, SHA-1, and MD5
values. SHA-256 is the primary fingerprint. SHA-1 and MD5 are legacy
identification values and must not be presented as collision-resistant
integrity assurances.

`metrics.entropy` is Shannon entropy in the inclusive range 0–8 and
`entropy_level` is its display interpretation. High entropy can indicate
compression, encryption, packed data, or multimedia; it is not a malware
verdict.

## Raw metadata records

`metadata` is a list rather than a dictionary so duplicate or contradictory
tags remain observable:

```json
{
  "id": "JPEG:r17",
  "namespace": "Exif",
  "name": "DateTimeOriginal",
  "path": "Exif.Photo.DateTimeOriginal",
  "value": "2026:08:20 18:31:20",
  "display_value": "2026-08-20 18:31:20",
  "tag_id": "0x9003",
  "category": "time",
  "description": "Date and time reported for original image capture",
  "offset": 324,
  "length": 20,
  "parser": "JPEG",
  "evidence": "observed"
}
```

`path` is a stable parser namespace path. `id` is unique within the result and
is used by normalized values, findings, and timeline events. Offsets and
lengths are optional when a value is derived from container semantics rather
than one contiguous range.

Unknown metadata is retained with a generated name/tag identifier. Binary data
is JSON-safe and bounded:

```json
{
  "type": "binary",
  "length": 3381,
  "preview_hex": "ffd8ffe1..."
}
```

An optional `base64` value is permitted only for deliberately bounded data.
Large embedded bytes belong behind an artifact/range endpoint, not inline in
the result.

## Normalized metadata

The normalized object groups stable concepts:

```text
file, media, camera, lens, location, timestamps, software,
author, document, audio, video, security
```

Each domain is a map of names to `NormalizedField`:

```json
{
  "value": 41.7200277778,
  "display_value": "41.720028° N",
  "unit": "degrees",
  "source_record_ids": ["JPEG:r31", "JPEG:r32"],
  "evidence": "derived"
}
```

Examples of stable paths include:

```text
file.name                  media.width
camera.make                camera.model
camera.serial              lens.make
lens.model                 location.latitude
location.longitude         location.altitude
timestamps.created         timestamps.modified
timestamps.captured        software.creator
software.producer          author.name
document.company           audio.title
video.duration             security.encrypted
```

Raw values are not removed after normalization. When sources disagree,
DolosMeta retains all records, identifies the inconsistency, and avoids
silently treating one claim as authoritative.

## Structure and artifacts

Each `StructureNode` has an ID, optional parent ID, label, kind, absolute byte
offset, byte length, and bounded details map. A node range must remain inside
the source file. The flat parent-linked representation is convenient for JSON
and can be rendered as a tree by clients.

`Artifact` represents an addressable embedded region:

```json
{
  "id": "JPEG:a1",
  "name": "Embedded EXIF thumbnail",
  "media_type": "image/jpeg",
  "offset": 1042,
  "length": 3971,
  "description": "JPEG thumbnail referenced by IFD1"
}
```

Artifacts are observations, not an instruction to execute active content.

## Strings

Each string item contains value, category, encoding, and byte offset. Supported
categories can include URLs, domains, IP addresses, email addresses, paths,
registry paths, usernames, software names, and generic strings. Output count,
input scan bytes, and individual display length are bounded. No discovered
network value is contacted.

## Timeline

A timeline event retains both the exact raw timestamp and an optional ISO
normalization:

```json
{
  "id": "timeline:3",
  "timestamp_raw": "2026:08:20 18:31:20",
  "timestamp_iso": "2026-08-20T18:31:20+04:00",
  "timezone_known": true,
  "label": "Original capture time reported by EXIF",
  "category": "capture",
  "source_record_ids": ["JPEG:r17", "JPEG:r18"],
  "evidence": "derived"
}
```

An absent timezone must not be silently interpreted as UTC or server local
time. Impossible timestamps remain raw records and produce warnings/anomalies.

## Privacy and forensics

Both sections contain a score from 0–100, a display level, and findings. The
forensics section also contains parser warnings and anomalies.

A finding includes a stable code, factual title/message, category, severity,
configured point contribution, and supporting record IDs. Scores must be
explainable as the bounded composition of their findings.

Warnings contain a stable code, parser name, recoverability state, message, and
optional byte offset. Warnings describe parse limitations; they do not imply
maliciousness.

## Evidence vocabulary

| Kind | Meaning | Example |
| --- | --- | --- |
| `observed` | Directly represented in file bytes | EXIF latitude rational values |
| `derived` | Deterministic calculation from observations | Decimal GPS coordinate or aspect ratio |
| `inference` | Analytical interpretation with uncertainty | Potential timestamp inconsistency |

UI copy should use language such as “the file reports” or “metadata indicates.”
It should not replace these distinctions with claims of proof.

## Limits and compatibility

`limits_applied` lists resource bounds reached during analysis. Clients must
not interpret a missing value as definitively absent when a relevant limit was
applied or parser status is partial.

Exports preserve schema and engine versions. CSV necessarily flattens nested
data and therefore is not a lossless replacement for JSON. TXT and HTML are
human-readable reports; they must escape untrusted metadata before display.

