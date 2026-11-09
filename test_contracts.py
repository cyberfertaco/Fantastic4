"""Persona 1: esquemas cerrados, valores finitos y copias sin datos ocultos."""
from copy import deepcopy
import unittest
from contratos import (huella, validar_estrategia, validar_personas,
                       validar_propuesta, vista_publica)
from evolucion.motor import estrategia_inicial
from personas import generar_personas


class ContractTests(unittest.TestCase):
    def test_public_view_is_independent_and_rejects_unknown_fields(self):
        people = generar_personas()
        before = deepcopy(people)
        public = vista_publica(people)
        self.assertNotIn("real", public[0])
        public[0]["estimado"]["liderazgo"] = 1.5
        self.assertEqual(before, people)
        people[0]["secret_extra"] = "x"
        with self.assertRaises(ValueError):
            vista_publica(people)

    def test_person_ids_and_numeric_profiles_cannot_silently_coerce(self):
        people = generar_personas()
        people[1]["id"] = people[0]["id"]
        with self.assertRaises(ValueError):
            validar_personas(people)
        for value in (float("nan"), float("inf"), True, 0, 6):
            people = generar_personas()
            people[0]["estimado"]["creatividad"] = value
            with self.assertRaises(ValueError):
                validar_personas(people)

    def test_weights_are_finite_normalized_and_fields_closed(self):
        for weights in ({"lessons": -1, "balance": 2}, {"lessons": .3, "balance": .3},
                        {"lessons": float("nan"), "balance": 1}):
            strategy = estrategia_inicial()
            strategy["parameters"]["weights"] = weights
            with self.assertRaises(ValueError):
                validar_estrategia(strategy)
        strategy = estrategia_inicial()
        strategy["parameters"]["executable"] = "code"
        with self.assertRaises(ValueError):
            validar_estrategia(strategy)

    def test_proposal_parent_is_consistent_and_hash_canonical(self):
        strategy = estrategia_inicial()
        strategy["parent_id"] = "parent-a"
        proposal = {"schema_version": 1, "id": "p", "parent_id": "parent-b",
                    "strategy": strategy, "evidence_ids": [], "case_ids": [], "owner": "Persona 3"}
        with self.assertRaises(ValueError):
            validar_propuesta(proposal)
        self.assertEqual(huella({"a": 1, "b": 2}), huella({"b": 2, "a": 1}))


if __name__ == "__main__":
    unittest.main()
