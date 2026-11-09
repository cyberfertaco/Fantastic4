"""Persona 2: integridad, aislamiento y continuidad de la persistencia SQLite."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from almacenamiento import Almacen
from evolucion.motor import estrategia_inicial


def decision(parent, candidate, identifier="d1"):
    return {"schema_version": 1, "id": identifier, "proposal_id": "p1",
            "parent_id": parent["id"], "candidate_id": candidate["id"],
            "accepted": False, "reasons": ["Prueba de almacenamiento"],
            "comparison": {}, "checks": {}, "observed_state": {},
            "created_at": "2026-11-09T00:00:00+00:00", "owner": "Persona 1"}


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "state.sqlite3"
        self.store = Almacen(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_batches_append_unique_ids_duplicates_and_reopen(self):
        first = self.store.registrar_lote(10, 9)
        second = self.store.registrar_lote(10, 9)
        self.assertEqual(second["duplicate_attributes"], 10)
        self.assertFalse(set(p["id"] for p in first["personas"]) & set(p["id"] for p in second["personas"]))
        reopened = Almacen(self.path)
        self.assertEqual(reopened.personas_lote(first["id"]), first["personas"])
        self.assertEqual(len(reopened.listar_lotes()), 2)
        self.assertNotIn("personas", reopened.listar_lotes()[0])

    def test_requested_batch_sizes_and_rejected_input_do_not_destroy_records(self):
        for size in (10, 50, 100, 500):
            result = self.store.registrar_lote(size, size)
            self.assertEqual(len(result["personas"]), size)
        before = self.store.listar_lotes()
        for size in (-1, 0, True, 1.5, 10_001):
            with self.assertRaises(ValueError):
                self.store.registrar_lote(size, 42)
        self.assertEqual(self.store.listar_lotes(), before)

    def test_versions_are_immutable_active_reference_can_roll_back(self):
        initial = estrategia_inicial()
        self.store.guardar_experimento("run", {"schema_version": 1})
        self.store.guardar_version(initial)
        self.store.guardar_version(initial)
        candidate = deepcopy(initial)
        candidate["id"] = "candidate-v1"
        candidate["parent_id"] = initial["id"]
        candidate["parameters"]["weights"] = {"lessons": 1.0, "balance": 0.0}
        self.store.guardar_version(candidate)
        altered = deepcopy(initial)
        altered["parameters"]["weights"] = {"lessons": .5, "balance": .5}
        with self.assertRaisesRegex(ValueError, "inmutable"):
            self.store.guardar_version(altered)
        self.store.activar_version("run", candidate["id"])
        self.store.activar_version("run", initial["id"])
        self.assertEqual(Almacen(self.path).version_activa("run"), initial)
        self.assertEqual(len(self.store.listar_versiones()), 2)

    def test_reset_is_scoped_export_reads_db_and_rejections_persist(self):
        initial = estrategia_inicial()
        self.store.guardar_version(initial)
        batch = self.store.registrar_lote(10, 42)
        for experiment in ("one", "other"):
            self.store.guardar_experimento(experiment, {"schema_version": 1, "mode": "determinista"})
            self.store.activar_version(experiment, initial["id"])
            self.store.guardar_evidencia(experiment, {"id": "e1", "score": 30})
            self.store.guardar_decision(experiment, decision(initial, initial))
        self.store.reiniciar_experimento("one")
        self.assertIsNone(self.store.cargar_experimento("one"))
        self.assertEqual(self.store.listar_evidencias("one"), [])
        self.assertEqual(self.store.listar_decisiones("one"), [])
        self.assertEqual(self.store.personas_lote(batch["id"]), batch["personas"])
        self.assertEqual(self.store.listar_versiones(), [initial])
        target = self.root / "evolution.json"
        self.store.exportar_experimento("other", target)
        result = json.loads(target.read_text())
        self.assertFalse(result["decisions"][0]["accepted"])
        self.assertEqual(result["evidence"], [{"id": "e1", "score": 30}])
        self.assertEqual(result["active_version"], initial)
        self.assertEqual(result["experiment_id"], "other")
        self.assertIn("updated_at", result)

    def test_failed_activation_rolls_back_and_evidence_does_not_silently_change(self):
        self.store.guardar_experimento("run", {})
        initial = estrategia_inicial()
        self.store.guardar_version(initial)
        self.store.activar_version("run", initial["id"])
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.activar_version("run", "unknown")
        self.assertEqual(self.store.version_activa("run"), initial)
        self.store.guardar_evidencia("run", {"id": "e", "score": 5})
        with self.assertRaisesRegex(ValueError, "inmutable"):
            self.store.guardar_evidencia("run", {"id": "e", "score": 99})
        self.assertEqual(self.store.listar_evidencias("run"), [{"id": "e", "score": 5}])


if __name__ == "__main__":
    unittest.main()
