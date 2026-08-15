/* Exercises the real bug an earlier version of the recompiler had: a
 * compiler-generated switch-statement lookup table lives in .rodata and
 * its *address* is taken (lis+la) for later runtime-indexed access
 * (lwzx), not read as a single fixed-offset scalar like a float/double
 * literal. An earlier compile-time-constant-fold approach for all
 * .rodata* accesses only handled the latter case correctly -- this test
 * would have silently returned garbage (or 0) for x in [0,5] under that
 * version instead of the real table values. x=6 additionally exercises
 * the out-of-range/default path, which doesn't touch the table at all. */
#include <stdio.h>

#include "ppc_runtime.h"

void ppc_classify(PpcContext *ctx);
void ppc_init_globals(PpcContext *ctx);

int main(void) {
    static PpcContext ctx; /* zero-initialized by BSS */
    static PpcSharedMemory ctx_shared;
    ctx.shared = &ctx_shared;
    ctx.r[1] = PPC_MEM_SIZE - 256; /* stack pointer, with headroom for stwu */
    ppc_init_globals(&ctx);

    for (int x = 0; x <= 6; x++) {
        ctx.r[3] = (uint32_t)x;
        ppc_classify(&ctx);
        printf("%d\n", (int32_t)ctx.r[3]);
    }

    return 0;
}
