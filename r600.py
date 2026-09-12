#!/usr/bin/env python3
"""Structure of the R600 shader programs GX2 hands the Wii U's GPU.

This reports the **layout** of a program and stops where the evidence stops.
It is not a disassembler yet, and the difference matters: the per-instruction
encodings are in AMD's R600/R700 ISA document, which is not on this machine,
and writing a decoder from memory is how you get output that looks like a
disassembly and is wrong in ways nobody notices for a week.

What IS established, by measurement against this game's own five shaders:

**Word order is big-endian.** Testing the CF end-of-program bit either way
gave 3 candidate positions big-endian against 15 scattered little-endian.
Confirmed independently by the layout below coming out clean one way and as
noise the other.

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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("programs", nargs="+", help=".r600.bin files from gfd.py")
    args = ap.parse_args()
    for p in args.programs:
        analyse(p)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
