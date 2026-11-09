"""Persona 1: reparto base aleatorio y búsqueda con lecciones observables."""
import random
from statistics import fmean

from config import RASGOS, TAM_EQUIPO, TIPOS_PROYECTO
from contratos import validar_leccion, validar_personas


def cumple(equipo, leccion) -> bool:
    """min/max limitan la cantidad cuyo estimado alcanza el umbral."""
    validar_leccion(leccion)
    if any("real" in persona for persona in equipo):
        raise ValueError("El constructor solo admite perfiles observables, sin real")
    cantidad = sum(p["estimado"][leccion["rasgo"]] >= leccion["umbral"] for p in equipo)
    return cantidad <= leccion["cantidad"] if leccion["operador"] == "max" else cantidad >= leccion["cantidad"]


def desequilibrio(equipos):
    """Varianza entre medias de equipo por rasgo, dividida por 4 (rango 0..1).

    Cada media está en [1,5], cuya varianza máxima es 4. No usa calidad real.
    """
    if not equipos:
        return 0.0
    variaciones = []
    for rasgo in RASGOS:
        medias = [fmean(p["estimado"][rasgo] for p in equipo) for equipo in equipos]
        centro = fmean(medias)
        variaciones.append(fmean((valor - centro) ** 2 for valor in medias) / 4.0)
    return fmean(variaciones)


def armar_equipos(personas, tipo, lecciones, tam=TAM_EQUIPO, semilla=0) -> list[list[dict]]:
    validar_personas(personas, publica=True)
    if tipo not in TIPOS_PROYECTO:
        raise ValueError(f"Tipo de proyecto desconocido: {tipo}")
    if not isinstance(tam, int) or isinstance(tam, bool) or tam < 1:
        raise ValueError("El tamaño de equipo debe ser un entero positivo")
    if not personas or len(personas) % tam:
        raise ValueError(f"El grupo de {len(personas)} personas debe ser divisible entre {tam}")
    relevantes = []
    for leccion in lecciones:
        validar_leccion(leccion)
        if leccion["tipo_proyecto"] in (tipo, "todos"):
            relevantes.append(leccion)
    rng = random.Random(semilla)
    mejor = None
    mejor_clave = None
    for _ in range(300 if relevantes else 1):
        orden = list(personas)
        rng.shuffle(orden)
        equipos = [orden[i:i + tam] for i in range(0, len(orden), tam)]
        if not relevantes:
            return equipos
        infracciones = sum(not cumple(equipo, leccion) for equipo in equipos for leccion in relevantes)
        clave = (infracciones, desequilibrio(equipos))
        if mejor_clave is None or clave < mejor_clave:
            mejor, mejor_clave = equipos, clave
    return mejor
