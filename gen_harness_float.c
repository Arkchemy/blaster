/* Same purpose as gen_harness.c but for testdata/floating.c's
 * float-returning compute(), which the recompiler leaves in ctx->f[1]
 * (PPC ABI: single-precision return values come back in f1). */
#include <stdio.h>

#include "ppc_runtime.h"

void ppc_compute(PpcContext *ctx);
void ppc_init_globals(PpcContext *ctx);

int main(void) {
    static PpcContext ctx; /* zero-initialized by BSS */
    static PpcSharedMemory ctx_shared;
    ctx.shared = &ctx_shared;
    ctx.r[1] = PPC_MEM_SIZE - 256; /* stack pointer, with headroom for stwu */
    ppc_init_globals(&ctx);

    ppc_compute(&ctx);

    printf("%.9g\n", (float)ctx.f[1]);
    return 0;
}
