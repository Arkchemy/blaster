int helper(int x);

int compute(int n) {
    int total = 0;
    for (int i = 0; i < n; i++) {
        total += helper(i);
    }
    return total;
}
