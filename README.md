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

Word order is **little-endian**. An earlier version of this README said
big-endian and was wrong: that test scanned whole programs for end-of-program
bits, where most words are ALU and TEX and bit 21 means something else, so it
counted noise. Scanning the CF section alone gives zero such bits big-endian,
which is impossible, and exactly one little-endian.

`r600.py --cf` disassembles the control-flow section and expands texture
clauses inline:

```
binkPixelShader
   0  TEX              addr=384    (3 instructions)
    0: SAMPLE         R1.w___ <- R0.xy0x  resource=1 sampler=1
    1: SAMPLE         R2.w___ <- R0.xy0x  resource=0 sampler=0
    2: SAMPLE         R0.w___ <- R0.xy0x  resource=2 sampler=2
   1  ALU              addr=256    (14 slots)
   2  EXPORT_DONE      type=0 array_base=0  END_OF_PROGRAM
```

Three single-channel samples at identical coordinates from three separate
resources: a planar YUV fetch, which is what a Bink video shader should be.
The alpha variant adds a fourth into the `w` channel; the default shader takes
all four channels from one texture. The Y/U/V prediction was made from byte
counts before any instruction could be decoded, and it holds at instruction
level. The ISA document
(`reference/r600isa.pdf`) arrived on 2026-09-12; the first thing it did was
disprove the word-order claim above.

### ALU clauses

ALU clauses decode too, which is where a shader's arithmetic actually lives.
The clause header counts 64-bit *slots*, not instructions: up to five
instructions issue together as a group, ended by the `LAST` bit, and any
literal constants the group reads occupy whole slots of their own directly
after it. Skipping those literal slots is not cosmetic -- decode one as an
instruction and every slot after it is misaligned.

```
   1  ALU              addr=256    (14 slots)
    0.0  MUL              ---- = R1.x, C0.x
    0.1  MUL              ---- = R1.x, C0.z
    0.2  MUL              ---- = R1.x, C0.y
    0.3  MOV              R1.w = literal.x
    0.lit  1.0
    1.5  MULADD           R123.x = R2.x, C3.y, PV.w
    ...
    3.11 ADD              R1.x = PV.z, C2.x
```

Y (`R1.x`, from the first sample) times a constant row, then the two
chroma planes accumulated with `MULADD`, then a bias vector added, then alpha
set to a literal 1.0 and exported: a YUV-to-RGB colour conversion, written out
by the hardware in the order a compiler would emit it. `binkVertexShader` and
`defaultVertexShader` come out as a four-row `MUL`/`MULADD` matrix multiply
against `C0`-`C3` with a texcoord passthrough, which is what a vertex shader
for a screen-space video quad has to be. Nothing here was predicted in advance
of decoding -- unlike the Y/U/V sample counts above -- but two shaders landing
on exactly the programs their names claim is not something a wrong opcode
table produces.

Two encodings share the second doubleword: `ALU_WORD1_OP2` (up to two source
operands) and `ALU_WORD1_OP3` (three). The R700 document contradicts itself on
where the OP2 opcode field starts -- its prose says ten bits at `[17:8]`, its
own field table says eleven at `[17:7]` -- and the shaders settle it. Read at
`[17:8]`, every `MUL` above decodes as `ADD` and the colour conversion becomes
nonsense. The field is `[17:7]`.

The opcode tables in `alu_tables.py` come from the field enumerations in the
microcode-format chapter, not from the per-instruction reference pages. Those
also disagree: the `NOP` page says "opcode 0 (0x0)", which is `ADD`'s opcode,
while the enumeration puts `NOP` at 26. The enumeration is what the shaders
agree with. Regenerate the tables with:

```bash
python3 -c "import re,sys; d=open('../reference/r700.txt').read(); [print(m.group(2),m.group(1),m.group(3)) for m in re.finditer(r'(\d+)\s+OP([23])_INST_([A-Z0-9_]+)', d)]"
```

### Translation to deko3d

`r600_glsl.py` turns a decoded program into GLSL, and `build-shaders.sh` runs
the whole dump through it and compiles each result with devkitPro's `uam` into
a deko3d `.dksh` module:

```bash
DEVKITPRO=~/devkitpro ./build-shaders.sh ../_hardware-logs/shaders out/
```

All five shaders in the executable translate and compile. The output is a
transliteration, not a decompilation -- registers become `vec4`s and slots
become assignments -- because a transliteration can be read line by line
against `r600.py --cf` and a reconstruction cannot:

```glsl
if (floatBitsToInt(uf[0].x) != floatBitsToInt(0.0)) {
    vec4 s0 = texture(tex0, vec2(R0.x, R0.y));
    R0.x = s0.x; R0.y = s0.y; R0.z = s0.z; R0.w = s0.w;
} else {
    float t0 = 1.0; ...
}
color0 = vec4(R0.x, R0.y, R0.z, R0.w);
```

That is `defaultPixelShader` in full: sample the texture if the texture-enable
constant is set, otherwise white.

Three hardware rules shape the output, and each one is a bug if ignored:

**A group issues at once.** Every slot in an instruction group reads the
register file and PV as they stood *before* the group. So each slot's result
goes to a temporary and the writes happen together at the end of the group.
Writing inline is wrong exactly when a group reads and writes the same
register -- which both vertex shaders do, in the last group of the matrix
multiply.

**The trans slot writes PS, not PV, and nothing in the encoding says which
slot that is.** The five units are fed in the fixed order X, Y, Z, W, T, so a
vector slot's destination channel always advances past the previous one; a
slot that does not advance cannot be a vector slot. `binkPixelShader`'s first
group ends with a `MOV` to channel `w` when an earlier slot already wrote `w`.
Treated as a vector slot, it clobbers a PV channel the next group reads, and
the colour conversion silently loses its blue term.

**A shader input is a register read before it is written.** Not every register
the program touches: compilers here use `R123` as a dummy destination for
results only wanted through PV, and declaring that an input claims a varying
at location 123 that nothing ever writes.

Unsupported instructions raise rather than emitting something plausible. The
one piece of control flow reconstructed is the `PUSH`/`JUMP`/`ELSE`/`POP`
diamond a compiler emits for an `if`; loops and nested pushes are refused,
because an if/else can be checked by eye against the disassembly and a
structurizer guessing at the predicate stack cannot.

Two mappings the translation depends on were **measured on hardware** rather
than assumed: that fetch-shader attribute *N* arrives in GPR *N+1*, and that
uniform-register offsets are u32 words so constant-file index *n* sits at
offset *4n*. Both hold. The evidence, including the `GX2AttribStream` field
order recovered from the data itself, is in `jouster/docs/graphics-plan.md`.

`build-shaders.sh` also writes a `manifest.tsv` keyed by the **SHA-256 of the
program bytes**. At run time the game does not name a shader -- it hands
`GX2SetVertexShader` a pointer -- so the port has to recognise programs by
content. Size will not do it: four of the seven programs this game binds are
within 40 bytes of each other.

### Prior art

Everything above was decoded from the AMD document rather than from existing
code, deliberately. The tools that already exist here are worth knowing about,
but their licences decide what can be done with them:

| Project | What it has | Licence | Use |
| --- | --- | --- | --- |
| [decaf-emu](https://github.com/decaf-emu/decaf-emu) | `latte-assembler`, `LatteDecompiler` -- a complete R700-to-GLSL path | GPLv3 | **Read only.** Nothing from it can be copied into Arkchemy |
| [kinnay/Nintendo-File-Formats](https://github.com/kinnay/Nintendo-File-Formats) | `gfx2.md`, the GFD container documented field by field | Documentation | Confirms `gfd.py` field for field, independently |
| [Exzap/CafeGLSL](https://github.com/Exzap/CafeGLSL) | GLSL compiler running on the Wii U itself | MIT | Usable; useful mainly for generating known-good shaders to test against |
| [GaryOderNichts/wiiu-shaders](https://github.com/GaryOderNichts/wiiu-shaders) | Worked GX2 shader examples | MIT | Usable as test input |

The GPLv3 line matters more than it looks. decaf-emu has solved this exact
problem well, and reading it would be faster than reading the ISA document --
but a static recompiler that ships GPLv3-derived code inherits GPLv3, so the
document is the only route that keeps the option open.

## Documentation

| Document | What it covers |
| --- | --- |
| [`ROADMAP.md`](ROADMAP.md) | Formats solved and formats open |
| [`FORMATS.md`](FORMATS.md) | igArchive container, block table, compression |
| [`IGZ.md`](IGZ.md) | igz structure, pools, fixups, packed pointers |
