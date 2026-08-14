/* Harness for recompiler-generated C: sets up a PpcContext, calls the
 * recovered entry function, and prints its PPC ABI return value (r3). Used
 * for both the host-native and QEMU-aarch64 verification runs. */
#include <stdio.h>

#include "ppc_runtime.h"

void ppc_compute(PpcContext *ctx);
void ppc_init_globals(PpcContext *ctx);

int main(void) {
    static PpcContext ctx; /* zero-initialized by BSS */
    ctx.r[1] = sizeof(ctx.mem) - 256; /* stack pointer, with headroom for stwu */
    ppc_init_globals(&ctx);

    ppc_compute(&ctx);

    printf("%d\n", (int32_t)ctx.r[3]);
    return 0;
}
