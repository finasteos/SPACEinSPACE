#!/usr/bin/env python3
"""Seed the Neo-Japanese Minimalist ("Neon Noir") World State into Supabase.

Populates:
  1. Agent Registry entries (planner, blender, memory, tool, review, human)
  2. Initial Scratchpad sections with Kanji markers (計画 Plan, 状態 State, 記憶 Memory)
  3. Default substrate conversation witness entries

Usage:
  $ python3 scripts/seed_neo_minimal_world.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Ensure workspace root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from shared.supabase_client import get_supabase


async def seed_world():
    print("🌟 Seeding Neo-Japanese Minimalist World State into Supabase...")
    db = get_supabase()
    thread_id = "neo-minimal-main"

    # 1. Register Agents
    agents_data = [
        {"id": "planner", "name": "Planner Agent (計画)", "role": "planner", "capabilities": ["plan", "delegate", "goal"]},
        {"id": "blender-agent", "name": "Blender Ambassador (道具)", "role": "blender", "capabilities": ["blender", "scene", "render"]},
        {"id": "memory-agent", "name": "Memory Agent (記憶)", "role": "memory", "capabilities": ["memory", "vector", "recall"]},
        {"id": "tool-agent", "name": "Tool Ambassador (道具)", "role": "tool", "capabilities": ["web", "file", "math"]},
        {"id": "review", "name": "Reviewer Agent (監査)", "role": "review", "capabilities": ["verify", "audit"]},
        {"id": "fallback", "name": "Fallback Agent (予備)", "role": "fallback", "capabilities": ["fallback"]},
        {"id": "human", "name": "Human Guest (人間)", "role": "human", "capabilities": ["override", "direct"]},
    ]

    for a in agents_data:
        try:
            await db.register_agent(
                agent_id=a["id"],
                name=a["name"],
                role=a["role"],
                capabilities=a["capabilities"],
            )
            print(f"  ✅ Agent registered: {a['name']}")
        except Exception as e:
            print(f"  ⚠️ Could not register {a['id']}: {e}")

    # 2. Seed Scratchpad Sections
    scratchpad_sections = {
        "plan": """# 計画 (Plan): Neo-Japanese Minimalist Substrate

1. [x] Supabase integration & vector schema verified
2. [x] Neo-Japanese Minimalist design system (`neo_minimal.css`) created
3. [x] Dashboard & 3D vector space styled (Electric Cyan & Cyber Yellow on Obsidian Void)
4. [x] 3D Blender environment script (`create_neo_minimal_world.py`) ready
5. [ ] Continuous multi-agent task execution on the A2A bus
""",
        "state": """# 状態 (World State)

- Environment: Neo-Minimalist Obsidian Substrate (無 - Mu)
- Color Palette: Neon Noir (Electric Cyan `#00F0FF` & Cyber Yellow `#FFE600` on Obsidian `#050508`)
- Active Thread: `neo-minimal-main`
- Status: Operational
""",
        "memory": """# 記憶 (Memory Index)

- Vector Embeddings: 4096-dim (`qwen3-embedding:8b`)
- Spatial Zones: 無 (Mu), 記憶 (Kioku), 計画 (Keikaku), 道具 (Dōgu)
"""
    }

    for sec, content in scratchpad_sections.items():
        try:
            v = await db.upsert_scratchpad(
                thread_id=thread_id,
                section=sec,
                content=content,
                agent_id="planner",
            )
            print(f"  ✅ Scratchpad section '{sec}' updated (v{v})")
        except Exception as e:
            print(f"  ⚠️ Could not update scratchpad section '{sec}': {e}")

    # 3. Log initial witness message
    try:
        msg_id = await db.log_message(
            thread_id=thread_id,
            from_agent="planner",
            content="Neo-Japanese Minimalist world substrate (無 - Mu) initialized. Electric Cyan and Cyber Yellow active.",
            message_type="plan_update",
            to_agent="human",
        )
        print(f"  ✅ Initial witness message logged: {msg_id}")
    except Exception as e:
        print(f"  ⚠️ Could not log witness message: {e}")

    print("\n🎉 World seeding complete!")


if __name__ == "__main__":
    asyncio.run(seed_world())
