"""Persona 1: controles y evaluación externa fijos; registra aceptación o rechazo.

No modifica estrategias, escenarios, fórmula, política ni almacenamiento.
Las regresiones acumuladas son declarativas y se ejecutan sin eval/exec.
"""
from copy import deepcopy
from datetime import datetime, timezone

from benchmark import POLICY, comparar
from config import TIPOS_PROYECTO
from contratos import (huella, validar_caso, validar_decision,
                       validar_estrategia, validar_propuesta, vista_publica)
from evolucion.motor import contar_incumplimientos, formar_equipos


def ejecutar_caso(caso, estrategia):
    validar_caso(caso)
    datos = caso["input"]
    equipos = formar_equipos(datos["personas"], datos["tipo"], datos["lecciones"],
                            estrategia, semilla=datos["semilla"])
    violations = contar_incumplimientos(equipos, datos["lecciones"])
    return {"case_id": caso["id"], "passed": violations <= caso["condition"]["max_value"],
            "violations": violations, "maximum": caso["condition"]["max_value"],
            "strategy_id": estrategia["id"]}


def validar(propuesta, anterior, escenarios, lecciones, casos, observed_state):
    reasons, comparison = [], {}
    checks = {"contracts": False, "budget": False, "validation_scenarios": False,
              "regressions": [], "new_regressions_detect_previous_failure": False,
              "external_improvement": False, "no_type_regression": False}
    candidate = propuesta.get("strategy", {}) if isinstance(propuesta, dict) else {}
    state = deepcopy(observed_state)
    state.update({"scenario_ids": [s.get("id") for s in escenarios],
                  "scenario_fingerprint": huella(escenarios),
                  "lessons_fingerprint": huella(lecciones),
                  "policy": deepcopy(POLICY)})
    try:
        validar_estrategia(anterior)
        validar_propuesta(propuesta)
        if propuesta["parent_id"] != anterior["id"]:
            raise ValueError("La propuesta no deriva de la versión comparada")
        for caso in casos:
            validar_caso(caso)
        if len({c["id"] for c in casos}) != len(casos):
            raise ValueError("La batería contiene identificadores de caso duplicados")
        if not set(propuesta["case_ids"]).issubset({c["id"] for c in casos}):
            raise ValueError("Faltan casos declarados en la propuesta")
        checks["contracts"] = True
    except (ValueError, TypeError, KeyError) as error:
        reasons.append(f"Contrato inválido: {error}")
    if checks["contracts"]:
        checks["budget"] = (anterior["search_budget"] == candidate["search_budget"] == POLICY["search_budget"])
        if not checks["budget"]:
            reasons.append("El presupuesto de búsqueda debe ser el mismo y coincidir con la política fija")
        checks["validation_scenarios"] = (
            len({s["id"] for s in escenarios}) == len(escenarios)
            and all(s.get("split") == "validation" for s in escenarios)
            and all(len({s["semilla"] for s in escenarios if s["tipo"] == tipo})
                    >= POLICY["validation_seeds_per_type"] for tipo in TIPOS_PROYECTO)
        )
        if not checks["validation_scenarios"]:
            reasons.append("Validación exige tres tipos, al menos cinco semillas por tipo y un bloque reservado a validación")
        nuevos_validos = True
        for caso in casos:
            resultado = ejecutar_caso(caso, candidate)
            previo = ejecutar_caso(caso, anterior)
            resultado["previous"] = previo
            checks["regressions"].append(resultado)
            if caso["id"] in propuesta["case_ids"] and caso["expected"]["previous_fails"] and previo["passed"]:
                nuevos_validos = False
        checks["new_regressions_detect_previous_failure"] = nuevos_validos
        if not nuevos_validos:
            reasons.append("Una regresión nueva no detecta el fallo declarado en la estrategia anterior")
        if not all(r["passed"] for r in checks["regressions"]):
            reasons.append("La candidata incumple una regresión obligatoria acumulada")
        # Medimos también candidatos que fallen regresiones para informar rechazos empíricos.
        if checks["budget"] and checks["validation_scenarios"]:
            state["observable_profiles_fingerprint"] = huella([vista_publica(s["personas"]) for s in escenarios])
            comparison = comparar(anterior, candidate, escenarios, lecciones)
            checks["external_improvement"] = comparison["delta"] >= POLICY["min_improvement"]
            checks["no_type_regression"] = all(
                comparison["by_type"][tipo]["delta"] >= -POLICY["max_type_drop"]
                for tipo in TIPOS_PROYECTO
            )
            if not checks["external_improvement"]:
                reasons.append(f"Mejora media {comparison['delta']:.3f} < {POLICY['min_improvement']:.1f} puntos exigidos")
            if not checks["no_type_regression"]:
                reasons.append("Al menos un tipo empeora más del máximo de 2 puntos")
    accepted = (checks["contracts"] and checks["budget"] and checks["validation_scenarios"]
                and checks["new_regressions_detect_previous_failure"]
                and all(r["passed"] for r in checks["regressions"])
                and checks["external_improvement"] and checks["no_type_regression"])
    if accepted:
        reasons.append("Aceptada: contratos y regresiones aprobados, mejora media >=2 y caída por tipo <=2")
    contenido = {"schema_version": 1, "proposal_id": propuesta.get("id", "invalid-proposal"),
                 "parent_id": anterior["id"], "candidate_id": candidate.get("id", "invalid-strategy"),
                 "accepted": bool(accepted), "reasons": reasons, "comparison": comparison,
                 "checks": checks, "observed_state": state,
                 "created_at": datetime.now(timezone.utc).isoformat(), "owner": "Persona 1"}
    decision = {"id": "decision-" + huella(contenido)[:20], **contenido}
    validar_decision(decision)
    return decision
