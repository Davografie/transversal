---
title: Contributing
date: 2026-10-18
last-updated: 2026-10-18
tags:
  - transversal
  - contributing
aliases:
  - Contributing
status: canonical
---

# Contributing

Transversal is a virtual tabletop RPG — a shared world, Cortex Prime underneath, played through a
browser. This page is about **reporting problems**: what to send, where it goes, and when to expect it.

> **Issues, not patches — for now**
> There is no licence on this repository yet, so there is no stated basis for accepting a code
> contribution. **Bug reports and feature requests are very welcome. Please do not open a pull
> request** — there is nothing that can be done with it yet, and it would only sit there.

## Report something

Two forms, both in the [issue tracker](https://github.com/Davografie/transversal/issues/new/choose):

| form | for |
|---|---|
| [**Bug**](https://github.com/Davografie/transversal/issues/new?template=bug.yml) | something broke, crashed, or is wrong |
| [**Feature**](https://github.com/Davografie/transversal/issues/new?template=feature.yml) | something it should do and does not |

The forms ask for the things that actually decide how fast a report gets picked up. The most useful
sentence in a bug report is **what you expected instead** — "it did nothing" and "it did nothing, but
I expected a roll" are different bugs.

Before filing, it is worth a glance at the [open issues](https://github.com/Davografie/transversal/issues)
to see whether someone got there first. If they did, add what you saw to theirs rather than starting
a new one.

## What happens to it

1. **It is triaged.** Someone reads it, decides whether it is real, whether it is already covered, and
   which part of the project owns it.
2. **It is routed.** It gets a label naming the area, and it becomes work that someone is tracking.
   The working board itself is not public — the issue is where you can see it.
3. **It is fixed and lands.** When the fix reaches the integration branch, the issue **closes itself**.

> **Closed means landed, not live**
> The integration branch is a staging tree. A fix landing there means it is in and can be tested; it
> does not mean it is deployed. Deployment is a separate, deliberate step, so an issue may close before
> the change is available where you play. If you want to know whether something is actually live,
> re-test it — don't read the issue state.

If it will not be done, it gets closed with a reason rather than left open forever. That is a
decision, not a dismissal — it is better to know.

## What makes a report land well

- **Say what you were doing.** The step before the problem is usually the load-bearing one.
- **Say where.** Which screen, panel, or entry. Screenshots help.
- **Say how bad.** "I cannot carry on" gets handled differently from "the label is misplaced".
- **One thing at a time.** Two problems in one issue tend to get one of them fixed.

## What not to send

This is a game with real people's characters in it. Please **do not** put any of the following in a
public issue:

- passwords, tokens, or keys of any kind;
- another player's name, handle, or character sheet;
- screenshots that show other people's accounts or devices.

If a screenshot would show any of that, describe the problem in words instead.

> **If you think you have found a security problem, do not open an issue.**
> Issues are public. Report it privately, through whatever channel you already have with the
> maintainer.

## Where the documentation is

- **The manuals** — how to play, run, and author content — are in the
  [wiki](https://github.com/Davografie/transversal/wiki), generated from the repository's own notes.
- **The design and technical notes** live in [`docs/`](https://github.com/Davografie/transversal/tree/release-build/docs).
  Start at [Transversal Hub](https://github.com/Davografie/transversal/blob/release-build/docs/Transversal%20Hub.md).
- **The game rules** are Cortex Prime; the local reading list is
  [Cortex Rules Library](https://github.com/Davografie/transversal/blob/release-build/docs/Reference/Cortex%20Rules%20Library.md).

## Licence

None yet. Until one is chosen, everything here is **all rights reserved** — you may read it and fork
it on GitHub, but there is no grant to reuse or modify it, and that is why code contributions are not
being accepted. Issues are unaffected by this.
