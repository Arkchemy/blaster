/* Exercises mtctr/bdnz counted-loop branches (only appears in compiler
 * output at -O2 and above -- see testdata/build_ppc.sh's OPT argument for
 * this pipeline) as an alternative to the cmp+conditional-branch loop form
 * every other test so far has used. */
#include <stdio.h>

#include "ppc_runtime.h"

void ppc_sumn(PpcContext *ctx);
void ppc_init_globals(PpcContext *ctx);

int main(void) {
    static PpcContext ctx; /* zero-initialized by BSS */
    static PpcSharedMemory ctx_shared;
    ctx.shared = &ctx_shared;
    ctx.r[1] = PPC_MEM_SIZE - 256; /* stack pointer, with headroom */
    ppc_init_globals(&ctx);

    uint32_t acc_addr = 0x100;
    ppc_store_u32(&ctx, acc_addr, 7);

    ctx.r[3] = 5;         /* n */
    ctx.r[4] = acc_addr;  /* acc */
    ppc_sumn(&ctx);

    printf("%d\n", (int32_t)ctx.r[3]);
    return 0;
}
