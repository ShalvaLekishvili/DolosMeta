"""Bounded RFC 5322/MIME metadata parser; no remote content is loaded."""

from __future__ import annotations

from email import policy
from email.parser import BytesParser
from email.utils import getaddresses

from ..binary import BinaryReader
from .base import OutputBuilder, ParseContext, ParserDescriptor, ParserOutput


class EmailParser:
    descriptor = ParserDescriptor(
        name="Email Parser",
        version="1.0",
        formats=("EML",),
        capability="good",
        description="RFC 5322 headers, routing hops, MIME structure, and attachment inventory",
    )

    def parse(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        builder = OutputBuilder("email", context.budget)
        maximum = min(reader.size, context.budget.settings.max_metadata_block_bytes)
        if maximum < reader.size:
            builder.warn("email.scan_limit", "Email parsing was limited to the configured metadata window")
            context.budget.note("email scan bounded by metadata block limit")
        data = reader.read(0, maximum)
        try:
            message = BytesParser(policy=policy.default).parsebytes(data, headersonly=False)
        except Exception as exc:
            builder.warn("email.malformed", "Email could not be parsed: {}".format(type(exc).__name__), reader.base)
            return builder.output
        root_id = builder.node("RFC 5322 message", "email", reader.base, maximum)
        header_map = (
            ("From", "author"),
            ("To", "author"),
            ("Cc", "author"),
            ("Reply-To", "author"),
            ("Return-Path", "author"),
            ("Subject", "document"),
            ("Date", "time"),
            ("Message-ID", "document"),
            ("User-Agent", "software"),
            ("X-Mailer", "software"),
            ("Authentication-Results", "security"),
        )
        for name, category in header_map:
            for value in message.get_all(name, []):
                builder.record("Email.Header", name, "Email.Header.{}".format(name), str(value)[:16_384], category)
        builder.record("Email.Security", "DKIMSignaturePresent", "Email.Security.DKIMSignaturePresent", bool(message.get_all("DKIM-Signature")), "security")
        received = message.get_all("Received", [])
        for index, value in enumerate(reversed(received)):
            builder.record("Email.Routing", "ReceivedHop", "Email.Routing.Received[{}]".format(index), str(value)[:16_384], "security")
        attachment_count = 0
        part_count = 0
        for part in message.walk():
            part_count += 1
            content_type = part.get_content_type()
            filename = part.get_filename()
            disposition = part.get_content_disposition()
            if filename or disposition == "attachment":
                attachment_count += 1
                builder.record(
                    "Email.Attachment",
                    "Attachment",
                    "Email.Attachment[{}]".format(attachment_count - 1),
                    {"filename": str(filename or "unnamed")[:1024], "content_type": content_type, "transfer_encoding": str(part.get("Content-Transfer-Encoding", ""))[:128]},
                    "security",
                )
            builder.node(
                content_type,
                "mime-part",
                reader.base,
                0,
                root_id,
                {"disposition": disposition, "filename": str(filename)[:1024] if filename else None},
            )
            if part_count >= context.budget.settings.max_structure_nodes:
                builder.warn("email.part_limit", "MIME part inventory was truncated")
                break
        builder.record("Email", "MIMEPartCount", "Email.MIMEPartCount", part_count, "document")
        builder.record("Email", "AttachmentCount", "Email.AttachmentCount", attachment_count, "security")
        return builder.output

