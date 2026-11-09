"""Persona 1: servicio y CLI; orquesta experimentos sin filtrar verdad al aprendizaje."""
import argparse
import copy
import json
from datetime import datetime, timezone
from statistics import fmean

from config import RASGOS, RONDAS, TIPOS_PROYECTO, ruta_proyecto
from contratos import huella, vista_publica, validar_personas


def ahora():
    return datetime.now(timezone.utc).isoformat()


def escribir_json(ruta, objeto):
    destino = ruta_proyecto(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(destino.suffix + ".tmp")
    temporal.write_text(json.dumps(objeto, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporal.replace(destino)


def _error(personas):
    """Métrica autorizada; nunca se entrega al constructor o builder."""
    return fmean(abs(p["estimado"][r] - p["real"][r]) for p in personas for r in RASGOS)


def _equipos_completos(equipos_publicos, personas):
    indice = {p["id"]: p for p in personas}
    return [[indice[p["id"]] for p in equipo] for equipo in equipos_publicos]


def ejecutar_demo(semilla=42):
    """Repite únicamente el experimento longitudinal sintético base."""
    from personas import generar_personas, guardar
    from simulador import REGLAS_OCULTAS
    from agentes.constructor import armar_equipos
    from agentes.evaluador import evaluar
    from agentes.reflexionador import actualizar_perfiles, sacar_lecciones, evidencia_leccion
    from agentes.curador import Biblioteca

    iniciales = generar_personas(semilla=semilla)
    memoria, base = copy.deepcopy(iniciales), copy.deepcopy(iniciales)
    biblioteca = Biblioteca()
    # El archivo base pertenece solo a esta demo. Lotes/versiones SQLite se conservan.
    biblioteca.lecciones = []
    biblioteca.historial = {tipo: {"sum": 0.0, "count": 0} for tipo in TIPOS_PROYECTO}
    biblioteca.evidencias = {}
    metricas = {"con_memoria": [], "sin_memoria": [], "personas": [],
                "reglas_ocultas": list(REGLAS_OCULTAS)}
    historial = []
    actualizaciones = []
    for i in range(RONDAS):
        tipo = TIPOS_PROYECTO[i % len(TIPOS_PROYECTO)]
        observables = vista_publica(memoria)
        lecciones = biblioteca.relevantes(tipo)
        equipos = armar_equipos(observables, tipo, lecciones, semilla=semilla + i)
        resultados = evaluar(_equipos_completos(equipos, memoria), tipo, i)
        snapshot = {p["id"]: copy.deepcopy(p["estimado"]) for p in observables}
        observed_at = ahora()
        for j, resultado in enumerate(resultados):
            historial.append({**copy.deepcopy(resultado), "id": f"demo-r{i + 1}-e{j}",
                              "perfiles_observados": snapshot, "observed_at": observed_at})
        biblioteca.registrar_uso(lecciones, resultados)
        actualizar_perfiles(observables, resultados)
        por_id = {p["id"]: p for p in observables}
        for persona in memoria:
            persona["estimado"] = copy.deepcopy(por_id[persona["id"]]["estimado"])
        actualizaciones.append({"ronda": i + 1, "observed_at": observed_at,
                                "updated_at": ahora(), "before": snapshot,
                                "after": {p["id"]: p["estimado"] for p in observables}})
        for leccion in sacar_lecciones(historial, observables, tipo):
            almacenada, _ = biblioteca.agregar(leccion)
            biblioteca.agregar_evidencia(almacenada["id"], evidencia_leccion(historial, observables, leccion))
        biblioteca.podar()
        equipos_base = armar_equipos(vista_publica(base), tipo, [], semilla=semilla + i)
        resultados_base = evaluar(_equipos_completos(equipos_base, base), tipo, i)
        for nombre, poblacion, filas, cantidad in (
                ("con_memoria", memoria, resultados, len(biblioteca.lecciones)),
                ("sin_memoria", base, resultados_base, 0)):
            metricas[nombre].append({"ronda": i + 1, "tipo": tipo,
                                     "score_promedio": fmean(r["score"] for r in filas),
                                     "error_perfiles": _error(poblacion), "lecciones": cantidad})
    metricas["personas"] = memoria
    guardar(memoria)
    biblioteca.guardar()
    escribir_json("resultados/metricas.json", metricas)
    escribir_json("resultados/demo-trazabilidad.json", {
        "schema_version": 1, "mode": "determinista", "semilla": semilla,
        "historial": historial, "actualizaciones": actualizaciones,
        "baseline_initial_hash": huella(iniciales), "baseline_final_hash": huella(base),
        "interpretacion": "Experimento longitudinal: mezcla actualización de perfiles y memoria; no aísla estrategia."})
    return metricas


def _descubrir(estrategia, escenarios, lecciones, ciclo):
    """Única frontera de descubrimiento: devuelve evidencia pública sin reglas ocultas."""
    from evolucion.motor import formar_equipos
    from simulador import simular
    evidencias, historial = [], []
    for escenario in escenarios:
        publicas = vista_publica(escenario["personas"])
        equipos = formar_equipos(publicas, escenario["tipo"], lecciones, estrategia,
                                 semilla=escenario["semilla"])
        snapshot = {p["id"]: copy.deepcopy(p["estimado"]) for p in publicas}
        filas = []
        for j, equipo in enumerate(_equipos_completos(equipos, escenario["personas"])):
            salida = simular(equipo, escenario["tipo"], escenario["semilla"] + j)
            fila = {"miembros": [p["id"] for p in equipo], "tipo": escenario["tipo"],
                    "ronda": ciclo, **salida}
            filas.append(fila)
            historial.append({**fila, "id": f"{escenario['id']}-equipo-{j}",
                              "perfiles_observados": copy.deepcopy(snapshot)})
        evidencias.append({"id": f"evidence-{escenario['id']}", "tipo": escenario["tipo"],
                            "semilla": escenario["semilla"], "personas": publicas,
                            "lecciones": copy.deepcopy(lecciones),
                            "equipos": [[p["id"] for p in equipo] for equipo in equipos],
                            "resultados": filas, "strategy_id": estrategia["id"],
                            "observed_at": ahora(), "split": "discovery",
                            "simulation_seeds": [escenario["semilla"] + j for j in range(len(equipos))]})
    return evidencias, historial


def ejecutar_evolucion(experimento_id="demo-evolucion", semilla=2026, reiniciar=False):
    """Hasta dos ciclos; comparación fija, persistencia y prueba reservada una vez."""
    from almacenamiento import Almacen
    from benchmark import crear_manifiesto, comparar
    from evolucion.motor import estrategia_inicial
    from evolucion.builder import proponer
    from evolucion.validador import validar, ejecutar_caso
    from agentes.reflexionador import sacar_lecciones, evidencia_leccion

    if not isinstance(experimento_id, str) or not experimento_id.strip():
        raise ValueError("Identificador de experimento vacío")
    almacen = Almacen()
    existente = almacen.cargar_experimento(experimento_id)
    if reiniciar:
        almacen.reiniciar_experimento(experimento_id)
        existente = None
    if existente:
        if existente.get("manifest", {}).get("id") != crear_manifiesto(semilla)["id"]:
            raise ValueError("Ese ID pertenece a otro manifiesto; usa otro --id o --reiniciar para repetir explícitamente.")
        if existente.get("final_result", {}).get("executed_once"):
            almacen.exportar_experimento(experimento_id)
            return json.loads(ruta_proyecto("resultados/evolucion.json").read_text(encoding="utf-8"))
        raise ValueError("El experimento quedó incompleto; usa otro --id o --reiniciar para repetirlo explícitamente.")

    manifiesto = crear_manifiesto(semilla)
    inicial = estrategia_inicial()
    vigente = copy.deepcopy(inicial)
    almacen.guardar_version(vigente)
    datos = {"schema_version": 1, "experiment_id": experimento_id, "mode": "determinista",
             "manifest": manifiesto, "cycles": [], "active_version": vigente,
             "versions": [], "decisions": [], "evidence": [], "cases": [],
             "lessons": [], "lesson_evidence": {}, "final_result": {},
             "mechanism_rejection": {}, "created_at": ahora(), "updated_at": ahora()}
    almacen.guardar_experimento(experimento_id, datos)
    almacen.activar_version(experimento_id, vigente["id"])
    lecciones, casos_estables = [], []
    for bloque in manifiesto["cycles"]:
        ciclo = bloque["cycle"]
        print(f"Ciclo {ciclo}: descubrimiento y comparación fija…", flush=True)
        inicio = copy.deepcopy(vigente)
        evidencias, historial = _descubrir(inicio, bloque["discovery"], lecciones, ciclo)
        for evidencia in evidencias:
            almacen.guardar_evidencia(experimento_id, evidencia)
        index_lecciones = {l["id"]: l for l in lecciones}
        publicas = vista_publica(bloque["discovery"][0]["personas"])
        for tipo in TIPOS_PROYECTO:
            for leccion in sacar_lecciones(historial, publicas, tipo):
                if leccion["id"] in index_lecciones:
                    index_lecciones[leccion["id"]]["veces_vista"] += 1
                else:
                    index_lecciones[leccion["id"]] = leccion
                datos["lesson_evidence"].setdefault(leccion["id"], []).append({
                    **evidencia_leccion(historial, publicas, leccion), "cycle": ciclo,
                    "observed_at": ahora(), "evidence_ids": [e["id"] for e in evidencias if e["tipo"] == tipo]})
        lecciones = list(index_lecciones.values())
        propuestas, nuevos_casos = proponer(copy.deepcopy(inicio), copy.deepcopy(evidencias),
                                            copy.deepcopy(lecciones), ciclo=ciclo)
        if len(propuestas) > manifiesto["policy"]["max_candidates"]:
            raise ValueError("Builder excede el presupuesto de candidatos")
        # La batería acumulativa no se reemplaza. Las condiciones provienen de fallos observados.
        existentes = {c["id"] for c in casos_estables}
        for caso in nuevos_casos:
            if caso["id"] not in existentes:
                previo = ejecutar_caso(caso, inicio)
                if caso["expected"]["previous_fails"] and previo["passed"]:
                    raise ValueError("La regresión propuesta no detecta el fallo en su versión anterior")
                casos_estables.append(caso)
        estado = {"cycle": ciclo, "active_version": inicio["id"], "observed_at": ahora(),
                  "validation_scenario_ids": [s["id"] for s in bloque["validation"]],
                  "observable_profiles_hash": huella([vista_publica(s["personas"]) for s in bloque["validation"]]),
                  "lessons_hash": huella(lecciones), "manifest_id": manifiesto["id"],
                  "formula_version": manifiesto["formula_version"], "final_seen": False}
        decisiones = []
        for propuesta in propuestas:
            almacen.guardar_version(propuesta["strategy"])
            decision = validar(propuesta, inicio, bloque["validation"], lecciones, casos_estables, estado)
            almacen.guardar_decision(experimento_id, decision)
            decisiones.append(decision)
        aptas = [d for d in decisiones if d["accepted"]]
        if aptas:
            mejor = max(aptas, key=lambda d: d["comparison"]["delta"])
            vigente = copy.deepcopy(next(p["strategy"] for p in propuestas if p["strategy"]["id"] == mejor["candidate_id"]))
            almacen.activar_version(experimento_id, vigente["id"])
        datos["cycles"].append({"cycle": ciclo, "starting_version": inicio["id"],
                                "lesson_ids": [l["id"] for l in lecciones], "proposals": propuestas,
                                "decisions": decisiones, "selected_version": vigente["id"],
                                "discovery_summary": {"n": len(historial), "mean": fmean(r["score"] for r in historial)},
                                "regressions_added": [c["id"] for c in nuevos_casos], "observed_at": estado["observed_at"]})
        datos.update(lessons=copy.deepcopy(lecciones), cases=copy.deepcopy(casos_estables),
                     active_version=vigente, updated_at=ahora())
        almacen.guardar_experimento(experimento_id, datos)
        print(f"  {len(lecciones)} hipótesis; {len(propuestas)} candidatas; {len(aptas)} aptas. Vigente: {vigente['id']}", flush=True)

    # Prueba explícita del control: no se presenta como aprendizaje espontáneo.
    invalida = copy.deepcopy(vigente)
    invalida.update(id="control-invalido-" + huella(vigente)[:12], parent_id=vigente["id"])
    invalida["parameters"]["weights"] = {"lessons": -1, "balance": 2}
    control = {"schema_version": 1, "id": "propuesta-" + invalida["id"], "parent_id": vigente["id"],
               "strategy": invalida, "evidence_ids": [], "case_ids": [], "owner": "Persona 1"}
    decision_control = validar(control, vigente, manifiesto["cycles"][-1]["validation"], lecciones, casos_estables,
                               {"mechanism_test": True, "description": "Pesos inválidos introducidos expresamente"})
    if decision_control["accepted"]:
        raise RuntimeError("El control inválido fue aceptado")
    almacen.guardar_decision(experimento_id, decision_control)
    datos["mechanism_rejection"] = decision_control
    # Marca el consumo antes de ejecutar: un cierre interrumpido no ejecuta la reserva silenciosamente otra vez.
    datos["final_result"] = {"status": "consumed", "strategy_id": vigente["id"]}
    almacen.guardar_experimento(experimento_id, datos)
    print("Ejecutando prueba final reservada, una vez después de seleccionar…", flush=True)
    final = comparar(inicial, vigente, manifiesto["final"], lecciones)
    datos["final_result"] = {"executed_once": True, "strategy_id": vigente["id"],
                              "comparison": final, "completed_at": ahora(),
                              "interpretation": "Reserva informativa; no se utiliza para ajustar ni aceptar versiones."}
    datos["updated_at"] = ahora()
    almacen.guardar_experimento(experimento_id, datos)
    almacen.exportar_experimento(experimento_id)
    return json.loads(ruta_proyecto("resultados/evolucion.json").read_text(encoding="utf-8"))


def generar_lote(n, semilla):
    from almacenamiento import Almacen
    return Almacen().registrar_lote(n, semilla)


def aplicar_vigente(experimento_id="demo-evolucion", tipo="creativo", semilla=43, lote_id=None):
    """Nueva ejecución operativa con la versión persistida; no consulta la reserva."""
    from almacenamiento import Almacen
    from personas import generar_personas
    from evolucion.motor import formar_equipos
    from agentes.reflexionador import actualizar_perfiles
    from simulador import simular
    almacen = Almacen()
    experimento = almacen.cargar_experimento(experimento_id)
    estrategia = almacen.version_activa(experimento_id)
    if not experimento or not estrategia:
        raise ValueError("Primero ejecuta la evaluación para registrar una versión vigente")
    personas = almacen.personas_lote(lote_id) if lote_id else generar_personas(semilla=semilla)
    publicas = vista_publica(personas)
    observadas = copy.deepcopy(publicas)
    lecciones = experimento.get("lessons", [])
    equipos = formar_equipos(publicas, tipo, lecciones, estrategia, semilla=semilla)
    observed_at = ahora()
    resultados = []
    for j, equipo in enumerate(_equipos_completos(equipos, personas)):
        resultados.append({"miembros": [p["id"] for p in equipo], "tipo": tipo, "ronda": 1,
                           **simular(equipo, tipo, semilla * 100 + j)})
    actualizar_perfiles(publicas, resultados)
    registro = {"schema_version": 1, "experiment_id": experimento_id, "split": "application",
                "strategy_id": estrategia["id"], "tipo": tipo, "semilla": semilla,
                "personas": observadas, "lecciones": copy.deepcopy(lecciones),
                "equipos": [[p["id"] for p in equipo] for equipo in equipos],
                "resultados": resultados, "updated_profiles": publicas,
                "observed_at": observed_at, "updated_at": ahora(),
                "score_promedio": fmean(r["score"] for r in resultados),
                "simulation_seeds": [semilla * 100 + j for j in range(len(equipos))],
                "interpretation": "Aplicación posterior con versión activa; no selecciona ni valida otra estrategia."}
    registro["id"] = "application-" + huella(registro)[:20]
    almacen.guardar_evidencia(experimento_id, registro)
    almacen.exportar_experimento(experimento_id)
    guardado = next(e for e in almacen.listar_evidencias(experimento_id) if e["id"] == registro["id"])
    escribir_json("resultados/aplicacion.json", guardado)
    return guardado


def main():
    parser = argparse.ArgumentParser(description="TEAMFORGE · experimentos sintéticos reproducibles, sin API")
    sub = parser.add_subparsers(dest="comando", required=True)
    demo = sub.add_parser("demo", help="10 rondas con/sin memoria; genera metricas.json")
    demo.add_argument("--semilla", type=int, default=42)
    evolucion = sub.add_parser("evolucion", help="Dos ciclos y evaluación final reservada")
    evolucion.add_argument("--id", default="demo-evolucion")
    evolucion.add_argument("--semilla", type=int, default=2026)
    evolucion.add_argument("--reiniciar", action="store_true", help="Repite solo este experimento; conserva lotes y versiones")
    lote = sub.add_parser("lote", help="Añade un lote sintético sin borrar otros")
    lote.add_argument("--cantidad", type=int, default=24)
    lote.add_argument("--semilla", type=int, default=42)
    inspeccion = sub.add_parser("inspeccionar-lote")
    inspeccion.add_argument("id")
    inspeccion.add_argument("--validar-equipos", action="store_true", help="Exige divisibilidad entre 4")
    aplicar = sub.add_parser("aplicar", help="Forma nuevos equipos usando la versión activa persistida")
    aplicar.add_argument("--id", default="demo-evolucion")
    aplicar.add_argument("--tipo", choices=TIPOS_PROYECTO, default="creativo")
    aplicar.add_argument("--semilla", type=int, default=43)
    aplicar.add_argument("--lote", default=None)
    sub.add_parser("lotes", help="Lista metadatos de lotes")
    args = parser.parse_args()
    try:
        if args.comando == "demo":
            m = ejecutar_demo(args.semilla)
            print(f"Demo completa: {len(m['con_memoria'])} rondas; resultados/metricas.json")
        elif args.comando == "evolucion":
            e = ejecutar_evolucion(args.id, args.semilla, args.reiniciar)
            print(f"Versión vigente: {e['active_version']['id']}; resultados/evolucion.json")
            print(f"Delta reservado: {e['final_result']['comparison']['delta']:+.3f} puntos")
        elif args.comando == "lote":
            registro = generar_lote(args.cantidad, args.semilla)
            print(json.dumps({k: v for k, v in registro.items() if k != "personas"}, ensure_ascii=False, indent=2))
        elif args.comando == "aplicar":
            aplicacion = aplicar_vigente(args.id, args.tipo, args.semilla, args.lote)
            print(f"Nueva ejecución con {aplicacion['strategy_id']}; {len(aplicacion['equipos'])} equipos; resultados/aplicacion.json")
        else:
            from almacenamiento import Almacen
            almacen = Almacen()
            if args.comando == "lotes":
                salida = almacen.listar_lotes()
            else:
                salida = almacen.personas_lote(args.id)
                if args.validar_equipos and (not salida or len(salida) % 4):
                    raise ValueError(f"El lote tiene {len(salida)} personas: se requiere un múltiplo de 4; selecciona explícitamente otro grupo.")
            print(json.dumps(salida, ensure_ascii=False, indent=2))
    except (ValueError, FileNotFoundError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
