/* Same purpose as gen_harness.c but for testdata/misc_bitops.c's
 * compute(unsigned int, unsigned int) -- exercises cntlzw/andc/eqv/subfic. */
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
    ctx.r[3] = 0x0F0F0F0Fu;
    ctx.r[4] = 0xFF00FF00u;

    ppc_compute(&ctx);

    printf("%d\n", (int32_t)ctx.r[3]);
    return 0;
}
