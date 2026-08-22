int compute(void) {
    unsigned int a = 0xF0F0F0F0u;
    unsigned int b = 0x0F0F0F0Fu;
    unsigned int c = a & b;
    unsigned int d = a | b;
    unsigned int e = a ^ b;
    unsigned int f = ~(a | b);
    int g = -((int)c + 1);
    unsigned int h = a << 4;
    unsigned int i = a >> 4;
    int j = ((int)a) >> 4;

    unsigned char buf[4];
    buf[0] = (unsigned char)(d & 0xFF);
    buf[1] = (unsigned char)((e >> 8) & 0xFF);
    signed char sc = (signed char)buf[0];
    int k = (int)sc;

    unsigned short hbuf[2];
    hbuf[0] = (unsigned short)(h & 0xFFFF);
    short ss = (short)hbuf[0];
    int l = (int)ss;

    int sum = c + d + e + f + g + h + i + j + k + l;
    return sum;
}
