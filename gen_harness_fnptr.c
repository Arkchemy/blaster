/* Exercises mtctr/bctrl indirect calls: compute() picks between add/mul via
 * a function pointer and calls through it, instead of a direct bl. Calling
 * it twice with different `which` proves the dispatch actually branches to
 * a different function, not just one hardcoded target. */
#include <stdio.h>

#include "ppc_runtime.h"

void ppc_compute(PpcContext *ctx);
void ppc_init_globals(PpcContext *ctx);

int main(void) {
    static PpcContext ctx; /* zero-initialized by BSS */
    ctx.r[1] = sizeof(ctx.mem) - 256; /* stack pointer, with headroom for stwu */
    ppc_init_globals(&ctx);

    ctx.r[3] = 10;
    ctx.r[4] = 20;
    ctx.r[5] = 0;
    ppc_compute(&ctx);
    printf("%d\n", (int32_t)ctx.r[3]);

    ctx.r[3] = 10;
    ctx.r[4] = 20;
    ctx.r[5] = 1;
    ppc_compute(&ctx);
    printf("%d\n", (int32_t)ctx.r[3]);

    return 0;
}
