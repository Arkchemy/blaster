unsigned int compute(int n) {
    unsigned int x = (unsigned int)n * 0x9E3779B1u;
    unsigned int a = x & 0x3Fu;
    unsigned int b = (x << 3) | (x >> 29);
    unsigned int masked = a + b;

    int sum = 0;
    for (int i = 0; i < n; i++) {
        sum += i * 2 + 1;
    }

    return masked + (unsigned int)sum;
}
