#!/usr/bin/env python3
"""Structure of the R600 shader programs GX2 hands the Wii U's GPU.

This reports the **layout** of a program and stops where the evidence stops.
It is not a disassembler yet, and the difference matters: the per-instruction
encodings are in AMD's R600/R700 ISA document, which is not on this machine,
and writing a decoder from memory is how you get output that looks like a
disassembly and is wrong in ways nobody notices for a week.

What IS established, by measurement against this game's own five shaders:

**Word order is LITTLE-endian.** Corrected 2026-09-12 with the ISA document in
hand; the earlier claim of big-endian here was wrong.

The first test scanned the whole program for end-of-program bits and read 3
hits big-endian against 15 little-endian as evidence for big-endian. That test
was worthless: most of a program is ALU and TEX words, where bit 21 means
something else entirely, so it was counting noise both ways.

Scanning only the CF section settles it. Big-endian gives **zero** end-of-
program bits in all five shaders, which is impossible -- every program must
end. Little-endian gives exactly one, in the last CF instruction, which is
what a program looks like.

And the decode cross-checks against structure measured independently: in
binkPixelShader the first CF instruction decodes as TEX with count 3 and
address 0x30, and 0x30 x 8 is byte 384, which is exactly where the region
scan found a 48-byte clause of three 16-byte texture fetches. A wrong word
order does not produce an address that lands on a boundary found another
way.

**The layout is: CF section, pad to byte 256, ALU clause, TEX clause.**
Every one of the five shaders has its first region at word 0, and every one
resumes at word 32, which is byte 256 exactly.

**The tail region is a TEX clause of 16-byte instructions.** This was a
prediction before it was a measurement. Bink video is YUV, so its pixel shader
should sample three planes and the alpha variant four:

    binkPixelShader        48 bytes  = 3 x 16   Y, U, V
    binkAlphaPixelShader   64 bytes  = 4 x 16   Y, U, V, A
    defaultPixelShader     16 bytes  = 1 x 16   one diffuse texture

Three for three, and all exact multiples. A wrong instruction size or word
order would not produce that.

    r600.py <program.bin> [...]
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

#: R600 CF and ALU instructions are 64-bit; TEX and VTX are 128-bit.
WORD = 8
TEX_SIZE = 16

#: Clause data starts here in every shader measured. The CF section occupies
#: the front and the rest is zero padding, which is how the GPU's clause
#: addresses stay byte-aligned.
CLAUSE_BASE = 256


class Region:
    def __init__(self, first: int, last: int):
        self.first = first          # inclusive, in 64-bit words
        self.last = last

    @property
    def words(self) -> int:
        return self.last - self.first + 1

    @property
    def size(self) -> int:
        return self.words * WORD

    @property
    def byte_offset(self) -> int:
        return self.first * WORD


def regions(words) -> list[Region]:
    """Runs of non-zero 64-bit words.

    Zero words are padding: the GPU is told where each clause starts, so the
    gaps between them are never executed and the compiler leaves them empty.
    """
    out, start = [], None
    for i in range(0, len(words), 2):
        zero = words[i] == 0 and words[i + 1] == 0
        if not zero and start is None:
            start = i // 2
        elif zero and start is not None:
            out.append(Region(start, i // 2 - 1))
            start = None
    if start is not None:
        out.append(Region(start, len(words) // 2 - 1))
    return out


def analyse(path: str) -> None:
    with open(path, "rb") as fh:
        blob = fh.read()
    if len(blob) % WORD:
        print(f"{path}: {len(blob)} bytes is not a multiple of {WORD} -- "
              "not a whole number of instruction words", file=sys.stderr)
    words = struct.unpack(f">{len(blob) // 4}I", blob)
    regs = regions(words)

    print(f"{path}")
    print(f"  {len(blob)} bytes, {len(blob) // WORD} instruction words")
    if not regs:
        print("  entirely zero -- not a program")
        return

    for i, r in enumerate(regs):
        kind = "?"
        note = ""
        if r.byte_offset == 0:
            kind = "CF section"
            note = f"{r.words} control-flow instructions"
        elif r.byte_offset == CLAUSE_BASE:
            kind = "ALU clause"
            note = f"{r.words} instruction words"
        elif i == len(regs) - 1 and r.size % TEX_SIZE == 0:
            kind = "TEX clause"
            note = f"{r.size // TEX_SIZE} texture fetches"
        else:
            note = f"{r.words} words"
            if r.size % TEX_SIZE == 0:
                note += f" (could be {r.size // TEX_SIZE} 16-byte instructions)"
        print(f"  @{r.byte_offset:4}  {kind:11} {r.size:4} bytes   {note}")

    if regs[0].byte_offset != 0:
        print("  !! first region is not at byte 0 -- the CF section should be")
    if len(regs) > 1 and regs[1].byte_offset != CLAUSE_BASE:
        print(f"  !! clauses start at {regs[1].byte_offset}, not {CLAUSE_BASE} -- "
              "the padding assumption does not hold for this shader")


# ---------------------------------------------------------------------------
# Control-flow disassembly.
#
# From reference/r600isa.pdf chapter 8 for the field layout, and the R700
# supplement for the opcode numbering -- the two differ and it matters. Three DWORD1 formats share the CF slot
# and they are NOT interchangeable -- reading one as another is how you get a
# plausible-looking disassembly that is wrong:
#
#   CF_DWORD1              CF_INST at [29:23], 7 bits.  Clauses, flow control.
#   CF_ALU_DWORD1          CF_INST at [29:26], 4 bits.  ALU clauses.
#   CF_ALLOC_EXPORT_DWORD1 CF_INST at [29:23], 7 bits.  Exports.
#
# The ALU forms are told apart by the top bit of the 7-bit field being set:
# every 4-bit ALU opcode (8..11) lands at 64 or above when read as 7 bits,
# and no 7-bit CF opcode does -- the plain ones stop at 21 and the export and
# memory ones sit at 32..40.
# ---------------------------------------------------------------------------

# R700 opcode numbering, NOT R600. The Wii U's GPU is R700-family and the two
# tables diverge from opcode 10 onward -- R600 has JUMP at 16 and CALL_FS at
# 15, R700 has JUMP at 10 and CALL_FS at 19.
#
# This was caught by the output rather than by reading: with the R600 table,
# binkVertexShader opened with EMIT_CUT_VERTEX, which is meaningless as the
# first instruction of a vertex shader. Under R700 the same word is CALL_FS,
# which is exactly what a vertex shader starts with. Every other field agreed
# under both tables, so a disassembly built on the R600 numbering would have
# looked entirely reasonable and been wrong about control flow.
CF_INST = {
    0: "NOP", 1: "TEX", 2: "VTX", 3: "VTX_TC",
    4: "LOOP_START", 5: "LOOP_END", 6: "LOOP_START_DX10", 7: "LOOP_START_NO_AL",
    8: "LOOP_CONTINUE", 9: "LOOP_BREAK",
    10: "JUMP", 11: "PUSH", 12: "PUSH_ELSE", 13: "ELSE", 14: "POP",
    15: "POP_JUMP", 16: "POP_PUSH", 17: "POP_PUSH_ELSE",
    18: "CALL", 19: "CALL_FS", 20: "RETURN",
    21: "EMIT_VERTEX", 22: "EMIT_CUT_VERTEX", 23: "CUT_VERTEX", 24: "KILL",
    26: "WAIT_ACK",
    32: "MEM_STREAM0", 33: "MEM_STREAM1", 34: "MEM_STREAM2", 35: "MEM_STREAM3",
    36: "MEM_SCRATCH", 37: "MEM_REDUCTION", 38: "MEM_RING",
    39: "EXPORT", 40: "EXPORT_DONE",
}

CF_ALU_INST = {8: "ALU", 9: "ALU_PUSH_BEFORE", 10: "ALU_POP_AFTER",
               11: "ALU_POP2_AFTER", 13: "ALU_CONTINUE", 14: "ALU_BREAK",
               15: "ALU_ELSE_AFTER"}

#: Clauses whose ADDR points at instruction data rather than a jump target.
CLAUSE_INSTS = {"TEX", "VTX", "VTX_TC"}


def disasm_cf(blob: bytes) -> list[str]:
    """Control flow, expanding texture clauses inline."""
    """Disassemble the control-flow section, which runs until the first
    all-zero slot -- the padding out to the clause base."""
    words = struct.unpack(f"<{len(blob) // 4}I", blob)
    out = []
    i = 0
    while i * 2 + 1 < len(words):
        w0, w1 = words[i * 2], words[i * 2 + 1]
        if w0 == 0 and w1 == 0:
            break
        raw = (w1 >> 23) & 0x7F
        if raw >= 64:                       # an ALU form, 4-bit opcode
            op = (w1 >> 26) & 0xF
            name = CF_ALU_INST.get(op, f"ALU?{op}")
            count = ((w1 >> 18) & 0x7F) + 1     # CF_ALU_DWORD1.COUNT, [24:18]
            # ADDR is bits 34:3 of a byte offset, i.e. a quadword index.
            out.append(f"  {i:2}  {name:16} addr={w0 * 8:<6} "
                       f"({count} slot{'s' if count != 1 else ''})")
        else:
            name = CF_INST.get(raw, f"?{raw}")
            count = ((w1 >> 10) & 7) + 1
            eop = (w1 >> 21) & 1
            extra = ""
            if name in CLAUSE_INSTS:
                extra = f"addr={w0 * 8:<6} ({count} instruction{'s' if count != 1 else ''})"
            elif name.startswith("EXPORT"):
                extra = f"type={(w0 >> 13) & 3} array_base={w0 & 0x1FFF}"
            else:
                extra = f"addr={w0 * 8}"
            out.append(f"  {i:2}  {name:16} {extra}{'  END_OF_PROGRAM' if eop else ''}")
            if name == "TEX":
                out.extend(disasm_tex(blob, w0 * 8, count))
        i += 1
    return out


# ---------------------------------------------------------------------------
# Texture-fetch clause disassembly. R700 doc, "Texture Fetch Doubleword 0/1/2".
#
# A TEX instruction is 128 bits: three used doublewords and one of zeros.
# ---------------------------------------------------------------------------

TEX_INST = {
    0: "VTX_FETCH", 1: "VTX_SEMANTIC", 2: "MEM", 3: "LD",
    4: "GET_TEXTURE_RESINFO", 5: "GET_NUMBER_OF_SAMPLES", 6: "GET_COMP_TEX_LOD",
    7: "GET_GRADIENTS_H", 8: "GET_GRADIENTS_V", 9: "GET_LERP",
    10: "KEEP_GRADIENTS", 11: "SET_GRADIENTS_H", 12: "SET_GRADIENTS_V",
    14: "SET_CUBEMAP_INDEX", 15: "FETCH4",
    16: "SAMPLE", 17: "SAMPLE_L", 18: "SAMPLE_LB", 19: "SAMPLE_LZ",
    20: "SAMPLE_G", 21: "SAMPLE_G_L", 22: "SAMPLE_G_LB", 23: "SAMPLE_G_LZ",
    24: "SAMPLE_C", 25: "SAMPLE_C_L", 26: "SAMPLE_C_LB", 27: "SAMPLE_C_LZ",
    28: "SAMPLE_C_G", 29: "SAMPLE_C_G_L", 30: "SAMPLE_C_G_LB", 31: "SAMPLE_C_G_LZ",
}

#: Channel selects. 4 and 5 are the constants, 7 means the channel is not
#: written -- which is how a shader says it only wants one component back.
SEL = {0: "x", 1: "y", 2: "z", 3: "w", 4: "0", 5: "1", 6: "?", 7: "_"}


def disasm_tex(blob: bytes, offset: int, count: int) -> list[str]:
    words = struct.unpack_from(f"<{count * 4}I", blob, offset)
    out = []
    for i in range(count):
        w0, w1, w2 = words[i * 4], words[i * 4 + 1], words[i * 4 + 2]
        inst = w0 & 0x1F
        res = (w0 >> 8) & 0xFF
        src_gpr = (w0 >> 16) & 0x7F
        dst_gpr = w1 & 0x7F
        dsel = "".join(SEL[(w1 >> b) & 7] for b in (9, 12, 15, 18))
        sampler = (w2 >> 15) & 0x1F
        ssel = "".join(SEL[(w2 >> b) & 7] for b in (20, 23, 26, 29))
        out.append(f"    {i}: {TEX_INST.get(inst, '?%d' % inst):14} "
                   f"R{dst_gpr}.{dsel} <- R{src_gpr}.{ssel}  "
                   f"resource={res} sampler={sampler}")
    return out


def fingerprint(blob: bytes) -> tuple:
    """What identifies a program regardless of where it was found.

    Not a hash of the bytes: a program copied into GPU memory can differ from
    the one in .rodata by patched constants or relocated clause addresses
    while being the same shader. Size plus the shape of its regions plus the
    first control-flow word is enough to match them up and cheap to eyeball.
    """
    words = struct.unpack(f">{len(blob) // 4}I", blob)
    regs = regions(words)
    shape = tuple((r.byte_offset, r.size) for r in regs)
    return (len(blob), shape, words[0] if words else 0, words[1] if len(words) > 1 else 0)


def match(dumped: list[str], known: list[str]) -> None:
    """Say which runtime dump corresponds to which extracted shader.

    The point is to find the ones that match *nothing*: those are the shaders
    that are not in the executable, and knowing which they are says where the
    rest of the shader path has to look."""
    table = {}
    for k in known:
        with open(k, "rb") as fh:
            table[fingerprint(fh.read())] = k

    print(f"{'dumped':34} {'bytes':>6}  matches")
    unmatched = []
    for dpath in dumped:
        with open(dpath, "rb") as fh:
            blob = fh.read()
        fp = fingerprint(blob)
        hit = table.get(fp)
        if hit is None:
            # Same size and shape but different constants still counts as a
            # lead worth reporting, so fall back to size and region shape.
            for kfp, kname in table.items():
                if kfp[0] == fp[0] and kfp[1] == fp[1]:
                    hit = os.path.basename(kname) + "  (same shape, different constants)"
                    break
        name = os.path.basename(dpath)
        if hit:
            print(f"{name:34} {len(blob):6}  {os.path.basename(str(hit))}")
        else:
            print(f"{name:34} {len(blob):6}  -- not in the executable")
            unmatched.append(name)
    if unmatched:
        print(f"\n{len(unmatched)} program(s) came from the archives or were built at "
              "load time:\n  " + ", ".join(unmatched))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("programs", nargs="+", help=".r600.bin files from gfd.py")
    ap.add_argument("--cf", action="store_true", help="disassemble the control-flow section")
    ap.add_argument("--match-against", nargs="*", metavar="KNOWN",
                    help="identify these programs against shaders extracted from the executable")
    args = ap.parse_args()
    if args.match_against:
        match(args.programs, args.match_against)
        return 0
    if args.cf:
        for p in args.programs:
            print(os.path.basename(p))
            with open(p, "rb") as fh:
                for line in disasm_cf(fh.read()):
                    print(line)
            print()
        return 0
    for p in args.programs:
        analyse(p)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
