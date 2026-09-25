/* Guest functions whose names are also names in conquertron's runtime:
 * every guest function becomes ppc_<name> in generated C, and ppc_dispatch,
 * ppc_init_globals and ppc_load_u32 are the runtime's own. Before
 * 2026-09-26 the generated C did not compile (conflicting types for
 * ppc_dispatch); recomp now renames such functions to <name>_guest and
 * says so. */
__attribute__((noinline)) int dispatch(int x) { return x * 5 + 3; }
__attribute__((noinline)) int init_globals(int x) { return x ^ 0x2a; }
__attribute__((noinline)) int load_u32(int x) { return x - 11; }

int compute(int mode) {
    return dispatch(mode) + init_globals(mode + 7) * load_u32(mode + 100);
}
