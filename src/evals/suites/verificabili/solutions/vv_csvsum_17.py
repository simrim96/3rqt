import csv
import io

def solve(data):
    rd = csv.DictReader(io.StringIO(data))
    tot = sum(float(r["importo"]) for r in rd)
    return f"{tot:.2f}"
