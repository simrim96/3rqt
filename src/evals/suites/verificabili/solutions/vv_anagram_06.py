from collections import Counter

def solve(data):
    lines = data.split()
    words = lines[1 : 1 + int(lines[0])]
    groups = Counter("".join(sorted(w)) for w in words)
    return str(max(groups.values()))
