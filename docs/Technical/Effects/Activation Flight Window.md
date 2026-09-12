---
title: Activation Flight Window
date: 2026-09-12
tags:
  - transversal
  - sfx
  - effects
  - durations
  - targeting
aliases:
  - Flight Window
  - Taking an activation back
  - Activation Holds
status: implemented
---

# Activation Flight Window

A **manual rule** can be taken back until it *commits*. Pressing an in-flight
rule again applies every undo it still owes — the razmerit it earned, the die it
added, the rating it stepped up — and drops the parts of it that were still
waiting on a roll. Once it commits, what it changed is paid for for real.

This note records the model and why it is shaped this way; the author's
correction during the design is part of it.

## The two commit points

An activation is *in flight* from the moment it applies until the first of:

1. **A delayed part of it fires.** An armed `on_roll`/`on_result` effect, a
   deferred `end_of_scene` part, a timed revert reaching its boundary.
2. **The activating entity's dice are rolled.** The roll is what consumes a pool;
   from the dice landing, what the rule did is *used*.

The second point is the one the author pinned down: a rule whose effects are all
immediate — Hinder's *add a d4 to the pool and earn 1 razmerit* — has no delayed
part at all, but it must still be cancelable *before the roll* and committed by
it. Otherwise the razmerit could be collected, the die spent in the roll, and the
cost refunded afterwards. The window closes at the dice, not at the effect.

## Holds: the undo of an effect that had no timer

The duration system already booked a **timed revert** for every effect that had
a duration: `ScheduledEvent` rows in the central store, fired when their timers
expire. What an activation changed with an *untimed* effect had no such record,
so there was nothing to apply on a take-back.

Now every effect the registry can invert books its undo, and the rows carry a
`kind`:

- **`revert`** — an undo timer: applies its effect when the timers expire.
- **`pending`** — a deferred forward effect: applies when the timers expire.
- **`hold`** — the undo of an effect that had no timer. It never fires on its
  own. A take-back applies it; a commit **dissolves** it (drops the row without
  applying — the change becomes permanent).

Holds are booked only inside a *manual* activation: an auto rule or a menu move
applies nothing anyone can take back. The activation context threads from the
engine through `EffectRegistry.apply` into the booking helpers, so the rows a
rule books are attributed to it (`source_sfx_id`) — which is also what lets the
commit sweeps find them.

## Ending an activation

`end_activation(repo, entity_id, sfx_id)` — reached from the sheet's chip
(`POST /api/v1/effects/end`) and, in authorable form, from the **End Active
Effect** action:

1. Apply every remaining row's stored effect in **reverse order of application**
   (a later effect may depend on an earlier one), newest first.
2. Drop the rows it never reached (a deferred part that has not fired never will).
3. Un-arm anything still waiting on a roll (`roll_deferral.drop_armed`).

`End Active Effect` itself means *end the effect*: a revert/hold row's undo is
applied on the spot, a deferred forward row is dropped. (It used to delete the
row without applying — which made a temporary change permanent, the opposite of
what its label promises. No content used it, so the semantics were corrected.)

## The pool is the ledger

Removing a rule's die from the pool before it commits *is* taking the rule back:
the benefit is held by the cost, so if the cost leaves the table the benefit goes
with it. `fire_pool_change_sfx` checks every save — for each **manual** rule in
flight for the entity that had dice in the saved pool, if none of them survives,
the activation is ended (its undos applied, its waiting parts dropped) and an
`sfx_ended` event tells the table — a toast, and the sheet re-derives its chips.
(An SSE event is invisible until the client subscribes to it; `sfx_ended` lives
in `useSSE.js`'s allow-list beside `sfx_triggered`.)

Which dice are a rule's is answered by evidence already in the data: a die the
client added while the rule was active carries it in `armed_sfx_ids`; a pool add
an *effect* performed records its dice in the rule's own undo row
(`pool_add.entries`); and the row itself records **the trait instance the rule
lived on** — its declared source, `activation_source` — so a die from that source
is attributed with no client stamp at all. A rule that contributed no dice is
untouched — it has no cost here to lose. The undo itself removes by **identity at
the recorded position** (falling back to where the die moved), so a pool that
shifted under the player's hands cannot make it remove a stranger.

The honest boundary: the server sees saves and rolls, not the screen. This is the
rules *noticing*, never preventing — and it reads as a feature, because dropping
the die is simply how a player takes Hinder back.

## One reversal, and it is booked

The money side has one mechanism, deliberately: an activation's economy effects
book their undo (`book_undo`, in `effects_applier/reverts.py` — the one home,
called by both the registry's razmerit operations and the applier's earn/spend
handlers, because production runs the former and tests the latter). The legacy
`{reverse: true}` trigger branch that predated it was **retired** — it reversed
an earn a second time once the generic take-back existed, and two reversal
mechanisms can only disagree.

A take-back survives an undo it cannot apply — a refund the balance can no longer
cover (the razmerit was spent elsewhere), a target that is gone. That row is
logged, counted as `failed` in the summary, and the rest of the take-back
proceeds: the change happened, it just could not be paid back.

## What a take-back can and cannot undo

Reversibility is a **declaration on the action**, not something each rule has to
build: the registry's `inverse` pair, the same one the undo timers read
(`build_revert`). Costs are ordinary effects, so they are reversible like
anything else once declared — `earn`/`spend` razmerit invert (the refund), and a
pool add inverts by removing exactly the dice it appended (the handler records
their positions; `modify_pool/remove_added_dice` pops them newest first).

The rest is honest about itself:

- **`transfer_razmerit` has no inverse.** A faithful undo needs the two sides
  swapped, which the declarative builder cannot express. It stays un-invertible
  rather than wrong.
- **Effects that are moments, not state** — a roll resolved, a table opened,
  someone travelled, something was revealed — cannot be un-happened. For those,
  a *commitment gate* is the right authoring tool (put the effect behind the roll
  it should commit to), because the engine will not pretend.
- `validateSfx` names the mixture: a manual rule that can be taken back warns
  which effects a take-back would leave in place — and says nothing when all of
  it is reversible, or none of it is.

## Where it lives

| Concern | Module |
|---------|--------|
| Booking context, holds, commit sweeps, `end_activation`, `in_flight_sfx_ids` | `services/scheduled_events.py` |
| `ScheduledEvent.kind` / `created_at` | `domain/effects.py` |
| The activation context threaded to handlers | `services/effects_engine/engine.py`, `services/effects_applier/registry.py` |
| The commit at the dice | `services/roll_orchestrator.fire_roll_sfx` |
| Un-arming on a take-back | `services/roll_deferral.drop_armed` |
| The chip's take-back state | GraphQL `inFlightSfxIds`, `CharacterSheet.vue`, `useApi.endSfx` |
| The authorable action | `services/effects_applier/handlers_world._apply_cancel_scheduled_event` |

## Related

- [[SFX and Effects]] — the effect model and the duration/scheduled-event store.
- [[Effect Holders and Owners]] — where a rule may live.
- [[SFX Authoring]] — the author-facing view (the "Taking it back" section).
