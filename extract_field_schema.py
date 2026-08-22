#!/usr/bin/env python3
"""
Static extractor for the real Core::igMetaObject / Core::igMetaField field
schema (class name -> ordered list of {field_name, meta_field_type}),
pulled directly out of Arkchemy's own recompiled C source -- no running
game required.

Why this works at all: every Alchemy engine class that participates in
the igz reflection system has a compiler-generated
`arkRegisterInitialize__Q2_4Core<N><ClassName>SFv` static function that
registers that class's own fields, one at a time, by calling real
functions like `setMetaFieldBasicPropertiesAndValidateAll` or a
per-type `setDefault__Q2_4Core<N><FieldType>MetaFieldF...`. Each call is
preceded by a `lis`/`addi` pair loading the field's real NAME STRING
address (a real pointer into the game's own .rodata), which Arkchemy's
recompiler (recomp/src/codegen.cpp) already resolves at compile time and
prints as a `/* &.rodata+OFFSET */` comment -- OFFSET being the real,
plain byte offset from the start of the real .rodata section's content,
not a synthetic Arkchemy-internal address (see assign_global_addrs in
recomp/src/elf_loader.cpp for why the numeric ctx->r[] value itself is
*not* directly usable here: it's a Arkchemy-synthetic PpcContext::mem
address, unrelated to the real game's .rodata layout -- only the human-
readable comment preserves the real section+offset).

This script:
  1. Reads the real tfbGame_cafe.rpx (RPL-zlib-decompressing sections as
     needed -- same logic as recomp/src/elf_loader.cpp, reimplemented
     here in Python since this is a standalone analysis tool, not part
     of the C++ recompiler itself).
  2. Scans every switch/game/source/generated_*.c file for
     `ppc_arkRegisterInitialize__...` function bodies.
  3. Within each, finds every field-registration call and resolves its
     preceding `&.rodata+OFFSET` field-name comment to the real string
     by reading that offset directly out of the real .rodata bytes.
  4. Also records the real meta-field *type* class name (e.g.
     `igBoolMetaField`, `igSizeTypeMetaField`) on the minority of
     registrations where a `setDefault__*MetaField*` call for that
     specific field is inlined directly into the same
     `arkRegisterInitialize` body right before the name-registration
     call -- confirmed real (see e.g. igStackMemoryPool), but most
     classes route their default-value setup through a separate, shared
     helper function this script doesn't follow, so `meta_field_type` is
     `null` far more often than not. Real, honestly-reported gap: a
     field-name-only result is still correct, just missing the type.

Real, important wrinkle confirmed by hand against the real .rodata bytes
(igInfo's own registration, real .rodata offset 388484): the `&.rodata+
OFFSET` comment on the field-name argument (r4) does NOT point straight
at a NUL-terminated string -- it points at a real, compiled *pointer
slot* (part of a small static per-field descriptor struct the original
Wii U linker laid out in .rodata) that itself holds a real absolute
vaddr pointing at the actual name string. One extra dereference is
needed: read a big-endian u32 at that .rodata offset, then resolve
*that* address (by real vaddr range, against every section this script
loads -- confirmed the string always lands back in .rodata for the
name argument, but other same-shaped args on the same call can resolve
into .bss instead, e.g. a per-field mutable default-value cache slot --
correctly not a string, and skipped). This is exactly how a compiler
lays out an initialized `const char* const` static table, so it fits
the mangled parameter type of the real callee
(`setMetaFieldBasicPropertiesAndValidateAll`) precisely.

Real, deliberate limitation, not an oversight: this does NOT recover
each field's byte OFFSET within its object. Checked directly against the
disassembly (see e.g. igInfo::arkRegisterInitialize) -- the offset
argument is loaded via a register *copy* from a runtime-computed value
(an accumulating counter read back out of the meta-object itself, e.g.
`lwz r28, 0xc(r31)` then `mr r7, r28`), not a compile-time immediate.
Alchemy's own registration API computes each field's offset at runtime
as fields are registered, so there is no compile-time constant to fold
here at all -- this is a real fact about how the engine works, not a
gap in what this script parses. A real byte-offset table would need
either running the game (walking the live igMetaObject after real
static init) or hand-tracing each class's own known C++ struct layout.

Usage:
    python3 tools/extract_field_schema.py [--class igLocalizedInfo] [--out schema.json]
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import zlib
from pathlib import Path
from typing import Dict, List, Optional

RPX_PATH = "stufftonotincludeintherepo/decrypted/GM0005000010142D00000000000000/code/tfbGame_cafe.rpx"
SOURCE_GLOB = "switch/game/source/generated_*.c"

SHF_RPL_ZLIB = 0x08000000
SHT_NOBITS = 8


# ---------------------------------------------------------------------------
# Minimal ELF32 big-endian / RPL section reader (just enough to get real,
# decompressed section bytes by name -- ported from recomp/src/elf_loader.cpp's
# read_section_bytes/load_elf, trimmed to what this script actually needs).
# ---------------------------------------------------------------------------


class RpxImage:
    """Real, decompressed section bytes plus each section's real (original
    Wii U) vaddr -- needed to resolve raw pointer values read out of
    .rodata back to a section+offset, not just to read .rodata by a
    pre-known byte offset."""

    def __init__(self):
        self.section_bytes: Dict[str, bytes] = {}
        self.section_vaddr: Dict[str, int] = {}

    def resolve_vaddr(self, vaddr: int) -> Optional[bytes]:
        """Returns the bytes starting at `vaddr`, in whichever real section
        contains it, or None if it doesn't fall in any loaded section
        (e.g. it points into .bss, which has no real file content)."""
        for name, base in self.section_vaddr.items():
            content = self.section_bytes.get(name, b"")
            if not content:
                continue
            if base <= vaddr < base + len(content):
                return content[vaddr - base:]
        return None


def read_rpl_image(path: str) -> RpxImage:
    data = Path(path).read_bytes()
    if data[:4] != b"\x7fELF":
        raise ValueError(f"{path}: not an ELF file")
    if data[4] != 1:
        raise ValueError(f"{path}: only ELF32 is supported")
    if data[5] != 2:
        raise ValueError(f"{path}: only big-endian ELF is supported")

    e_shoff, = struct.unpack_from(">I", data, 32)
    e_shentsize, = struct.unpack_from(">H", data, 46)
    e_shnum, = struct.unpack_from(">H", data, 48)
    e_shstrndx, = struct.unpack_from(">H", data, 50)

    def shdr(i: int) -> bytes:
        off = e_shoff + i * e_shentsize
        return data[off:off + e_shentsize]

    def read_section_bytes(sh: bytes) -> bytes:
        sh_type, sh_flags = struct.unpack_from(">II", sh, 4)
        sh_offset, sh_size = struct.unpack_from(">II", sh, 16)
        if sh_type == SHT_NOBITS or sh_size == 0:
            return b""
        raw = data[sh_offset:sh_offset + sh_size]
        if not (sh_flags & SHF_RPL_ZLIB):
            return raw
        decompressed_size, = struct.unpack_from(">I", raw, 0)
        out = zlib.decompress(raw[4:])
        if len(out) != decompressed_size:
            # Not fatal -- zlib already validated the stream; the size
            # prefix is just a hint. Real files have matched every time
            # this has been checked, but don't hard-fail over it.
            pass
        return out

    section_bytes_by_index = [read_section_bytes(shdr(i)) for i in range(e_shnum)]
    shstrtab = section_bytes_by_index[e_shstrndx]

    def secname(name_off: int) -> str:
        end = shstrtab.index(b"\x00", name_off)
        return shstrtab[name_off:end].decode("ascii", "replace")

    img = RpxImage()
    for i in range(e_shnum):
        sh = shdr(i)
        name_off, = struct.unpack_from(">I", sh, 0)
        sh_type, = struct.unpack_from(">I", sh, 4)
        sh_addr, = struct.unpack_from(">I", sh, 12)
        if sh_type == 0:
            continue
        name = secname(name_off)
        if not name:
            continue
        img.section_bytes[name] = section_bytes_by_index[i]
        img.section_vaddr[name] = sh_addr
    return img


def read_cstring(blob: bytes, offset: int) -> Optional[str]:
    if offset >= len(blob):
        return None
    end = blob.find(b"\x00", offset)
    if end == -1:
        return None
    try:
        return blob[offset:end].decode("utf-8")
    except UnicodeDecodeError:
        return blob[offset:end].decode("latin-1")


def resolve_field_name(img: RpxImage, section: str, offset: int) -> Optional[str]:
    """See this file's module docstring: the `&section+offset` comment
    points at a real compiled pointer slot, not directly at the string --
    one dereference (real vaddr -> real section+offset) is needed first."""
    blob = img.section_bytes.get(section)
    if blob is None or offset + 4 > len(blob):
        return None
    vaddr = int.from_bytes(blob[offset:offset + 4], "big")
    target = img.resolve_vaddr(vaddr)
    if target is None:
        return None  # e.g. resolves into .bss -- a real, non-string slot
    return read_cstring(target, 0)


# ---------------------------------------------------------------------------
# Name demangling -- Alchemy/CodeWarrior-style qualified names as used in
# this project's own generated symbol names, e.g.
#   Q2_4Core15igLocalizedInfo  -> Core::igLocalizedInfo
#   6igInfo                    -> igInfo
# ---------------------------------------------------------------------------

_QUALIFIED_RE = re.compile(r"^Q(\d+)_(.+)$")


def demangle_qualified_name(mangled: str) -> str:
    m = _QUALIFIED_RE.match(mangled)
    if not m:
        return _demangle_single(mangled)
    count = int(m.group(1))
    rest = m.group(2)
    parts = []
    for _ in range(count):
        lm = re.match(r"^(\d+)", rest)
        if not lm:
            break
        length = int(lm.group(1))
        rest = rest[len(lm.group(1)):]
        parts.append(rest[:length])
        rest = rest[length:]
    return "::".join(parts) if parts else mangled


def _demangle_single(mangled: str) -> str:
    lm = re.match(r"^(\d+)(.+)$", mangled)
    if not lm:
        return mangled
    length = int(lm.group(1))
    return lm.group(2)[:length]


# Matches e.g. "arkRegisterInitialize__Q2_4Core15igLocalizedInfoSFv"
_ARK_REGISTER_RE = re.compile(r"^ppc_arkRegisterInitialize__(.+)SFv$")

# A call site inside the function body, e.g.
#   ppc_setMetaFieldBasicPropertiesAndValidateAll__Q2_4Core12igMetaObjectF...(ctx);
# or
#   ppc_setDefault__Q2_4Core19igSizeTypeMetaFieldFUi(ctx);
_CALL_RE = re.compile(r"^\s*ppc_([A-Za-z_][A-Za-z0-9_]*)\(ctx\);\s*$")

# A resolved rodata load, e.g.
#   ctx->r[4] = 1138948u; /* &.rodata+388484 */
_RODATA_LOAD_RE = re.compile(r"^\s*ctx->r\[(\d)\] = \d+u; /\* &(\.\w+)\+(\d+) \*/\s*$")

_FUNC_START_RE = re.compile(r"^void (ppc_[A-Za-z0-9_]+)\(PpcContext \*ctx\) \{\s*$")

# Pull a real meta-field *type* class name out of a callee that mentions
# "MetaField", e.g. "setDefault__Q2_4Core19igSizeTypeMetaFieldFUi" ->
# "igSizeTypeMetaField". Deliberately permissive: falls back to None if
# the callee doesn't look like a per-type field setter at all (plenty of
# calls inside arkRegisterInitialize are unrelated plumbing).
_META_FIELD_TYPE_RE = re.compile(r"(\d+)(ig\w*MetaField)\b")


def guess_meta_field_type(callee: str) -> Optional[str]:
    m = _META_FIELD_TYPE_RE.search(callee)
    if not m:
        return None
    length = int(m.group(1))
    name = m.group(2)
    return name if len(name) == length else name


def split_functions(source: str):
    lines = source.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        m = _FUNC_START_RE.match(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1)
        start = i + 1
        j = start
        while j < n and lines[j] != "}":
            j += 1
        yield name, lines[start:j]
        i = j + 1


def extract_schema(source_dir: Path, rpx_path: str, class_filter: Optional[str]) -> Dict[str, List[dict]]:
    img = read_rpl_image(rpx_path)
    schema: Dict[str, List[dict]] = {}

    files = sorted(source_dir.glob("generated_*.c"))
    for path in files:
        text = path.read_text(errors="replace")
        if "ppc_arkRegisterInitialize__" not in text:
            continue
        for func_name, body_lines in split_functions(text):
            m = _ARK_REGISTER_RE.match(func_name)
            if not m:
                continue
            class_name = demangle_qualified_name(m.group(1))
            if class_filter and class_filter not in class_name:
                continue

            fields: List[dict] = []
            pending_name: Optional[str] = None
            pending_type: Optional[str] = None
            for line in body_lines:
                rm = _RODATA_LOAD_RE.match(line)
                if rm:
                    reg, section, offset = rm.group(1), rm.group(2), int(rm.group(3))
                    if reg == "4":  # r4: field name arg, but ONLY on the real
                        # registration call below -- a setDefault__*MetaField*
                        # call also loads r4, but with a raw default *value*,
                        # not a name-pointer comment, so this only ever
                        # overwrites pending_name from a genuine name load.
                        pending_name = resolve_field_name(img, section, offset)
                    continue
                cm = _CALL_RE.match(line)
                if not cm:
                    continue
                callee = cm.group(1)
                if callee == "setMetaFieldBasicPropertiesAndValidateAll__Q2_4Core12igMetaObjectFPCPCcPCPvPCUsi":
                    # The one real, confirmed call site that takes the
                    # field's real name pointer (r4) -- see this file's
                    # module docstring. Any per-type setDefault__*MetaField*
                    # call immediately before this one (same field) already
                    # set pending_type.
                    if pending_name is not None:
                        fields.append({"name": pending_name, "meta_field_type": pending_type, "registered_by": callee})
                    pending_name = None
                    pending_type = None
                elif callee.startswith("setDefault__") and "MetaField" in callee:
                    # A per-type setter (setDefault__Q2_4Core19igSizeTypeMetaFieldF...
                    # etc.) -- real, valuable signal for *type*, but its own
                    # r4 is a value, not a name, so never treat it as a name
                    # source. Restricted to this one real prefix -- matching
                    # any callee containing "MetaField" also caught unrelated
                    # calls that merely mention igMetaField as part of a
                    # longer mangled parameter type, producing a bogus guess.
                    guessed = guess_meta_field_type(callee)
                    if guessed:
                        pending_type = guessed

            schema.setdefault(class_name, [])
            schema[class_name].extend(fields)

    return schema


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rpx", default=RPX_PATH, help="path to the real tfbGame_cafe.rpx")
    ap.add_argument("--source-dir", default="switch/game/source", help="directory of generated_*.c files")
    ap.add_argument("--class", dest="class_filter", default=None,
                     help="only extract classes whose demangled name contains this substring")
    ap.add_argument("--out", default=None, help="write JSON here instead of stdout")
    args = ap.parse_args()

    rpx_path = Path(args.rpx)
    if not rpx_path.exists():
        print(f"error: {rpx_path} not found (real game dump required, not included in this repo)", file=sys.stderr)
        return 1

    schema = extract_schema(Path(args.source_dir), str(rpx_path), args.class_filter)
    schema = {k: v for k, v in schema.items() if v}  # drop classes with zero recovered fields

    out_json = json.dumps(schema, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(out_json + "\n")
        print(f"wrote {sum(len(v) for v in schema.values())} fields across {len(schema)} classes to {args.out}")
        print("Thanks to the Arkchemy Contributors for the recompiler this reads directly out of "
              "(https://github.com/Arkchemy).")
    else:
        print(out_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
