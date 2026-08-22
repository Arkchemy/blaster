int compute(int a, int b, unsigned int c, unsigned int d) {
    int q1 = a / b;
    unsigned int q2 = c / d;
    int r1 = a % b;
    return q1 + (int)q2 + r1;
}
