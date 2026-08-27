#!/bin/sh
# Compiles a testdata/*.c source as an unstripped, big-endian PowerPC32
# relocatable object -- the recomp tool's input.
#
# -fwrapv -fno-sanitize=undefined: without these, zig cc/clang inserts
# UBSan-style trap sequences around signed arithmetic (overflow checks),
# which drags in instructions well outside this milestone's supported
# subset and isn't representative of how a retail game binary is built
# anyway.
#
# eabihf, not eabi: the Wii U's Espresso is a PPC750 derivative with a
# real FPU and the retail binary is built for it, so hardware floating
# point is what these tests should be producing. Plain
# powerpc-freestanding-eabi leaves that to the zig version's own
# default, and newer zig (checked on 0.16.0) picks SOFT float there --
# which turns every FP operation into a libgcc helper call
# (__adddf3, __truncdfsf2, ...) that recomp emits as an unresolved
# ppc___adddf3 extern, and means testdata/addis_frsp.c stops containing
# the frsp instruction it exists to cover. Pinning eabihf makes that
# independent of which zig is installed.
set -e
cd "$(dirname "$0")/.."

ZIG="${ZIG:-$HOME/devtools/zig/zig}"
SRC="${1:-testdata/arithmetic.c}"
OUT="${2:-/tmp/$(basename "$SRC" .c)_ppc.o}"
OPT="${3:--O0}"

"$ZIG" cc -target powerpc-freestanding-eabihf "$OPT" -fwrapv -fno-sanitize=undefined \
    -c "$SRC" -o "$OUT"

echo "wrote $OUT"
