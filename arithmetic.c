int add(int x, int y) {
    return x + y;
}

int compute(void) {
    int a = 0;
    int b = 1;
    int i;
    for (i = 0; i < 10; i++) {
        int t = add(a, b);
        a = b;
        b = t;
    }
    int scaled = b * 3 - 7;
    return scaled;
}
