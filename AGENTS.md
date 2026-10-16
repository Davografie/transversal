# Transversal — Agent Instructions

Transversal is a VTTRPG (Virtual Tabletop RPG) where players travel across a multiverse using a common backend application. Rules based on Cortex Prime with a dual-pipeline dice resolution system.

## Interaction Rules

- A **question** is a request for information, not an implicit request for action. Answer questions directly — do not jump to conclusions, start work, or assume intent.
- A **directive** is a clear statement to do something ("do X," "build Y," "fix Z"). Only then should you act.
- If a message could be interpreted either way, treat it as a question. When in doubt, ask for clarification rather than proceeding.

## Player characters & the testing character

**Player characters belong to the players — do not author, alter, or "clean up" one.** Never rewrite a PC's traits, SFX, history or images, and never tidy its settings. `GMC` is fair game; so are factions, locations, assets, roll tables, life paths, registry traits and trait *sets*. When a PC needs material, the answer is **scenario** — locations, GMCs, factions, challenges, clocks, support cast — never the PC's sheet.

The distinction is by type: an entity of type `CHARACTER` is a PC **unless it is Kael Drift**.

**Kael Drift (`character-kael-drift-e555ccde`) is the project's testing character — use it for testing.** Act as Kael Drift rather than claiming a player's character. Do **not** run tests or drive the UI as a real PC (any other `CHARACTER`): the human sees them come online while sessions are testing, and exercising a player's character reads and writes that player's data.

Kael Drift is this project's own character and the **only** `CHARACTER` an agent may act as. It is owned **as a main by the dedicated test player `DSH MCP`** — log in as that identity to reach it. See [[Overseer Operations]] for the standing state and the e2e harness's use of it.

## Git

Commit often and early — after every **verified, coherent step** (a test passes, a function works, a refactor compiles, a bug is fixed), not only at the end of a task. Small, focused commits keep changes recoverable and the history legible. Ignore files you didn't change. Verify before committing: run the relevant tests and build. See `.agents/skills/git/SKILL.md` for the full workflow.

### ⚠ `origin` is live — `git push` now publishes

Until 2026-10-16 nothing left this machine. GitHub hosting was set up at the human's direction and
`origin` is written to the **shared** `.git/config`, so **all 20 worktrees carry it**: any session
running `git push` publishes to `github.com/Davografie/transversal` (**public** since 2026-10-16).

- **Do not push unless you were asked to.** Commit locally, as always; merging into `release-build`
  is still the way work lands.
- **Never push a force-push of a role branch.** Role branches **rebase** by convention, so a pushed
  role branch requires force-pushing rewritten history. Only **`release-build`** and **`production`**
  are published — role branches are not.
- **Do not push either long-lived branch from a role worktree.** `release-build` and `production` are
  the [[Overseer]]'s to publish, and only when the tree is verified.
- Issues are the one thing worth *reading* from GitHub: see [[GitHub Issue Loop]].

### ⚠ The coordination layer is NOT tracked — your doc and ticket edits are local-only

When the repo went public on 2026-10-16, the internal material was **gitignored** rather than
published. Verified: the public history contains **zero** commits touching these paths, so the
redaction covers history as well as the tree.

| ignored path | is |
|---|---|
| `docs/sessions/` | the session docs — **including yours** |
| `docs/Process/` | tickets, the generated board, [[Division of Labor]] |
| `docs/to-do.md` | the human's capture file |
| `docs/Technical/Security Posture.md` | the unfixed-vulnerability register |
| `deploy/headscale/`, `.backups/`, `backups/`, `*.data.json.gz` | the private tailnet config and DB dumps containing player characters |
| `.deepseek/`, `.codewhale/` | agent internal state |

**What this means in practice, and it will surprise you if nobody says it:** `git status` will not
show your session-doc or ticket edits, `git add` refuses them, and **committing them does nothing**.
The whole coordination layer now lives **on this machine only — no history, no backup**. So do not
treat a commit as a save for those files; if you care about a change surviving, it has to be
somewhere else too.

`AGENTS.md` **is** tracked, and was generalised for publication before it was published — so **do not
put personal names, player handles, or internal detail in it.** That is the file the public sees.

## Git Identity

AI-agent commits must not reuse the user's `user.name` / `user.email`. Always commit under a distinct agent identity so agent-authored work is distinguishable in history:

```bash
git -c user.name="Codewhale (DeepSeek-v4-PRO)" \
    -c user.email="codewhale@example.invalid" \
    commit -m "..."
```

### Attribution trailers — the identity does not say *which* session

The identity above is **shared by every session**, so on its own it cannot answer
"which session wrote this?". Three properties of the workflow destroy the other signals:
landings on `release-build` are **fast-forwards** (so no merge commit records the source
branch), the role branches **rebase** onto it (so `git branch --contains` returns a dozen
answers — 3 to 21 measured), and the committer is whoever ran the merge (589 commits
carry an agent author and the human as committer). The branch name *is* the role and it is
known at commit time, so it gets written down as a message trailer:

    Session: effects
    Ticket: B219

`scripts/git-hooks/prepare-commit-msg` adds these automatically — for agent commits only,
never the human's, and never on merges or squashes. `Session:` comes from the branch
(`release-build` → `Overseer`); `Ticket:` comes from a **staged ticket note**, else from the
subject, and is omitted rather than guessed. Idempotent. Install once per checkout:

```bash
bash scripts/install-git-hooks.sh   # sets core.hooksPath (shared config → all worktrees)
```

Run it with `bash` — this repo has `core.fileMode = false`, so executable bits are not
tracked reliably across checkouts; the script `chmod +x`es the hook it installs.

Read them back:

```bash
git log --format='%h %(trailers:key=Session,valueonly) %s'
git log --grep='^Session: effects'
```

`.mailmap` canonicalises the identity's three spellings for `%aN`, `log --author` and
`shortlog`. Use `%aN`, not `%an` — `%an` is the raw spelling and is **not** canonicalised.

Stage only the files you changed; never `git add -A` when unrelated modifications are present.

### CodeWhale `/edit` filesystem-snapshot revert

Using CodeWhale's `/edit` to rewrite the **last sent prompt** can trigger a
filesystem-snapshot restore that reverts **working-tree files to older
versions**. Git commits and the index are untouched — only the working tree
drifts. Symptom: `git status` shows ` M` files whose on-disk content is *older*
than HEAD (recent committed work looks "undone"); genuine uncommitted work can
also be lost.

**Remedy (cheap):** history is intact — re-sync the working tree from HEAD:

```bash
git status --short                              # the drifted files
git restore --source=HEAD --worktree -- <file>…  # specific files only
git status --short                              # confirm clean
```

Restore only the specific drifted files; never `git restore .` (it would also
discard legitimate uncommitted work). If unsure whether a file is a revert or
real WIP, `git diff -- <file>` disambiguates: a revert shows recent HEAD content
being *removed*, WIP shows new/edited content.

## Parallel Sessions & Worktrees

More than one agent session may work in this repo at a time. The working tree is shared mutable state — only committed history is safe.

- Work in your own `git worktree` (own directory + own branch). Don't write to the shared branch while another session may be active.
- **Tool-path gotcha:** agent tools (`edit`/`read`/`write`) resolve *relative* paths against the **main checkout**, not your role worktree — a relative-path edit silently lands in `release-build`'s tree. When editing inside a worktree, use **absolute** paths (`/home/dave/dev/transversal2-<role>/…`).
- Commit early and often; treat uncommitted changes as fragile.
- Never run broad discards: `git checkout -- .`, `git restore .`, `git reset --hard`, or an IDE "discard all". Revert only the specific files you changed, and commit before any sweeping operation.
- When finished, merge your branch back into the integration branch (see **Merging back** below).

### The branches: staging and production

Two long-lived branches, and the distinction is the whole point:

| branch | is | who moves it |
|---|---|---|
| **`release-build`** | **staging** — the integration branch every role merges into, and the tree the dev frontend serves at `:3000` | every session, by merging finished work (as below) |
| **`production`** | **what is deployed** — the actual application | the [[Overseer]], deliberately, by promotion only |

**`production` only ever fast-forwards to `release-build`**, so it stays an *ancestor* of it. That
invariant is load-bearing: it makes `git log production..release-build` mean exactly **"staged but not
yet live"**, which is the question you ask before a deploy. Promotions are made and tagged with
`bash scripts/promote.sh` (`--check` reports what is staged without changing anything), and **the tag
is the record** — not a merge commit, which would break the linearity.

**Nobody but the [[Overseer]] advances `production`**, and never by committing to it: a direct commit
there breaks the ancestor invariant and `promote.sh` will refuse to promote afterwards. If you find
yourself wanting to, that is a bug fix that goes to `release-build` and then gets promoted.

To re-base a role branch, target the **staging** branch: `git rebase release-build`.

> [!success] Branch protection is ON — both long-lived branches (2026-10-16)
> Enabled once the repo went public. Verified on **`release-build`** and **`production`**:
> **force-pushes blocked**, **deletions blocked**, **admins enforced** — and deliberately **no
> required PR reviews and no required status checks**, because the fleet fast-forwards and does not
> open pull requests; requiring either would block every merge. So you can still fast-forward a merge
> into `release-build`, and the [[Overseer]] can still promote `production`. What you *cannot* do is
> rewrite either branch's history or delete it, by accident or otherwise.
>
> `scripts/promote.sh` still **refuses to promote a diverged `production`**, which remains the local
> alarm that a direct commit landed; the server-side rules now stop the history rewrite that would
> have hidden it.

### One branch per role

Sessions are role-scoped and long-lived (weeks, many compactions). Each role owns one
branch and one worktree for its whole life; a session attaches to its role's branch and
keeps using it across compactions. Do not create a new branch per session or per
compaction.

- Branch names are the role's name and are stable, e.g. `effects/<sub-area>`,
  `character-sheet`, `game-mechanics`. Create a role branch once:

  ```bash
  git worktree add -b <role-slug> ../transversal2-<role-slug> <integration>
  ```

  If the role already has a worktree/branch, reuse it — check first: `git worktree list`
  and `git branch` (`+` marks branches checked out elsewhere).

- Establish your identity from git, not from memory — at startup and after every
  compaction:

  ```bash
  git rev-parse --show-toplevel   # which worktree dir am I in?
  git branch --show-current        # which role branch am I on?
  ```

  The branch name and worktree directory live in git/filesystem and survive any number
  of compactions. Re-derive them; never trust stale context or a handoff over the live
  result.

- Make direct commits on the integration branch only for the `:3000` test loop — see **Merging back** below.

### Merging back

`release-build` is both the integration branch and the tree the dev frontend serves at
`:3000`. It is **not a scratch space** — development happens on your own branch/worktree;
`release-build` only receives finished work. Work lands in two ways:

- **Default — you merge your own finished feature.** Once a feature is finished and
  verified (tests/build pass), rebase your branch onto `release-build` and merge it
  yourself. Do **not** wait for the overseer — merging is your job, not a hand-off. The
  overseer coordinates a merge **only** when a feature spans multiple domains and its
  pieces must land in a specific order (the exception, not the norm).
- **Test loop — direct commit (narrow exception).** Only when the *human* is actively
  testing a fix at `:3000` may the session driving that loop commit directly to
  `release-build` in the main checkout. This is for the human's loop, not for an agent's
  own testing.

**During development**, commit to your own branch, never `release-build`. Test in your own
worktree — `scripts/dev-worktree.sh` for the frontend (`:3002+`, never `:3000`) or mount
the worktree over the image for backend tests. Never leave uncommitted edits in the main
checkout.

Either way:

- Rebase onto `release-build` before merging; resolve conflicts on your own branch.
- Merge only after the relevant tests/build pass; resolve conflicts explicitly; never
  `git add -A` when unrelated changes are present.
- Do **not** edit shared coordination files (`docs/sessions/Sessions.md`, `AGENTS.md`, or
  cross-role `docs/`) — the overseer owns these. During a rebase, drop your own roster
  edits; the overseer has already recorded your row. **Exception: you own your tickets.**
  A ticket is its own note (`docs/Process/Tickets/<ID>.md`) — update its status/frontmatter
  and body yourself and commit it, then regenerate the board
  (`python3 scripts/gen-ticket-board.py`). Never hand-edit `docs/Process/Tickets.md`; it is
  generated. Mint new tickets with `scripts/new-ticket.sh "<title>"`, never by inventing an id.
- The overseer owns the shared docs and coordinates multi-domain merges; single-domain
  merges are the session's own.

**Nothing you merge goes live.** Merging into `release-build` puts work in **staging**; the
[[Overseer]] promotes staging to `production` separately, deliberately, and tagged. You do not deploy,
and you should not try to — a deploy is a decision, not a merge.

### Session coordination

Each role keeps a coordination doc in `docs/sessions/` that the other sessions and the
overseer read. It carries what git can't express: current focus, blockers, and what you
need from other sessions.

- **Your doc** — copy `docs/sessions/_template.md` to `docs/sessions/<role-slug>.md` and
  fill it in (frontmatter `role` / `branch` / `worktree` / `status`, plus About, Current
  focus, Status, Blockers & needs, Log). Update it at every compaction.
- **The roster** — `docs/sessions/Sessions.md` is the index, maintained by the **overseer**
  (not by individual roles). When you create your doc, ask the overseer to add your row —
  do not edit the roster yourself.
- **Getting attention** — request another session's attention by wikilinking their doc
  under your **Blockers & needs**, e.g. `[[Overseer]] — multi-domain feature: sequence the merges (X before Y)`.
  The target sees it via Obsidian backlinks; the overseer greps for `[[<note>]]`. Set
  frontmatter `status: blocked` for anything blocking; delete the line once resolved.
- **Ownership & deferral** — every ticket is owned by a role; the map lives in
  `docs/Process/Division of Labor.md`. To hand a ticket to another role, ask the overseer
  to re-own it and wikilink the new owner under your **Blockers & needs**.
- **To-do triage** — `docs/to-do.md` is the **human's capture file**, not an agent work surface.
  An agent may only **add tags** to an item or **tick its box** — never add, delete, reword,
  reorder or restructure items, and never write an editorial note as an item. (The human's own
  rule for this file, restated 2026-09-23 after an agent-written note landed as a to-do item.)
  The overseer sweeps it and turns new items into owned ticket notes ([[Tickets]], B-prefix,
  `owner:` frontmatter) or marks them deferred. Ask the overseer rather than creating tickets
  from to-do yourself.
- **Ticket state is yours to update** — when you start, finish, or discover something about a
  ticket you own, edit `docs/Process/Tickets/<ID>.md` directly (status in frontmatter, plus
  the body's `**Status:**` line), then run `python3 scripts/gen-ticket-board.py` and commit
  both. The [[Overseer]] sweeps for stale statuses and duplicates; it is no longer the only
  writer. `docs/Process/Tickets.md` is generated — never hand-edit it.
- **Overseer** — the coordination session reads all branches and docs, maintains the
  roster, and tracks merge state. It is the one role that may write coordination docs to
  the integration branch (`release-build`) directly; all other roles stay on their own
  branch.

### Local dev & testing

> [!warning] SEC-3: the app has real sessions now — logging in changed
> Identity is no longer client-asserted. A device must be **admitted** before the app
> works at all, and there is no in-app login:
> - **Owner / GM:** open `/enter?a=$ARCHITECT_TOKEN`. `ARCHITECT_TOKEN` must be in
>   `.env` **and named in `docker-compose.yaml`** — compose passes only the variables
>   a service lists, so `.env` alone leaves the container without it.
> - **Players:** a member opens a window in the GM panel under **Prep → Players**;
>   one QR for the whole table, ~30 min, closable early.
> - `localStorage.playerId` is **ignored**; anything that logs in by seeding it will
>   land on the roster picker. `e2e/helpers/session.js` obtains a real session, and
>   the e2e suite reads `ARCHITECT_TOKEN` from `.env`.
> - Full operating notes: [[Identity Programme]] § "Operating it".


Testing is generally done against the main checkout, not a role worktree: the dev
containers (`tv2_api`, `tv2_frontend`) are mounted there, and the frontend app is served
at `http://localhost:3000` (compose service `frontend`, container `tv2_frontend`).
A role worktree's changes are **not** live at `:3000` — to exercise them, mount the
worktree over the image (see "Testing from a worktree" below).

### Testing from a worktree

The dev containers (`tv2_api`, `tv2_frontend`) are mounted to the *main* checkout, not a worktree. Run a worktree's code by mounting it over the image in a throwaway container (reuses the image's installed deps).

Backend tests (needs the compose network + env; two tests hit Arango):

```bash
docker run --rm \
  --network transversal2_default \
  -e ARANGO_URL=http://arango:8529 \
  -e REDIS_URL=redis://redis:6379 \
  -e ARANGO_ROOT_PASSWORD="$(docker exec tv2_api printenv ARANGO_ROOT_PASSWORD)" \
  -v /path/to/worktree/src/api/src:/app/src \
  -v /path/to/worktree/src/api/tests:/app/tests \
  -w /app \
  transversal2-api:latest python -m pytest tests/ -q
```

⚠ **`ARANGO_ROOT_PASSWORD` is not optional.** Without it `tests/test_graphql.py`,
`tests/test_integration.py` and `tests/test_one_trick.py` fail at *collection* with
`arango.exceptions.DatabaseListError: [HTTP 401]`, which reads as a red baseline when the
tree is green. The three `ARANGO`/`REDIS` variables above are the complete set the API
container carries — read them from the live `tv2_api` (never hard-code or print the
secret), rather than mounting a copy to disk.

### Serving a worktree frontend (interactive testing)

To interactively test a worktree's frontend, use the helper — it auto-assigns a free
port and **never** uses `:3000`, which is reserved for `release-build`:

```bash
scripts/dev-worktree.sh /path/to/worktree             # → http://localhost:3002+
scripts/dev-worktree.sh /path/to/worktree wt-effects  # named container
```

⚠ Do **not** `docker run -p 3000:3000` against a worktree, and never stop the
canonical `tv2_frontend` — `:3000` must always serve `release-build` (the
integration tree every session merges into).

## Build

Verify the frontend build inside Docker, not on the host:

```bash
docker exec tv2_frontend npm run build
```

⚠ tv2_frontend is mounted to the main checkout, so the command above
builds the main tree — not a git worktree. To build a worktree's code, mount
it over the same image (reuses the image's node_modules; a fresh worktree has
none):

`bash
docker run --rm \
-v /path/to/worktree/src/frontend/src:/app/src \
-v /path/to/worktree/src/frontend/public:/app/public \
-v /path/to/worktree/src/frontend/vite.config.js:/app/vite.config.js \
-w /app transversal2-frontend:latest npm run build
`

## Compaction

When the user asks for a compaction handoff, write it in-chat. Before writing it, check
and update the role's documentation in `/docs` against the work done (docs should reflect
the finished state, not a stale one), and refresh your session doc at
`docs/sessions/<role-slug>.md` (status, current focus, blockers, log). Include your role
and, near the top, the session identity:

- role and its branch (`git branch --show-current`)
- worktree path (`git rev-parse --show-toplevel`)
- integration branch (see "The branches: staging and production" — staging is `release-build`)
- commit state (`git status --short` + `git log --oneline -3`)
- the role's key documentation, listed so it can be read in full on alignment

When the user asks for post-compaction alignment, re-derive the identity above from git
before trusting the handoff — the branch name is self-describing (it is the role), so
even a partial handoff is recoverable. Then read the role's key documentation in `/docs` completely,
and understand the project (macro), the relevant docs and code for your role (micro), and
how the micro fits into the macro — before touching any code.

## Key Files to Read First

1. `docs/Transversal Hub.md` — entry point for all docs
2. `docs/Project Roadmap.md` — current phase and progress
3. `docker-compose.yaml` — service definitions and ports
4. `src/api/src/transversal/main.py` — app entry, startup, seed
5. `src/api/src/transversal/domain/__init__.py` — all Pydantic models
6. `src/frontend/src/App.vue` — root component, state management
7. `docs/sessions/Sessions.md` — session roster and coordination conventions

## Documentation
- All docs in `docs/` as Obsidian-wiki markdown files
- Use `[[wikilinks]]` for internal references
- Frontmatter with `title`, `tags`, `aliases`

## Cortex Prime Rules (RAW)

**Start with the local library — check the rulebook first-hand.**
The project has a local, searchable copy of the Cortex rules corpus (the Game
Handbook, Cortex Lite, the Tales of Xadia primer, Smallville, Marvel Heroic,
Firefly, TorchLite and others). Read and cite from it; fall back to web search
only for what it doesn't cover.

- **Index & topic→page map:** [[Cortex Rules Library]] (`docs/Reference/Cortex Rules Library.md`)
- **PDFs:** `/mnt/disk2/TTRPG-merged/Cortex/`
- **Extracted text (greppable):** `/mnt/disk2/TTRPG-merged/.index/text/Cortex/`

```bash
RULES=/mnt/disk2/TTRPG-merged/.index/text/Cortex
grep -rn -i "effect die" "$RULES/Cortex_Prime.pdf.txt" | head
pdftotext -f 21 -l 24 -layout /mnt/disk2/TTRPG-merged/Cortex/"Cortex Prime.pdf" -
```

Cite as book + page (e.g. *Cortex Prime*, PDF p. 21). The page numbers in the
index are `pdftotext` indices and are usually **offset** from the printed
folios — confirm the passage before quoting a printed page. The library is
**outside the workspace**, so a session on the `workspace-write` policy may not
be able to read it; if that blocks you, tell the [[Overseer]].

### Web fallback

To check Cortex Prime rules when the library doesn't cover it, use **web search,
not direct fetch**. The official site is JavaScript-rendered, so a direct
`fetch`/`open` returns "no readable page content"; the search backend
(Firecrawl) renders the JS and returns the text in snippets.

#### Sources
- **Official compendium** (Dire Wolf Digital): `https://www.cortexrpg.com/compendium/explore-the-rules`
  - JS-rendered; search it with `domains: ["cortexrpg.com"]`. Sub-pages are indexed.
- **Cortex Prime SRD** (free System Reference Document — the RAW reference):
  - "Cortex Prime System Reference" draft 2019-07-08 and "Cortex Prime SRD v1.1".
  - Mirrors: `https://pdfcoffee.com/cortex-prime-srd-pdf-free.html`, Scribd ("Cortex Prime SRD v1.1").
- **Cortex Prime Game Handbook** (2020) is the paid rulebook — and it is **in the local library** ([[Cortex Rules Library]]).

#### Method
1. `Web` search scoped to `cortexrpg.com` for compendium text (search renders JS; fetch does not).
2. `Web` search with **quoted verbatim phrases** to surface exact RAW (SRD/Handbook text and community quotes), e.g. `"Contests go back and forth until one side gives in or fails"`.
3. Don't `fetch`/`open` `cortexrpg.com` directly — use search snippets or browser automation instead.
