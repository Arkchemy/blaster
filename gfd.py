#!/usr/bin/env python3
"""Read GFD shader containers -- the Cafe SDK's compiled-shader format.

Skylanders does not ship its Wii U shaders in the archives. The GX2 workflow
compiles a shader into a C byte array, so they are linked into the executable
and sit in `.rodata` with a `_size` symbol beside each one. Five of them, found
by their own source filenames left in the binary:

    temp\\cafe-ghs-fin\\gfx\\defaultVertexShader.c
    temp\\cafe-ghs-fin\\gfx\\defaultPixelShader.c
    temp\\cafe-ghs-fin\\movie\\binkMovie\\binkVertexShader.c
    temp\\cafe-ghs-fin\\movie\\binkMovie\\binkPixelShader.c
    temp\\cafe-ghs-fin\\movie\\binkMovie\\binkAlphaPixelShader.c

The container is GFD ("Gfx2"), version 7.1: a 32-byte file header followed by
blocks, each 32 bytes of block header and then its data. A shader is a header
block carrying the GX2 register struct, optional padding, a program block
carrying raw R600 microcode, and an end marker.

None of that is taken on trust. The offsets of the GX2 structs are documented
in decaf-emu and Cemu and are easy to recite; reciting them is how a wrong
assumption gets built on, so this parses the container and reports what it
finds rather than asserting a layout. The first attempt at reading these blobs
as bare GX2VertexShader structs produced a size of 255 and a program pointer
of 0x000000ff, which is what being wrong looks like, and is why the container
is parsed instead.

    gfd.py <rpx>                 list the shaders found in a Wii U executable
    gfd.py <rpx> -o DIR          write each as .gsh plus its raw program
    gfd.py --file <blob.gsh>     parse a container already on disk
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

GFD_MAGIC = 0x47667832      # 'Gfx2'
BLOCK_MAGIC = 0x424C4B7B    # 'BLK{'

#: Block types, from the Cafe SDK via decaf-emu. Only the ones this game
#: actually uses are exercised; the rest are named so an unexpected one is
#: reported by name rather than as a number.
BLOCK_TYPES = {
    1: "EndOfFile", 2: "Padding",
    3: "VertexShaderHeader", 5: "VertexShaderProgram",
    6: "PixelShaderHeader", 7: "PixelShaderProgram",
    8: "GeometryShaderHeader", 9: "GeometryShaderProgram",
    10: "GeometryShaderCopyProgram",
    11: "TextureHeader", 12: "TextureImage", 13: "TextureMipmap",
    14: "ComputeShaderHeader", 15: "ComputeShaderProgram",
}
PROGRAM_TYPES = {5, 7, 9, 10, 15}
HEADER_TYPES = {3, 6, 8, 14}

#: The shaders known to be linked into Skylanders: Spyro's Adventure, by the
#: symbol names the unstripped retail binary still carries.
KNOWN = ["defaultVertexShader", "defaultPixelShader",
         "binkVertexShader", "binkPixelShader", "binkAlphaPixelShader"]


class GfdError(Exception):
    pass


class Block:
    def __init__(self, type_id: int, data: bytes, offset: int):
        self.type_id = type_id
        self.data = data
        self.offset = offset

    @property
    def name(self) -> str:
        return BLOCK_TYPES.get(self.type_id, f"Unknown({self.type_id})")

    @property
    def is_program(self) -> bool:
        return self.type_id in PROGRAM_TYPES

    @property
    def is_header(self) -> bool:
        return self.type_id in HEADER_TYPES


class Gfd:
    def __init__(self, blob: bytes, name: str = "<blob>"):
        self.name = name
        self.blob = blob
        self.blocks: list[Block] = []
        self._parse()

    def _parse(self) -> None:
        if len(self.blob) < 32:
            raise GfdError(f"{self.name}: too short to hold a GFD header")
        magic, hdr_size, self.major, self.minor, self.gpu, self.align, _, _ = \
            struct.unpack_from(">8I", self.blob, 0)
        if magic != GFD_MAGIC:
            raise GfdError(f"{self.name}: not a GFD container "
                           f"(magic {magic:08x}, expected {GFD_MAGIC:08x})")
        off = hdr_size
        while off + 32 <= len(self.blob):
            bm, bhs, _bmaj, _bmin, btype, dsize, _dlen, _bid = \
                struct.unpack_from(">8I", self.blob, off)
            if bm != BLOCK_MAGIC:
                raise GfdError(f"{self.name}: block at {off} has magic {bm:08x}, "
                               f"expected {BLOCK_MAGIC:08x} -- the container is "
                               "truncated or the header size is wrong")
            data = self.blob[off + bhs: off + bhs + dsize]
            self.blocks.append(Block(btype, data, off))
            if btype == 1:          # EndOfFile
                break
            off += bhs + dsize

    def program(self) -> bytes | None:
        for b in self.blocks:
            if b.is_program:
                return b.data
        return None

    def header_block(self) -> bytes | None:
        for b in self.blocks:
            if b.is_header:
                return b.data
        return None

    def kind(self) -> str:
        for b in self.blocks:
            if b.is_header:
                return b.name.replace("ShaderHeader", "")
        return "?"

    def describe(self) -> str:
        prog = self.program()
        parts = [f"{self.name:24} GFD v{self.major}.{self.minor} gpu={self.gpu}",
                 f"{self.kind():8}"]
        if prog is not None:
            # R600 instructions are 64-bit, so a program that is not a multiple
            # of 8 bytes is a parse error rather than an odd shader.
            words = len(prog) // 8
            odd = "" if len(prog) % 8 == 0 else "  !! not a multiple of 8"
            parts.append(f"program {len(prog):5} bytes = {words:4} instr words{odd}")
        hdr = self.header_block()
        if hdr is not None:
            parts.append(f"regs {len(hdr):4} bytes")
        return "  ".join(parts)


def from_rpx(path: str):
    """Yield (name, Gfd) for every known shader symbol in a Wii U executable."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import rpx as rpxmod

    r = rpxmod.Rpx(path)
    st, strt = r.section(".symtab"), r.section(".strtab")
    if not st or not strt:
        raise GfdError(f"{path} has no symbol table, so the shaders cannot be located")
    d, sd = st["data"], strt["data"]
    syms = {}
    for o in range(0, len(d) - 15, 16):
        nm, val, size, _info, _other, _shndx = struct.unpack_from(">IIIBBH", d, o)
        if nm == 0 or nm >= len(sd):
            continue
        e = sd.find(b"\0", nm)
        name = sd[nm:e].decode("ascii", "replace")
        if name and (name not in syms or syms[name][0] == 0):
            syms[name] = (val, size)

    sections = [s for s in r.sections if s["addr"] and s.get("data")]
    for name in KNOWN:
        if name not in syms:
            continue
        addr, size = syms[name]
        if not addr or not size:
            continue
        for s in sections:
            if s["addr"] <= addr < s["addr"] + len(s["data"]):
                blob = s["data"][addr - s["addr"]: addr - s["addr"] + size]
                yield name, Gfd(blob, name)
                break


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="a Wii U .rpx, or a .gsh with --file")
    ap.add_argument("--file", action="store_true", help="target is a container, not an executable")
    ap.add_argument("-o", "--out", help="write .gsh and .bin for each shader here")
    args = ap.parse_args()

    if args.file:
        with open(args.target, "rb") as fh:
            found = [(os.path.basename(args.target), Gfd(fh.read(), os.path.basename(args.target)))]
    else:
        found = list(from_rpx(args.target))

    if not found:
        print("no GFD shaders found", file=sys.stderr)
        return 1

    for name, g in found:
        print(g.describe())
        for b in g.blocks:
            print(f"    @{b.offset:5}  {b.name:26} {len(b.data):5} bytes")
        if args.out:
            os.makedirs(args.out, exist_ok=True)
            with open(os.path.join(args.out, name + ".gsh"), "wb") as fh:
                fh.write(g.blob)
            prog = g.program()
            if prog:
                with open(os.path.join(args.out, name + ".r600.bin"), "wb") as fh:
                    fh.write(prog)
            hdr = g.header_block()
            if hdr:
                with open(os.path.join(args.out, name + ".regs.bin"), "wb") as fh:
                    fh.write(hdr)
    if args.out:
        print(f"\nwrote {len(found)} shader(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
