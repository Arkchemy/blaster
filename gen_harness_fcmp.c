/* Same purpose as gen_harness_float.c but for testdata/fcmp.c's
 * compute(float, float), which takes two float args (PPC ABI: f1, f2). */
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
    ctx.f[1] = 3.5;
    ctx.f[2] = 7.25;

    ppc_compute(&ctx);

    printf("%.9g\n", (float)ctx.f[1]);
    return 0;
}
