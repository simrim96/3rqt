def solve(data):
    sw = ss = 0.0
    for line in data.splitlines():
        line = line.strip()
        if not line:
            continue
        w, s = line.split(",")
        sw += float(w)
        ss += float(w) * float(s)
    return f"{ss / sw:.2f}"
