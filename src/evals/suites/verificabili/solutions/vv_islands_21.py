def solve(data):
    grid = [list(r) for r in data.splitlines() if r]
    h, w = len(grid), len(grid[0])
    def flood(i, j):
        stack = [(i, j)]
        while stack:
            y, x = stack.pop()
            if not (0 <= y < h and 0 <= x < w) or grid[y][x] != "#":
                continue
            grid[y][x] = "."
            stack += [(y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)]
    n = 0
    for i in range(h):
        for j in range(w):
            if grid[i][j] == "#":
                flood(i, j)
                n += 1
    return str(n)
