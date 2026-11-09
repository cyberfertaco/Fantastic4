"""Persona 1: contratos end-to-end, aislamiento y consumo único de la reserva."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
import main
from agentes import constructor, reflexionador
from contratos import huella, vista_publica
from personas import generar_personas


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        # ruta_proyecto consulta config.ROOT dinámicamente. El skill es código
        # del proyecto y conserva su ROOT importado, no se copia al almacén temporal.
        self.patch_root = patch.object(config, "ROOT", self.raiz)
        self.patch_root.start()
        self.addCleanup(self.patch_root.stop)

    def assertObservable(self, objeto):
        if isinstance(objeto, dict):
            self.assertFalse({"real", "reglas_ocultas"} & set(objeto))
            for valor in objeto.values():
                self.assertObservable(valor)
        elif isinstance(objeto, (list, tuple)):
            for valor in objeto:
                self.assertObservable(valor)

    def test_demo_reproducible_contrato_baseline_y_fronteras(self):
        entradas_constructor = []
        llamada_constructor = constructor.armar_equipos
        llamada_actualizar = reflexionador.actualizar_perfiles
        llamada_extraer = reflexionador.sacar_lecciones

        def construir(*args, **kwargs):
            self.assertObservable(args)
            entradas_constructor.append(copy.deepcopy(args[0]))
            return llamada_constructor(*args, **kwargs)

        def actualizar(*args, **kwargs):
            self.assertObservable(args)
            return llamada_actualizar(*args, **kwargs)

        def extraer(*args, **kwargs):
            self.assertObservable(args)
            return llamada_extraer(*args, **kwargs)

        with patch.object(constructor, "armar_equipos", side_effect=construir) as constructor_spy, \
                patch.object(reflexionador, "actualizar_perfiles", side_effect=actualizar) as actualizar_spy, \
                patch.object(reflexionador, "sacar_lecciones", side_effect=extraer) as extraer_spy:
            primera = main.ejecutar_demo()
        self.assertEqual(constructor_spy.call_count, 20)
        self.assertEqual(actualizar_spy.call_count, 10)
        self.assertEqual(extraer_spy.call_count, 10)
        self.assertEqual(set(primera), {"con_memoria", "sin_memoria", "personas", "reglas_ocultas"})
        campos = {"ronda", "tipo", "score_promedio", "error_perfiles", "lecciones"}
        for nombre in ("con_memoria", "sin_memoria"):
            self.assertEqual(len(primera[nombre]), 10)
            self.assertEqual(primera[nombre][0]["tipo"], "creativo")
            self.assertEqual([r["ronda"] for r in primera[nombre]], list(range(1, 11)))
            self.assertTrue(all(set(r) == campos for r in primera[nombre]))

        # Cada segunda construcción es la línea base: siempre el mismo perfil
        # declarado inicial, aun cuando la otra rama recibe feedback y aprende.
        iniciales = generar_personas()
        for entrada in entradas_constructor[1::2]:
            self.assertEqual(entrada, vista_publica(iniciales))
        self.assertTrue(any(entrada != vista_publica(iniciales) for entrada in entradas_constructor[2::2]))
        self.assertEqual(len({r["error_perfiles"] for r in primera["sin_memoria"]}), 1)
        self.assertTrue(all(r["lecciones"] == 0 for r in primera["sin_memoria"]))
        trazabilidad = json.loads((self.raiz / "resultados/demo-trazabilidad.json").read_text(encoding="utf-8"))
        self.assertEqual(trazabilidad["baseline_initial_hash"], huella(iniciales))
        self.assertEqual(trazabilidad["baseline_final_hash"], huella(iniciales))
        self.assertEqual(len(trazabilidad["actualizaciones"]), 10)
        for actualizacion in trazabilidad["actualizaciones"]:
            self.assertLessEqual(actualizacion["observed_at"], actualizacion["updated_at"])
        self.assertEqual(primera, json.loads((self.raiz / "resultados/metricas.json").read_text(encoding="utf-8")))
        self.assertEqual(primera, main.ejecutar_demo())

    def test_evolucion_compara_candidatas_y_reserva_una_vez(self):
        import benchmark
        from evolucion import builder, validador
        from simulador import FORMULA_VERSION
        from almacenamiento import Almacen

        propuestas_entradas, comparaciones = [], []
        llamada_proponer = builder.proponer
        llamada_comparar = benchmark.comparar
        policy = copy.deepcopy(benchmark.POLICY)

        def proponer(*args, **kwargs):
            self.assertObservable(args)
            evidencias = args[1]
            self.assertTrue(evidencias)
            self.assertTrue(all(e["split"] == "discovery" for e in evidencias))
            self.assertTrue(all("discovery" in e["id"] for e in evidencias))
            self.assertTrue(all("validation" not in e["id"] and "final" not in e["id"] for e in evidencias))
            propuestas_entradas.append(copy.deepcopy((args, kwargs)))
            return llamada_proponer(*args, **kwargs)

        def comparar(anterior, candidata, escenarios, lecciones):
            congelados = copy.deepcopy((anterior, candidata, escenarios, lecciones))
            splits = {s["split"] for s in escenarios}
            comparaciones.append(splits)
            resultado = llamada_comparar(anterior, candidata, escenarios, lecciones)
            self.assertEqual((anterior, candidata, escenarios, lecciones), congelados)
            return resultado

        with patch.object(builder, "proponer", side_effect=proponer), \
                patch.object(benchmark, "comparar", side_effect=comparar), \
                patch.object(validador, "comparar", side_effect=comparar), \
                contextlib.redirect_stdout(io.StringIO()):
            resultado = main.ejecutar_evolucion(experimento_id="integracion")
            cantidad_comparaciones = len(comparaciones)
            guardado = main.ejecutar_evolucion(experimento_id="integracion")
        self.assertEqual(guardado, resultado)
        self.assertEqual(len(comparaciones), cantidad_comparaciones)
        self.assertEqual(comparaciones.count({"final"}), 1)
        self.assertEqual(comparaciones[-1], {"final"})
        self.assertEqual(benchmark.POLICY, policy)
        self.assertEqual(resultado["manifest"]["formula_version"], FORMULA_VERSION)
        self.assertTrue(resultado["final_result"]["executed_once"])
        self.assertEqual(len(propuestas_entradas), 2)
        self.assertEqual(len(resultado["cycles"]), 2)
        primero, segundo = resultado["cycles"]
        self.assertEqual(segundo["starting_version"], primero["selected_version"])
        self.assertEqual(propuestas_entradas[1][0][0]["id"], segundo["starting_version"])
        self.assertEqual(resultado["active_version"]["id"], segundo["selected_version"])
        self.assertEqual(Almacen().version_activa("integracion"), resultado["active_version"])
        self.assertFalse(resultado["mechanism_rejection"]["accepted"])
        self.assertFalse(resultado["mechanism_rejection"]["checks"]["contracts"])

        validaciones = 0
        for ciclo in resultado["cycles"]:
            self.assertTrue(0 < len(ciclo["proposals"]) <= policy["max_candidates"])
            self.assertEqual(len(ciclo["decisions"]), len(ciclo["proposals"]))
            for decision in ciclo["decisions"]:
                # Previene una falsa demo completa que rechace cada candidata
                # por etiquetas de split incompatibles sin medir resultados.
                self.assertTrue(decision["checks"]["contracts"])
                self.assertTrue(decision["checks"]["validation_scenarios"])
                self.assertTrue(decision["comparison"])
                self.assertGreaterEqual(decision["comparison"]["n"], 15)
                self.assertEqual(set(decision["comparison"]["by_type"]), set(config.TIPOS_PROYECTO))
                self.assertFalse(decision["observed_state"]["final_seen"])
                validaciones += 1
            aceptadas = [d for d in ciclo["decisions"] if d["accepted"]]
            if not aceptadas:
                self.assertEqual(ciclo["selected_version"], ciclo["starting_version"])
            else:
                self.assertIn(ciclo["selected_version"], {d["candidate_id"] for d in aceptadas})
        self.assertEqual(comparaciones.count({"validation"}), validaciones)

        # Aplicar la versión activa es una ejecución posterior con feedback,
        # sin reabrir la reserva ni volver a seleccionar candidatos.
        from evolucion import motor
        llamar_motor = motor.formar_equipos
        versiones_aplicadas = []

        def formar_aplicacion(personas, tipo, lecciones, estrategia, **kwargs):
            self.assertObservable(personas)
            versiones_aplicadas.append(copy.deepcopy(estrategia))
            return llamar_motor(personas, tipo, lecciones, estrategia, **kwargs)

        reserva_anterior = copy.deepcopy(resultado["final_result"])
        with patch.object(benchmark, "comparar", side_effect=AssertionError("No se debe reabrir la reserva")), \
                patch.object(validador, "comparar", side_effect=AssertionError("Aplicar no valida otra candidata")), \
                patch.object(builder, "proponer", side_effect=AssertionError("Aplicar no genera candidatas")), \
                patch.object(motor, "formar_equipos", side_effect=formar_aplicacion):
            aplicacion = main.aplicar_vigente(experimento_id="integracion")
            with self.assertRaisesRegex(ValueError, "otro manifiesto"):
                main.ejecutar_evolucion(experimento_id="integracion", semilla=2027)
        self.assertEqual(versiones_aplicadas, [resultado["active_version"]])
        self.assertEqual(aplicacion["strategy_id"], resultado["active_version"]["id"])
        self.assertEqual(aplicacion["split"], "application")
        self.assertObservable(aplicacion)
        ids = [identificador for equipo in aplicacion["equipos"] for identificador in equipo]
        self.assertEqual(len(ids), 24)
        self.assertEqual(len(set(ids)), 24)
        self.assertTrue(all(len(equipo) == 4 for equipo in aplicacion["equipos"]))
        self.assertEqual(set(ids), {p["id"] for p in aplicacion["personas"]})
        self.assertNotEqual(aplicacion["personas"], aplicacion["updated_profiles"])
        antes = {p["id"]: p for p in aplicacion["personas"]}
        feedback = {identificador: perfil for r in aplicacion["resultados"]
                    for identificador, perfil in r["feedback"].items()}
        for persona in aplicacion["updated_profiles"]:
            self.assertEqual(persona["declarado"], antes[persona["id"]]["declarado"])
            for rasgo in config.RASGOS:
                self.assertAlmostEqual(persona["estimado"][rasgo],
                                       0.7 * antes[persona["id"]]["estimado"][rasgo]
                                       + 0.3 * feedback[persona["id"]][rasgo])
        self.assertEqual(Almacen().cargar_experimento("integracion")["final_result"], reserva_anterior)
        exportado = json.loads((self.raiz / "resultados/evolucion.json").read_text(encoding="utf-8"))
        self.assertEqual(exportado["final_result"], reserva_anterior)
        self.assertIn(aplicacion, exportado["evidence"])
        self.assertEqual(aplicacion, json.loads((self.raiz / "resultados/aplicacion.json").read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
