---
name: git
description: When to commit, branch, stash, and how to structure work for safe, recoverable progress. Use when starting a task, finishing a step, recovering from a wrong turn, or cleaning up.
---

# Git Skill

These are agentic workflow rules, not a command reference. You already know the commands. These rules tell you *when* to use them.

## Commit Often and Early

Commit after every **verified, coherent step**. Not after every file edit — after something that stands on its own: a test passes, a function works, a refactor compiles, a bug is fixed.

Why:
- A bad edit is cheap to undo when the last commit was 30 seconds ago.
- If the user says "actually, go back," you can revert to a known-good point instead of trying to unpick 200 lines of tangled changes.
- The history becomes a legible narrative of what happened.

What *not* to do: wait until the entire task is done, then make one giant commit. That defeats every purpose of version control.

A commit message should say what changed and, when it's not obvious, why. Use conventional commit prefixes: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`.

## Verify Before Committing

Never commit broken code. Before `git commit`:
- If the project has tests, run the relevant ones.
- If it's a buildable project, make sure it builds.
- If it's a config change, validate the config.

A commit that doesn't work is worse than no commit — it creates a false checkpoint that will mislead whoever bisects later (including you).

If the step can't be verified yet, don't commit yet. Keep going until it can.

## Branch for Multi-Step Work

Create a branch when:
- The task has more than one commit's worth of work.
- The work might take a wrong turn and need to be abandoned.
- You're experimenting and might want to throw it away.
- You're working in parallel with other work (including other agent sessions).

Branch naming: short, descriptive, lowercase, hyphens. E.g. `fix-sse-reconnect`, `add-character-import`, `refactor-dice-pipeline`.

When the branch is merged, delete it. Don't leave stale branches lying around.

## Stash for Interruptions

If the user interrupts mid-task with something higher-priority, stash your work rather than committing half-done code. A stash preserves your state without polluting the commit history. Commit when you have something coherent; stash when you don't yet.

## Keep Commits Focused

One commit = one logical change. If you fixed a bug and also reformatted an unrelated file, those are two commits. If the bug fix required the reformat to work, it's one commit — explain why in the body.

## Safety Boundaries That Require Asking

These are not defaults to override with justification. Ask before:
- `push --force` or force-pushing in any form to a shared branch.
- Amending or rebasing commits that have already been pushed.
- `git reset --hard` that would discard work that isn't backed up in another branch or stash.
- Deleting a remote branch.

## Commit Message Format

```
<type>: <imperative summary, max 72 chars>

<optional body — what changed and why>
```

Types: `feat`, `fix`, `refactor`, `docs`, `chore`, `test`, `style`, `perf`, `ci`, `build`.

## Recovery Mindset

You will make mistakes. Git gives you reflog, cherry-pick, and the stash stack. When an edit goes wrong, your first question should be "what's the last good commit?" — not "how do I manually unpick this?" Use the tools: `git reflog` to find lost commits, `git stash` to save work-in-progress, `git checkout <hash> -- <file>` to recover a single file from history.
