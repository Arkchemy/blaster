// Real regression test for a real bug found 2026-08-20 while chasing a
// genuine hang in the actual Skylanders game build: assign_global_addrs
// used to reserve synthetic address space for a .bss-only section purely
// off section_bytes -- which is deliberately *empty* for .bss, since
// SHT_NOBITS sections have no real file content to copy (see load_elf) --
// so every .bss region silently got capped at a 256-byte placeholder
// minimum, no matter how big it actually declared itself in the real ELF
// section header. The real Skylanders binary's actual .bss is ~622KB;
// every global past the first 256 bytes was silently aliasing on top of
// whatever section got assigned space right after .bss (confirmed: a
// lazily-cached heap handle read back as 0/garbage instead of its real,
// already-set value).
//
// big_table below is deliberately much bigger than that old 256-byte cap
// (1200 bytes), and lookup is a real, separate .rodata global assigned
// its own synthetic address right after .bss's (same real ordering as
// the actual game binary that exposed this). Under the old bug, writing
// every element of big_table silently corrupted lookup's synthetic
// address space too, since offsets past byte 256 within .bss overflowed
// straight into it.
static int big_table[300];
static const int lookup[4] = {111, 222, 333, 444};

int fill_and_check(void) {
    for (int i = 0; i < 300; i++) {
        big_table[i] = i + 1;
    }
    int sum = 0;
    for (int i = 0; i < 300; i++) {
        sum += big_table[i];
    }
    return sum + lookup[2];
}
