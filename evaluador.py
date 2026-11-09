"""Persona 1: frontera autorizada hacia el simulador, con salida observable."""
import hashlib

from config import TIPOS_PROYECTO
from contratos import validar_personas
from simulador import simular


def evaluar(equipos, tipo, ronda) -> list[dict]:
    if tipo not in TIPOS_PROYECTO:
        raise ValueError(f"Tipo de proyecto desconocido: {tipo}")
    if not isinstance(ronda, int) or isinstance(ronda, bool) or ronda < 0:
        raise ValueError("La ronda debe ser un entero no negativo")
    todos = [persona for equipo in equipos for persona in equipo]
    validar_personas(todos)
    resultados = []
    for indice, equipo in enumerate(equipos):
        if not equipo:
            raise ValueError("No se puede evaluar un equipo vacío")
        # Hash estable: no depende del hash aleatorio del proceso de Python.
        material = f"quimica-evaluador-v1:{tipo}:{ronda}:{indice}".encode()
        semilla = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
        resultado = simular(equipo, tipo, semilla)
        resultados.append({
            "miembros": [p["id"] for p in equipo], "tipo": tipo, "ronda": ronda,
            "score": float(resultado["score"]), "feedback": resultado["feedback"],
        })
    return resultados
