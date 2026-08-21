#!/usr/bin/env python3
"""
Real round-trip test for igz_tools.py's IGA archive writer, run against
this project's own real, legally-dumped game files (not synthetic test
data) -- the same real check that first confirmed write_iga_archive()
actually produces a valid, correctly-repacked archive: replace one real
entry's content, write a new archive, read it back, and confirm the
replaced entry has the new content while every other entry stays
byte-identical to the original.

Writes its output to a real OS temp file via `tempfile` (not a hardcoded
/tmp path -- a real, hard-learned lesson from testing this exact writer
the first time: /tmp can have its own per-user quota separate from actual
free disk space, and a 4GB scratch extraction left over from an unrelated
investigation quietly filled it), and cleans up after itself either way.

Usage: python3 tools/test_igz_tools.py
"""

import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from igz_tools import read_iga_archive, extract_iga_file, write_iga_archive, read_igz_file, write_igz_file

SRC = "stufftonotincludeintherepo/decrypted/GM0005000010142D00000000000000/content/character/000_AirDragon.arc"
ENTRY = (
    "c:/tfb/build/wiiu/levels/includes/minions/airdragon/sounds/"
    "vo_tempest_dragon_selected_01.wav/0x38fe1687.wav.hz.wav.enc"
)


def test_iga_archive_roundtrip() -> bool:
    new_content = b"THIS IS REPLACEMENT TEST AUDIO DATA - NOT REAL AUDIO"
    with tempfile.TemporaryDirectory() as tmp:
        out_path = str(Path(tmp) / "AirDragon_modified.arc")
        write_iga_archive(SRC, {ENTRY: new_content}, out_path)

        orig = read_iga_archive(SRC)
        modified = read_iga_archive(out_path)

        ok = orig.num_files == modified.num_files
        if not ok:
            print(f"FAIL: file count changed ({orig.num_files} -> {modified.num_files})")

        for d_orig, d_mod in zip(orig.descriptors, modified.descriptors):
            if d_orig.name != d_mod.name:
                print(f"FAIL: name mismatch: {d_orig.name!r} vs {d_mod.name!r}")
                ok = False
                continue
            mod_bytes = extract_iga_file(out_path, d_mod)
            if d_orig.name == ENTRY:
                if mod_bytes != new_content:
                    print(f"FAIL: replaced entry does not match new content: {d_orig.name}")
                    ok = False
            else:
                orig_bytes = extract_iga_file(SRC, d_orig)
                if mod_bytes != orig_bytes:
                    print(f"FAIL: unchanged entry differs from original: {d_orig.name}")
                    ok = False
    return ok


def test_igz_object_roundtrip() -> bool:
    """Real round-trip test for write_igz_file -- one level deeper than the
    archive-level test above: replace one real *object's* data inside a
    real .igz, rebuild the whole file, and confirm every other real
    object (including ones whose real offset shifts because of the size
    change) comes back byte-identical. Random sizes across a broad real
    sample, not just one hand-picked case -- this is exactly the kind of
    boundary-dependent bug (see the real 4-byte RVTB padding bug this
    caught during development) that a single fixed-size test would miss."""
    arc = read_iga_archive(SRC)
    igz_entries = [d for d in arc.descriptors if d.name.endswith(".igz")]
    if not igz_entries:
        print("SKIPPED: no .igz entries found in the test archive")
        return True

    random.seed(1234)  # deterministic across runs, not because it matters cryptographically
    ok = True
    tested = 0
    for desc in igz_entries:
        blob = extract_iga_file(SRC, desc)
        try:
            igz = read_igz_file(blob)
        except ValueError:
            continue
        if igz.version != 7 or not igz.objects:
            continue
        for obj_idx in range(len(igz.objects)):
            new_len = random.choice([0, 1, 7, 33, 127, 500])
            new_data = bytes((i * 31 + 7) % 256 for i in range(new_len))
            tested += 1
            try:
                new_blob = write_igz_file(blob, {obj_idx: new_data})
            except ValueError as e:
                print(f"FAIL (unexpected refusal): {desc.name} object {obj_idx}: {e}")
                ok = False
                continue
            reread = read_igz_file(new_blob)
            if reread.objects[obj_idx].data != new_data:
                print(f"FAIL: {desc.name} object {obj_idx}: replaced data mismatch")
                ok = False
            for i, (o1, o2) in enumerate(zip(igz.objects, reread.objects)):
                if i == obj_idx:
                    continue
                if o1.data != o2.data or o1.type_name != o2.type_name:
                    print(f"FAIL: {desc.name} object {i} ({o1.type_name}) changed unexpectedly")
                    ok = False
    if tested == 0:
        print("SKIPPED: no real v7 objects found to test against")
    return ok


def main() -> int:
    if not Path(SRC).exists():
        print(f"SKIPPED: {SRC} not present (needs a real game dump to test against)")
        return 0

    ok = test_iga_archive_roundtrip()
    ok = test_igz_object_roundtrip() and ok

    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
