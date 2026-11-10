def solve(data):
    v = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    out = []
    for line in data.splitlines():
        s = line.strip()
        if not s:
            continue
        tot, prev = 0, 0
        for ch in reversed(s):
            val = v[ch]
            tot += val if val >= prev else -val
            prev = max(prev, val)
        out.append(str(tot))
    return "\n".join(out)
