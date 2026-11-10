import bisect

def solve(data):
    lines = data.splitlines()
    arr = [int(t) for t in lines[0].split()]
    out = []
    for line in lines[1:]:
        if not line.strip():
            continue
        q = int(line)
        i = bisect.bisect_left(arr, q)
        out.append(str(i if i < len(arr) and arr[i] == q else -1))
    return "\n".join(out)
