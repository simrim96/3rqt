def _enc(line):
    out = []
    i = 0
    while i < len(line):
        j = i
        while j < len(line) and line[j] == line[i]:
            j += 1
        out.append(f"{line[i]}{j - i}")
        i = j
    return "".join(out)

def solve(data):
    return "\n".join(_enc(line) for line in data.splitlines())
