/* setjmp/longjmp across recompiled frames -- see testdata/setjmp.c. Three
 * calls, each of which leaves a stack of recompiled frames by longjmp. */
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

    for (int m = 0; m < 3; m++) {
        ctx.r[3] = (uint32_t)m;
        ppc_compute(&ctx);
        printf("%d\n", (int32_t)ctx.r[3]);
    }
    return 0;
}
