#include <stdio.h>

#include "ppc_runtime.h"

void ppc_compute(PpcContext *ctx);
void ppc_init_globals(PpcContext *ctx);

int main(void) {
    static PpcContext ctx;
    ctx.r[1] = sizeof(ctx.mem) - 256;
    ppc_init_globals(&ctx);

    ctx.f[1] = 3.5;   /* a (double) */
    ctx.f[2] = 1.25;  /* b (float, PPC ABI: still its own FPR slot) */
    ctx.r[3] = 100;   /* base (unsigned int) */
    ppc_compute(&ctx);

    printf("%.6f\n", ctx.f[1]);
    return 0;
}
