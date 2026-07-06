"""Sync your ReelSkill library from the server to a local folder for the find-skills meta-skill.

Usage:
    python sync_skills.py --server https://your-deployment.example.com --user <your IG-scoped id> \
        [--dest meta-skill/find-skills/library]
"""

import argparse
import json
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--dest", type=Path, default=Path("meta-skill/find-skills/library"))
    args = parser.parse_args()

    base = args.server.rstrip("/")
    index = httpx.get(f"{base}/skills/{args.user}/index.json", timeout=30).raise_for_status().json()

    args.dest.mkdir(parents=True, exist_ok=True)
    (args.dest / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")

    for skill in index["skills"]:
        slug = skill["slug"]
        md = httpx.get(f"{base}/skills/{args.user}/{slug}/SKILL.md", timeout=30).raise_for_status().text
        skill_dir = args.dest / slug
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text(md, encoding="utf-8")
        print(f"synced {slug}")

    print(f"\n{len(index['skills'])} skill(s) -> {args.dest}")


if __name__ == "__main__":
    main()
