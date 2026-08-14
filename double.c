double compute(double a, double b) {
    double c = a + b;
    double d = a * b - c;
    int i = (int)d;
    return d + (double)i;
}
