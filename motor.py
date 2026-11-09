"""Persona 1: selección por configuración explícita, sin acceso a verdad sintética.

Objetivos minimizados en [0, 1]: fracción ponderada de incumplimientos y
varianza de medias de equipos (dividida por 4, máximo para valores 1–5).
Las lecciones son penalizaciones blandas; tamaño y unicidad son restricciones
obligatorias. El presupuesto cuenta repartos completos, incluido el primero.
"""
import random

from config import RASGOS, SEARCH_BUDGET, TAM_EQUIPO, TIPOS_PROYECTO
from contratos import huella, validar_estrategia, validar_leccion, validar_personas


def estrategia_inicial() -> dict:
    contenido = {
        "schema_version": 1, "parent_id": None,
        "parameters": {"weights": {"lessons": 0.0, "balance": 1.0},
                       "lesson_priorities": {}},
        "search_budget": SEARCH_BUDGET, "lesson_ids": [], "owner": "Persona 3",
    }
    return {"id": "strategy-" + huella(contenido)[:16], **contenido}


def _cumple(equipo, leccion):
    cantidad = sum(p["estimado"][leccion["rasgo"]] >= leccion["umbral"] for p in equipo)
    if leccion["operador"] == "max":
        return cantidad <= leccion["cantidad"]
    return cantidad >= leccion["cantidad"]


def contar_incumplimientos(equipos, lecciones) -> int:
    for leccion in lecciones:
        validar_leccion(leccion)
    return sum(not _cumple(equipo, leccion) for equipo in equipos for leccion in lecciones)


def _objetivo(equipos, lecciones, estrategia):
    priorities = estrategia["parameters"]["lesson_priorities"]
    total_prioridad = sum(priorities.get(l["id"], 1.0) for l in lecciones)
    incumplimiento = 0.0
    if total_prioridad:
        incumplimiento = sum(
            priorities.get(l["id"], 1.0) * (not _cumple(e, l))
            for e in equipos for l in lecciones
        ) / (len(equipos) * total_prioridad)
    medias = [[sum(p["estimado"][r] for p in e) / len(e) for r in RASGOS] for e in equipos]
    balance = 0.0
    for j in range(len(RASGOS)):
        media = sum(m[j] for m in medias) / len(medias)
        balance += sum((m[j] - media) ** 2 for m in medias) / len(medias)
    balance /= 4 * len(RASGOS)
    weights = estrategia["parameters"]["weights"]
    return weights["lessons"] * incumplimiento + weights["balance"] * balance


def formar_equipos(personas, tipo, lecciones, estrategia, tam=TAM_EQUIPO, semilla=0):
    validar_personas(personas, publica=True)
    validar_estrategia(estrategia)
    if tipo not in TIPOS_PROYECTO:
        raise ValueError("Tipo de proyecto desconocido")
    if isinstance(tam, bool) or not isinstance(tam, int) or tam < 1:
        raise ValueError("El tamaño de equipo debe ser un entero positivo")
    if not personas or len(personas) % tam:
        raise ValueError(f"El grupo de {len(personas)} personas debe ser divisible entre {tam}")
    for leccion in lecciones:
        validar_leccion(leccion)
    relevantes = [l for l in lecciones if l["tipo_proyecto"] in (tipo, "todos")]
    rng = random.Random(semilla)
    mejor, valor = None, float("inf")
    for _ in range(estrategia["search_budget"]):
        reparto = list(personas)
        rng.shuffle(reparto)
        equipos = [reparto[i:i + tam] for i in range(0, len(reparto), tam)]
        actual = _objetivo(equipos, relevantes, estrategia)
        if actual < valor:
            mejor, valor = equipos, actual
    return mejor
