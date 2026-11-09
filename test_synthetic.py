"""Persona 2: contratos, sesgos, RNG y persistencia del mundo sintético."""
import copy
import random
import tempfile
import unittest
from pathlib import Path

from config import RASGOS, TIPOS_PROYECTO
from personas import cargar, generar_personas, guardar
from simulador import FORMULA_VERSION, REGLAS_OCULTAS, simular


class PersonasTests(unittest.TestCase):
    def test_exact_contract_and_bias_counts(self):
        personas = generar_personas()
        self.assertEqual(24, len(personas))
        counts = {"over": 0, "under": 0, "faithful": 0}
        for p in personas:
            self.assertEqual({"id", "nombre", "declarado", "real", "estimado"}, set(p))
            self.assertEqual(p["declarado"], p["estimado"])
            self.assertIsNot(p["declarado"], p["estimado"])
            differences = [p["declarado"][r] - p["real"][r] for r in RASGOS]
            counts["over" if max(differences) > 0 else "under" if min(differences) < 0 else "faithful"] += 1
            for profile in ("declarado", "real", "estimado"):
                self.assertEqual(set(RASGOS), set(p[profile]))
                self.assertTrue(all(type(v) is int and 1 <= v <= 5 for v in p[profile].values()))
        self.assertEqual({"over": 8, "under": 4, "faithful": 12}, counts)
        self.assertEqual(24, len({p["id"] for p in personas}))

    def test_reproducible_independent_rng(self):
        state = random.getstate()
        first = generar_personas(50, 7)
        self.assertEqual(first, generar_personas(50, 7))
        self.assertNotEqual(first, generar_personas(50, 8))
        self.assertEqual(state, random.getstate())

    def test_sizes_and_validation(self):
        for n in (10, 50, 100, 500):
            with self.subTest(n=n):
                self.assertEqual(n, len(generar_personas(n, 3)))
        for n in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                generar_personas(n)

    def test_json_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            ruta = Path(directory) / "nested" / "personas.json"
            personas = generar_personas()
            guardar(personas, ruta)
            self.assertEqual(personas, cargar(ruta))


class SimuladorTests(unittest.TestCase):
    def test_contract_range_reproducibility_and_no_mutation(self):
        equipo = generar_personas()[:4]
        original = copy.deepcopy(equipo)
        state = random.getstate()
        for tipo in TIPOS_PROYECTO:
            result = simular(equipo, tipo, 8)
            self.assertEqual(result, simular(equipo, tipo, 8))
            self.assertEqual(result, simular(list(reversed(equipo)), tipo, 8))
            self.assertEqual({"score", "feedback"}, set(result))
            self.assertIsInstance(result["score"], float)
            self.assertTrue(0 <= result["score"] <= 100)
            self.assertEqual({p["id"] for p in equipo}, set(result["feedback"]))
            for profile in result["feedback"].values():
                self.assertEqual(set(RASGOS), set(profile))
                self.assertTrue(all(isinstance(v, float) and 1 <= v <= 5 for v in profile.values()))
        self.assertEqual(original, equipo)
        self.assertEqual(state, random.getstate())

    def test_score_uses_real_not_estimated(self):
        equipo = generar_personas()[:4]
        altered = copy.deepcopy(equipo)
        for p in altered:
            p["estimado"] = {r: 1.0 for r in RASGOS}
            p["declarado"] = {r: 5 for r in RASGOS}
        self.assertEqual(simular(equipo, "creativo", 3), simular(altered, "creativo", 3))

    def test_known_interaction_and_invalid_inputs(self):
        equipo = generar_personas(4)
        for p in equipo:
            p["real"] = {r: 2 for r in RASGOS}
        better = copy.deepcopy(equipo)
        better[0]["real"]["creatividad"] = 4
        better[1]["real"]["creatividad"] = 4
        self.assertGreater(simular(better, "creativo", 0)["score"] - simular(equipo, "creativo", 0)["score"], 30)
        with self.assertRaises(ValueError):
            simular(equipo, "desconocido", 1)
        with self.assertRaises(ValueError):
            simular([], "creativo", 1)
        self.assertTrue(FORMULA_VERSION)
        self.assertTrue(all(isinstance(rule, str) for rule in REGLAS_OCULTAS))


if __name__ == "__main__":
    unittest.main()
