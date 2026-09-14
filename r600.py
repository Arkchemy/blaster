#!/usr/bin/env python3
"""Disassembler for the R600/R700 shader programs GX2 hands the Wii U's GPU.

`--cf` walks the control-flow section and expands texture and ALU clauses
inline; without it, the tool reports only the structural layout it can measure
without decoding anything.

Written against AMD's R700-Family ISA document (`reference/r700.txt`) rather
than against an existing decoder, because the one complete public
implementation -- decaf-emu's LatteDecompiler -- is GPL-3.0 and a static
recompiler cannot ship code derived from it. The document is wrong in two
places; both are noted where they bite, and both were caught by decoding a
shader whose job is known from its name and checking the instructions do that
job.

What is established, by measurement against this game's own five shaders:

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

**The shaders decode into the programs their names claim.** binkPixelShader is
a YUV-to-RGB conversion: Y times a constant row, the two chroma planes
accumulated with MULADD, a bias vector added, alpha set to a literal 1.0.
binkAlphaPixelShader is the same with a fourth sample supplying alpha instead
of the literal -- which is what the difference between those two names has to
mean. Both vertex shaders are a four-row matrix multiply against C0-C3 with a
texcoord passthrough. None of that was predicted in advance; it is what came
out.

    r600.py <program.bin> [--cf]
"""

from __future__ import annotations

from dataclasses import dataclass, field

import argparse
import os
import re
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
# Decoded forms.
#
# Decoding and printing are separate on purpose. The disassembly below is one
# consumer of these; the GLSL translator in r600_glsl.py is another, and a
# translator that re-extracted the bit fields itself would be a second decoder
# to keep in agreement with this one. There is exactly one place where a field
# position is written down.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Src:
    """One ALU source operand. `sel` is the raw select; see src_name()."""
    sel: int
    chan: int
    neg: int = 0
    abs: int = 0


@dataclass
class AluSlot:
    group: int          # instruction group this slot belongs to
    index: int          # slot index within the clause
    name: str
    op3: bool
    srcs: list          # list[Src] -- two for OP2, three for OP3
    dst_gpr: int
    dst_chan: int
    write: bool         # WRITE_MASK; OP3 always writes
    clamp: bool
    pred: int
    omod: int           # 0 none, 1 *2, 2 *4, 3 /2
    trans: bool         # issued on the scalar unit, so it writes PS not PV
    last: bool
    literals: tuple = ()   # attached to the group's last slot


@dataclass
class TexInst:
    index: int
    name: str
    resource: int
    sampler: int
    src_gpr: int
    src_sel: tuple      # four raw selects, 0-7
    dst_gpr: int
    dst_sel: tuple


@dataclass
class CfInst:
    index: int
    name: str
    kind: str           # 'alu' | 'clause' | 'export' | 'flow'
    addr: int = 0       # byte offset for clauses, target for flow
    count: int = 0
    eop: bool = False
    export_type: int = 0
    array_base: int = 0
    rw_gpr: int = 0
    swiz: tuple = ()
    alu: list = field(default_factory=list)
    tex: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Control-flow disassembly.
#
# From reference/r600isa.pdf chapter 8 for the field layout, and the R700
# supplement for the opcode numbering -- the two differ and it matters.
#
# Three DWORD1 formats share the CF slot and they are NOT interchangeable --
# reading one as another is how you get a plausible-looking disassembly that
# is wrong:
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


def decode_cf(blob: bytes) -> list[CfInst]:
    """Decode the control-flow section, which runs until the first all-zero
    slot -- the padding out to the clause base at byte 256."""
    words = struct.unpack(f"<{len(blob) // 4}I", blob)
    out: list[CfInst] = []
    i = 0
    while i * 2 + 1 < len(words):
        w0, w1 = words[i * 2], words[i * 2 + 1]
        if w0 == 0 and w1 == 0:
            break
        raw = (w1 >> 23) & 0x7F
        if raw >= 64:                       # an ALU form, 4-bit opcode
            op = (w1 >> 26) & 0xF
            count = ((w1 >> 18) & 0x7F) + 1     # CF_ALU_DWORD1.COUNT, [24:18]
            # ADDR is bits 34:3 of a byte offset, i.e. a quadword index.
            cf = CfInst(i, CF_ALU_INST.get(op, f"ALU?{op}"), "alu",
                        addr=w0 * 8, count=count)
            cf.alu = decode_alu(blob, cf.addr, count)
        else:
            name = CF_INST.get(raw, f"?{raw}")
            count = ((w1 >> 10) & 7) + 1
            eop = bool((w1 >> 21) & 1)
            if name in CLAUSE_INSTS:
                cf = CfInst(i, name, "clause", addr=w0 * 8, count=count, eop=eop)
                if name == "TEX":
                    cf.tex = decode_tex(blob, cf.addr, count)
            elif name.startswith("EXPORT"):
                # CF_ALLOC_EXPORT_WORD0: ARRAY_BASE [12:0], TYPE [14:13],
                # RW_GPR [21:15]. WORD1_SWIZ: SEL_X/Y/Z/W at [2:0] upward.
                cf = CfInst(i, name, "export", eop=eop,
                            export_type=(w0 >> 13) & 3, array_base=w0 & 0x1FFF,
                            rw_gpr=(w0 >> 15) & 0x7F,
                            swiz=tuple((w1 >> b) & 7 for b in (0, 3, 6, 9)))
            else:
                cf = CfInst(i, name, "flow", addr=w0 * 8, eop=eop)
        out.append(cf)
        i += 1
    return out


def disasm_cf(blob: bytes) -> list[str]:
    """Control flow, expanding texture and ALU clauses inline."""
    out = []
    for cf in decode_cf(blob):
        eop = "  END_OF_PROGRAM" if cf.eop else ""
        if cf.kind == "alu":
            out.append(f"  {cf.index:2}  {cf.name:16} addr={cf.addr:<6} "
                       f"({cf.count} slot{'s' if cf.count != 1 else ''})")
            out.extend(render_alu(cf.alu))
        elif cf.kind == "clause":
            out.append(f"  {cf.index:2}  {cf.name:16} addr={cf.addr:<6} "
                       f"({cf.count} instruction{'s' if cf.count != 1 else ''}){eop}")
            out.extend(render_tex(cf.tex))
        elif cf.kind == "export":
            out.append(f"  {cf.index:2}  {cf.name:16} "
                       f"type={cf.export_type} array_base={cf.array_base}{eop}")
        else:
            out.append(f"  {cf.index:2}  {cf.name:16} addr={cf.addr}{eop}")
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


def decode_tex(blob: bytes, offset: int, count: int) -> list[TexInst]:
    words = struct.unpack_from(f"<{count * 4}I", blob, offset)
    out = []
    for i in range(count):
        w0, w1, w2 = words[i * 4], words[i * 4 + 1], words[i * 4 + 2]
        out.append(TexInst(
            index=i,
            name=TEX_INST.get(w0 & 0x1F, "?%d" % (w0 & 0x1F)),
            resource=(w0 >> 8) & 0xFF,
            sampler=(w2 >> 15) & 0x1F,
            src_gpr=(w0 >> 16) & 0x7F,
            src_sel=tuple((w2 >> b) & 7 for b in (20, 23, 26, 29)),
            dst_gpr=w1 & 0x7F,
            dst_sel=tuple((w1 >> b) & 7 for b in (9, 12, 15, 18))))
    return out


def render_tex(insts: list[TexInst]) -> list[str]:
    return [f"    {t.index}: {t.name:14} "
            f"R{t.dst_gpr}.{''.join(SEL[c] for c in t.dst_sel)} <- "
            f"R{t.src_gpr}.{''.join(SEL[c] for c in t.src_sel)}  "
            f"resource={t.resource} sampler={t.sampler}" for t in insts]


# ---------------------------------------------------------------------------
# ALU clause disassembly.
#
# Each slot is 64 bits. Slots group into instruction groups, and the LAST bit
# of ALU_WORD0 ends a group -- a group issues together across the five ALU
# units, which is why a clause's slot count is not its instruction count.
#
# Two encodings share the second doubleword. ALU_WORD1_OP2 holds ALU_INST at
# [17:7]; ALU_WORD1_OP3 holds a five-bit ALU_INST at [17:13]. The fields are
# aligned so their MSBs overlap, and a nonzero value in the top three bits of
# the OP3 field discriminates the two -- which is also why the OP3 opcodes
# start at 8 rather than 0.
#
# (The doc's prose calls the OP2 field ten bits at [17:8] and its own field
# table calls it eleven at [17:7]; the shaders settle it. Read at [17:8],
# every MUL in binkPixelShader decodes as ADD.)
# ---------------------------------------------------------------------------

from alu_tables import OP2_INST, OP3_INST   # noqa: E402

CHAN = "xyzw"

#: Source selects outside the GPR file. Bases are from the R700 doc:
#: GPR 0, kcache bank 0 at 128, kcache bank 1 at 144, constant file at 256.
SRC_SPECIAL = {244: "1.0_dbl_l", 245: "1.0_dbl_m", 246: "0.5_dbl_l",
               247: "0.5_dbl_m", 248: "0.0", 249: "1.0", 250: "1i",
               251: "-1i", 252: "0.5", 253: "literal", 254: "PV", 255: "PS"}

#: Opcodes with no source operands at all.
NOSRC = {"NOP"}

#: Opcodes that read src0 only. The microcode always encodes both source
#: fields, so a second operand is present in the bits for these too; printing
#: it would be printing whatever the assembler happened to leave there.
UNARY = re.compile(r"^(MOV|MOVA|MOVA_INT|MOVA_FLOOR|FRACT|TRUNC|CEIL|RNDNE"
                   r"|FLOOR|EXP_IEEE|LOG_CLAMPED|LOG_IEEE|RECIP_[A-Z]+"
                   r"|RECIPSQRT_[A-Z]+|SQRT_IEEE|SIN|COS|NOT_INT"
                   r"|[A-Z]+_TO_[A-Z]+)$")


def src_name(sel: int, chan: int, neg: int, abs_: int = 0) -> str:
    if sel < 128:
        base = f"R{sel}.{CHAN[chan]}"
    elif sel < 144:
        base = f"KC0[{sel - 128}].{CHAN[chan]}"
    elif sel < 160:
        base = f"KC1[{sel - 144}].{CHAN[chan]}"
    elif sel >= 256:
        base = f"C{sel - 256}.{CHAN[chan]}"
    else:
        base = SRC_SPECIAL.get(sel, f"sel{sel}")
        if sel in (253, 254, 255):
            base += f".{CHAN[chan]}"
    if abs_:
        base = f"|{base}|"
    return ("-" + base) if neg else base


def _f32(word: int) -> str:
    """Render a literal dword as whichever of float/int reads as deliberate."""
    f = struct.unpack("<f", struct.pack("<I", word))[0]
    if word < 0x1000 or 1e-6 < abs(f) < 1e9:
        return repr(f) if abs(f) >= 1e-6 else f"{word}"
    return f"0x{word:08x}"


#: Opcodes that issue only on the scalar (trans) unit, so they write PS
#: rather than a channel of PV.
TRANS_ONLY = re.compile(r"^(RECIP_[A-Z]+|RECIPSQRT_[A-Z]+|SQRT_IEEE|SIN|COS"
                        r"|EXP_IEEE|LOG_CLAMPED|LOG_IEEE|MUL_LIT.*"
                        r"|MULLO_[A-Z]+|MULHI_[A-Z]+|FLT_TO_[A-Z]+"
                        r"|[A-Z]+_TO_FLT|ASHR_INT|LSHR_INT|LSHL_INT)$")


def _is_trans(name: str, pos: int, chan: int, last_vec_chan: int) -> bool:
    """Which unit issues this slot -- and so whether it writes PV or PS.

    Nothing in the encoding says. The units are fed in the fixed order
    X, Y, Z, W, T and slots may be skipped, so a vector slot's destination
    channel always advances past the previous one; a slot that does not
    advance cannot be a vector slot, and a group's fifth slot has nowhere
    left to go. That is the whole rule.

    It matters: binkPixelShader's group 0 ends with a MOV writing channel w
    when an earlier slot already wrote w. Called a vector slot, it overwrites
    a PV channel the next group reads, and the colour conversion loses a term.
    """
    return pos == 4 or chan <= last_vec_chan or bool(TRANS_ONLY.match(name))


def decode_alu(blob: bytes, offset: int, slots: int) -> list[AluSlot]:
    """Decode one ALU clause of `slots` 64-bit slots.

    Literal constants occupy slots of their own, immediately after the group
    that reads them, so they have to be consumed here rather than decoded as
    instructions -- decode one as an instruction and every slot after it is
    misaligned.
    """
    if offset < 0 or offset + slots * 8 > len(blob):
        return []
    words = struct.unpack_from(f"<{slots * 2}I", blob, offset)

    out: list[AluSlot] = []
    group = i = 0
    group_start = 0
    last_vec_chan = -1
    while i < slots:
        w0, w1 = words[i * 2], words[i * 2 + 1]
        i += 1

        inst = (w1 >> 7) & 0x7FF
        op3 = inst >= 0x200
        srcs = [Src(w0 & 0x1FF, (w0 >> 10) & 3, (w0 >> 12) & 1,
                    0 if op3 else w1 & 1),
                Src((w0 >> 13) & 0x1FF, (w0 >> 23) & 3, (w0 >> 25) & 1,
                    0 if op3 else (w1 >> 1) & 1)]
        if op3:
            name = OP3_INST.get(inst >> 6, f"OP3?{inst >> 6}")
            srcs.append(Src(w1 & 0x1FF, (w1 >> 10) & 3, (w1 >> 12) & 1))
            write, omod = True, 0
        else:
            name = OP2_INST.get(inst, f"OP2?{inst}")
            if name in NOSRC:
                srcs = []
            elif UNARY.match(name):
                srcs = srcs[:1]
            write, omod = bool((w1 >> 4) & 1), (w1 >> 5) & 3

        last = bool((w0 >> 31) & 1)
        slot = AluSlot(group=group, index=i - 1, name=name, op3=op3, srcs=srcs,
                       dst_gpr=(w1 >> 21) & 0x7F, dst_chan=(w1 >> 29) & 3,
                       write=write, clamp=bool((w1 >> 31) & 1),
                       pred=(w0 >> 29) & 3, omod=omod,
                       trans=_is_trans(name, i - 1 - group_start,
                                       (w1 >> 29) & 3, last_vec_chan),
                       last=last)
        out.append(slot)
        if not slot.trans:
            last_vec_chan = slot.dst_chan

        if last:
            # A literal is 1 or 2 slots: one dword per channel read, rounded
            # up to a whole slot. Only the group's highest channel matters.
            chans = {s.chan for sl in out[group_start:] for s in sl.srcs
                     if s.sel == 253}
            if chans:
                n = 2 if max(chans) >= 2 else 1
                slot.literals = words[i * 2: (i + n) * 2]
                i += n
            group += 1
            group_start = len(out)
            last_vec_chan = -1
    return out


def render_alu(slots: list[AluSlot]) -> list[str]:
    out = []
    for sl in slots:
        args = ", ".join(src_name(s.sel, s.chan, s.neg, s.abs) for s in sl.srcs)
        name = sl.name + ("", "*2", "*4", "/2")[sl.omod]
        dst = f"R{sl.dst_gpr}.{CHAN[sl.dst_chan]}" if sl.write else "----"
        flags = ("_sat" if sl.clamp else "") + (f" [pred{sl.pred}]" if sl.pred else "")
        body = f"{dst}{flags} = {args}" if args else ""
        out.append(f"    {sl.group}.{sl.index:<2} {name:16} {body}".rstrip())
        if sl.literals:
            chans = {s.chan for s in sl.srcs if s.sel == 253}
            vals = sl.literals[:max(chans) + 1] if chans else sl.literals
            out.append(f"    {sl.group}.lit  " + ", ".join(_f32(v) for v in vals))
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
