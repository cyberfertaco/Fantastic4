"""Persona 2: manifiesto predefinido y evaluación externa fija del simulador."""
from copy import deepcopy
import statistics

from config import N_PERSONAS, SEARCH_BUDGET, TIPOS_PROYECTO
from contratos import huella, validar_estrategia, validar_personas, vista_publica
from personas import generar_personas
from simulador import FORMULA_VERSION, simular


POLICY = {
    "min_improvement": 2.0,
    "max_type_drop": 2.0,
    "search_budget": SEARCH_BUDGET,
    "max_candidates": 3,
    "max_cycles": 2,
    "validation_seeds_per_type": 5,
}


def crear_manifiesto(semilla=2026):
    """Fija todas las poblaciones antes del builder; no selecciona semillas por score."""
    if isinstance(semilla, bool) or not isinstance(semilla, int):
        raise ValueError("La semilla del manifiesto debe ser un entero.")

    def scenarios(block_name, block, split):
        result = []
        for kind_index, tipo in enumerate(TIPOS_PROYECTO):
            for index in range(POLICY["validation_seeds_per_type"]):
                offset = block * 10_000 + kind_index * 100 + index
                population_seed = semilla + offset
                scenario_id = f"{block_name}-{tipo}-{index}"
                population = generar_personas(n=N_PERSONAS, semilla=population_seed)
                for persona in population:
                    persona["id"] = f"{scenario_id}:{persona['id']}"
                result.append({"id": scenario_id, "split": split, "tipo": tipo,
                               "semilla": semilla + 1_000_000 + offset,
                               "personas": population})
        return result

    manifest = {
        "schema_version": 1,
        "formula_version": FORMULA_VERSION,
        "policy": deepcopy(POLICY),
        "cycles": [{"cycle": cycle,
                    "discovery": scenarios(f"c{cycle}-discovery", 2 * cycle - 1, "discovery"),
                    "validation": scenarios(f"c{cycle}-validation", 2 * cycle, "validation")}
                   for cycle in (1, 2)],
        "final": scenarios("final", 5, "final"),
    }
    manifest["id"] = "manifest-" + huella(manifest)[:16]
    return manifest


def _summary(values):
    return {"n": len(values), "mean": statistics.mean(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0.0}


def evaluar_estrategia(estrategia, escenarios, lecciones):
    """n cuenta poblaciones/proyectos; score es media de sus seis equipos.

    La frontera del motor recibe copias sin real; solo el evaluador autorizado
    resuelve IDs y entrega los perfiles completos al simulador. Las estimaciones
    no se actualizan durante esta evaluación. El ruido está emparejado por
    escenario y posición de equipo para ambas estrategias.
    """
    from evolucion.motor import formar_equipos

    validar_estrategia(estrategia)
    if estrategia["search_budget"] != POLICY["search_budget"]:
        raise ValueError("La evaluación fija exige presupuesto de búsqueda 300.")
    if not escenarios:
        raise ValueError("La evaluación requiere escenarios.")
    if len({scenario["id"] for scenario in escenarios}) != len(escenarios):
        raise ValueError("Los identificadores de escenarios deben ser únicos.")
    scores = []
    before_hash = huella(escenarios)
    for scenario in escenarios:
        if scenario["tipo"] not in TIPOS_PROYECTO:
            raise ValueError("Tipo de proyecto desconocido en el escenario.")
        validar_personas(scenario["personas"])
        population = {persona["id"]: persona for persona in scenario["personas"]}
        teams = formar_equipos(vista_publica(scenario["personas"]), scenario["tipo"],
                              deepcopy(lecciones), deepcopy(estrategia), semilla=scenario["semilla"])
        ids = [persona["id"] for team in teams for persona in team]
        if len(ids) != len(population) or len(set(ids)) != len(ids) or set(ids) != set(population):
            raise ValueError("El motor debe repartir todas las personas sin duplicar ni descartar.")
        if not teams or any(len(team) != 4 for team in teams):
            raise ValueError("El evaluador fijo exige equipos de cuatro personas.")
        values = [simular([population[p["id"]] for p in team], scenario["tipo"],
                          scenario["semilla"] * 100 + index)["score"]
                  for index, team in enumerate(teams)]
        scores.append({"scenario_id": scenario["id"], "tipo": scenario["tipo"],
                       "score": statistics.mean(values)})
    if huella(escenarios) != before_hash:
        raise RuntimeError("La evaluación alteró un snapshot congelado.")
    result = _summary([row["score"] for row in scores])
    result["by_type"] = {tipo: _summary([row["score"] for row in scores if row["tipo"] == tipo])
                         for tipo in TIPOS_PROYECTO if any(row["tipo"] == tipo for row in scores)}
    result["scores"] = scores
    return result


def comparar(anterior, candidata, escenarios, lecciones):
    """Mismo evaluador, requisitos, perfiles, lecciones, semillas y presupuesto."""
    if anterior.get("search_budget") != candidata.get("search_budget"):
        raise ValueError("No se comparan estrategias con presupuestos diferentes.")
    snapshot = deepcopy(escenarios)
    before = evaluar_estrategia(anterior, snapshot, lecciones)
    after = evaluar_estrategia(candidata, snapshot, lecciones)
    paired = [b["score"] - a["score"] for a, b in zip(before["scores"], after["scores"])]
    by_type = {tipo: {"before": before["by_type"][tipo]["mean"],
                      "after": after["by_type"][tipo]["mean"],
                      "delta": after["by_type"][tipo]["mean"] - before["by_type"][tipo]["mean"],
                      "n": before["by_type"][tipo]["n"]}
               for tipo in before["by_type"]}
    return {"n": before["n"], "before": before, "after": after,
            "delta": after["mean"] - before["mean"], "by_type": by_type,
            "paired_stdev": statistics.stdev(paired) if len(paired) > 1 else 0.0}
