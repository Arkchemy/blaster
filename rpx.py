"""Minimal Cafe RPX reader.

An RPX is a big-endian 32-bit ELF whose sections may be zlib-compressed
(flag SHF_RPL_ZLIB, 0x08000000).  A compressed section body starts with a
big-endian u32 giving the inflated size, then the deflate stream.

Enough to read .text/.rodata/.data at their virtual addresses, which is all
the static analysis here needs.
"""

import struct, zlib

SHF_RPL_ZLIB = 0x08000000


class Rpx:
    def __init__(self, path):
        with open(path, "rb") as fh:
            self.raw = fh.read()
        d = self.raw
        assert d[:4] == b"\x7fELF", "not an ELF"
        assert d[5] == 2, "expected big-endian"
        e_shoff, = struct.unpack_from(">I", d, 0x20)
        e_shentsize, e_shnum, e_shstrndx = struct.unpack_from(">HHH", d, 0x2E)

        raw_hdrs = []
        for i in range(e_shnum):
            o = e_shoff + i * e_shentsize
            name, typ, flags, addr, off, size = struct.unpack_from(">IIIIII", d, o)
            raw_hdrs.append((name, typ, flags, addr, off, size))

        # section-header string table (may itself be compressed)
        self.sections = []
        strtab = self._body(raw_hdrs[e_shstrndx])
        for h in raw_hdrs:
            name_off = h[0]
            end = strtab.find(b"\0", name_off)
            nm = strtab[name_off:end].decode("ascii", "replace") if end >= 0 else ""
            body = self._body(h) if h[1] != 8 else b""
            # h[5] is the *compressed* size for zlib sections; the mapped
            # extent is the inflated length (or h[5] for NOBITS, which has
            # no body at all).
            extent = len(body) if body else h[5]
            self.sections.append({"name": nm, "type": h[1], "flags": h[2],
                                  "addr": h[3], "size": extent,
                                  "raw_size": h[5], "data": body})

    def _body(self, h):
        _, typ, flags, addr, off, size = h
        if typ == 8 or size == 0:          # NOBITS
            return b""
        blob = self.raw[off:off + size]
        if flags & SHF_RPL_ZLIB:
            return zlib.decompress(blob[4:])
        return blob

    def section(self, name):
        for s in self.sections:
            if s["name"] == name:
                return s
        return None

    def read(self, vaddr, n):
        """Read n bytes at a virtual address, or None if unmapped."""
        for s in self.sections:
            if s["addr"] and s["addr"] <= vaddr < s["addr"] + s["size"]:
                o = vaddr - s["addr"]
                if o + n <= len(s["data"]):
                    return s["data"][o:o + n]
        return None

    def u32(self, vaddr):
        b = self.read(vaddr, 4)
        return None if b is None else struct.unpack(">I", b)[0]

    def find_u32(self, value, sections=None):
        """Every virtual address holding this big-endian word."""
        needle = struct.pack(">I", value)
        hits = []
        for s in self.sections:
            if not s["addr"] or not s["data"]:
                continue
            if sections and s["name"] not in sections:
                continue
            start = 0
            while True:
                i = s["data"].find(needle, start)
                if i < 0:
                    break
                if i % 4 == 0:
                    hits.append(s["addr"] + i)
                start = i + 1
        return hits


if __name__ == "__main__":
    import sys
    r = Rpx(sys.argv[1])
    for s in r.sections:
        if s["addr"]:
            print(f"  {s['name']:<16} addr=0x{s['addr']:08x} size=0x{s['size']:08x} "
                  f"{'zlib' if s['flags'] & SHF_RPL_ZLIB else ''}")


def symbols(r):
    """{name: (value, size)} from .symtab/.strtab, if present."""
    import struct as _s
    st = r.section(".symtab")
    strt = r.section(".strtab")
    if not st or not strt:
        return {}
    out = {}
    d, sd = st["data"], strt["data"]
    for o in range(0, len(d) - 15, 16):
        nm, val, size, info, other, shndx = _s.unpack_from(">IIIBBH", d, o)
        if nm == 0 or nm >= len(sd):
            continue
        e = sd.find(b"\0", nm)
        name = sd[nm:e].decode("ascii", "replace")
        if name:
            out[name] = (val, size)
    return out
