#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "skylanders_mifare_keys.h"

/* Real test vectors: this project's C port cross-checked byte-for-byte
 * against the actual original JavaScript
 * (skylandersNFC/SkyKeys-Generator's script.js) run via node, for 5 real
 * UIDs across all 16 real sectors -- 80 keys total, kept permanently so a
 * future change to this port can be re-verified without needing node
 * again. */
typedef struct { uint8_t uid[4]; const char *keys_hex[16]; } TestVector;

static const TestVector VECTORS[] = {
    { {0x04, 0x12, 0x34, 0x56}, {"4b0b20107ccb", "94ecc0683172", "b281143be6b1", "21b7fe920d50", "6d6d5635a3d7", "fe5bbc9c4836", "d83668cf9ff5", "4b0082667414", "d3b4d329291b", "40823980c2fa", "66efedd31539", "f5d9077afed8", "b903afdd505f", "2a354574bbbe", "0c5891276c7d", "9f6e7b8e879c"} },
    { {0xde, 0xad, 0xbe, 0xef}, {"4b0b20107ccb", "39425456afce", "1f2f8005780d", "8c196aac93ec", "c0c3c20b3d6b", "53f528a2d68a", "7598fcf10149", "e6ae1658eaa8", "7e1a4717b7a7", "ed2cadbe5c46", "cb4179ed8b85", "587793446064", "14ad3be3cee3", "879bd14a2502", "a1f60519f2c1", "32c0efb01920"} },
    { {0x00, 0x00, 0x00, 0x00}, {"4b0b20107ccb", "8b23426b3082", "ad4e9638e741", "3e787c910ca0", "72a2d436a227", "e1943e9f49c6", "c7f9eacc9e05", "54cf006575e4", "cc7b512a28eb", "5f4dbb83c30a", "79206fd014c9", "ea168579ff28", "a6cc2dde51af", "35fac777ba4e", "139713246d8d", "80a1f98d866c"} },
    { {0xff, 0xff, 0xff, 0xff}, {"4b0b20107ccb", "85619e22d4e9", "a30c4a71032a", "303aa0d8e8cb", "7ce0087f464c", "efd6e2d6adad", "c9bb36857a6e", "5a8ddc2c918f", "c2398d63cc80", "510f67ca2761", "7762b399f0a2", "e45459301b43", "a88ef197b5c4", "3bb81b3e5e25", "1dd5cf6d89e6", "8ee325c46207"} },
    { {0x01, 0x23, 0x45, 0x67}, {"4b0b20107ccb", "3c98f925a17f", "1af52d7676bc", "89c3c7df9d5d", "c5196f7833da", "562f85d1d83b", "704251820ff8", "e374bb2be419", "7bc0ea64b916", "e8f600cd52f7", "ce9bd49e8534", "5dad3e376ed5", "11779690c052", "82417c392bb3", "a42ca86afc70", "371a42c31791"} },
};
#define VECTOR_COUNT (sizeof(VECTORS) / sizeof(VECTORS[0]))

static void hex_to_bytes(const char *hex, uint8_t *out, int n) {
    int i;
    for (i = 0; i < n; i++) {
        unsigned int b;
        sscanf(hex + i * 2, "%2x", &b);
        out[i] = (uint8_t)b;
    }
}

int main(void) {
    size_t v;
    for (v = 0; v < VECTOR_COUNT; v++) {
        int sector;
        for (sector = 0; sector < 16; sector++) {
            uint8_t got[6], want[6];
            skylanders_mifare_key_a(sector, VECTORS[v].uid, got);
            hex_to_bytes(VECTORS[v].keys_hex[sector], want, 6);
            if (memcmp(got, want, 6) != 0) {
                printf("MISMATCH uid=%02x%02x%02x%02x sector=%d got=%02x%02x%02x%02x%02x%02x want=%s\n",
                       VECTORS[v].uid[0], VECTORS[v].uid[1], VECTORS[v].uid[2], VECTORS[v].uid[3], sector,
                       got[0],got[1],got[2],got[3],got[4],got[5], VECTORS[v].keys_hex[sector]);
                assert(0 && "key mismatch against real-JS-verified vector");
            }
        }
    }
    printf("skylanders_mifare_keys: all %zu UIDs x 16 sectors (%zu keys) match real-JS-verified vectors\n",
           VECTOR_COUNT, VECTOR_COUNT * 16);
    return 0;
}
