import re

def solve(data):
    return "\n".join(
        re.sub(r"(?<!^)(?=[A-Z])", "_", line.strip()).lower() for line in data.splitlines()
    )
