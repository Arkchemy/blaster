double compute(double a, float b, unsigned int base) {
    float rounded = (float)a;
    unsigned int addr = base + 0x50000;
    return (double)rounded + (double)addr;
}
