# blaster

Python tools and host-testable C regression tests for the Arkchemy Skylanders
recompiler project. Field-schema extraction, save-format tooling, the Wii→Wii U
audio transplant pipeline, and `verify.sh` — the actual recompiler-correctness
test suite.

## Running `verify.sh`

`verify.sh` predates the org's split into separate repos and still uses paths
that assume it's sitting inside the original monorepo (`recomp/`, `tools/`,
`testdata/` all as siblings under one root). To run it, clone this repo
(`blaster`) and [`conquertron`](https://github.com/Arkchemy/conquertron)
(the recompiler core) as siblings, then symlink or copy `conquertron`'s
contents in as `recomp/` and this repo's own contents in as `tools/`:

```bash
mkdir arkchemy-verify && cd arkchemy-verify
git clone https://github.com/Arkchemy/conquertron recomp
git clone https://github.com/Arkchemy/blaster tools
cp -r tools/testdata .
export ZIG=/path/to/zig
export QEMU_AARCH64=/path/to/qemu-aarch64-static
sh tools/verify.sh
```

`testdata/` needs to sit at the root alongside `recomp/` and `tools/`, not
inside either — it's a real, git-tracked directory in this repo
(`blaster/testdata/`), just referenced by `verify.sh` via a monorepo-relative
path rather than `tools/testdata/`.

## Shaders

The Wii U shaders are **not in the archives**. The GX2 workflow compiles a
shader into a C byte array, so they are linked into the executable and sit in
`.rodata` with a `_size` symbol beside each. Five of them, found by the source
filenames the compiler left in the binary:

    gfx/defaultVertexShader.c        gfx/defaultPixelShader.c
    movie/binkMovie/binkVertexShader.c
    movie/binkMovie/binkPixelShader.c
    movie/binkMovie/binkAlphaPixelShader.c

`gfd.py` reads them:

```sh
./gfd.py "path/to/tfbGame_cafe.rpx" -o out/
```

| shader | R600 program | register block |
| --- | --- | --- |
| defaultVertexShader | 440 B (55 words) | 556 B |
| defaultPixelShader | 400 B (50 words) | 388 B |
| binkVertexShader | 408 B (51 words) | 504 B |
| binkPixelShader | 432 B (54 words) | 536 B |
| binkAlphaPixelShader | 448 B (56 words) | 572 B |

The container is GFD (`Gfx2`) v7.1 — a 32-byte file header, then blocks of
32-byte header plus data: a header block holding the GX2 register struct,
padding, a program block of raw R600 microcode, and an end marker.

Worth recording how this was got wrong first. The GX2 struct offsets are
documented in decaf-emu and Cemu and are easy to recite, and reading the blobs
as bare `GX2VertexShader` structs produced a size of 255 and a program pointer
of `0x000000ff` — which is what being wrong looks like. The tool parses the
container and reports what it finds rather than asserting a layout.

**The Bink pair matters beyond shader work**: they are the shaders the boot
video needs, which is a milestone of its own.

### Program structure

`r600.py` reports the layout of an extracted program. Every one of the five is
the same shape — **CF section at byte 0, clauses from byte 256**:

| shader | CF | ALU clause | TEX clause |
| --- | --- | --- | --- |
| defaultVertexShader | 6 instr | 184 B | — |
| defaultPixelShader | 6 | 40 B | **1** fetch |
| binkVertexShader | 6 | 152 B | — |
| binkPixelShader | 3 | 112 B | **3** fetches |
| binkAlphaPixelShader | 3 | 96 B | **4** fetches |

The texture counts were a **prediction before they were a measurement**. Bink
video is YUV, so its pixel shader should sample three planes and the alpha
variant four; the default shader should sample one. Three for three, all exact
multiples of 16 bytes. A wrong instruction size or word order would not
produce that.

Word order is big-endian, established the same way: testing the CF
end-of-program bit gave 3 candidate positions big-endian against 15 scattered
little-endian, and the layout above comes out clean one way and as noise the
other.

`r600.py` is **not a disassembler**, deliberately. The per-instruction
encodings live in AMD's R600/R700 ISA document, which is not on this machine,
and writing a decoder from memory produces output that looks like a
disassembly and is wrong in ways nobody notices for a week.

## Documentation

| Document | What it covers |
| --- | --- |
| [`ROADMAP.md`](ROADMAP.md) | Formats solved and formats open |
| [`FORMATS.md`](FORMATS.md) | igArchive container, block table, compression |
| [`IGZ.md`](IGZ.md) | igz structure, pools, fixups, packed pointers |
