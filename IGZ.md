# igz format reference

Derived from **igRewrite8** (`igLibrary/Core/igIGZLoader.cs`, Apache-2.0) and
verified against `bootstrap.bld` on the SSA USA disc, 2026-09-06.

Written because not having it cost a whole session. See the postmortem at the
end before trusting any number in a log.

## Section table

At `0x14`, up to `0x20` entries of 16 bytes, big-endian:

```
u32  memPoolName    byte offset of the pool's name string, from 0x224
u32  offset         where the section's data starts
u32  length
u32  alignment
```

The loop stops at the first entry with `offset == 0`; that count is
`sectionCount`. **Entry 0 is the fixup section**, not a pool -- the loader
keeps its offset as `_fixups`. Entries 1..n are the pools, so **pool index i
is section i+1**.

`bootstrap.bld`'s first igz, decoded:

| i | offset | length | pool name |
|---|---|---|---|
| 0 | 0x800 | 0x98 | *(fixups)* |
| 1 | 0x898 | 0x40 | `Default` |
| 2 | 0x8d8 | — | `Image` |
| 3 | 0x8dc | — | `Vertex` |
| 4 | 0x8e0 | — | `Audio` |
| 5 | 0x8e4 | — | `AnimationData` |
| 6 | 0x8e8 | — | `VertexObject` |
| 7 | 0x8ec | 0x0d | `String` |
| 8 | 0x8f9 | 0x1fc | `Text` |

Pools resolve **by name**, not by number:
`igMemoryContext.Singleton.GetMemoryPoolByName(memoryPoolName)`.

## Packed pointers -- the thing that cost the session

A serialised igz pointer packs a pool index and an offset into one 32-bit
word, and **the split depends on the igz version**:

```csharp
if (_version <= 0x06) (poolIndex << 0x18) + (offsetInPool & 0x00FFFFFF)   // 8-bit pool
else                  (poolIndex << 0x1B) + (offsetInPool & 0x07FFFFFF)   // 5-bit pool
```

SSA Wii U igz is **version 7**, so: **pool = `value >> 27`, offset =
`value & 0x07FFFFFF`**. `_loadedPools` is sized `0x1F`, consistent with 5
bits. This is bone's "five bits instead of four".

So **`0x0000001C` is pool 0 (`Default`), offset 0x1C** -- and it is, as bone
said, the first `igMemoryRefMetaField` pointer any file uses, because of the
first `igObjectList`.

### Three numbering spaces that are easy to confuse

This is where the session went wrong. All three are small integers and none
of them mean the same thing:

1. **igz section/pool index** -- 0..7 here, 5 bits in the packed pointer,
   resolved to a real pool *by name*.
2. **Runtime memory pool index** -- what `Core::igGetMemoryPool(int)` and
   `igMemoryContext::getMemoryPoolByIndex(int)` take. bone lists SSA Wii U's
   as `0, 8, 10, 18, 20, 28`. A different space from (1).
3. **`EMemoryPoolID`** -- igRewrite8's enum, `MP_DEFAULT = 51` upward. From a
   **later game**, and a different space again.

The runtime object header at `+0x04` is a fourth packing: refCount in the low
bits, pool in the top 10, which is why `srwi rN, rM, 0x16` (>> 22) appears in
the recompiled code. That is *not* the igz pointer split.

## Fixup sections

Tags are stored **byte-reversed** relative to the big-endian file, so a search
for `TSTR` finds nothing and `RTST` finds it. igRewrite8 matches them as
reversed u32 constants (`0x52545354` for TSTR). Layout:

```
<tag, byte-reversed><u32 count><u32 total size><u32 header size><data>
```

| tag | field | meaning |
|---|---|---|
| `TMET` | metaobject types | type names, data begins `igOb...` |
| `TSTR` | strings | the string table |
| `TMHN` | | metaobject handles |
| `EXNM` | external names | **pairs of u32, namespace and name, both indices into TSTR** |
| `EXID` | external ids | resolved by hash |
| `RVTB` | `_vtables` | vtable fixups; **also instantiates the objects** |
| `ROOT` | `_objectLists` | the root object list -- `_objectLists[0]` is the main `igObjectList` |
| `ROFS` | `_offsets` | **the offsets that are pointers and need fixing up** |
| `RPID` | `_poolIds` | **memory pool ids** |
| `RSTT` | `_stringTables` | |
| `RSTR` | `_stringRefs` | |
| `RMHN` | `_memoryHandles` | |
| `REXT` / `RNEX` | externals / named externals | |
| `RHND` | `_handles` | |
| `ONAM` | name list | sets `_useNameList` |

Every `R***` table is read with `UnpackCompressedInts` -- they are
**compressed integer lists**, not plain arrays. `bootstrap.bld` carries
`ROFS`, `RPID`, `RVTB`, `ROOT`, `RSTR`, `RMHN`, `REXT`, `RNEX`, plus `TMET`,
`TSTR`, `TMHN`, `EXNM`, `EXID`, `MTSZ`.

## Postmortem: how this went wrong

The boot dies because `Core::igGetMemoryPool(0x1C)` returns NULL. Chasing it
took five instruments over a session, every one of which correctly reported
nothing, because the premise was wrong: nothing was corrupted. `0x1C` is an
unresolved igz pointer sitting in a global that wants a runtime pool index.

What would have prevented it:

* **Reading this file first.** Every fact above was already in igRewrite8,
  which was cloned into this repo hours before it was needed. bone did not
  out-debug anyone; he recognised a value on sight.
* **Treating a small integer as typed.** `0x1C` was compared against
  `EMemoryPoolID` (a different game's enum, a different space) instead of
  being asked "what kind of number is this?"
* **Stopping after two null results, not five.** When several independent,
  correctly-built probes all say "nothing here", the hypothesis is wrong.
  Building a sixth is a way of avoiding that conclusion.
