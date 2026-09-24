/* setjmp/longjmp across recompiled frames.
 *
 * In the game these are recompiled PowerPC like everything else, and a
 * recompiled longjmp cannot work: it restores guest registers and "returns"
 * into whatever host C frame happens to be current, instead of unwinding the
 * host call stack back to the setjmp. conquertron now recognises calls to
 * them and does both halves on the host -- see PPC_HOST_SETJMP in
 * ppc_runtime.h.
 *
 * For the PowerPC build there is no libc, so setjmp/longjmp are stand-ins
 * with the right names and signatures. The stand-in longjmp just returns,
 * which is roughly what the recompiled one did in effect: without the
 * recompiler's substitution, every case below produces a wrong answer
 * rather than a hang. The native ground-truth build uses the real ones.
 *
 * `weak` matters at -O1: without it clang can see that the stand-in setjmp
 * always returns 0 and fold that into the caller, which then ignores what
 * the host setjmp actually returned and loops for ever. The real setjmp is
 * in the C library, where no compiler can see its body. */

#if defined(__powerpc__) || defined(__PPC__)
typedef long jmp_buf[64];
__attribute__((noinline, weak)) int setjmp(jmp_buf env) { env[0] = 0x5e7; return 0; }
__attribute__((noinline, weak)) void longjmp(jmp_buf env, int val) { env[1] = val; }
#else
#include <setjmp.h>
#endif

static jmp_buf outer;
static jmp_buf inner;
static int calls;

/* Recurse a few frames, then leave all of them at once. */
static void thrower(int depth, int val) {
    calls++;
    if (depth == 0) { longjmp(outer, val); return; }
    thrower(depth - 1, val);
    calls += 1000;                     /* never reached if longjmp works */
}

/* Its own setjmp/longjmp pair, completed and returned from normally before
 * the outer one fires: two buffers live at once, and the inner one's frame
 * gone by the time the outer longjmp happens. */
static int inner_roundtrip(int x) {
    volatile int local = x;
    int r = setjmp(inner);
    if (r == 0) {
        local += 5;
        longjmp(inner, 3);
        return -1;                     /* never reached */
    }
    return local * 10 + r;
}

/* mode 0: longjmp(outer, 7) from six frames down
 * mode 1: longjmp(outer, 0), which setjmp must report as 1
 * mode 2: the inner pair first, then the outer longjmp */
int compute(int mode) {
    volatile int before = 40 + mode;   /* in the frame; must survive */
    int got;
    calls = 0;
    got = setjmp(outer);
    if (got == 0) {
        int extra = 0;
        if (mode == 2) extra = inner_roundtrip(4);
        calls += extra;
        thrower(5, mode == 1 ? 0 : 7);
        return -1;                     /* never reached */
    }
    return got * 10000 + before * 100 + calls;
}
