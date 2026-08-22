/* Real host-testable regression test for skylanders_figure.c -- the
 * header itself documents that this file was deliberately built with no
 * libnx/<switch.h> dependency specifically so it could be unit-tested on
 * a dev machine (see skylanders_figure.h's own file comment), but no
 * test existed yet. Uses only synthetic data (no real game dump or
 * figure needed) -- decode_block1's byte layout and the CHARACTER_IDS/
 * POP_FIZZ_VARIANTS tables are exercised directly, and
 * load_block/identify_dump/scan_dir are exercised against real temp
 * files this test creates and cleans up itself.
 *
 * Same host-testable-only convention as test_skylanders_mifare_keys.c
 * (its own file comment) and tools/gen_harness*.c -- not part of the
 * switch/native/ build, has its own main().
 *
 * Usage: gcc -Wall -Wextra -std=c99 -o test_skylanders_figure \
 *          test_skylanders_figure.c skylanders_figure.c && \
 *          ./test_skylanders_figure
 * (skylanders_figure.c/.h come from jouster/native/source and
 * jouster/native/include -- not duplicated into this repo, copy or
 * symlink them alongside this file to build.) */
#define _POSIX_C_SOURCE 200809L /* for mkdtemp under strict -std=c99 */

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "skylanders_figure.h"

static int g_failures = 0;

#define CHECK(cond, msg) do { \
    if (!(cond)) { \
        printf("FAIL: %s (%s:%d)\n", msg, __FILE__, __LINE__); \
        g_failures++; \
    } \
} while (0)

static void test_decode_block1(void) {
    /* CharacterID at bytes 0-1 LE, VariantID at bytes 12-13 LE -- per
     * the header's own documented block layout. */
    uint8_t block1[16] = {0};
    SkylandersFigureId id;

    /* Spyro (16) with variant 4096 ("Pop Fizz" in the table, but that's
     * fine -- decode_block1 doesn't validate against the table, it just
     * reads bytes; the table lookup is a separate function tested
     * below). */
    block1[0] = 0x10; block1[1] = 0x00;   /* 16 */
    block1[12] = 0x00; block1[13] = 0x10; /* 4096 */
    id = skylanders_figure_decode_block1(block1);
    CHECK(id.character_id == 16, "decode_block1 character_id (simple case)");
    CHECK(id.variant_id == 4096, "decode_block1 variant_id (simple case)");

    /* High-byte character ID (e.g. 0x0258 = 600) to confirm real
     * little-endian assembly, not just a low-byte-only accident. */
    memset(block1, 0xAA, sizeof(block1)); /* non-zero padding elsewhere shouldn't matter */
    block1[0] = 0x58; block1[1] = 0x02;   /* 600 */
    block1[12] = 0x01; block1[13] = 0x02; /* 0x0201 = 513 */
    id = skylanders_figure_decode_block1(block1);
    CHECK(id.character_id == 600, "decode_block1 character_id (high byte)");
    CHECK(id.variant_id == 513, "decode_block1 variant_id (high byte)");
}

static void test_name_lookups(void) {
    CHECK(strcmp(skylanders_figure_name(16), "Spyro") == 0, "figure_name(16) == Spyro");
    CHECK(strcmp(skylanders_figure_name(108), "Pop Fizz") == 0, "figure_name(108) == Pop Fizz");
    CHECK(strcmp(skylanders_figure_name(627), "Kaos") == 0, "figure_name(627) == Kaos");
    CHECK(skylanders_figure_name(999999) == NULL, "figure_name(unknown) == NULL");

    CHECK(strcmp(skylanders_figure_variant_name(108, 4096), "Pop Fizz") == 0,
          "variant_name(108, 4096) == Pop Fizz");
    CHECK(strcmp(skylanders_figure_variant_name(108, 10245), "Super Gulp Pop Fizz") == 0,
          "variant_name(108, 10245) == Super Gulp Pop Fizz");
    CHECK(skylanders_figure_variant_name(108, 1) == NULL,
          "variant_name(108, unknown variant) == NULL");
    /* Only Pop Fizz (108) has a real captured variant table -- any other
     * character_id must return NULL regardless of variant_id, per the
     * .c file's own real guard (`if (character_id != 108) return NULL`). */
    CHECK(skylanders_figure_variant_name(16, 4096) == NULL,
          "variant_name(non-Pop-Fizz character, valid Pop Fizz variant id) == NULL");
}

/* Writes a synthetic 64-block (1024-byte) MIFARE dump where block N's
 * bytes are all set to (uint8_t)N -- lets tests confirm exactly which
 * block got read back rather than trusting a real figure dump's actual
 * (irrelevant) contents. */
static void write_synthetic_dump(const char *path) {
    FILE *f = fopen(path, "wb");
    int block;
    assert(f && "failed to create synthetic test dump");
    for (block = 0; block < 64; block++) {
        uint8_t buf[16];
        memset(buf, (uint8_t)block, sizeof(buf));
        fwrite(buf, 1, 16, f);
    }
    fclose(f);
}

static void test_load_block_and_identify(const char *tmpdir) {
    char path[512];
    uint8_t block[16];
    SkylandersFigureId id;
    snprintf(path, sizeof(path), "%s/synthetic.bin", tmpdir);
    write_synthetic_dump(path);

    CHECK(skylanders_figure_load_block(path, 0, block), "load_block(0) succeeds");
    CHECK(block[0] == 0 && block[15] == 0, "load_block(0) content matches block 0's fill byte");

    CHECK(skylanders_figure_load_block(path, 1, block), "load_block(1) succeeds");
    CHECK(block[0] == 1 && block[15] == 1, "load_block(1) content matches block 1's fill byte");

    CHECK(skylanders_figure_load_block(path, 63, block), "load_block(63) succeeds (last real block)");
    CHECK(!skylanders_figure_load_block(path, 64, block), "load_block(64) fails (one past the real end)");
    CHECK(!skylanders_figure_load_block("/nonexistent/path/does/not/exist.bin", 0, block),
          "load_block on a nonexistent file fails cleanly");

    /* Block 1's fill byte (1) as both CharacterID bytes -> 0x0101 = 257,
     * and as both VariantID bytes -> 257 too. Just confirms
     * identify_dump really does chain load_block(path,1)+decode rather
     * than reading a different block. */
    CHECK(skylanders_figure_identify_dump(path, &id), "identify_dump succeeds on synthetic dump");
    CHECK(id.character_id == 257, "identify_dump reads block 1, not some other block");
    CHECK(!skylanders_figure_identify_dump("/nonexistent/path.bin", &id),
          "identify_dump on a nonexistent file fails cleanly");
}

typedef struct { int count; char last_path[512]; } ScanResult;

static void scan_callback(const SkylandersDumpEntry *entry, void *user_data) {
    ScanResult *r = (ScanResult *)user_data;
    r->count++;
    snprintf(r->last_path, sizeof(r->last_path), "%s", entry->path);
}

static void test_scan_dir(const char *tmpdir) {
    /* gcc's -Wformat-truncation still flags every snprintf below even
     * at this size: it can't see through the `const char *tmpdir`
     * parameter that the real string mkdtemp() returns is always short
     * (from the fixed "/tmp/skyfigtest_XXXXXX" template), so it assumes
     * an arbitrary-length %s and warns on principle. Real max path
     * length here is well under 100 bytes; verified safe by actually
     * running this, not just by silencing the warning. */
    char root[600], sub1[600], sub2[600];
    char p_root[600], p_sub1[600], p_sub2[600], p_garbage[600];
    ScanResult result = {0, ""};
    int n;
    FILE *f;

    snprintf(root, sizeof(root), "%s/scan_root", tmpdir);
    snprintf(sub1, sizeof(sub1), "%s/box1", root);
    snprintf(sub2, sizeof(sub2), "%s/toodeep", sub1);
    mkdir(root, 0777);
    mkdir(sub1, 0777);
    mkdir(sub2, 0777);

    /* One valid dump at the top level, one valid dump one level down
     * (both should be found -- "exactly one level of subfolder
     * recursion" per the header), one valid dump two levels down
     * (should NOT be found -- past the one-level recursion cap), and
     * one small garbage file at the top level (too short to contain a
     * real block 1, should be silently skipped, not reported/crash). */
    snprintf(p_root, sizeof(p_root), "%s/root_dump.bin", root);
    snprintf(p_sub1, sizeof(p_sub1), "%s/sub1_dump.bin", sub1);
    snprintf(p_sub2, sizeof(p_sub2), "%s/sub2_dump.bin", sub2);
    snprintf(p_garbage, sizeof(p_garbage), "%s/not_a_dump.txt", root);
    write_synthetic_dump(p_root);
    write_synthetic_dump(p_sub1);
    write_synthetic_dump(p_sub2);
    f = fopen(p_garbage, "wb");
    assert(f && "failed to create garbage test file");
    fwrite("too short", 1, 9, f);
    fclose(f);

    n = skylanders_figure_scan_dir(root, scan_callback, &result);
    CHECK(n == 2, "scan_dir finds exactly the top-level dump + one-level-deep dump");
    CHECK(result.count == 2, "scan_dir's callback fired exactly twice");

    CHECK(skylanders_figure_scan_dir("/nonexistent/scan/dir", scan_callback, NULL) == -1,
          "scan_dir on a nonexistent directory returns -1");
}

int main(void) {
    char tmpdir_template[] = "/tmp/skyfigtest_XXXXXX";
    char *tmpdir = mkdtemp(tmpdir_template);
    if (!tmpdir) {
        fprintf(stderr, "could not create a temp dir for testing\n");
        return 1;
    }

    test_decode_block1();
    test_name_lookups();
    test_load_block_and_identify(tmpdir);
    test_scan_dir(tmpdir);

    /* Best-effort cleanup -- not asserted, a leftover temp dir isn't
     * worth failing the whole test suite over. */
    {
        char cmd[600];
        snprintf(cmd, sizeof(cmd), "rm -rf '%s'", tmpdir);
        if (system(cmd) != 0) { /* ignore -- cleanup best-effort */ }
    }

    if (g_failures == 0) {
        printf("skylanders_figure: all checks passed\n");
        return 0;
    }
    printf("skylanders_figure: %d check(s) FAILED\n", g_failures);
    return 1;
}
