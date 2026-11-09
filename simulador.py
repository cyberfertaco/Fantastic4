"""Persona 2: evaluador externo sintético, fijo y sin dependencias externas.

Fórmula congelada antes de crear candidatos. Ninguna configuración de estrategia
es una entrada del simulador. Estas interacciones son supuestos del experimento,
no afirmaciones sobre personas o equipos reales.
"""
import random

from config import RASGOS, TIPOS_PROYECTO


FORMULA_VERSION = "quimica-sintetica-v1"

# (rasgo principal, rasgo secundario); no recibe pesos del constructor.
_OBJETIVOS = {
    "creativo": ("creatividad", "extroversion"),
    "tecnico": ("organizacion", "cumplimiento"),
    "entrega_rapida": ("cumplimiento", "organizacion"),
}

REGLAS_OCULTAS = [
    "Supuesto sintético v1: base 30 + 25 × (0.7 × media principal + 0.3 × media secundaria − 1) / 4.",
    "Creativo: principal creatividad y secundaria extroversión; técnico: organización y cumplimiento; entrega rápida: cumplimiento y organización.",
    "Al menos dos miembros con rasgo principal real >= 4: +22 puntos; de lo contrario: −10.",
    "Al menos un miembro con rasgo secundario real >= 4: +8 puntos; de lo contrario: −6.",
    "Más de un miembro con liderazgo real >= 4: −14 puntos; en otro caso: +4.",
    "Ruido uniforme local de score entre −2 y +2; recorte del score a 0–100.",
    "Feedback por persona y rasgo: real + ruido uniforme entre −0.35 y +0.35, recortado a 1–5.",
]


def simular(equipo: list[dict], tipo: str, semilla: int) -> dict:
    """Califica perfiles reales; produce solo score y feedback observable.

    El orden del equipo no cambia el resultado: el ruido de feedback se asigna
    por ID ordenado. Cada llamada usa un RNG local independiente.
    """
    from contratos import validar_personas
    validar_personas(equipo)
    if not equipo:
        raise ValueError("El simulador necesita al menos una persona.")
    if tipo not in TIPOS_PROYECTO:
        raise ValueError(f"Tipo de proyecto desconocido: {tipo}.")
    if isinstance(semilla, bool) or not isinstance(semilla, int):
        raise ValueError("semilla debe ser un entero.")
    rng = random.Random(semilla)
    principal, secundario = _OBJETIVOS[tipo]
    media_principal = sum(p["real"][principal] for p in equipo) / len(equipo)
    media_secundaria = sum(p["real"][secundario] for p in equipo) / len(equipo)
    score = 30 + 25 * (0.7 * media_principal + 0.3 * media_secundaria - 1) / 4
    score += 22 if sum(p["real"][principal] >= 4 for p in equipo) >= 2 else -10
    score += 8 if any(p["real"][secundario] >= 4 for p in equipo) else -6
    score += -14 if sum(p["real"]["liderazgo"] >= 4 for p in equipo) > 1 else 4
    score = round(min(100.0, max(0.0, score + rng.uniform(-2, 2))), 6)
    feedback = {
        p["id"]: {
            rasgo: round(min(5.0, max(1.0, p["real"][rasgo] + rng.uniform(-0.35, 0.35))), 6)
            for rasgo in RASGOS
        }
        for p in sorted(equipo, key=lambda persona: persona["id"])
    }
    return {"score": float(score), "feedback": feedback}
