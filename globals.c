static int counter = 100;
static int table[4] = {10, 20, 30, 40};

int compute(int idx) {
    counter += idx;
    return counter + table[idx & 3];
}
