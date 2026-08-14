#!/bin/sh
# End-to-end verification for Milestone 1: recompile testdata/arithmetic.c's
# PowerPC build, then check that both a host-native build and a
# QEMU-emulated ARM64 build of the generated C produce the same result as a
# plain native build of the original source (ground truth).
set -e
cd "$(dirname "$0")/.."

ZIG="${ZIG:-$HOME/devtools/zig/zig}"
QEMU_AARCH64="${QEMU_AARCH64:-$HOME/devtools/qemu-aarch64-static}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "== Building recomp tool =="
cmake -S recomp -B recomp/build -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build recomp/build -j"$(nproc)" >/dev/null
RECOMP="recomp/build/recomp"

echo "== Ground truth (native build of original source) =="
gcc -O0 testdata/arithmetic.c testdata/host_main.c -o "$WORK/ground_truth"
GROUND_TRUTH="$("$WORK/ground_truth")"
echo "ground truth result: $GROUND_TRUTH"

echo "== Compiling test program for PowerPC =="
testdata/build_ppc.sh testdata/arithmetic.c "$WORK/arithmetic_ppc.o" >/dev/null

echo "== Recompiling PPC object to C =="
"$RECOMP" "$WORK/arithmetic_ppc.o" -o "$WORK/generated.c"

echo "== Host-native check =="
gcc -O0 -Irecomp/include "$WORK/generated.c" tools/gen_harness.c -o "$WORK/generated_host"
HOST_RESULT="$("$WORK/generated_host")"
echo "host recompiled result: $HOST_RESULT"

echo "== ARM64 cross-compile + QEMU check =="
"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/generated.c" tools/gen_harness.c -o "$WORK/generated_arm64" 2>/dev/null
ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/generated_arm64")"
echo "arm64 recompiled result (qemu): $ARM64_RESULT"

echo "== Stripped-binary check (heuristic function boundary recovery) =="
"$ZIG" cc -target powerpc-freestanding-eabi -O0 -fwrapv -fno-sanitize=undefined -nostdlib \
    -Wl,-e,compute -o "$WORK/linked.elf" testdata/arithmetic.c
"$RECOMP" --stripped --entry-alias compute "$WORK/linked.elf" -o "$WORK/stripped_generated.c" >&2
gcc -O0 -Irecomp/include "$WORK/stripped_generated.c" tools/gen_harness.c -o "$WORK/stripped_generated_host"
STRIPPED_RESULT="$("$WORK/stripped_generated_host")"
echo "stripped/recovered result: $STRIPPED_RESULT"

echo "=========================================="
if [ "$GROUND_TRUTH" = "$HOST_RESULT" ] && [ "$GROUND_TRUTH" = "$ARM64_RESULT" ] && [ "$GROUND_TRUTH" = "$STRIPPED_RESULT" ]; then
    echo "PASS (integer/arithmetic): all results match ($GROUND_TRUTH)"
else
    echo "FAIL (integer/arithmetic): results differ (ground truth=$GROUND_TRUTH, host=$HOST_RESULT, arm64=$ARM64_RESULT, stripped=$STRIPPED_RESULT)"
    exit 1
fi

echo ""
echo "== Floating-point pipeline (testdata/floating.c) =="
gcc -O0 testdata/floating.c testdata/float_host_main.c -o "$WORK/float_ground_truth"
FLOAT_GROUND_TRUTH="$("$WORK/float_ground_truth")"
echo "ground truth result: $FLOAT_GROUND_TRUTH"

testdata/build_ppc.sh testdata/floating.c "$WORK/floating_ppc.o" >/dev/null
"$RECOMP" "$WORK/floating_ppc.o" -o "$WORK/float_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/float_generated.c" tools/gen_harness_float.c -o "$WORK/float_generated_host"
FLOAT_HOST_RESULT="$("$WORK/float_generated_host")"
echo "host recompiled result: $FLOAT_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/float_generated.c" tools/gen_harness_float.c -o "$WORK/float_generated_arm64" 2>/dev/null
FLOAT_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/float_generated_arm64")"
echo "arm64 recompiled result (qemu): $FLOAT_ARM64_RESULT"

echo "=========================================="
if [ "$FLOAT_GROUND_TRUTH" = "$FLOAT_HOST_RESULT" ] && [ "$FLOAT_GROUND_TRUTH" = "$FLOAT_ARM64_RESULT" ]; then
    echo "PASS (floating-point): all results match ($FLOAT_GROUND_TRUTH)"
else
    echo "FAIL (floating-point): results differ (ground truth=$FLOAT_GROUND_TRUTH, host=$FLOAT_HOST_RESULT, arm64=$FLOAT_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Bitwise/shift/byte-halfword pipeline (testdata/bitops.c) =="
gcc -O0 testdata/bitops.c testdata/bitops_host_main.c -o "$WORK/bitops_ground_truth"
BITOPS_GROUND_TRUTH="$("$WORK/bitops_ground_truth")"
echo "ground truth result: $BITOPS_GROUND_TRUTH"

testdata/build_ppc.sh testdata/bitops.c "$WORK/bitops_ppc.o" >/dev/null
"$RECOMP" "$WORK/bitops_ppc.o" -o "$WORK/bitops_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/bitops_generated.c" tools/gen_harness.c -o "$WORK/bitops_generated_host"
BITOPS_HOST_RESULT="$("$WORK/bitops_generated_host")"
echo "host recompiled result: $BITOPS_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/bitops_generated.c" tools/gen_harness.c -o "$WORK/bitops_generated_arm64" 2>/dev/null
BITOPS_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/bitops_generated_arm64")"
echo "arm64 recompiled result (qemu): $BITOPS_ARM64_RESULT"

echo "=========================================="
if [ "$BITOPS_GROUND_TRUTH" = "$BITOPS_HOST_RESULT" ] && [ "$BITOPS_GROUND_TRUTH" = "$BITOPS_ARM64_RESULT" ]; then
    echo "PASS (bitwise/shift): all results match ($BITOPS_GROUND_TRUTH)"
else
    echo "FAIL (bitwise/shift): results differ (ground truth=$BITOPS_GROUND_TRUTH, host=$BITOPS_HOST_RESULT, arm64=$BITOPS_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Rotate/mask pipeline (testdata/rotate.c, -O1 -- rlwinm/rlwimi/clrlwi/rotlwi only show up above -O0) =="
gcc -O0 testdata/rotate.c testdata/rotate_host_main.c -o "$WORK/rotate_ground_truth"
ROTATE_GROUND_TRUTH="$("$WORK/rotate_ground_truth")"
echo "ground truth result: $ROTATE_GROUND_TRUTH"

testdata/build_ppc.sh testdata/rotate.c "$WORK/rotate_ppc.o" -O1 >/dev/null
"$RECOMP" "$WORK/rotate_ppc.o" -o "$WORK/rotate_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/rotate_generated.c" tools/gen_harness_rotate.c -o "$WORK/rotate_generated_host"
ROTATE_HOST_RESULT="$("$WORK/rotate_generated_host")"
echo "host recompiled result: $ROTATE_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/rotate_generated.c" tools/gen_harness_rotate.c -o "$WORK/rotate_generated_arm64" 2>/dev/null
ROTATE_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/rotate_generated_arm64")"
echo "arm64 recompiled result (qemu): $ROTATE_ARM64_RESULT"

echo "=========================================="
if [ "$ROTATE_GROUND_TRUTH" = "$ROTATE_HOST_RESULT" ] && [ "$ROTATE_GROUND_TRUTH" = "$ROTATE_ARM64_RESULT" ]; then
    echo "PASS (rotate/mask): all results match ($ROTATE_GROUND_TRUTH)"
else
    echo "FAIL (rotate/mask): results differ (ground truth=$ROTATE_GROUND_TRUTH, host=$ROTATE_HOST_RESULT, arm64=$ROTATE_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Carry (64-bit arithmetic) pipeline (testdata/carry.c) =="
gcc -O0 testdata/carry.c testdata/carry_host_main.c -o "$WORK/carry_ground_truth"
CARRY_GROUND_TRUTH="$("$WORK/carry_ground_truth")"
echo "ground truth result: $CARRY_GROUND_TRUTH"

testdata/build_ppc.sh testdata/carry.c "$WORK/carry_ppc.o" >/dev/null
"$RECOMP" "$WORK/carry_ppc.o" -o "$WORK/carry_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/carry_generated.c" tools/gen_harness_carry.c -o "$WORK/carry_generated_host"
CARRY_HOST_RESULT="$("$WORK/carry_generated_host")"
echo "host recompiled result: $CARRY_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/carry_generated.c" tools/gen_harness_carry.c -o "$WORK/carry_generated_arm64" 2>/dev/null
CARRY_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/carry_generated_arm64")"
echo "arm64 recompiled result (qemu): $CARRY_ARM64_RESULT"

echo "=========================================="
if [ "$CARRY_GROUND_TRUTH" = "$CARRY_HOST_RESULT" ] && [ "$CARRY_GROUND_TRUTH" = "$CARRY_ARM64_RESULT" ]; then
    echo "PASS (carry/64-bit): all results match ($CARRY_GROUND_TRUTH)"
else
    echo "FAIL (carry/64-bit): results differ (ground truth=$CARRY_GROUND_TRUTH, host=$CARRY_HOST_RESULT, arm64=$CARRY_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Division pipeline (testdata/division.c) =="
gcc -O0 testdata/division.c testdata/division_host_main.c -o "$WORK/division_ground_truth"
DIVISION_GROUND_TRUTH="$("$WORK/division_ground_truth")"
echo "ground truth result: $DIVISION_GROUND_TRUTH"

testdata/build_ppc.sh testdata/division.c "$WORK/division_ppc.o" >/dev/null
"$RECOMP" "$WORK/division_ppc.o" -o "$WORK/division_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/division_generated.c" tools/gen_harness_division.c -o "$WORK/division_generated_host"
DIVISION_HOST_RESULT="$("$WORK/division_generated_host")"
echo "host recompiled result: $DIVISION_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/division_generated.c" tools/gen_harness_division.c -o "$WORK/division_generated_arm64" 2>/dev/null
DIVISION_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/division_generated_arm64")"
echo "arm64 recompiled result (qemu): $DIVISION_ARM64_RESULT"

echo "=========================================="
if [ "$DIVISION_GROUND_TRUTH" = "$DIVISION_HOST_RESULT" ] && [ "$DIVISION_GROUND_TRUTH" = "$DIVISION_ARM64_RESULT" ]; then
    echo "PASS (division): all results match ($DIVISION_GROUND_TRUTH)"
else
    echo "FAIL (division): results differ (ground truth=$DIVISION_GROUND_TRUTH, host=$DIVISION_HOST_RESULT, arm64=$DIVISION_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Indexed load/store pipeline (testdata/indexed.c) =="
gcc -O0 testdata/indexed.c testdata/indexed_host_main.c -o "$WORK/indexed_ground_truth"
INDEXED_GROUND_TRUTH="$("$WORK/indexed_ground_truth")"
echo "ground truth result: $INDEXED_GROUND_TRUTH"

testdata/build_ppc.sh testdata/indexed.c "$WORK/indexed_ppc.o" >/dev/null
"$RECOMP" "$WORK/indexed_ppc.o" -o "$WORK/indexed_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/indexed_generated.c" tools/gen_harness_indexed.c -o "$WORK/indexed_generated_host"
INDEXED_HOST_RESULT="$("$WORK/indexed_generated_host")"
echo "host recompiled result: $INDEXED_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/indexed_generated.c" tools/gen_harness_indexed.c -o "$WORK/indexed_generated_arm64" 2>/dev/null
INDEXED_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/indexed_generated_arm64")"
echo "arm64 recompiled result (qemu): $INDEXED_ARM64_RESULT"

echo "=========================================="
if [ "$INDEXED_GROUND_TRUTH" = "$INDEXED_HOST_RESULT" ] && [ "$INDEXED_GROUND_TRUTH" = "$INDEXED_ARM64_RESULT" ]; then
    echo "PASS (indexed load/store): all results match ($INDEXED_GROUND_TRUTH)"
else
    echo "FAIL (indexed load/store): results differ (ground truth=$INDEXED_GROUND_TRUTH, host=$INDEXED_HOST_RESULT, arm64=$INDEXED_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Float comparison pipeline (testdata/fcmp.c) =="
gcc -O0 testdata/fcmp.c testdata/fcmp_host_main.c -o "$WORK/fcmp_ground_truth"
FCMP_GROUND_TRUTH="$("$WORK/fcmp_ground_truth")"
echo "ground truth result: $FCMP_GROUND_TRUTH"

testdata/build_ppc.sh testdata/fcmp.c "$WORK/fcmp_ppc.o" >/dev/null
"$RECOMP" "$WORK/fcmp_ppc.o" -o "$WORK/fcmp_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/fcmp_generated.c" tools/gen_harness_fcmp.c -o "$WORK/fcmp_generated_host"
FCMP_HOST_RESULT="$("$WORK/fcmp_generated_host")"
echo "host recompiled result: $FCMP_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/fcmp_generated.c" tools/gen_harness_fcmp.c -o "$WORK/fcmp_generated_arm64" 2>/dev/null
FCMP_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/fcmp_generated_arm64")"
echo "arm64 recompiled result (qemu): $FCMP_ARM64_RESULT"

echo "=========================================="
if [ "$FCMP_GROUND_TRUTH" = "$FCMP_HOST_RESULT" ] && [ "$FCMP_GROUND_TRUTH" = "$FCMP_ARM64_RESULT" ]; then
    echo "PASS (float comparison): all results match ($FCMP_GROUND_TRUTH)"
else
    echo "FAIL (float comparison): results differ (ground truth=$FCMP_GROUND_TRUTH, host=$FCMP_HOST_RESULT, arm64=$FCMP_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== mulhw/mulhwu pipeline (testdata/mulhw.c, -O1 -- division-by-constant only shows up above -O0) =="
gcc -O0 testdata/mulhw.c testdata/mulhw_host_main.c -o "$WORK/mulhw_ground_truth"
MULHW_GROUND_TRUTH="$("$WORK/mulhw_ground_truth")"
echo "ground truth result: $MULHW_GROUND_TRUTH"

testdata/build_ppc.sh testdata/mulhw.c "$WORK/mulhw_ppc.o" -O1 >/dev/null
"$RECOMP" "$WORK/mulhw_ppc.o" -o "$WORK/mulhw_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/mulhw_generated.c" tools/gen_harness_mulhw.c -o "$WORK/mulhw_generated_host"
MULHW_HOST_RESULT="$("$WORK/mulhw_generated_host")"
echo "host recompiled result: $MULHW_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/mulhw_generated.c" tools/gen_harness_mulhw.c -o "$WORK/mulhw_generated_arm64" 2>/dev/null
MULHW_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/mulhw_generated_arm64")"
echo "arm64 recompiled result (qemu): $MULHW_ARM64_RESULT"

echo "=========================================="
if [ "$MULHW_GROUND_TRUTH" = "$MULHW_HOST_RESULT" ] && [ "$MULHW_GROUND_TRUTH" = "$MULHW_ARM64_RESULT" ]; then
    echo "PASS (mulhw/mulhwu): all results match ($MULHW_GROUND_TRUTH)"
else
    echo "FAIL (mulhw/mulhwu): results differ (ground truth=$MULHW_GROUND_TRUTH, host=$MULHW_HOST_RESULT, arm64=$MULHW_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Double-precision pipeline (testdata/double.c) =="
gcc -O0 testdata/double.c testdata/double_host_main.c -o "$WORK/double_ground_truth"
DOUBLE_GROUND_TRUTH="$("$WORK/double_ground_truth")"
echo "ground truth result: $DOUBLE_GROUND_TRUTH"

testdata/build_ppc.sh testdata/double.c "$WORK/double_ppc.o" >/dev/null
"$RECOMP" "$WORK/double_ppc.o" -o "$WORK/double_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/double_generated.c" tools/gen_harness_double.c -o "$WORK/double_generated_host"
DOUBLE_HOST_RESULT="$("$WORK/double_generated_host")"
echo "host recompiled result: $DOUBLE_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/double_generated.c" tools/gen_harness_double.c -o "$WORK/double_generated_arm64" 2>/dev/null
DOUBLE_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/double_generated_arm64")"
echo "arm64 recompiled result (qemu): $DOUBLE_ARM64_RESULT"

echo "=========================================="
if [ "$DOUBLE_GROUND_TRUTH" = "$DOUBLE_HOST_RESULT" ] && [ "$DOUBLE_GROUND_TRUTH" = "$DOUBLE_ARM64_RESULT" ]; then
    echo "PASS (double-precision): all results match ($DOUBLE_GROUND_TRUTH)"
else
    echo "FAIL (double-precision): results differ (ground truth=$DOUBLE_GROUND_TRUTH, host=$DOUBLE_HOST_RESULT, arm64=$DOUBLE_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Misc bitops pipeline (testdata/misc_bitops.c -- cntlzw/andc/eqv/subfic) =="
gcc -O0 testdata/misc_bitops.c testdata/misc_bitops_host_main.c -o "$WORK/misc_bitops_ground_truth"
MISC_GROUND_TRUTH="$("$WORK/misc_bitops_ground_truth")"
echo "ground truth result: $MISC_GROUND_TRUTH"

testdata/build_ppc.sh testdata/misc_bitops.c "$WORK/misc_bitops_ppc.o" >/dev/null
"$RECOMP" "$WORK/misc_bitops_ppc.o" -o "$WORK/misc_bitops_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/misc_bitops_generated.c" tools/gen_harness_misc_bitops.c -o "$WORK/misc_bitops_generated_host"
MISC_HOST_RESULT="$("$WORK/misc_bitops_generated_host")"
echo "host recompiled result: $MISC_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/misc_bitops_generated.c" tools/gen_harness_misc_bitops.c -o "$WORK/misc_bitops_generated_arm64" 2>/dev/null
MISC_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/misc_bitops_generated_arm64")"
echo "arm64 recompiled result (qemu): $MISC_ARM64_RESULT"

echo "=========================================="
if [ "$MISC_GROUND_TRUTH" = "$MISC_HOST_RESULT" ] && [ "$MISC_GROUND_TRUTH" = "$MISC_ARM64_RESULT" ]; then
    echo "PASS (misc bitops): all results match ($MISC_GROUND_TRUTH)"
else
    echo "FAIL (misc bitops): results differ (ground truth=$MISC_GROUND_TRUTH, host=$MISC_HOST_RESULT, arm64=$MISC_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Mixed double-precision integration pipeline (testdata/mixed_double.c) =="
gcc -O0 testdata/mixed_double.c testdata/mixed_double_host_main.c -o "$WORK/mixed_double_ground_truth"
MIXED_GROUND_TRUTH="$("$WORK/mixed_double_ground_truth")"
echo "ground truth result: $MIXED_GROUND_TRUTH"

testdata/build_ppc.sh testdata/mixed_double.c "$WORK/mixed_double_ppc.o" >/dev/null
"$RECOMP" "$WORK/mixed_double_ppc.o" -o "$WORK/mixed_double_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/mixed_double_generated.c" tools/gen_harness_mixed_double.c -o "$WORK/mixed_double_generated_host"
MIXED_HOST_RESULT="$("$WORK/mixed_double_generated_host")"
echo "host recompiled result: $MIXED_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/mixed_double_generated.c" tools/gen_harness_mixed_double.c -o "$WORK/mixed_double_generated_arm64" 2>/dev/null
MIXED_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/mixed_double_generated_arm64")"
echo "arm64 recompiled result (qemu): $MIXED_ARM64_RESULT"

echo "=========================================="
if [ "$MIXED_GROUND_TRUTH" = "$MIXED_HOST_RESULT" ] && [ "$MIXED_GROUND_TRUTH" = "$MIXED_ARM64_RESULT" ]; then
    echo "PASS (mixed double integration): all results match ($MIXED_GROUND_TRUTH)"
else
    echo "FAIL (mixed double integration): results differ (ground truth=$MIXED_GROUND_TRUTH, host=$MIXED_HOST_RESULT, arm64=$MIXED_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Global/static variable pipeline (testdata/globals.c) =="
gcc -O0 testdata/globals.c testdata/globals_host_main.c -o "$WORK/globals_ground_truth"
GLOBALS_GROUND_TRUTH="$("$WORK/globals_ground_truth")"
echo "ground truth result:"
echo "$GLOBALS_GROUND_TRUTH"

testdata/build_ppc.sh testdata/globals.c "$WORK/globals_ppc.o" >/dev/null
"$RECOMP" "$WORK/globals_ppc.o" -o "$WORK/globals_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/globals_generated.c" tools/gen_harness_globals.c -o "$WORK/globals_generated_host"
GLOBALS_HOST_RESULT="$("$WORK/globals_generated_host")"
echo "host recompiled result:"
echo "$GLOBALS_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/globals_generated.c" tools/gen_harness_globals.c -o "$WORK/globals_generated_arm64" 2>/dev/null
GLOBALS_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/globals_generated_arm64")"
echo "arm64 recompiled result (qemu):"
echo "$GLOBALS_ARM64_RESULT"

echo "=========================================="
if [ "$GLOBALS_GROUND_TRUTH" = "$GLOBALS_HOST_RESULT" ] && [ "$GLOBALS_GROUND_TRUTH" = "$GLOBALS_ARM64_RESULT" ]; then
    echo "PASS (global/static variables): all results match"
else
    echo "FAIL (global/static variables): results differ"
    exit 1
fi

echo ""
echo "== Multi-function global-sharing pipeline (testdata/multifunc_globals.c) =="
gcc -O0 testdata/multifunc_globals.c testdata/multifunc_globals_host_main.c -o "$WORK/multifunc_globals_ground_truth"
MFG_GROUND_TRUTH="$("$WORK/multifunc_globals_ground_truth")"
echo "ground truth result: $MFG_GROUND_TRUTH"

testdata/build_ppc.sh testdata/multifunc_globals.c "$WORK/multifunc_globals_ppc.o" >/dev/null
"$RECOMP" "$WORK/multifunc_globals_ppc.o" -o "$WORK/multifunc_globals_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/multifunc_globals_generated.c" tools/gen_harness_multifunc_globals.c -o "$WORK/multifunc_globals_generated_host"
MFG_HOST_RESULT="$("$WORK/multifunc_globals_generated_host")"
echo "host recompiled result: $MFG_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/multifunc_globals_generated.c" tools/gen_harness_multifunc_globals.c -o "$WORK/multifunc_globals_generated_arm64" 2>/dev/null
MFG_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/multifunc_globals_generated_arm64")"
echo "arm64 recompiled result (qemu): $MFG_ARM64_RESULT"

echo "=========================================="
if [ "$MFG_GROUND_TRUTH" = "$MFG_HOST_RESULT" ] && [ "$MFG_GROUND_TRUTH" = "$MFG_ARM64_RESULT" ]; then
    echo "PASS (multi-function global sharing): all results match ($MFG_GROUND_TRUTH)"
else
    echo "FAIL (multi-function global sharing): results differ (ground truth=$MFG_GROUND_TRUTH, host=$MFG_HOST_RESULT, arm64=$MFG_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Indirect call (function pointer) pipeline (testdata/fnptr.c -- mtctr/bctrl) =="
gcc -O0 testdata/fnptr.c testdata/fnptr_host_main.c -o "$WORK/fnptr_ground_truth"
FNPTR_GROUND_TRUTH="$("$WORK/fnptr_ground_truth")"
echo "ground truth result: $FNPTR_GROUND_TRUTH"

testdata/build_ppc.sh testdata/fnptr.c "$WORK/fnptr_ppc.o" >/dev/null
"$RECOMP" "$WORK/fnptr_ppc.o" -o "$WORK/fnptr_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/fnptr_generated.c" tools/gen_harness_fnptr.c -o "$WORK/fnptr_generated_host"
FNPTR_HOST_RESULT="$("$WORK/fnptr_generated_host")"
echo "host recompiled result: $FNPTR_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/fnptr_generated.c" tools/gen_harness_fnptr.c -o "$WORK/fnptr_generated_arm64" 2>/dev/null
FNPTR_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/fnptr_generated_arm64")"
echo "arm64 recompiled result (qemu): $FNPTR_ARM64_RESULT"

echo "=========================================="
if [ "$FNPTR_GROUND_TRUTH" = "$FNPTR_HOST_RESULT" ] && [ "$FNPTR_GROUND_TRUTH" = "$FNPTR_ARM64_RESULT" ]; then
    echo "PASS (indirect function-pointer calls): all results match"
else
    echo "FAIL (indirect function-pointer calls): results differ (ground truth=$FNPTR_GROUND_TRUTH, host=$FNPTR_HOST_RESULT, arm64=$FNPTR_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Counted-loop pipeline (testdata/loop_counted.c -- mtctr/bdnz, -O2) =="
gcc -O0 testdata/loop_counted.c testdata/loop_counted_host_main.c -o "$WORK/loop_counted_ground_truth"
LOOP_GROUND_TRUTH="$("$WORK/loop_counted_ground_truth")"
echo "ground truth result: $LOOP_GROUND_TRUTH"

testdata/build_ppc.sh testdata/loop_counted.c "$WORK/loop_counted_ppc.o" -O2 >/dev/null
"$RECOMP" "$WORK/loop_counted_ppc.o" -o "$WORK/loop_counted_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/loop_counted_generated.c" tools/gen_harness_loop_counted.c -o "$WORK/loop_counted_generated_host"
LOOP_HOST_RESULT="$("$WORK/loop_counted_generated_host")"
echo "host recompiled result: $LOOP_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/loop_counted_generated.c" tools/gen_harness_loop_counted.c -o "$WORK/loop_counted_generated_arm64" 2>/dev/null
LOOP_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/loop_counted_generated_arm64")"
echo "arm64 recompiled result (qemu): $LOOP_ARM64_RESULT"

echo "=========================================="
if [ "$LOOP_GROUND_TRUTH" = "$LOOP_HOST_RESULT" ] && [ "$LOOP_GROUND_TRUTH" = "$LOOP_ARM64_RESULT" ]; then
    echo "PASS (counted loop / mtctr+bdnz): all results match ($LOOP_GROUND_TRUTH)"
else
    echo "FAIL (counted loop / mtctr+bdnz): results differ (ground truth=$LOOP_GROUND_TRUTH, host=$LOOP_HOST_RESULT, arm64=$LOOP_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Rodata address-taking pipeline (testdata/rodata_table.c -- switch-statement lookup table, -O2) =="
gcc -O0 testdata/rodata_table.c testdata/rodata_table_host_main.c -o "$WORK/rodata_table_ground_truth"
RTBL_GROUND_TRUTH="$("$WORK/rodata_table_ground_truth")"
echo "ground truth result: $RTBL_GROUND_TRUTH"

testdata/build_ppc.sh testdata/rodata_table.c "$WORK/rodata_table_ppc.o" -O2 >/dev/null
"$RECOMP" "$WORK/rodata_table_ppc.o" -o "$WORK/rodata_table_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/rodata_table_generated.c" tools/gen_harness_rodata_table.c -o "$WORK/rodata_table_generated_host"
RTBL_HOST_RESULT="$("$WORK/rodata_table_generated_host")"
echo "host recompiled result: $RTBL_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/rodata_table_generated.c" tools/gen_harness_rodata_table.c -o "$WORK/rodata_table_generated_arm64" 2>/dev/null
RTBL_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/rodata_table_generated_arm64")"
echo "arm64 recompiled result (qemu): $RTBL_ARM64_RESULT"

echo "=========================================="
if [ "$RTBL_GROUND_TRUTH" = "$RTBL_HOST_RESULT" ] && [ "$RTBL_GROUND_TRUTH" = "$RTBL_ARM64_RESULT" ]; then
    echo "PASS (rodata address-taking / switch lookup table): all results match"
else
    echo "FAIL (rodata address-taking / switch lookup table): results differ (ground truth=$RTBL_GROUND_TRUTH, host=$RTBL_HOST_RESULT, arm64=$RTBL_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Many-arguments (stack-passed args) pipeline (testdata/manyargs.c) =="
gcc -O0 testdata/manyargs.c testdata/manyargs_host_main.c -o "$WORK/manyargs_ground_truth"
MANYARGS_GROUND_TRUTH="$("$WORK/manyargs_ground_truth")"
echo "ground truth result: $MANYARGS_GROUND_TRUTH"

testdata/build_ppc.sh testdata/manyargs.c "$WORK/manyargs_ppc.o" >/dev/null
"$RECOMP" "$WORK/manyargs_ppc.o" -o "$WORK/manyargs_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/manyargs_generated.c" tools/gen_harness_manyargs.c -o "$WORK/manyargs_generated_host"
MANYARGS_HOST_RESULT="$("$WORK/manyargs_generated_host")"
echo "host recompiled result: $MANYARGS_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/manyargs_generated.c" tools/gen_harness_manyargs.c -o "$WORK/manyargs_generated_arm64" 2>/dev/null
MANYARGS_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/manyargs_generated_arm64")"
echo "arm64 recompiled result (qemu): $MANYARGS_ARM64_RESULT"

echo "=========================================="
if [ "$MANYARGS_GROUND_TRUTH" = "$MANYARGS_HOST_RESULT" ] && [ "$MANYARGS_GROUND_TRUTH" = "$MANYARGS_ARM64_RESULT" ]; then
    echo "PASS (many arguments / stack-passed calling convention): all results match ($MANYARGS_GROUND_TRUTH)"
    exit 0
else
    echo "FAIL (many arguments / stack-passed calling convention): results differ (ground truth=$MANYARGS_GROUND_TRUTH, host=$MANYARGS_HOST_RESULT, arm64=$MANYARGS_ARM64_RESULT)"
    exit 1
fi
