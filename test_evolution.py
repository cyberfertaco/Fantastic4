"""Persona 1/3: aislamiento, motor, regresiones y controles de aceptación."""
from copy import deepcopy
import random
import unittest
from unittest.mock import patch

from config import RASGOS, TIPOS_PROYECTO
from contratos import vista_publica
from evolucion.builder import proponer
from evolucion.motor import contar_incumplimientos, estrategia_inicial, formar_equipos
from evolucion.validador import ejecutar_caso, validar


def fixture():
    personas = []
    for i in range(24):
        perfil = {r: 2 for r in RASGOS}
        perfil["creatividad"] = 5 if i < 12 else 1
        personas.append({"id": f"p{i}", "nombre": f"Persona {i}",
                         "declarado": dict(perfil), "estimado": dict(perfil)})
    leccion = {"id": "l-creatividad", "tipo_proyecto": "creativo", "rasgo": "creatividad",
               "umbral": 4, "operador": "min", "cantidad": 3,
               "texto": "Hipótesis de prueba: concentrar tres perfiles creativos",
               "veces_vista": 1, "veces_aplicada": 0, "veces_ayudo": 0}
    evidencia = {"id": "e-test", "tipo": "creativo", "semilla": 19,
                 "personas": personas, "lecciones": [leccion],
                 "equipos": [[p["id"] for p in equipo] for equipo in formar_equipos(
                     personas, "creativo", [leccion], estrategia_inicial(), semilla=19)],
                 "resultados": [], "strategy_id": estrategia_inicial()["id"]}
    return personas, leccion, evidencia


def escenarios_test():
    personas, _, _ = fixture()
    completas = [dict(deepcopy(p), real=deepcopy(p["declarado"])) for p in personas]
    return [{"id": f"v-{tipo}-{i}", "tipo": tipo, "split": "validation",
             "semilla": i, "personas": deepcopy(completas)}
            for tipo in TIPOS_PROYECTO for i in range(5)]


def comparacion(delta=3, delta_tipo=None):
    return {"n": 15, "before": {"n": 15, "mean": 50, "stdev": 4},
            "after": {"n": 15, "mean": 50 + delta, "stdev": 4},
            "delta": delta, "paired_stdev": 1.0,
            "by_type": {tipo: {"before": 50, "after": 50 + (delta_tipo or {}).get(tipo, delta),
                               "delta": (delta_tipo or {}).get(tipo, delta), "n": 5}
                        for tipo in TIPOS_PROYECTO}}


class EvolutionTests(unittest.TestCase):
    def test_motor_exact_reproducible_and_rng_local(self):
        personas, leccion, _ = fixture()
        before = deepcopy(personas)
        rng = random.getstate()
        a = formar_equipos(personas, "creativo", [leccion], estrategia_inicial(), semilla=19)
        b = formar_equipos(personas, "creativo", [leccion], estrategia_inicial(), semilla=19)
        self.assertEqual(a, b)
        self.assertEqual(before, personas)
        self.assertEqual(rng, random.getstate())
        self.assertEqual(sorted(p["id"] for e in a for p in e), sorted(p["id"] for p in personas))
        self.assertTrue(all(len(e) == 4 for e in a))
        with self.assertRaisesRegex(ValueError, "divisible"):
            formar_equipos(personas[:10], "creativo", [], estrategia_inicial())

    def test_hidden_data_rejected_at_motor_and_builder(self):
        personas, leccion, evidencia = fixture()
        personas[0]["real"] = deepcopy(personas[0]["declarado"])
        with self.assertRaises(ValueError):
            formar_equipos(personas, "creativo", [], estrategia_inicial())
        with self.assertRaises(ValueError):
            proponer(estrategia_inicial(), [evidencia], [leccion])
        evidencia["personas"] = vista_publica(personas)
        evidencia["split"] = "final"
        with self.assertRaises(ValueError):
            proponer(estrategia_inicial(), [evidencia], [leccion])

    def test_builder_and_case_detect_reproducible_previous_failure(self):
        personas, leccion, evidencia = fixture()
        original = deepcopy(evidencia)
        anterior = estrategia_inicial()
        propuestas, casos = proponer(anterior, [evidencia], [leccion])
        self.assertEqual(3, len(propuestas))
        self.assertTrue(casos)
        self.assertEqual(evidencia, original)
        self.assertFalse(ejecutar_caso(casos[0], anterior)["passed"])
        self.assertTrue(any(ejecutar_caso(casos[0], p["strategy"])["passed"] for p in propuestas))
        for p in propuestas:
            self.assertEqual(300, p["strategy"]["search_budget"])
            self.assertEqual(["e-test"], p["evidence_ids"])
        self.assertEqual((propuestas, casos), proponer(anterior, [evidencia], [leccion]))

    def test_cases_require_same_observed_partition(self):
        _, leccion, evidencia = fixture()
        anterior = estrategia_inicial()
        propuestas, casos = proponer(anterior, [evidencia], [leccion])
        self.assertTrue(casos)
        distinta = deepcopy(evidencia)
        distinta["equipos"][0][0], distinta["equipos"][1][0] = (
            distinta["equipos"][1][0], distinta["equipos"][0][0])
        propuestas_distintas, casos_distintos = proponer(anterior, [distinta], [leccion])
        self.assertEqual([], casos_distintos)
        self.assertTrue(all(not p["case_ids"] for p in propuestas_distintas))
        self.assertEqual([p["strategy"] for p in propuestas],
                         [p["strategy"] for p in propuestas_distintas])
        reordenada = deepcopy(evidencia)
        reordenada["equipos"] = [list(reversed(e)) for e in reversed(evidencia["equipos"])]
        self.assertEqual((propuestas, casos), proponer(anterior, [reordenada], [leccion]))

    def test_acceptance_and_empirical_rejection_fixed_policy(self):
        _, leccion, evidencia = fixture()
        anterior = estrategia_inicial()
        propuestas, casos = proponer(anterior, [evidencia], [leccion])
        propuesta = next(p for p in propuestas if all(ejecutar_caso(c, p["strategy"])["passed"] for c in casos))
        escenarios = escenarios_test()
        before = deepcopy((propuesta, anterior, escenarios, [leccion], casos))
        with patch("evolucion.validador.comparar", return_value=comparacion(3)):
            decision = validar(propuesta, anterior, escenarios, [leccion], casos, {"cycle": 1})
        self.assertTrue(decision["accepted"], decision["reasons"])
        self.assertEqual(before, (propuesta, anterior, escenarios, [leccion], casos))
        with patch("evolucion.validador.comparar", return_value=comparacion(1.9)):
            self.assertFalse(validar(propuesta, anterior, escenarios, [leccion], casos, {})["accepted"])
        with patch("evolucion.validador.comparar", return_value=comparacion(3, {"tecnico": -2.01})):
            self.assertFalse(validar(propuesta, anterior, escenarios, [leccion], casos, {})["accepted"])

    def test_invalid_strategy_rejects_without_external_evaluation(self):
        _, leccion, evidencia = fixture()
        anterior = estrategia_inicial()
        propuestas, casos = proponer(anterior, [evidencia], [leccion])
        mala = deepcopy(propuestas[0])
        mala["strategy"]["parameters"]["weights"] = {"lessons": -1, "balance": 2}
        with patch("evolucion.validador.comparar") as comparar_mock:
            decision = validar(mala, anterior, escenarios_test(), [leccion], casos, {"mechanism_test": True})
        self.assertFalse(decision["accepted"])
        self.assertFalse(decision["checks"]["contracts"])
        comparar_mock.assert_not_called()

    def test_unequal_budget_and_small_validation_are_rejected(self):
        _, leccion, evidencia = fixture()
        anterior = estrategia_inicial()
        propuestas, casos = proponer(anterior, [evidencia], [leccion])
        mala = deepcopy(propuestas[0])
        mala["strategy"]["search_budget"] = 301
        with patch("evolucion.validador.comparar") as comparar_mock:
            decision = validar(mala, anterior, escenarios_test(), [leccion], casos, {})
        self.assertFalse(decision["accepted"])
        comparar_mock.assert_not_called()
        with patch("evolucion.validador.comparar") as comparar_mock:
            decision = validar(propuestas[0], anterior, escenarios_test()[:4], [leccion], casos, {})
        self.assertFalse(decision["accepted"])
        comparar_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
