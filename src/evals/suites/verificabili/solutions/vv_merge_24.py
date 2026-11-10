import heapq

def solve(data):
    lists = [[int(t) for t in ln.split(",")] for ln in data.splitlines() if ln.strip()]
    merged = list(heapq.merge(*lists))
    return ",".join(map(str, merged))
