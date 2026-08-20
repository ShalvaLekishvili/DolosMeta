# Security model

## Scope

DolosMeta performs static metadata and structure inspection of untrusted files.
This model covers the local frontend, FastAPI upload boundary, temporary result
store, native parser engine, exporters, CLI, and container defaults.

The preferred deployment is a single trusted operator on loopback. Exposing the
service to untrusted or multiple users changes the threat model and requires
outer authentication, transport security, rate limiting, and stronger parser
isolation.

## Assets to protect

- Uploaded file bytes and extracted metadata.
- Location, device, author, organization, network, and path information.
- Host filesystem contents and credentials.
- Backend CPU, memory, disk capacity, descriptors, and availability.
- Integrity of analysis results and capability claims.
- Other users' active temporary analyses in a shared deployment.

## Trust boundaries

```text
Untrusted browser input
  |  filename, declared MIME, body bytes, query ranges
  v
HTTP/upload boundary
  |  generated IDs, size checks, CORS, response escaping
  v
Temporary storage boundary
  |  read-only parser source, expiry, artifact ranges
  v
Native parser boundary
  |  bounded offsets, budgets, secure XML/decompression
  v
Structured result boundary
  |  strict schema, bounded binary/string values
  v
UI/export boundary
     escaping, pagination, copy/download actions initiated by user
```

Extensions, MIME declarations, archive paths, XML namespaces, timestamps,
object references, relationships, metadata values, and discovered network
addresses remain untrusted after parsing.

## Threats and controls

| Threat | Control |
| --- | --- |
| Filename traversal or shell injection | Server-generated storage names; filenames used only as data; no shell command built from uploads |
| Extension spoofing | Signature/content detection selects parsers; extension and browser MIME are only compared evidence |
| Out-of-bounds reads and huge lengths | `BinaryReader` bounded views, checked arithmetic, metadata-block and output limits |
| Parser cycles or excessive nesting | Shared recursion-depth and elapsed-time budgets |
| Output amplification | Limits on metadata records, structure nodes, strings, hex ranges, batches, and binary previews |
| ZIP/decompression bomb | Central-directory-first inspection, entry/expanded-byte limits, ratio findings, no unlimited recursion |
| Archive extraction escape | No routine extraction; member path and link checks before any future materialization |
| XXE/entity expansion | Hardened XML parsing; DTD, external entity, schema, and network resolution disabled |
| Macro or script execution | Static presence/structure reporting only; no Office, shell, PDF, or interpreter invocation |
| SSRF/DNS leakage | Discovered URLs, remote templates, coordinates, email links, and IPs are never fetched automatically |
| Memory disclosure through raw values | Strict result models and bounded hex/base64 previews |
| Stack trace or host path leakage | Controlled error conversion and generic API error responses |
| Persistent sensitive uploads | Configured expiry and cleanup of temporary bytes, artifacts, and result records |
| Misleading forensic conclusions | Evidence types, source-record links, cautious language, explainable findings and scores |
| Cross-origin browser use | Explicit CORS allow-list; loopback defaults |

## Upload lifecycle

1. Reject a request that exceeds `MAX_UPLOAD_SIZE_MB` while streaming rather
   than after loading it wholly into memory.
2. Allocate a generated analysis/storage identifier.
3. Store only under `TEMP_DIR`; do not concatenate the supplied filename.
4. Open the completed temporary file read-only for analysis.
5. Publish only schema-safe result values and bounded artifact/range access.
6. Set `expires_at` from `UPLOAD_RETENTION_MINUTES`.
7. Delete bytes, artifacts, and cached result state at expiry.

Cleanup should be idempotent and run both periodically and opportunistically on
access. Failure to delete must be logged without including extracted metadata.
Operators should put `TEMP_DIR` on a capacity-limited filesystem.

## Parser behavior

Parsers are passive. They may read file ranges, decode local strings and XML,
and perform bounded decompression. They must not:

- execute the uploaded file or any embedded program;
- open a user-provided path;
- invoke ExifTool, Office, a PDF viewer, media player, shell, or system utility;
- load a remote image, URL, schema, relationship, font, or map tile;
- resolve a hostname or make a DNS request;
- recursively unpack containers without explicit budgets;
- treat a timestamp, signature claim, or author value as verified identity.

Recoverable corruption should add warnings and preserve prior output. Unknown
tags remain visible through safe values. A malformed rational or time must not
produce non-standard JSON numbers such as `NaN` or infinity.

## XML policy

The policy applies to XMP, OOXML, SVG, and every other XML-derived input:

- no DTD processing;
- no external general or parameter entities;
- no XInclude fetching;
- no remote schema or namespace retrieval;
- bounded XML input and output;
- bounded element depth/count where the parser walks recursively.

Namespaces are identifiers, not URLs to fetch. Unknown namespace properties
are displayed rather than resolved.

## Archive policy

Archive listing is preferred over extraction. The engine records compressed and
uncompressed sizes, entry counts, names, timestamps, ratios, and nested archive
indicators from container metadata where possible.

Member names are normalized only for security comparison; the original name is
retained as evidence. Flag:

- parent traversal components;
- POSIX or Windows absolute paths;
- drive-qualified and UNC paths;
- link entries that could escape an extraction root;
- duplicate/conflicting names;
- excessive counts, claimed expansion, ratios, or nesting.

A nested archive indicator does not authorize recursive analysis.

## Active and embedded content

JavaScript, launch/open actions, AcroForms, macros, OLE objects, attachments,
remote templates, external relationships, executables, and embedded thumbnails
are informational indicators. DolosMeta reports their presence, offsets, and
bounded metadata where safe. It does not render or execute them and does not
label their presence alone as malware.

## Frontend and export safety

All file-derived text is rendered as text, not trusted HTML. HTML exports must
escape values and use a restrictive, self-contained representation. Links
discovered in metadata are inert text unless the user deliberately copies
them. Hex and artifact endpoints validate offset/length against both the file
and configured response limits.

The frontend contains no permanent upload history by default. A hosted
frontend must not imply browser-only analysis when it sends bytes to FastAPI.

## Deployment controls

Local defaults bind ports to `127.0.0.1`. Compose additionally uses non-root
users, capability dropping, `no-new-privileges`, and a separate temporary data
volume. Recommended controls for a network service include:

- TLS and authenticated authorization at a reverse proxy;
- strict request and concurrency rate limits;
- per-tenant storage and result authorization;
- container CPU, memory, process, descriptor, and disk quotas;
- short-lived worker processes for parsers;
- security monitoring that excludes raw metadata and file contents;
- routine dependency and base-image updates.

## Residual risks

- Parsers currently share the API process, so a Python interpreter crash or
  native dependency fault can affect the service.
- Cooperative wall-clock checks cannot pre-empt every blocking native call.
- Signature detection can identify a container while encrypted or proprietary
  internals remain unavailable.
- Hashes identify bytes, not their author, safety, or authenticity.
- Scores depend on configurable policy and are not universally calibrated.
- A named Docker volume may persist after container shutdown until explicitly
  removed.

## Security verification

Tests should cover boundary arithmetic, truncation at structural offsets,
declared length/count mutation, cyclic references, DTD/entity payloads,
decompression and entry limits, path traversal, range pagination, expiry, and
wrong-extension parser selection. Representative tests must fail any attempted
subprocess or network use.

See [../TESTING.md](../TESTING.md) and [../SECURITY.md](../SECURITY.md).

