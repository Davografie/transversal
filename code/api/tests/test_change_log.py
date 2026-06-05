"""Tests for the change log and wired services."""

import pytest

from transversal.services.change_log import ChangeLog, Mutation


class TestChangeLog:
    def test_record_and_count(self):
        log = ChangeLog()
        log.record("e1", "razmerit", 5, 3, "s1")
        assert log.count() == 1

    def test_undo_last(self):
        log = ChangeLog()
        log.record("e1", "razmerit", 5, 3, "s1")
        log.record("e1", "razmerit", 3, 1, "s1")
        assert log.count() == 2

        undone = log.undo_last("e1", "s1")
        assert undone is not None
        assert undone.old_value == 3
        assert undone.new_value == 1
        assert log.count() == 1

    def test_undo_last_session_scoped(self):
        log = ChangeLog()
        log.record("e1", "razmerit", 5, 3, "s1")
        log.record("e1", "razmerit", 3, 1, "s2")

        # Undo from s1 should only get the s1 mutation
        undone = log.undo_last("e1", "s1")
        assert undone is not None
        assert undone.session_id == "s1"
        assert log.count() == 1

        # s2 mutation still there
        undone = log.undo_last("e1", "s2")
        assert undone is not None
        assert undone.session_id == "s2"
        assert log.count() == 0

    def test_undo_entity(self):
        log = ChangeLog()
        log.record("e1", "razmerit", 5, 3, "s1")
        log.record("e1", "trait.hacking", "d8", "d10", "s1")
        log.record("e2", "razmerit", 10, 8, "s1")
        assert log.count() == 3

        undone = log.undo_entity("e1", "s1")
        assert len(undone) == 2
        assert log.count() == 1  # e2 still there

    def test_undo_empty(self):
        log = ChangeLog()
        assert log.undo_last("nonexistent") is None
        assert log.undo_entity("nonexistent") == []

    def test_mutations_for(self):
        log = ChangeLog()
        log.record("e1", "razmerit", 5, 3, "s1")
        log.record("e1", "trait", "d6", "d8", "s1")
        log.record("e2", "razmerit", 3, 1, "s1")

        e1_muts = log.mutations_for("e1")
        assert len(e1_muts) == 2

    def test_clear(self):
        log = ChangeLog()
        log.record("e1", "razmerit", 5, 3)
        log.clear()
        assert log.count() == 0

    def test_sequence(self):
        log = ChangeLog()
        m1 = log.record("e1", "f", 1, 2)
        m2 = log.record("e1", "f", 2, 3)
        assert m1.sequence == 1
        assert m2.sequence == 2


class TestChangeLogIntegration:
    """Test that services actually record mutations."""

    def test_razmerit_spend_records_change(self):
        from transversal.services.razmerit import RazmeritService
        from tests.test_entity_manager import InMemoryRepository
        from transversal.services.entity_manager import EntityManager
        from transversal.domain import EntityType

        repo = InMemoryRepository()
        em = EntityManager(repository=repo)
        raz = RazmeritService(repository=repo)
        kael = em.create("Kael", EntityType.CHARACTER, "earth", razmerit=5)

        from transversal.services.change_log import change_log
        change_log.clear()

        raz.spend(kael.id, 2, session_id="test-session")
        assert change_log.count() == 1
        m = change_log.mutations_for(kael.id)[0]
        assert m.field == "razmerit"
        assert m.old_value == 5
        assert m.new_value == 3

    def test_step_up_records_change(self):
        from tests.test_entity_manager import InMemoryRepository
        from transversal.services.entity_manager import EntityManager
        from transversal.domain import EntityType, DieType, RatingType, TraitSetting

        repo = InMemoryRepository()
        em = EntityManager(repository=repo)
        kael = em.create("Kael", EntityType.CHARACTER, "earth")

        ts = TraitSetting(
            id=f"{kael.id}:hacking", entity_id=kael.id, trait_id="t-hack",
            traitset_id="ts-skills", die_type=DieType.D6,
            rating_type=RatingType.STATIC, rating="d6",
        )
        em.add_traitsetting(ts)

        from transversal.services.change_log import change_log
        change_log.clear()

        em.step_up_trait(ts, session_id="test")
        assert change_log.count() == 1
