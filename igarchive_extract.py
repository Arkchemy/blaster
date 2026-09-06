#!/usr/bin/env python3
"""Decompress an igArchive's blocks and pull out the igz files inside.

Cracked 2026-09-06. The payload is a run of independently compressed chunks,
each laid out as:

    u16   compressed length, little-endian, NOT counting the 5 bytes below
    u8    LZMA properties, 0x5d  (lc=3 lp=0 pb=2)
    u32   dictionary size, 0x00008000  (32 KB)
    ...   raw LZMA1 data, decompressing to at most 32 KB

There is no uncompressed-size field, so the stream is fed to FORMAT_ALONE with
the size set unknown. Chunks sit on 2048-byte sector boundaries.

    igarchive_extract.py ARCHIVE [-o OUTDIR]
"""
import argparse
import lzma
import pathlib
import struct

SECTOR = 2048
LZMA_PROPS = bytes([0x5D, 0x00, 0x80, 0x00, 0x00])


def chunks(d):
    """Yield (offset, complen, decompressed) for every chunk found."""
    for off in range(0, len(d) - 7, SECTOR):
        if d[off + 2:off + 7] != LZMA_PROPS:
            continue
        n = struct.unpack_from("<H", d, off)[0]
        blob = LZMA_PROPS + b"\xff" * 8 + d[off + 7: off + 7 + n]
        try:
            out = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(blob)
        except lzma.LZMAError:
            continue
        yield off, n, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archive")
    ap.add_argument("-o", "--outdir")
    a = ap.parse_args()

    d = pathlib.Path(a.archive).read_bytes()
    if d[:4] != b"IGA\x1a":
        raise SystemExit("not an igArchive")

    total_in = total_out = 0
    found = []
    for off, n, out in chunks(d):
        total_in += n
        total_out += len(out)
        found.append((off, n, out))

    igz = [f for f in found if f[2][:3] == b"IGZ"]
    print(f"  {len(found)} chunks decompressed, {total_in} -> {total_out} bytes "
          f"({total_out / max(total_in,1):.1f}x)")
    print(f"  {len(igz)} of them start with the IGZ magic")

    if a.outdir:
        out = pathlib.Path(a.outdir)
        out.mkdir(parents=True, exist_ok=True)
        for off, n, blob in found:
            ext = "igz" if blob[:3] == b"IGZ" else "bin"
            (out / f"chunk_{off:06x}.{ext}").write_bytes(blob)
        print(f"  written to {out}/")


if __name__ == "__main__":
    main()
