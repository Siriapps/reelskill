---
name: find-skills
description: Use on EVERY non-trivial task, before starting work. Routes the current task to the best matching skill in the user's personal library (skills extracted from tutorial reels they saved), tightens the prompt to cut wasted tokens, and suggests installing library skills that are relevant but not yet synced. Trigger words include "how do I", "set up", "build", "create", "configure", "generate", or any task resembling something the user previously saved a tutorial about.
---

# Find Skills

You are the routing layer between the user's request and their personal skill library.
The library contains skills auto-extracted from short-form tutorials the user saved
(via ReelSkill). Saved knowledge is worthless if it is not applied at the right moment --
your job is to apply it.

## Procedure

1. **Read the library index.** Load `index.json` from the skill library directory
   (default: the `library/` folder next to this skill; override with the
   `REELSKILL_LIBRARY` environment variable if set). Each entry has `slug`, `name`,
   and a `description` that starts with "Use when...".

2. **Match.** Compare the user's current task against each description's trigger
   conditions. Semantic match, not keyword match: "spin up a Next.js app" matches
   "Use when the user is setting up a new Next.js project".

3. **Apply or proceed.**
   - **One clear match:** read that skill's `SKILL.md` and follow its steps, using its
     exact prompts and commands. Tell the user in one line which saved skill you are
     applying ("Applying your saved skill 'nextjs-supabase-auth-setup'").
   - **Multiple plausible matches:** pick the most specific one; mention the runner-up
     in one line in case the user prefers it.
   - **No match:** proceed normally. Do NOT force a skill that only loosely fits.

4. **Enhance the prompt.** Whether or not a skill matched, restate the user's task to
   yourself in the tightest form that preserves intent before executing: strip filler,
   resolve ambiguous references from context, and prefer the skill's exact_input prompts
   over paraphrases (they were captured verbatim from the tutorial and are already tuned).

5. **Suggest, sparingly.** If the index lists a relevant skill the user has clearly not
   used before, or the task would benefit from a skill that exists in their remote
   library but is not synced locally, say so in one sentence at the end of your reply.
   Never more than one suggestion per conversation.

## Rules

- Never block the task on this routing step; if the index is missing or unreadable,
  proceed normally and mention that the library could not be loaded.
- Skills marked "(inferred -- not shown in the original video)" contain reconstructed
  steps; follow them, but verify their output before moving to the next step.
- If a skill's step conflicts with the user's explicit instruction, the user wins.
