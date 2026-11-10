"""Probe: heavy risponde a messaggi singoli vs system+user?"""

import asyncio
from pathlib import Path

from nodes.adapter import NodeAdapter
from nodes.config import load_nodes_config

cfg = load_nodes_config(Path("config/nodes.yaml"))
node = cfg.enabled_nodes()["heavy"]


async def main():
    async with NodeAdapter(node) as ad:
        r1 = await ad.chat(
            [{"role": "user", "content": "Rispondi solo con la parola OK"}],
            max_tokens=64,
            temperature=0.0,
            extra_body={"seed": 7},
            read_timeout=120.0,
        )
        print("solo-user:", repr(r1.text[:200]), "| comp:", r1.usage.completion_tokens)
        r2 = await ad.chat(
            [
                {"role": "system", "content": "Rispondi solo con la parola OK."},
                {"role": "user", "content": "Adesso."},
            ],
            max_tokens=64,
            temperature=0.0,
            extra_body={"seed": 7},
            read_timeout=120.0,
        )
        print("sys+user:", repr(r2.text[:200]), "| comp:", r2.usage.completion_tokens)


asyncio.run(main())
