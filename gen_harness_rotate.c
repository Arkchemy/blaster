/* Same purpose as gen_harness.c but for testdata/rotate.c's compute(int n),
 * which takes an argument (PPC ABI: first int arg in r3) and returns
 * unsigned (also r3). */
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
    ctx.r[3] = 9; /* n */

    ppc_compute(&ctx);

    printf("%u\n", ctx.r[3]);
    return 0;
}
