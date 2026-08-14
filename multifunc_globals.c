static int shared = 5;

void bump(int by) {
    shared += by;
}

int read_shared(void) {
    return shared;
}

int compute(int a, int b) {
    bump(a);
    bump(b);
    return read_shared();
}
