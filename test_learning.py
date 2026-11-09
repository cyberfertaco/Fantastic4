"""Personas 1 y 3: pruebas del reparto, reflexión observable y memoria histórica."""
import copy
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import RASGOS
from contratos import vista_publica
from personas import generar_personas
from agentes.constructor import armar_equipos, cumple
from agentes.curador import Biblioteca
from agentes.evaluador import evaluar
from agentes.reflexionador import (
    actualizar_perfiles, cargar_politica_skill, evidencia_leccion, sacar_lecciones,
)
from llm import generar_lecciones


def regla(identificador="l1", cantidad=1, operador="min", tipo="creativo"):
    return {"id": identificador, "tipo_proyecto": tipo, "rasgo": "liderazgo",
            "umbral": 4, "operador": operador, "cantidad": cantidad,
            "texto": "Hipótesis de prueba", "veces_vista": 1,
            "veces_aplicada": 0, "veces_ayudo": 0}


def observaciones():
    personas = vista_publica(generar_personas(8, 91))
    for i, persona in enumerate(personas):
        persona["estimado"] = {r: 1.0 for r in RASGOS}
        persona["estimado"]["liderazgo"] = 5.0 if i < 4 else 1.0
    snapshot = {p["id"]: copy.deepcopy(p["estimado"]) for p in personas}
    historial = []
    for i in range(6):
        miembros = personas[:4] if i < 3 else personas[4:]
        historial.append({"id": f"r{i}", "miembros": [p["id"] for p in miembros],
                          "tipo": "creativo", "ronda": i, "score": 80.0 if i < 3 else 40.0,
                          "feedback": {}, "perfiles_observados": copy.deepcopy(snapshot)})
    return personas, historial


class ConstructorTests(unittest.TestCase):
    def test_reparto_aleatorio_reproducible_sin_perdidas(self):
        personas = vista_publica(generar_personas())
        previo = random.getstate()
        equipos = armar_equipos(personas, "creativo", [], semilla=19)
        self.assertEqual(equipos, armar_equipos(personas, "creativo", [], semilla=19))
        esperado = list(personas)
        random.Random(19).shuffle(esperado)
        self.assertEqual([p for e in equipos for p in e], esperado)
        self.assertEqual(random.getstate(), previo)
        self.assertTrue(all(len(e) == 4 for e in equipos))

    def test_busqueda_respeta_lecciones_factibles(self):
        personas = vista_publica(generar_personas())
        for i, persona in enumerate(personas):
            persona["estimado"]["liderazgo"] = 5.0 if i < 6 else 1.0
        leccion = regla()
        equipos = armar_equipos(personas, "creativo", [leccion], semilla=10)
        self.assertTrue(all(cumple(e, leccion) for e in equipos))
        maximo = regla(operador="max")
        self.assertTrue(cumple(equipos[0], maximo))

    def test_rechaza_ocultos_divisibilidad_y_duplicados(self):
        with self.assertRaises(ValueError):
            armar_equipos(generar_personas(), "creativo", [])
        with self.assertRaisesRegex(ValueError, "divisible"):
            armar_equipos(vista_publica(generar_personas(10)), "creativo", [])
        personas = vista_publica(generar_personas(4))
        personas[1]["id"] = personas[0]["id"]
        with self.assertRaises(ValueError):
            armar_equipos(personas, "creativo", [])

    def test_evaluador_solo_entrega_contrato_observable(self):
        personas = generar_personas(8)
        resultados = evaluar([personas[:4], personas[4:]], "tecnico", 1)
        self.assertEqual(resultados, evaluar([personas[:4], personas[4:]], "tecnico", 1))
        for resultado in resultados:
            self.assertEqual(set(resultado), {"miembros", "tipo", "ronda", "score", "feedback"})
            self.assertEqual(set(resultado["feedback"]), set(resultado["miembros"]))
        with self.assertRaises(ValueError):
            evaluar([personas[:4], personas[:4]], "tecnico", 1)


class ReflexionTests(unittest.TestCase):
    def test_actualizacion_en_sitio_y_atomica_al_validar(self):
        personas = vista_publica(generar_personas(4))
        persona = personas[0]
        perfil = persona["estimado"]
        previo = copy.deepcopy(personas)
        feedback = {p["id"]: {r: 3.0 for r in RASGOS} for p in personas}
        resultados = [{"miembros": list(feedback), "feedback": feedback}]
        actualizar_perfiles(personas, resultados, 0.3)
        self.assertIs(personas[0]["estimado"], perfil)
        for i, p in enumerate(personas):
            self.assertEqual(p["declarado"], previo[i]["declarado"])
            for rasgo in RASGOS:
                self.assertAlmostEqual(p["estimado"][rasgo], 0.7 * previo[i]["estimado"][rasgo] + 0.3 * 3)
        copia = copy.deepcopy(personas)
        feedback[personas[-1]["id"]]["creatividad"] = 99
        with self.assertRaises(ValueError):
            actualizar_perfiles(personas, resultados)
        self.assertEqual(personas, copia)

    def test_extrae_asociaciones_solo_con_evidencia_suficiente(self):
        personas, historial = observaciones()
        lecciones = sacar_lecciones(historial, personas, "creativo")
        self.assertEqual({l["cantidad"] for l in lecciones}, {1, 2, 3})
        self.assertTrue(all(l["operador"] == "min" for l in lecciones))
        self.assertTrue(all("No demuestra causalidad" in l["texto"] for l in lecciones))
        self.assertEqual(sacar_lecciones(historial[:5], personas, "creativo"), [])
        for resultado in historial[:3]:
            resultado["score"] = 48.0
        self.assertEqual(sacar_lecciones(historial, personas, "creativo"), [])

    def test_snapshots_conservan_estado_y_retrospectivo_es_explicito(self):
        personas, historial = observaciones()
        leccion = sacar_lecciones(historial, personas, "creativo")[0]
        evidencia = evidencia_leccion(historial, personas, leccion)
        self.assertFalse(evidencia["retrospectivo"])
        self.assertEqual(evidencia["resultados_cumplen"], ["r0", "r1", "r2"])
        for p in personas:
            p["estimado"]["liderazgo"] = 1
        self.assertEqual(evidencia_leccion(historial, personas, leccion), evidencia)
        for resultado in historial:
            resultado.pop("perfiles_observados")
        self.assertTrue(evidencia_leccion(historial, personas, leccion)["retrospectivo"])

    def test_reflexion_y_adaptador_rechazan_ocultos(self):
        with self.assertRaises(ValueError):
            sacar_lecciones([], generar_personas(), "creativo")
        personas, historial = observaciones()
        historial[0]["reglas_ocultas"] = ["secreto"]
        with self.assertRaises(ValueError):
            sacar_lecciones(historial, personas, "creativo")
        with self.assertRaisesRegex(ValueError, "no integrado"):
            generar_lecciones([], personas, "creativo", modo="llm")

    def test_skill_tiene_efecto_en_extraccion(self):
        politica = cargar_politica_skill()
        self.assertEqual(politica["minimo_por_grupo"], 3)
        personas, historial = observaciones()
        with patch("agentes.reflexionador.cargar_politica_skill", return_value={**politica, "minimo_por_grupo": 10}):
            self.assertEqual(sacar_lecciones(historial, personas, "creativo"), [])


class CuradorTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.ruta = Path(self.temporal.name) / "lecciones.json"
        self.biblioteca = Biblioteca(self.ruta)

    def test_identidad_incluye_cantidad_y_booleano_es_nueva(self):
        primera, nueva = self.biblioteca.agregar(regla())
        self.assertTrue(nueva)
        segunda, nueva = self.biblioteca.agregar(regla("otra-id"))
        self.assertFalse(nueva)
        self.assertIs(primera, segunda)
        self.assertEqual(primera["veces_vista"], 2)
        self.assertTrue(self.biblioteca.agregar(regla("cantidad-distinta", 2))[1])
        with self.assertRaises(ValueError):
            self.biblioteca.agregar(regla("l1", 3))
        self.assertEqual(len(self.biblioteca.lecciones), 2)

    def test_ayuda_usa_historial_previo_y_persiste(self):
        leccion, _ = self.biblioteca.agregar(regla())
        self.biblioteca.registrar_uso([leccion], [{"tipo": "creativo", "score": 100}])
        self.assertEqual(leccion["veces_ayudo"], 0)
        self.biblioteca.registrar_uso([leccion], [{"tipo": "creativo", "score": 0}])
        self.assertEqual(leccion["veces_ayudo"], 0)
        self.biblioteca.registrar_uso([leccion], [{"tipo": "creativo", "score": 50}])
        self.assertEqual(leccion["veces_ayudo"], 1)  # Igual al promedio previo de 50.
        self.biblioteca.agregar_evidencia(leccion["id"], {"resultados": ["r1"]})
        self.biblioteca.guardar()
        recargada = Biblioteca(self.ruta)
        self.assertEqual(recargada.historial, self.biblioteca.historial)
        self.assertEqual(recargada.evidencias, self.biblioteca.evidencias)
        self.assertEqual(recargada.lecciones, self.biblioteca.lecciones)
        self.assertNotIn("evidencias", recargada.lecciones[0])

    def test_poda_y_relevancia(self):
        leccion, _ = self.biblioteca.agregar(regla())
        todos, _ = self.biblioteca.agregar(regla("todos", tipo="todos"))
        self.assertEqual(self.biblioteca.relevantes("tecnico"), [todos])
        for score in (100, 50, 0):
            self.biblioteca.registrar_uso([leccion], [{"tipo": "creativo", "score": score}])
        self.biblioteca.podar()
        self.assertEqual(self.biblioteca.lecciones, [todos])


if __name__ == "__main__":
    unittest.main()
