/* Exercises linking two SEPARATELY recompiled objects together --
 * testdata/multifile_a.c (helper()) and testdata/multifile_b.c
 * (compute(), which calls helper() across the object boundary) are each
 * run through `recomp` independently, then their generated C files are
 * compiled into the same binary. multifile_a.c is recompiled with
 * --extern-globals (it has no data of its own, so it's safe) so its
 * ppc_init_globals/ppc_dispatch don't collide with multifile_b's. */
#include <stdio.h>

#include "ppc_runtime.h"

void ppc_compute(PpcContext *ctx);
void ppc_init_globals(PpcContext *ctx);

int main(void) {
    static PpcContext ctx; /* zero-initialized by BSS */
    ctx.r[1] = sizeof(ctx.mem) - 256; /* stack pointer, with headroom for stwu */
    ppc_init_globals(&ctx);

    ctx.r[3] = 5;
    ppc_compute(&ctx);

    printf("%d\n", (int32_t)ctx.r[3]);
    return 0;
}
