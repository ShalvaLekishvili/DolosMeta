# File formats and support depth

DolosMeta separates three different claims:

1. **Detection**: a signature or container marker can identify the format.
2. **Native metadata**: a registered parser understands format-specific fields.
3. **Structure**: a registered parser inventories meaningful internal regions.

Detection alone is not advertised as full metadata support. Every file still
receives generic fingerprints, entropy, binary/text classification, bounded
strings, a magic-byte preview, and bounded hex access.

`GET /api/v1/parsers` is the authority for the parsers enabled in a running
instance. Feature gates can disable PDF, archive, or executable analysis. The
UI `/formats` page should derive its claims from that inventory.

## Capability labels

| Label | Meaning |
| --- | --- |
| Full | Native traversal of the format's principal metadata structures and the common tags listed here |
| Good | Native structure and common metadata, with explicitly documented proprietary/complex omissions |
| Basic | Static header or container inventory and selected high-value indicators |
| Generic | Signature/text detection and universal analysis; no specialized metadata claim |

“Full” does not mean every vendor maker note, codec-private atom, proprietary
extension, encrypted object, or future revision of a format.

## Current support matrix

| Format | Detection | Native metadata | Structure | Notes |
| --- | --- | --- | --- | --- |
| JPEG | Yes | Full | Markers and EXIF IFD tree | JFIF, common TIFF/EXIF, GPS, XMP, ICC chunk presence, IPTC-IIM, embedded thumbnail range |
| TIFF | Yes | Full | IFD tree | II/MM classic TIFF and common EXIF/GPS; BigTIFF is detected but not parsed |
| PNG | Yes | Full | Chunk inventory | IHDR, text chunks, eXIf, XMP in iTXt, pHYs, tIME, color/profile presence |
| WebP | Yes | Good | RIFF/WebP chunks | VP8/VP8L/VP8X dimensions, EXIF, XMP, ICC, animation indicators |
| PDF | Yes | Good | Objects and key dictionaries | Info, XMP, pages, encryption/linearization and passive active/embedded-content indicators |
| DOCX/DOCM | ZIP then package refinement | Good | Package parts/relationships | Core, app, custom properties; macro, external relationship, remote-template, OLE/embedded-object indicators |
| XLSX/XLSM | ZIP then package refinement | Good | Package parts/relationships | Document properties, macros and external/embedded indicators; sheet internals are not decoded |
| PPTX/PPTM | ZIP then package refinement | Good | Package parts/relationships | Document properties including declared slide counts, macros and external/embedded indicators |
| MP3 | Yes | Good | ID3 frames and audio boundary | ID3v1 and ID3v2.2/v2.3/v2.4 common frames; bounded cover-art metadata |
| MP4/M4V | `ftyp` brand | Good | ISO BMFF box tree | Movie/track time, timescale, dimensions, handlers, codecs, rotation, common `ilst` metadata |
| MOV | QuickTime `ftyp` brand | Good | ISO BMFF box tree | Container-level QuickTime metadata; not a video-frame decoder |
| M4A | Audio `ftyp` brand | Good | ISO BMFF box tree | Audio track/container metadata; not waveform decoding |
| ZIP | Yes | Basic | Central-directory inventory | Counts, sizes, ratios, timestamps, paths, nesting and traversal indicators; no unbounded recursion |
| GZIP/TAR | Yes where signature/header is present | Basic | Header/member inventory where enabled | Bounded archive inspection; no automatic recursive extraction |
| PE | Yes | Basic | Headers, sections, selected directories | Static inspection only; never loaded or executed |
| ELF | Yes | Basic | ELF/program/section headers | Static architecture, interpreter/library/build identifiers where present |
| Mach-O | Yes | Basic | Header/load commands | Static architecture, linked-library, UUID and signature-presence indicators where present |
| EML | Header heuristics | Good | MIME/header structure | Routing/header and attachment metadata; remote content is never loaded |
| Text/JSON/XML | Yes | Generic | Partial | Encoding/text classification and universal analysis; XML remains non-resolving |
| GIF/BMP | Yes | Generic | Partial | Signature and universal analysis; no full specialized parser claim |
| WAV | Yes | Good | RIFF chunks | Format fields, duration, INFO/BEXT and embedded ID3 metadata |
| AVI | Yes | Good | RIFF chunks | RIFF inventory and INFO metadata; no video-frame decoding |
| FLAC/OGG | Yes | Generic | Partial | Signature and universal analysis; no full specialized parser claim |
| RAR/7Z | Yes | Generic | Partial | Identification only unless a bounded parser is enabled |
| Unknown | Fallback | Generic | Partial | Fingerprints, entropy, strings, magic/hex and mismatch findings |

## JPEG, TIFF, and EXIF

The JPEG parser inventories SOI, APP0, APP1, APP2, APP13, APP14, COM, SOF,
SOS, EOI, and unknown markers. APP1 EXIF is delegated to the bounded TIFF
reader, which supports classic TIFF field types, IFD0, IFD1, ExifIFD, GPSIFD,
InteropIFD, and SubIFD pointers.

Common output includes camera/lens identity, dimensions, orientation,
resolution, exposure, ISO, software, timestamps and offsets, owner/serial
identifiers, decimal GPS coordinates, altitude/time/direction/speed, unknown
tags, and an addressable embedded-thumbnail range. A zero rational denominator
or invalid offset produces a warning rather than a non-finite JSON number.

BigTIFF magic is observed and reported as unsupported by the current TIFF
parser. Vendor maker notes are retained only as bounded unknown/binary metadata
unless an explicit native decoder exists.

## PNG and WebP

PNG chunk CRCs are verified for bounded metadata chunks. Large IDAT data is not
reread merely to recalculate its CRC. Compressed text and profiles share the
global decompression budget. An `eXIf` payload begins directly with TIFF bytes,
unlike JPEG APP1's `Exif\0\0` prefix.

WebP inspection is RIFF/container-level. It recognizes VP8, VP8L, VP8X, EXIF,
XMP, ICCP, and animation chunks. It does not decode pixels or animation frames.

## PDF

PDF analysis is passive. Metadata dictionaries and XMP are parsed when safely
reachable, while encryption, linearization, pages, objects, fonts, images,
AcroForms, JavaScript/actions, and embedded-file references are reported as
indicators. Embedded JavaScript is never run, and PDF content is not rendered
by the backend.

Malformed xref tables or object references may result in partial recovery.
Encrypted files may expose only header/trailer and structural information.

## OOXML

OOXML subtype comes from package contents, not the extension. The parser
inventories `[Content_Types].xml` and package parts, and reads
`docProps/core.xml`, `docProps/app.xml`, `docProps/custom.xml`, and relationship
parts with hardened XML handling.

Macros, remote templates, external hyperlinks, embedded/OLE objects, and
package path anomalies are presence indicators. No macro, link, or embedded
program is executed. Legacy binary `.doc`, `.xls`, and `.ppt` files are not
equivalent to OOXML and receive only whatever generic/signature support the
runtime reports.

## Audio and video

MP3 support focuses on ID3 metadata. Cover art is described with type, media
type, length, and a bounded representation; it is not treated as executable
content. Codec decoding and acoustic analysis are outside this parser.

MP4/MOV/M4A support is ISO Base Media File Format container inspection. The box
tree and selected movie/track/item fields are read without loading `mdat` into
memory. Codec-private bitstreams and frame-level analysis are outside the
current scope.

## Archives

Archive metadata is preferred over extraction. Entry names, size claims,
compression ratios, paths, timestamps, and nested signatures are inspected
under configured count/decompression/depth limits. A nested-archive indicator
does not trigger unlimited recursion. Password-protected content may expose
only its container metadata.

## Executables

Executable support is static metadata inspection. DolosMeta does not map,
launch, emulate, disassemble, or dynamically instrument uploaded binaries.
Signature presence is not a trust decision, and an unusual timestamp or
section is not independently a malware verdict.

## Capability honesty

When adding or removing a parser:

1. update its `ParserDescriptor` and tests;
2. verify `/api/v1/parsers` output;
3. update this matrix and the UI `/formats` page;
4. describe proprietary, encrypted, or malformed limitations explicitly.

Never infer “supported” merely because the detector recognizes magic bytes.
