"""Vector DB maintenance commands for Sahayak 1092.

Usage:
  python -m backend.vector_admin seed
  python -m backend.vector_admin backfill --limit 100
  python -m backend.vector_admin diagnose-supabase
"""

from __future__ import annotations

import argparse
import asyncio

from backend.intelligence.similarity import (
    backfill_resolved_case_embeddings,
    seed_demo_vector_cases,
)
from backend import supabase_client as db


async def _run(command: str, limit: int) -> dict:
    if command == "seed":
        return await seed_demo_vector_cases()
    if command == "backfill":
        return await backfill_resolved_case_embeddings(limit=limit)
    if command == "diagnose-supabase":
        health = db.supabase_health(probe=True)
        write_probe = db.write_diagnostic_call_log(cleanup=True)
        return {"health": health, "write_probe": write_probe}
    raise ValueError(f"Unknown vector admin command: {command}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sahayak 1092 vector DB maintenance")
    parser.add_argument("command", choices=("seed", "backfill", "diagnose-supabase"))
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    result = asyncio.run(_run(args.command, args.limit))
    print(result)


if __name__ == "__main__":
    main()
