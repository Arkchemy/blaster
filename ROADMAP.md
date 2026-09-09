# blaster roadmap

Format research and tooling. Blaster is where a format gets understood; the
other repos consume the result.

## Solved, verified against the disc

- **igArchive container** — `IGA\x1a`, little-endian header on a big-endian
  title, FNV-1a-32 filename hashes, 2048-byte sectors, block table where bit 15
  marks compression
- **Block compression** — each block is raw LZMA1: `u16` length, then
  `5d 00 80 00 00` (lc=3 lp=0 pb=2, 32 KB dict), no size field
- **igz** — section table at `0x14`, pools resolved by name, fixup tags stored
  byte-reversed, packed pointer v7 as `pool = v >> 27, offset = v & 0x07FFFFFF`
- **The retail `.rpx` is unstripped** — 175,174 symbols. `rpx.py` reads
  sections, symbols and virtual addresses, which turns layout questions into
  lookups instead of inferences.

See `FORMATS.md` and `IGZ.md`.

## Open

- [ ] **`.hka` animation** — reportedly stored plainly; ~20 MB per file across
      SSA and Giants. Unparsed.
- [ ] **Model/mesh igz** — the asset path jouster will need. `igModelTool2`
      (Apache-2.0) and `igArchiveLib` (MIT) exist publicly and should be read
      before writing anything.
- [ ] **Textures** — GX2 surface formats, tiling and swizzle. Needed by the
      graphics work and shared with it.
- [ ] **Audio banks** — `Item_Pet_*.arc` carry 3–40 banks each.
- [ ] **`alchemy.xml`** — the runtime config schema. Now known to matter far
      more than it looked: it sets the start level and the VRAM budget.

## Tooling

- [x] `rpx.py` — RPX sections, symbols, virtual addresses
- [x] `igarchive_extract.py` — LZMA1 block extraction
- [x] `igz_tools.py`, `extract_field_schema.py`
- [ ] a round-trip test: extract an archive, repack it, compare byte for byte.
      Nothing currently proves the writers are correct.
- [ ] a schema dump for every metaobject in the binary, generated rather than
      hand-transcribed
