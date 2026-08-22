float compute(void) {
    float a = 1.5f;
    float b = 2.25f;
    float sum = 0.0f;
    int i;
    for (i = 0; i < 4; i++) {
        sum = sum + a * b;
        a = a + 0.5f;
    }
    return sum;
}
