# Alchemy container formats

What is established about the containers the engine reads, and where each fact
came from. Community knowledge is attributed and marked unverified until it is
checked against the disc.

## `.bld` is an igArchive, not an igz

Verified 2026-09-06 against `content/permanent/bootstrap.bld` on the USA disc.
Despite the extension, a `.bld` is an **igArchive** container:

```
+0x00  49 47 41 1a   "IGA\x1a"   magic
+0x04  0x00000008                version
+0x08  0x0000006a                106 entries
+0x0c  0x00000002
+0x10  0x00000800                2048, sector or alignment
+0x14  0x7fffffff
+0x1c  0x00030800                198656, just under the 198695-byte file
+0x20  0x00000027                39
+0x28  0x00000024                36
+0x34  0x4d44506c
```

The header is **little-endian** even though the title is big-endian PowerPC.

This is confirmed end to end against jouster's boot: the runtime logs
`fsz=198695`, which is `bootstrap.bld`'s exact size, and
`head=[0x4947411a,0x08000000,0x6a000000,0x02000000]`, which is these same
first sixteen bytes read as big-endian words. The read path is correct; the
boot stalls after this, not before it.

150 `.bld` files ship on the disc.

## `.igz` is a list of objects

Community knowledge, from the Discord, 2026-09-06 — **not yet verified here**:

> An igz file (`level.bld` and friends) is a list of objects, and one of those
> objects is just an array of bytes.

That matches what the engine does at runtime: `igObjectList` and `igDataList`
are the types jouster is currently sitting inside, and a raw byte array as one
member of an object list is exactly the shape a blob field would take.

## igArchive compresses in blocks, not per file

maff, 2026-09-06: *"the igarchive format uses a compressed block system for
compression and such"*. Verified against all 150 `.bld` files on the USA disc.

The payload is split into fixed-size blocks and each is compressed on its own,
so reading one archive means decompressing many times. The block table is one
`uint16` per block at `+0x54`:

* **bit 15** — set = compressed, clear = stored
* **bits 0-14** — start sector, multiplied by the block size at `+0x10`

`bootstrap.bld` decodes as **36 blocks, 35 compressed and 1 stored**, sectors
0..95, and its payload is exactly 97 blocks of 2048. Across the whole disc:
50,052 blocks, of which 2,654 (5.3%) are stored. Every archive is version 8
with a 2048-byte block, and every payload is a whole number of blocks.

**This is the number that matters for the boot.** jouster reaches LZMA
**once** (`INFLATE lzma n=1`) and that one call fails on an allocation. A
correct load of `bootstrap.bld` has to run it **35 times**. So the archive not
draining is not a subtle protocol problem -- the loader fails on the first
block of thirty-five and stops.

`blaster/igarchive_blocks.py` dumps the table for any archive.

### Known limit: three archives use more than one block group

`Init_Setup.bld`, `Credits.bld` and `PvP_MainControl.bld` have a table that
restarts at `0x8000` partway through -- a second block group, not corruption --
and `Init_Setup.bld` also pads with `0xffff`. The group boundaries are not
understood yet, and the tool reports them rather than guessing. The other 147
archives decode as a single group.

## `.hka` is stored, not compressed

Community knowledge, same source, **unverified**:

> The `.hka` files are just stored like that.

i.e. held in the archive uncompressed rather than LZMA'd. Worth confirming,
because it bears directly on the boot: jouster reaches LZMA exactly once
(`INFLATE lzma n=1 ok=1`) against an archive with 106 entries. If some entries
are stored rather than compressed, the loader needs a path that does not run
them through LZMA at all.

Also reported: every SSA and Giants Build 1 `.hka` is only around 20 MB in
total, which the source called surprising. No loose `.hka` files exist on the
disc, so they live inside the archives.

## Platform-specific content does not matter here

Also from the Discord, and worth writing down because it is the reasoning
behind the whole approach:

> The files use a lot of platform-specific stuff, but for a recomp that
> shouldn't affect anything.

Correct, and it is the argument for recompiling over reimplementing. A
reimplementation has to understand every platform-specific encoding a file
uses. A recompilation runs *the original code that already understands them*,
so platform-specific asset content is handled by the same routines that
handled it on the Wii U.

## igz fixups: EXNM, and how external references work

From bone, 2026-09-06, **not yet verified here**:

* An igz carries fixup sections; **EXNM** is the external-name one.
* An EXNM entry is **8 bytes: two 32-bit indices into TSTR**, the string
  table. One is the namespace, the other the name -- bone was not certain
  which way round.
* So instead of a plain `0000000000000001` you find pairs like
  `0000000800000002` in the middle of the section.
* Resolved, a pair names something like **`ActorInfo::testActor`**.

He also said memory pools on Wii U are **counted**, and listed
`0, 8, 10, 18, 20, 28` (hex, spaced 8 apart, so six entries of 8 bytes),
noting Wii U *"uses the first five bits, instead of 4 like in the other
games"*, and that **there is a defined order of which memory pool comes first
in the file**. Asked which is 6th in `bootstrap.bld`, he answered **`0x28`** --
consistent with 8-byte entries where the 6th sits at offset 0x28.

### An open discrepancy worth resolving

At runtime our LZMA path asks `igMemoryContext::getMemoryPoolByIndex()` for
**`0x1c`** and gets NULL. `0x1c` is not in bone's list, and it is not a
multiple of 8, so either it is a different quantity from the one he listed
(an index rather than an offset) or we are deriving it wrongly. This is the
single value the boot dies on, so it is worth settling before anything else.

Where our `0x1c` comes from, exactly: a game global -- jouster address 421612,
`.bss+306684` -- holds `0x1c`, and that value is passed straight to
`getMemoryPoolByIndex`. Separately, a different path derives an index by
`word >> 22` from an object's `+0x04` field, which for the objects we have
dumped (`+0x04 = 0x00800001`) yields **2**, matching the `idx=2` the runtime
reports elsewhere. Those two paths disagree, and only the first one fails.

## Who to ask

**Bone** and **NefariousTechSupport** are the igz experts. NefariousTechSupport
wrote [igRewrite8](https://github.com/NefariousTechSupport/igRewrite8), the C#
reimplementation of the Alchemy runtime, and is already credited in
CONTRIBUTORS. Ask them before reverse-engineering igz internals from scratch.

Note that igRewrite8 models the **filesystem and work-item** side well and its
`igMemoryPool` is a 45-line stub, so it answers file-format questions but not
allocator ones.
