"""Test the full pipeline on a local video file, no Meta app required.

Usage:
    python cli.py path/to/reel.mp4 --caption "the reel's caption" [--user me]

If the pipeline pauses for a missing resource, it asks on stdin (playing the role
of the Instagram DM thread) and then finishes the skill.
"""

import argparse
import asyncio
from pathlib import Path

from reelskill.pipeline import process_reel, resume_with_answer


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="Path to a downloaded reel / tutorial video (mp4)")
    parser.add_argument("--caption", default="", help="Caption text of the reel")
    parser.add_argument("--user", default="local-user", help="User id for the skill library")
    args = parser.parse_args()

    result = await process_reel(args.user, args.video, caption=args.caption)
    print("\n[bot]", result.message)

    if result.status == "needs_input":
        answer = input("\n[you] > ")
        result = await resume_with_answer(args.user, answer)
        print("\n[bot]", result.message)

    if result.skill_path:
        print(f"\nSkill written to: {result.skill_path}")
        print("-" * 60)
        print(result.skill_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    asyncio.run(main())
