import heapq

def solve(data):
    lines = data.split()
    n = int(lines[0])
    iv = sorted((int(lines[1 + 2 * i]), int(lines[2 + 2 * i])) for i in range(n))
    rooms = []
    for s, e in iv:
        if rooms and rooms[0] <= e:
            heapq.heapreplace(rooms, e)
        else:
            heapq.heappush(rooms, e)
    return str(len(rooms))
