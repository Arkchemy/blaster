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

## Documentation

| Document | What it covers |
| --- | --- |
| [`ROADMAP.md`](ROADMAP.md) | Formats solved and formats open |
| [`FORMATS.md`](FORMATS.md) | igArchive container, block table, compression |
| [`IGZ.md`](IGZ.md) | igz structure, pools, fixups, packed pointers |
