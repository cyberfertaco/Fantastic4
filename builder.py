"""Persona 3: propone JSON y regresiones desde evidencia observable de descubrimiento.

No conoce el simulador ni el benchmark. Los pesos candidatos se fijan antes
de evaluar: 0.7, 0.9 y 1.0 para lecciones. Prioridades reflejan frecuencia de
incumplimientos, no scores del conjunto de validación. Las regresiones usan
snapshots congelados; aplicar una hipótesis nueva a ellos es retrospectivo.
Solo generan un caso si la reproducción conserva exactamente la partición
observada: mismos equipos y perfiles, aunque cambie el orden de sus IDs.
"""
from copy import deepcopy

from contratos import (huella, validar_caso, validar_estrategia,
                       validar_leccion, validar_personas, validar_propuesta)
from evolucion.motor import contar_incumplimientos, formar_equipos


def _comprobar_vista(value):
    if isinstance(value, dict):
        if {"real", "reglas_ocultas", "final", "final_result"}.intersection(value):
            raise ValueError("El builder solo acepta evidencia observable de descubrimiento")
        if "split" in value and value["split"] != "discovery":
            raise ValueError("El builder no puede recibir validación ni prueba final")
        for child in value.values():
            _comprobar_vista(child)
    elif isinstance(value, list):
        for child in value:
            _comprobar_vista(child)


def _particion(equipos):
    """Identidad de una partición independiente del orden de equipos/miembros."""
    if not isinstance(equipos, list) or any(
        not isinstance(equipo, list) or any(not isinstance(pid, str) for pid in equipo)
        for equipo in equipos
    ):
        return None
    return tuple(sorted(tuple(sorted(equipo)) for equipo in equipos))


def proponer(estrategia, evidencias, lecciones, ciclo=1):
    validar_estrategia(estrategia)
    if ciclo not in (1, 2):
        raise ValueError("La demo admite como máximo dos ciclos")
    _comprobar_vista(evidencias)
    for e in evidencias:
        validar_personas(e["personas"], publica=True)
    for l in lecciones:
        validar_leccion(l)
    if not evidencias or not lecciones:
        return [], []
    evidence_ids = [e["id"] for e in evidencias]
    # Reconstrucción de hipótesis sobre los perfiles observados, nunca posteriores.
    prioridades = {l["id"]: 1.0 for l in lecciones}
    reconstruidos = []
    for e in evidencias:
        relevantes = [l for l in lecciones if l["tipo_proyecto"] in (e["tipo"], "todos")]
        anteriores = formar_equipos(e["personas"], e["tipo"], relevantes, estrategia, semilla=e["semilla"])
        reconstruidos.append((e, relevantes, anteriores))
        for l in relevantes:
            prioridades[l["id"]] += contar_incumplimientos(anteriores, [l]) / len(anteriores)
    # Normalizar a [1, 2] conserva significado: frecuencia de fallos por snapshot.
    prioridades = {k: 1.0 + (v - 1.0) / len(evidencias) for k, v in prioridades.items()}
    estrategias = []
    for peso in (0.7, 0.9, 1.0):
        contenido = {
            "schema_version": 1, "parent_id": estrategia["id"],
            "parameters": {"weights": {"lessons": peso, "balance": round(1.0 - peso, 10)},
                           "lesson_priorities": deepcopy(prioridades)},
            "search_budget": estrategia["search_budget"],
            "lesson_ids": [l["id"] for l in lecciones], "owner": "Persona 3",
        }
        candidata = {"id": "strategy-" + huella(contenido)[:16], **contenido}
        validar_estrategia(candidata)
        if candidata["parameters"] != estrategia["parameters"]:
            estrategias.append(candidata)
    casos, tipos_cubiertos = [], set()
    for e, relevantes, anteriores in reconstruidos:
        if e["tipo"] in tipos_cubiertos or not relevantes:
            continue
        # Una hipótesis nueva se analiza retrospectivamente sobre el mismo
        # reparto observado. Si cambia el reparto, no hay fallo observado
        # reproducido y este snapshot no puede originar una regresión.
        particion_reproducida = _particion([[p["id"] for p in equipo] for equipo in anteriores])
        if particion_reproducida != _particion(e.get("equipos")):
            continue
        fallos = contar_incumplimientos(anteriores, relevantes)
        if not fallos:
            continue
        # No convertir una restricción imposible en requisito obligatorio:
        # al menos una propuesta debe demostrar menor incumplimiento observable.
        mejora_posible = any(
            contar_incumplimientos(formar_equipos(e["personas"], e["tipo"], relevantes, c,
                                                 semilla=e["semilla"]), relevantes) < fallos
            for c in estrategias
        )
        if not mejora_posible:
            continue
        contenido = {
            "schema_version": 1,
            "input": {"personas": deepcopy(e["personas"]), "tipo": e["tipo"],
                      "lecciones": deepcopy(relevantes), "semilla": e["semilla"]},
            "condition": {"kind": "max_violations", "max_value": fallos - 1},
            "evidence_ids": [e["id"]], "expected": {"previous_fails": True},
            "owner": "Persona 3",
        }
        caso = {"id": "case-" + huella(contenido)[:16], **contenido}
        validar_caso(caso)
        assert fallos > caso["condition"]["max_value"]
        casos.append(caso)
        tipos_cubiertos.add(e["tipo"])
    propuestas = []
    for candidata in estrategias:
        contenido = {"schema_version": 1, "parent_id": estrategia["id"],
                     "strategy": candidata, "evidence_ids": evidence_ids,
                     "case_ids": [c["id"] for c in casos], "owner": "Persona 3"}
        propuesta = {"id": "proposal-" + huella(contenido)[:16], **contenido}
        validar_propuesta(propuesta)
        propuestas.append(propuesta)
    return propuestas, casos
