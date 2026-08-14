int compute(unsigned int x, unsigned int y) {
    int lz = __builtin_clz(x | 1);
    unsigned int a = x & ~y;
    unsigned int b = ~(x ^ y);
    int diff = 1000 - (int)x;
    return lz + (int)a + (int)b + diff;
}
