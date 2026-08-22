float compute(float a, float b) {
    if (a < b) {
        return a - b;
    } else if (a > b) {
        return a + b;
    }
    return 0.0f;
}
