/* Same purpose as gen_harness_globals.c but for testdata/bss_large.c's
 * fill_and_check() -- real regression coverage for a real bug found
 * 2026-08-20 (see that file's own comment). Must call ppc_init_globals()
 * first, same as any program with .data/.bss content, see main.cpp. */
#include <stdio.h>

#include "ppc_runtime.h"

void ppc_fill_and_check(PpcContext *ctx);
void ppc_init_globals(PpcContext *ctx);

int main(void) {
    static PpcContext ctx; /* zero-initialized by BSS */
    static PpcSharedMemory ctx_shared;
    ctx.shared = &ctx_shared;
    ctx.r[1] = PPC_MEM_SIZE - 256; /* stack pointer, with headroom for stwu */
    ppc_init_globals(&ctx);

    ppc_fill_and_check(&ctx);
    printf("%d\n", (int32_t)ctx.r[3]);
    return 0;
}
