"""Probe: una chiamata reale su mid per vv_reverse_02 — finish_reason,
truncation e motivo di grading."""

import asyncio
import json
from pathlib import Path

from evals.grader import grade_verificabili
from evals.suite import load_suite
from nodes.adapter import NodeAdapter
from nodes.config import load_nodes_config

cfg = load_nodes_config(Path("config/nodes.yaml"))
node = cfg.enabled_nodes()["mid"]
item = next(i for i in load_suite("verificabili").items if i.id == "vv_reverse_02")


async def main():
    async with NodeAdapter(node) as ad:
        res = await ad.chat(
            [
                {"role": "system", "content": load_suite("verificabili").gen_system},
                {"role": "user", "content": item.prompt},
            ],
            max_tokens=2048,
            temperature=0.0,
            top_p=1.0,
            extra_body={
                "seed": 1234,
                "thinking_ratio": 0.0,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            read_timeout=180.0,
        )
    txt = res.text
    print("finish:", res.finish_reason)
    print("usage:", res.usage)
    print("len_txt:", len(txt), "lines:", txt.count("\n"))
    print("--- head 300 ---")
    print(txt[:300])
    print("--- tail 300 ---")
    print(txt[-300:])
    g = grade_verificabili(item, txt)
    print("grade:", json.dumps(g, ensure_ascii=False)[:400])


asyncio.run(main())
