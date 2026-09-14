#!/bin/sh
# Translate every dumped Latte shader program into a deko3d module.
#
#     build-shaders.sh <dump-dir> <out-dir>
#
# Input is the directory the courier collects from the console (and the
# statically extracted programs beside them): one `*.r600.bin` per shader, the
# raw microcode exactly as GX2 received it. Output is, per shader, the
# generated GLSL, the compiled `.dksh`, and one `manifest.tsv` for the runtime.
#
# The naming is the part that matters at run time. The game does not ask for a
# shader by name -- it hands GX2SetVertexShader a pointer to a program, and the
# port has to recognise it. So each module is named after a hash of the program
# bytes themselves: stable across runs, independent of where the program is
# allocated, and not confusable with a different shader of the same length.
# Four of this game's seven bound programs are within 40 bytes of each other.
#
# The hash is FNV-1a 64 rather than SHA-256, because the other end of this is a
# recompiler shim that has to compute the same value over guest memory. FNV-1a
# is nine lines there; SHA-256 is a dependency. The manifest still records the
# SHA-256 as the provenance key, since that is what a human checks a file
# against, but the runtime only ever needs the filename.
#
# Shaders that do not translate are reported and skipped rather than failing
# the run: the point of a batch is to see how much of the set is covered.
set -e

DUMPS="${1:?usage: build-shaders.sh <dump-dir> <out-dir>}"
OUT="${2:?usage: build-shaders.sh <dump-dir> <out-dir>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
UAM="${UAM:-${DEVKITPRO:-$HOME/devkitpro}/tools/bin/uam}"

[ -x "$UAM" ] || { echo "no uam at $UAM -- set DEVKITPRO or UAM" >&2; exit 1; }
mkdir -p "$OUT"

manifest="$OUT/manifest.tsv"
printf 'fnv1a64\tstage\tmodule\tsource\tsha256\n' > "$manifest"

# FNV-1a 64 over the raw program bytes. Kept here, in one place, beside the
# nine lines of C that have to agree with it.
fnv1a64() {
    python3 -c "import sys,functools;print('%016x' % functools.reduce(lambda h,b: ((h^b)*0x100000001b3) & 0xFFFFFFFFFFFFFFFF, open(sys.argv[1],'rb').read(), 0xcbf29ce484222325))" "$1"
}

ok=0; skipped=0
for f in "$DUMPS"/*.r600.bin; do
    [ -f "$f" ] || continue
    name="$(basename "$f" .r600.bin)"

    key="$(fnv1a64 "$f")"

    if ! stage="$("$HERE/r600_glsl.py" "$f" -o "$OUT/$name.glsl" 2>"$OUT/$name.err")"; then
        echo "SKIP $name -- $(cat "$OUT/$name.err")"
        skipped=$((skipped + 1))
        continue
    fi
    stage="$(printf '%s' "$stage" | cut -f1)"

    if ! "$UAM" -s "$stage" -o "$OUT/$key.dksh" "$OUT/$name.glsl" 2>"$OUT/$name.err"; then
        echo "SKIP $name -- uam rejected the generated GLSL:"
        sed 's/^/       /' "$OUT/$name.err"
        skipped=$((skipped + 1))
        continue
    fi
    rm -f "$OUT/$name.err"

    sha="$(sha256sum "$f" | cut -d' ' -f1)"
    printf '%s\t%s\t%s\t%s\t%s\n' "$key" "$stage" "$key.dksh" "$name" "$sha" >> "$manifest"
    echo "OK   $name ($stage) -> $key.dksh  $(wc -c < "$OUT/$key.dksh") bytes"
    ok=$((ok + 1))
done

echo "$ok translated, $skipped skipped -> $manifest"
