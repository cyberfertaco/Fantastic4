"""Persona 2: manifiesto fijo, unidad experimental y frontera del evaluador."""
from copy import deepcopy
import random
import unittest
from unittest.mock import patch

from benchmark import POLICY, comparar, crear_manifiesto, evaluar_estrategia
from config import TIPOS_PROYECTO
from contratos import huella
from evolucion.motor import estrategia_inicial, formar_equipos
from simulador import FORMULA_VERSION


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = crear_manifiesto()

    def test_manifest_is_reproducible_disjoint_and_locked_before_candidates(self):
        state = random.getstate()
        self.assertEqual(self.manifest, crear_manifiesto())
        self.assertEqual(state, random.getstate())
        self.assertEqual(self.manifest["formula_version"], FORMULA_VERSION)
        self.assertEqual(self.manifest["policy"], POLICY)
        blocks = [block for cycle in self.manifest["cycles"] for block in (cycle["discovery"], cycle["validation"])]
        blocks.append(self.manifest["final"])
        ids, seeds, people = set(), set(), set()
        for block in blocks:
            self.assertEqual(len(block), 15)
            for tipo in TIPOS_PROYECTO:
                self.assertEqual(sum(s["tipo"] == tipo for s in block), 5)
            for scenario in block:
                self.assertNotIn(scenario["id"], ids)
                self.assertNotIn(scenario["semilla"], seeds)
                ids.add(scenario["id"])
                seeds.add(scenario["semilla"])
                for person in scenario["personas"]:
                    self.assertNotIn(person["id"], people)
                    people.add(person["id"])

    def test_split_names_match_validator_and_scenario_inputs_are_unchanged(self):
        scenarios = []
        for cycle in self.manifest["cycles"]:
            for split in ("discovery", "validation"):
                self.assertTrue(all(s["split"] == split for s in cycle[split]))
                scenarios.extend(cycle[split])
        self.assertTrue(all(s["split"] == "final" for s in self.manifest["final"]))
        scenarios.extend(self.manifest["final"])
        # Huella previa al arreglo de metadatos: protege IDs, semillas y las
        # poblaciones congeladas de cambios accidentales o selección posterior.
        frozen_inputs = [{k: v for k, v in s.items() if k != "split"} for s in scenarios]
        self.assertEqual(huella(frozen_inputs), "2b0421ac4e8ae409f0b8fb95c93ff4e3366699587adc12f2de435904d35d1f7a")

    def test_manifest_validation_block_reaches_fixed_evaluator(self):
        from evolucion.validador import validar
        initial = estrategia_inicial()
        candidate = deepcopy(initial)
        candidate["id"] = "equal-candidate"
        candidate["parent_id"] = initial["id"]
        proposal = {"schema_version": 1, "id": "equal-proposal",
                    "parent_id": initial["id"], "strategy": candidate,
                    "evidence_ids": [], "case_ids": [], "owner": "Persona 3"}
        decision = validar(proposal, initial, self.manifest["cycles"][0]["validation"], [], [], {})
        self.assertTrue(decision["checks"]["validation_scenarios"])
        self.assertEqual(decision["comparison"]["n"], 15)
        self.assertEqual(decision["comparison"]["delta"], 0)
        self.assertFalse(decision["accepted"])

    def test_identical_strategy_is_zero_delta_and_population_stays_frozen(self):
        scenarios = self.manifest["cycles"][0]["validation"][::5]
        initial = estrategia_inicial()
        fingerprint = huella(scenarios)
        result = comparar(initial, initial, scenarios, [])
        self.assertEqual(result["n"], 3)
        self.assertEqual(result["delta"], 0)
        self.assertEqual(result["paired_stdev"], 0)
        self.assertEqual(set(result["by_type"]), set(TIPOS_PROYECTO))
        self.assertEqual(fingerprint, huella(scenarios))

    def test_motor_receives_no_hidden_field_and_cannot_mutate_snapshot(self):
        scenarios = self.manifest["cycles"][0]["validation"][:1]
        snapshot = deepcopy(scenarios)
        seen = []

        def inspect(public, *args, **kwargs):
            self.assertTrue(all("real" not in person for person in public))
            seen.extend(person["id"] for person in public)
            return formar_equipos(public, *args, **kwargs)

        with patch("evolucion.motor.formar_equipos", side_effect=inspect):
            summary = evaluar_estrategia(estrategia_inicial(), scenarios, [])
        self.assertEqual(len(seen), 24)
        self.assertEqual(summary["n"], 1)
        self.assertEqual(summary["stdev"], 0)
        self.assertEqual(scenarios, snapshot)

    def test_budget_mismatch_is_rejected_before_comparison(self):
        initial = estrategia_inicial()
        candidate = deepcopy(initial)
        candidate["search_budget"] = 299
        with self.assertRaisesRegex(ValueError, "presupuestos"):
            comparar(initial, candidate, self.manifest["final"], [])
        with self.assertRaisesRegex(ValueError, "300"):
            evaluar_estrategia(candidate, self.manifest["final"], [])

    def test_duplicate_or_missing_participants_are_rejected(self):
        scenarios = self.manifest["cycles"][0]["validation"][:1]
        def broken(public, *args, **kwargs):
            return [public[:4]] * 6
        with patch("evolucion.motor.formar_equipos", side_effect=broken):
            with self.assertRaisesRegex(ValueError, "duplicar"):
                evaluar_estrategia(estrategia_inicial(), scenarios, [])


if __name__ == "__main__":
    unittest.main()
