"""Fog-of-war trait reveal.

A ``TraitSetting.known_to`` list records which entity ids know about that
trait instance.  Knowledge is monotonic: once a character has seen a trait used
it stays revealed.  This module holds the single low-level operation used by
every reveal path (dice-pool observation, spying SFX effects, and future
content) so they can never drift apart.
"""

from __future__ import annotations

from typing import Optional


def reveal_trait_to(ts, learner_id: str) -> bool:
    """Append ``learner_id`` to a trait setting's ``known_to`` (idempotent).

    Returns True when the learner was newly added (a real reveal); False when
    they already knew it.  Fog of war is monotonic — knowledge is never removed
    here.
    """
    if not learner_id:
        return False
    if learner_id in ts.known_to:
        return False
    ts.known_to = [*ts.known_to, learner_id]
    return True


def trait_setting_ids_from_pool(dice: list[dict]) -> list[str]:
    """Return the de-duplicated trait-setting ids a saved dice pool references."""
    ids: list[str] = []
    seen: set[str] = set()
    for d in dice or []:
        if d.get("source_kind") != "trait":
            continue
        ts_id = d.get("ts_id") or d.get("source_id") or ""
        if ts_id and ts_id not in seen:
            seen.add(ts_id)
            ids.append(ts_id)
    return ids


def reveal_pool_traits(
    repo,
    location_id: str,
    owner_id: str,
) -> tuple[list[str], list[str]]:
    """Reveal every trait in ``owner_id``'s pool at ``location_id``.

    Everyone currently at the location learns each trait in the pool (the pool
    owner included — they aren't necessarily the trait owner, e.g. an offered
    negative trait).  Returns ``(changed_trait_setting_ids, learner_ids)``.
    """
    from transversal.services.scene_state import get_scene_store

    dice = get_scene_store().get_pool(location_id, owner_id)
    ts_ids = trait_setting_ids_from_pool(dice)
    if not ts_ids:
        return [], []

    learner_ids = [e.id for e in repo.list_entities_by_location(location_id)]
    if not learner_ids:
        return [], []

    changed: list[str] = []
    reveals: list[tuple] = []  # (trait setting, learner_id)
    for ts_id in ts_ids:
        ts = repo.get_traitsetting(ts_id)
        if ts is None:
            continue
        modified = False
        for learner_id in learner_ids:
            if reveal_trait_to(ts, learner_id):
                modified = True
                reveals.append((ts, learner_id))
        if modified:
            repo.update_traitsetting(ts)
            changed.append(ts_id)

    for ts, learner_id in reveals:
        fire_on_trait_learn(ts.entity_id, learner_id, ts.trait_id, ts.id)

    return changed, learner_ids


def fire_on_trait_learn(owner_id: str, learner_id: str, trait_id: str, trait_setting_id: str) -> None:
    """Fire ``on_trait_learn`` for the learner of a newly-revealed trait."""
    from transversal.services.state_events import fire_state_sfx

    fire_state_sfx(
        learner_id,
        "",
        "on_trait_learn",
        {
            "trait_id": trait_id,
            "trait_setting_id": trait_setting_id,
            "owner": owner_id,
            "learner": learner_id,
        },
    )
