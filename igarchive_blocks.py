#!/usr/bin/env python3
"""Dump an igArchive's compressed-block table.

igArchive does not compress per file. It splits the payload into fixed-size
blocks and compresses each one independently, which is why a loader has to
decompress many times to read one archive. Confirmed against the SSA USA disc
2026-09-06, after maff pointed out the format uses "a compressed block system".

Header (little-endian, even though the title is big-endian PowerPC):

    +0x00  "IGA\\x1a"      magic
    +0x04  version         8 on SSA
    +0x08  file count
    +0x10  block size      2048
    +0x1c  payload length  always a whole number of blocks
    +0x28  block count
    +0x54  block table     one uint16 per block:
                             bit 15  set = compressed, clear = stored
                             bits 0..14  start sector, x block size
"""
import struct
import sys


def read(path):
    d = open(path, "rb").read()
    if d[:4] != b"IGA\x1a":
        raise SystemExit(f"{path}: not an igArchive (magic {d[:4]!r})")
    h = struct.unpack_from("<16I", d, 0)
    n = h[10]
    tab = struct.unpack_from(f"<{n}H", d, 0x54)
    return d, h, tab


def main():
    for path in sys.argv[1:] or ["bootstrap.bld"]:
        d, h, tab = read(path)
        blk, payload, files = h[4], h[7], h[2]
        comp = sum(1 for v in tab if v & 0x8000)
        print(f"{path}")
        print(f"  version {h[1]}  files {files}  block size {blk}")
        print(f"  payload {payload} = {payload / blk:g} blocks"
              f"{'  (exact)' if payload % blk == 0 else '  (NOT a whole number -- check)'}")
        print(f"  block table: {len(tab)} entries, {comp} compressed, {len(tab) - comp} stored")
        # sectors must increase; a decreasing entry means the decode is wrong
        secs = [v & 0x7FFF for v in tab]
        # A table that restarts at 0x8000 (sector 0, compressed) is a second
        # block group, not corruption. 0xffff is padding. Three archives on the
        # SSA disc do this -- Init_Setup, Credits and PvP_MainControl -- and
        # the group boundaries are not yet understood, so they are reported
        # rather than guessed at.
        groups, cur = [], []
        for i, v in enumerate(tab):
            if v == 0xFFFF:
                continue
            if cur and (v & 0x7FFF) < (cur[-1] & 0x7FFF):
                groups.append(cur); cur = []
            cur.append(v)
        if cur:
            groups.append(cur)
        if len(groups) == 1:
            print(f"  sectors {secs[0]}..{max(secs)}, monotonic, one block group")
        else:
            print(f"  !! {len(groups)} block groups "
                  f"({', '.join(str(len(g)) for g in groups)} entries) -- "
                  f"multi-group layout is not yet understood")
        stored = [i for i, v in enumerate(tab) if not (v & 0x8000)]
        if stored:
            print(f"  stored blocks at index: {stored}")
        print()


if __name__ == "__main__":
    main()
