# Parser development

This guide describes how to add a native DolosMeta parser without changing API
routes or depending on ExifTool.

## Parser contract

Parsers implement the protocol in `dolosmeta.engine.parsers.base`:

```python
class MetadataParser(Protocol):
    descriptor: ParserDescriptor

    def parse(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        ...
```

The descriptor is both selection metadata and the public capability inventory:

```python
descriptor = ParserDescriptor(
    name="Example",
    version="1.0",
    formats=("EXAMPLE",),
    capability="basic",
    description="Native Example container metadata",
)
```

Use format names emitted by `engine.detector`. If a container can refine a
generic detection—for example ZIP to DOCX—return `format_override` and
`mime_override` from `ParserOutput` rather than trusting the filename.

## Minimal parser

```python
from dolosmeta.engine.binary import BinaryReader
from dolosmeta.engine.parsers.base import (
    OutputBuilder,
    ParseContext,
    ParserDescriptor,
    ParserOutput,
)


class ExampleParser:
    descriptor = ParserDescriptor(
        name="Example",
        version="1.0",
        formats=("EXAMPLE",),
        capability="basic",
        description="Example metadata and structure",
    )

    def parse(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        out = OutputBuilder(self.descriptor.name, context.budget)
        reader.require(reader.size >= 8, "truncated Example header")
        reader.require(reader.read(0, 4) == b"EXMP", "invalid Example signature")

        root = out.node("Example", "container", 0, reader.size)
        version = reader.u16(4, ">")
        out.node("Header", "header", 0, 8, parent_id=root)
        out.record(
            namespace="Example",
            name="Version",
            path="Example.Header.Version",
            value=version,
            category="file",
            tag_id="0x0004",
            description="Example container version",
            offset=4,
            length=2,
        )
        return out.output
```

Register one parser instance in the engine's explicit registry. Registration
fails if another parser already owns the same detected format.

## Safe binary parsing

Use `BinaryReader` exclusively for file access:

- `read(offset, length)` for checked byte ranges;
- `subreader(offset, length)` to confine a nested block;
- `u8`, `u16`, `u32`, `u64`, and signed variants for checked integers;
- explicit `"<"` or `">"` endian arguments when the format requires them;
- `cstring` with a hard maximum;
- `require` for structural invariants.

Before arithmetic, prefer the overflow-safe relationship
`length <= reader.size - offset` after establishing non-negative inputs. Never
allocate directly from an untrusted declared length. Never seek through a raw
file handle behind `BinaryReader`.

Call `context.budget.check()` in long loops, `budget.depth(level)` before nested
traversal, and `budget.claim_decompressed(count)` before retaining decompressed
content. `OutputBuilder` claims record and structure budgets automatically.

## Output rules

### Records

Create one `MetadataRecord` for each raw fact. Paths should be stable and retain
the format namespace, for example:

```text
Exif.Photo.DateTimeOriginal
PNG.tEXt.Author
PDF.Info.Producer
Office.Core.creator
ID3.TIT2
QuickTime.moov.mvhd.timescale
```

Supply offsets and lengths when the bytes are directly addressable. Unknown
tags should use a stable identifier such as `UnknownTag0xC7A1` and preserve a
bounded value.

### Binary values

Pass bytes through `safe_value` or `OutputBuilder.record`. They become a JSON
safe structure containing the original length and a bounded hexadecimal
preview. Do not base64-encode or return an entire large image, profile, macro,
stream, or attachment by default.

### Structure

Every node must have a stable parent relationship and an offset/length within
the file. Nodes describe what was observed, not what the parser expected to
find. Container roots, segments/chunks/boxes, directories, and metadata blocks
should be visible even when their contents are unknown.

### Artifacts

An `Artifact` identifies a safely addressable embedded range, such as an EXIF
thumbnail. It does not authorize executing or automatically rendering active
content. Keep media type, offset, length, and description factual.

### Warnings

Use `OutputBuilder.warn` for recoverable malformed content. Warning codes must
be stable, machine-readable identifiers; messages may be more descriptive.
Include the byte offset when known. Raise a controlled `MalformedFile`,
`BoundsError`, `LimitExceeded`, or `AnalysisTimeout` when safe continuation is
impossible.

Do not catch `Exception` broadly inside low-level loops. The analysis boundary
is responsible for converting controlled parser failures to partial results and
for keeping unexpected faults visible to tests and operators without exposing
them to API clients.

## XML and compressed content

- Use the project's hardened XML helper or `defusedxml`.
- Reject DTD declarations and external entities; do not resolve schemas.
- Never perform network access based on XML attributes or relationships.
- Bound the compressed input before decompression and claim output bytes as
  they are produced.
- Inspect archive central-directory metadata without extraction where possible.
- Treat `../`, absolute, drive-qualified, UNC, and suspicious link targets as
  findings, never extraction destinations.

## Normalization

Parsers emit raw records; centralized normalization maps them to the stable
domains. Add mapping rules rather than writing directly into the API model from
the parser. A normalized field should include every supporting raw record ID
and the correct evidence kind.

When multiple tags disagree, retain all raw values and create an anomaly. Do
not silently choose a convenient value or infer authenticity.

## Tests required for a new parser

1. Build at least one valid fixture programmatically.
2. Assert signature selection with a correct extension, no extension, and a
   misleading extension/MIME declaration.
3. Assert raw records, normalized fields, structure offsets, parser version,
   and relevant findings.
4. Test little/big endian or format versions when applicable.
5. Truncate at structural boundaries.
6. Mutate length, count, and offset fields to zero, undersized, and oversized
   values.
7. Exercise recursion, decompression, output-count, and elapsed-time budgets.
8. Verify unknown tags remain visible and binary values stay bounded.
9. Confirm results serialize without `NaN`, infinity, traceback, or host paths.
10. Add an API upload test and a CLI JSON test using the same fixture.

See [../TESTING.md](../TESTING.md) for the shared fixture matrix.

## Review checklist

- No ExifTool executable, wrapper, subprocess, or external metadata API.
- No code execution, macro execution, PDF action execution, URL fetch, or DNS
  request.
- All parser-controlled loops check bounds and budgets.
- All XML and decompression use hardened bounded helpers.
- Unknown fields and recoverable corruption produce useful output.
- Capability description reflects tested depth rather than intended future
  support.
- Documentation and `/api/v1/parsers` are updated together.

