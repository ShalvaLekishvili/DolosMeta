# Architecture

## Purpose and constraints

DolosMeta is a local-first metadata and file-structure analyzer. Its central
constraint is that metadata extraction belongs to this codebase: no ExifTool
executable, wrapper, or vendored ExifTool package participates in analysis.
Standard libraries may provide low-level decompression, XML decoding, or HTTP
serving, but format traversal, normalization, and interpretation are native
DolosMeta behavior.

Files are untrusted. The system favors partial, evidence-linked results over
all-or-nothing parsing and applies shared budgets before parser output reaches
the API or UI.

## Runtime topology

```text
                         local or explicitly configured network boundary
  +----------------+          +-------------------------------------------+
  | vinext / React |  HTTP    | FastAPI                                   |
  | UI, port 8080  +--------->| upload validation and temporary results   |
  +----------------+          +----------------------+--------------------+
                                                   |
  +----------------+                               v
  | CLI            +--------------------> analysis service
  +----------------+                               |
                                                   v
                                       signature detector
                                                   |
                                                   v
                                         parser registry
                                                   |
                         +-------------------------+-----------------------+
                         | native bounded parser selected by detected type |
                         +-------------------------+-----------------------+
                                                   |
                                                   v
                              normalize -> timeline -> privacy/forensics
                                                   |
                                                   v
                                    versioned `AnalysisResult`
```

The UI and API are separate processes. A hosted Sites frontend does not imply a
hosted analysis service; its `NEXT_PUBLIC_API_BASE_URL` must point to a backend
the operator intentionally deploys.

## Backend layers

### File boundary

The API streams an upload into a generated temporary location, enforces the
configured size ceiling, and retains the original filename only as display
metadata. The user-provided name never selects a server path. An analysis ID
addresses the temporary result and any safe artifacts until expiry.

### Detector

`dolosmeta.engine.detector` examines signatures and container markers. It
returns a `DetectionResult` with format, MIME type, confidence, recognized
extensions, and binary/text classification. Extension and declared MIME values
remain corroborating evidence and can produce mismatch findings; they do not
select a parser.

### Binary access

`FileSource` provides read-only random access without shared seek state.
`BinaryReader` creates bounded views and rejects negative or out-of-range reads.
Parsers operate on readers rather than unrestricted filesystem handles.

### Parser registry

`ParserRegistry` is an explicit allow-list. Each parser has a
`ParserDescriptor` containing its name, version, supported detected formats,
capability level, and description. The registry prevents two parsers from
claiming the same detected format accidentally.

A parser receives a bounded reader and `ParseContext`. It returns only a
`ParserOutput` containing metadata records, structure nodes, warnings,
artifacts, and optional format/MIME refinement. Parser exceptions in the
controlled error hierarchy become partial-result warnings at the analysis
boundary.

### Shared resource budget

`AnalysisBudget` cooperatively limits:

- elapsed analysis time;
- parser recursion depth;
- metadata-record and structure-node counts;
- decompressed bytes.

Settings additionally bound upload bytes, metadata block size, archive entries,
string scanning/output, hex ranges, and batch size. Limit application is
recorded in `AnalysisResult.limits_applied` so callers can distinguish absence
of metadata from intentionally bounded analysis.

### Normalization and evidence

Raw `MetadataRecord` objects remain the source of truth. Normalized fields
reference their source record IDs and are grouped into file, media, camera,
lens, location, timestamps, software, author, document, audio, video, and
security domains.

Timeline events and findings distinguish:

- `observed`: directly stored in the uploaded file;
- `derived`: mechanically calculated from observed values;
- `inference`: a bounded interpretation that is not itself a stored fact.

Privacy and forensic scores are explanations over findings, not claims that a
file is authentic or malicious.

### Temporary result service

The result service exposes retrieval, focused metadata/structure/strings views,
bounded hex ranges, and exports. Records and artifacts carry expiry times and
are removed after the configured retention interval. Duplicate SHA-256 values
may reuse a live session result when safe; they are not permanent user tracking.

## Frontend

The frontend uses React with vinext and a Sites-compatible Cloudflare Worker
entry point. It consumes only the versioned API model and does not embed parser
logic. Its principal routes are:

```text
/                     upload and analysis entry
/analysis/[id]        result dashboard
/batch                multi-file analysis
/compare              two-file comparison
/formats              runtime capability explanation
/engine               native-engine architecture
/privacy              retention and privacy behavior
```

The result dashboard presents relevant tabs only. Search, filters, copy actions,
structure, strings, hex pagination, findings, and exports operate on values
returned from real analyses rather than demonstration metadata.

## Request sequence

```text
1. Browser uploads bytes, name, and browser MIME declaration.
2. API enforces body limits and assigns a server-controlled temporary name.
3. Analysis computes hashes and reads signature/header data.
4. Detector identifies content and records extension/MIME agreement.
5. Registry selects the applicable native parser.
6. Parser performs bounded random-access traversal and returns partial output.
7. Engine normalizes records and builds timeline/privacy/forensic findings.
8. Result receives schema, engine, parser, creation, and expiry versions.
9. API returns the result ID and structured analysis.
10. UI requests only needed views or bounded byte ranges.
11. Cleanup removes expired bytes, artifacts, and results.
```

No step contacts a discovered URL, resolves a domain, executes an attachment,
macro, program, or PDF action, or sends coordinates to a map provider.

## Deployment modes

### Local launcher

`start.sh` installs missing dependencies, creates the configured temporary
directory, starts FastAPI at `127.0.0.1:8000`, and starts vinext at
`127.0.0.1:8080`. Signals are forwarded to both child processes.

### Containers

Compose builds independent frontend and backend images. The backend runs as a
non-root user with dropped capabilities and stores temporary files in a named
volume. Published ports bind to loopback by default. The frontend API base URL
is a build argument because browser code must know the reachable backend URL.

### Future parser workers

Parsers are not coupled to FastAPI request objects. `BinaryReader`,
`ParseContext`, `ParserOutput`, and the public models form a serialization-ready
boundary for moving expensive parsers into short-lived worker processes. That
future design should add OS-level CPU, memory, descriptor, and wall-clock
limits; it should preserve the current public result schema.

## Design invariants

- The detector, not the filename, selects the parser.
- Every read is bounded by the source or a narrower subreader.
- Unknown metadata is represented safely rather than silently discarded.
- Raw binary values use length and bounded previews.
- Parser failure does not erase generic fingerprints already obtained.
- Raw records remain traceable from normalized fields and findings.
- Public schemas and parser versions are explicit for reproducibility.
- UI capability claims follow the runtime registry.

