/* Same purpose as gen_harness.c but for testdata/globals.c's
 * compute(int) -- calls ppc_init_globals() first (mandatory for any
 * program with .data/.bss content, see main.cpp), then compute() three
 * times in a row to prove the global `counter` genuinely persists and
 * accumulates across calls, not just that a single call happens to read
 * the right initial value. */
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

    int idxs[3] = {0, 1, 3};
    for (int i = 0; i < 3; i++) {
        ctx.r[3] = (uint32_t)idxs[i];
        ppc_compute(&ctx);
        printf("%d\n", (int32_t)ctx.r[3]);
    }
    return 0;
}
