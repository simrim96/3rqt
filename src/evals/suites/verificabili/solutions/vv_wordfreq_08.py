from collections import Counter
import re

def solve(data):
    words = re.findall(r"[a-z0-9]+", data.lower())
    c = Counter(words)
    best = min(c, key=lambda w: (-c[w], w))
    return f"{best} {c[best]}"
