long long compute(unsigned int a, unsigned int b) {
    long long x = ((long long)a << 32) | b;
    long long y = 0x123456789ABCDEF0LL;
    long long sum = x + y;

    unsigned int u1 = 5, u2 = 10;
    int cmp_result = (u1 < u2) ? 1 : 0;

    return sum + cmp_result;
}
