"""Static native PE, ELF, and Mach-O header inspection; files are never executed."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from ..binary import BinaryReader
from ..errors import BoundsError, LimitExceeded
from .base import OutputBuilder, ParseContext, ParserDescriptor, ParserOutput, safe_text


PE_MACHINES = {0x014C: "x86", 0x8664: "x86-64", 0x01C0: "ARM", 0xAA64: "ARM64"}
ELF_MACHINES = {3: "x86", 8: "MIPS", 20: "PowerPC", 40: "ARM", 62: "x86-64", 183: "AArch64", 243: "RISC-V"}
MACH_CPU = {7: "x86", 0x01000007: "x86-64", 12: "ARM", 0x0100000C: "ARM64"}


class ExecutableParser:
    descriptor = ParserDescriptor(
        name="Executable Parser",
        version="1.0",
        formats=("PE", "ELF", "Mach-O", "Mach-O Universal"),
        capability="basic",
        description="Static executable headers, sections/load commands, linkage, IDs, and signature presence",
    )

    def parse(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        if context.detection.format == "PE":
            return self._pe(reader, context)
        if context.detection.format == "ELF":
            return self._elf(reader, context)
        return self._macho(reader, context)

    def _pe(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        builder = OutputBuilder("pe", context.budget)
        root_id = builder.node("Portable Executable", "executable", reader.base, reader.size)
        try:
            if reader.size < 64 or reader.read(0, 2) != b"MZ":
                raise BoundsError("DOS header is missing or truncated")
            pe_offset = reader.u32(0x3C, "<")
            if pe_offset > reader.size - 24 or reader.read(pe_offset, 4) != b"PE\x00\x00":
                raise BoundsError("PE signature offset is invalid")
            coff = pe_offset + 4
            machine = reader.u16(coff, "<")
            section_count = reader.u16(coff + 2, "<")
            timestamp = reader.u32(coff + 4, "<")
            optional_size = reader.u16(coff + 16, "<")
            characteristics = reader.u16(coff + 18, "<")
            builder.node("DOS header", "header", reader.base, min(pe_offset, reader.size), root_id)
            pe_id = builder.node("PE/COFF header", "header", reader.base + pe_offset, min(24 + optional_size, reader.size - pe_offset), root_id)
            for name, value in (
                ("Machine", PE_MACHINES.get(machine, "0x{:04X}".format(machine))),
                ("NumberOfSections", section_count),
                ("Timestamp", datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z") if timestamp else None),
                ("Characteristics", "0x{:04X}".format(characteristics)),
            ):
                builder.record("PE", name, "PE.{}".format(name), value, "executable" if name != "Timestamp" else "time")
            optional = coff + 20
            if optional_size >= 70 and optional_size <= reader.size - optional:
                magic = reader.u16(optional, "<")
                is_64 = magic == 0x20B
                if magic not in {0x10B, 0x20B}:
                    builder.warn("pe.optional_magic", "Unknown PE optional-header magic", reader.base + optional)
                entry = reader.u32(optional + 16, "<")
                image_base = reader.u64(optional + 24, "<") if is_64 else reader.u32(optional + 28, "<")
                subsystem = reader.u16(optional + 68, "<")
                builder.record("PE", "Class", "PE.Class", "PE32+" if is_64 else "PE32", "executable")
                builder.record("PE", "EntryPoint", "PE.EntryPoint", "0x{:X}".format(entry), "executable")
                builder.record("PE", "ImageBase", "PE.ImageBase", "0x{:X}".format(image_base), "executable")
                builder.record("PE", "Subsystem", "PE.Subsystem", subsystem, "executable")
                directory_offset = optional + (112 if is_64 else 96)
                if directory_offset + 8 * 5 <= optional + optional_size:
                    for index, name in ((0, "ExportDirectory"), (1, "ImportDirectory"), (4, "SecurityDirectory")):
                        rva = reader.u32(directory_offset + index * 8, "<")
                        size = reader.u32(directory_offset + index * 8 + 4, "<")
                        builder.record("PE", name, "PE.{}".format(name), {"address": rva, "size": size, "present": bool(rva and size)}, "security" if index == 4 else "executable")
            section_table = optional + optional_size
            if section_count > 96:
                builder.warn("pe.section_limit", "PE section count exceeds the safety limit")
                section_count = 96
            for index in range(section_count):
                position = section_table + index * 40
                if position > reader.size - 40:
                    builder.warn("pe.truncated_sections", "PE section table is truncated", reader.base + min(position, reader.size))
                    break
                name = safe_text(reader.read(position, 8), "ascii", 8) or "section_{}".format(index)
                builder.node(name, "section", reader.base + position, 40, pe_id, {"virtual_size": reader.u32(position + 8, "<"), "virtual_address": reader.u32(position + 12, "<"), "raw_size": reader.u32(position + 16, "<"), "raw_offset": reader.u32(position + 20, "<"), "characteristics": "0x{:08X}".format(reader.u32(position + 36, "<"))})
        except (BoundsError, OSError, ValueError) as exc:
            builder.warn("pe.malformed", "PE inspection stopped safely: {}".format(str(exc)), reader.base)
        return builder.output

    def _elf(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        builder = OutputBuilder("elf", context.budget)
        root_id = builder.node("ELF", "executable", reader.base, reader.size)
        try:
            if reader.size < 52 or reader.read(0, 4) != b"\x7fELF":
                raise BoundsError("ELF header is missing or truncated")
            elf_class = reader.u8(4)
            endian_code = reader.u8(5)
            endian = "<" if endian_code == 1 else ">"
            if elf_class not in {1, 2} or endian_code not in {1, 2}:
                raise BoundsError("invalid ELF class or byte order")
            machine = reader.u16(18, endian)
            if elf_class == 2:
                entry = reader.u64(24, endian)
                phoff, shoff = reader.u64(32, endian), reader.u64(40, endian)
                phentsize, phnum = reader.u16(54, endian), reader.u16(56, endian)
                shentsize, shnum, shstrndx = reader.u16(58, endian), reader.u16(60, endian), reader.u16(62, endian)
            else:
                entry = reader.u32(24, endian)
                phoff, shoff = reader.u32(28, endian), reader.u32(32, endian)
                phentsize, phnum = reader.u16(42, endian), reader.u16(44, endian)
                shentsize, shnum, shstrndx = reader.u16(46, endian), reader.u16(48, endian), reader.u16(50, endian)
            for name, value in (
                ("Class", "64-bit" if elf_class == 2 else "32-bit"),
                ("Endianness", "little" if endian == "<" else "big"),
                ("Architecture", ELF_MACHINES.get(machine, machine)),
                ("EntryPoint", "0x{:X}".format(entry)),
                ("ProgramHeaderCount", phnum),
                ("SectionHeaderCount", shnum),
            ):
                builder.record("ELF", name, "ELF.{}".format(name), value, "executable")
            for index in range(min(phnum, 256)):
                position = phoff + index * phentsize
                if phentsize == 0 or position > reader.size - phentsize:
                    break
                p_type = reader.u32(position, endian)
                p_offset = reader.u64(position + 8, endian) if elf_class == 2 else reader.u32(position + 4, endian)
                p_filesz = reader.u64(position + 32, endian) if elf_class == 2 else reader.u32(position + 16, endian)
                if p_type == 3 and p_offset <= reader.size and p_filesz <= reader.size - p_offset:
                    interpreter = safe_text(reader.read(p_offset, min(p_filesz, 4096)), "utf-8")
                    builder.record("ELF", "Interpreter", "ELF.Interpreter", interpreter, "executable", offset=reader.base + p_offset, length=p_filesz)
                builder.node("ProgramHeader[{}]".format(index), "program-header", reader.base + position, phentsize, root_id, {"type": p_type, "file_offset": p_offset, "file_size": p_filesz})
            if shnum > 4096:
                builder.warn("elf.section_limit", "ELF section count exceeds the safety limit")
                shnum = 4096
            sections: List[Dict[str, int]] = []
            for index in range(shnum):
                position = shoff + index * shentsize
                if shentsize == 0 or position > reader.size - shentsize:
                    break
                if elf_class == 2:
                    sections.append({"name": reader.u32(position, endian), "type": reader.u32(position + 4, endian), "offset": reader.u64(position + 24, endian), "size": reader.u64(position + 32, endian), "link": reader.u32(position + 40, endian), "entsize": reader.u64(position + 56, endian)})
                else:
                    sections.append({"name": reader.u32(position, endian), "type": reader.u32(position + 4, endian), "offset": reader.u32(position + 16, endian), "size": reader.u32(position + 20, endian), "link": reader.u32(position + 24, endian), "entsize": reader.u32(position + 36, endian)})
            names = b""
            if shstrndx < len(sections):
                section = sections[shstrndx]
                if section["offset"] <= reader.size and section["size"] <= min(reader.size - section["offset"], context.budget.settings.max_metadata_block_bytes):
                    names = reader.read(section["offset"], section["size"])
            named_sections: Dict[str, Dict[str, int]] = {}
            for index, section in enumerate(sections):
                offset = section["name"]
                name = safe_text(names[offset : offset + 256], "ascii", 256) if offset < len(names) else "section_{}".format(index)
                named_sections[name] = section
                builder.node(name or "section_{}".format(index), "section", reader.base + shoff + index * shentsize, shentsize, root_id, {"type": section["type"], "file_offset": section["offset"], "size": section["size"]})
            dyn = named_sections.get(".dynamic")
            dynstr = named_sections.get(".dynstr")
            if dyn and dynstr and dynstr["offset"] <= reader.size and dynstr["size"] <= min(reader.size - dynstr["offset"], context.budget.settings.max_metadata_block_bytes):
                strings = reader.read(dynstr["offset"], dynstr["size"])
                entry_size = dyn["entsize"] or (16 if elf_class == 2 else 8)
                count = min(4096, dyn["size"] // max(1, entry_size))
                for index in range(count):
                    pos = dyn["offset"] + index * entry_size
                    if pos > reader.size - entry_size:
                        break
                    tag = reader.u64(pos, endian) if elf_class == 2 else reader.u32(pos, endian)
                    value = reader.u64(pos + 8, endian) if elf_class == 2 else reader.u32(pos + 4, endian)
                    if tag == 1 and value < len(strings):
                        library = safe_text(strings[value : value + 4096], "utf-8", 4096)
                        builder.record("ELF", "NeededLibrary", "ELF.NeededLibrary", library, "executable")
                    if tag == 0:
                        break
        except (BoundsError, OSError, ValueError) as exc:
            builder.warn("elf.malformed", "ELF inspection stopped safely: {}".format(str(exc)), reader.base)
        return builder.output

    def _macho(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        builder = OutputBuilder("macho", context.budget)
        root_id = builder.node("Mach-O", "executable", reader.base, reader.size)
        try:
            if reader.size < 28:
                raise BoundsError("Mach-O header is truncated")
            magic = reader.read(0, 4)
            if magic in {b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}:
                endian = ">" if magic == b"\xca\xfe\xba\xbe" else "<"
                count = reader.u32(4, endian)
                builder.record("MachO", "UniversalArchitectureCount", "MachO.UniversalArchitectureCount", count, "executable")
                for index in range(min(count, 64)):
                    pos = 8 + index * 20
                    if pos > reader.size - 20:
                        break
                    cpu = reader.u32(pos, endian)
                    builder.node(MACH_CPU.get(cpu, "CPU_{}".format(cpu)), "architecture", reader.base + pos, 20, root_id)
                return builder.output
            endian = "<" if magic in {b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe"} else ">"
            is_64 = magic in {b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe"}
            if magic not in {b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe"}:
                raise BoundsError("unknown Mach-O magic")
            cpu = reader.u32(4, endian)
            file_type = reader.u32(12, endian)
            commands = reader.u32(16, endian)
            command_bytes = reader.u32(20, endian)
            header_size = 32 if is_64 else 28
            builder.record("MachO", "Architecture", "MachO.Architecture", MACH_CPU.get(cpu, cpu), "executable")
            builder.record("MachO", "FileType", "MachO.FileType", file_type, "executable")
            builder.record("MachO", "LoadCommandCount", "MachO.LoadCommandCount", commands, "executable")
            if command_bytes > reader.size - header_size:
                builder.warn("macho.commands_span", "Mach-O load commands extend outside the file")
                commands = 0
            position = header_size
            for index in range(min(commands, 4096)):
                if position > reader.size - 8:
                    break
                command = reader.u32(position, endian)
                size = reader.u32(position + 4, endian)
                if size < 8 or size > reader.size - position:
                    builder.warn("macho.command_size", "Mach-O load command has an invalid size", reader.base + position)
                    break
                builder.node("LoadCommand[{}]".format(index), "load-command", reader.base + position, size, root_id, {"command": "0x{:X}".format(command)})
                base_command = command & 0x7FFFFFFF
                if base_command in {0xC, 0x18, 0x1F, 0x20, 0x23} and size >= 12:
                    name_offset = reader.u32(position + 8, endian)
                    if name_offset < size:
                        library = reader.cstring(position + name_offset, min(4096, size - name_offset), "utf-8")
                        builder.record("MachO", "LinkedLibrary", "MachO.LinkedLibrary", library, "executable")
                elif base_command == 0x1B and size >= 24:
                    raw_uuid = reader.read(position + 8, 16)
                    uuid = "{}-{}-{}-{}-{}".format(raw_uuid[:4].hex(), raw_uuid[4:6].hex(), raw_uuid[6:8].hex(), raw_uuid[8:10].hex(), raw_uuid[10:].hex())
                    builder.record("MachO", "UUID", "MachO.UUID", uuid, "executable")
                elif base_command == 0x1D:
                    builder.record("MachO", "CodeSignaturePresent", "MachO.CodeSignaturePresent", True, "security")
                position += size
        except (BoundsError, OSError, ValueError) as exc:
            builder.warn("macho.malformed", "Mach-O inspection stopped safely: {}".format(str(exc)), reader.base)
        return builder.output

