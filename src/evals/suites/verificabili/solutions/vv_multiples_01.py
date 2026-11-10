def _s(n, k):
    m = (n - 1) // k
    return k * m * (m + 1) // 2

def solve(data):
    out = []
    for tok in data.split():
        n = int(tok)
        out.append(str(_s(n, 3) + _s(n, 5) - _s(n, 15)))
    return "\n".join(out)
