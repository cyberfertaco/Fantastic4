"""Persona 3: actualización observable e hipótesis asociativas con evidencia."""
import hashlib
import json
import math
import re
from functools import lru_cache
from statistics import fmean

from config import RASGOS, ROOT, TIPOS_PROYECTO
from contratos import validar_leccion, validar_personas


def _sin_ocultos(objeto):
    if isinstance(objeto, dict):
        if set(objeto) & {"real", "reglas_ocultas"}:
            raise ValueError("La reflexión solo recibe información observable")
        for valor in objeto.values():
            _sin_ocultos(valor)
    elif isinstance(objeto, list):
        for valor in objeto:
            _sin_ocultos(valor)


@lru_cache(maxsize=1)
def cargar_politica_skill():
    """Lee parámetros declarativos del skill local, con esquema cerrado."""
    contenido = (ROOT / "skills/formar-equipos/SKILL.md").read_text(encoding="utf-8")
    bloque = re.search(r"```json\s*(.*?)\s*```", contenido, re.DOTALL)
    if bloque is None:
        raise ValueError("El skill no contiene una política JSON")
    politica = json.loads(bloque.group(1))
    esperada = {"schema_version": 1, "umbral": 4, "cantidades": [0, 1, 2, 3],
                "operadores": ["min", "max"], "minimo_por_grupo": 3, "diferencia_minima": 8}
    if politica != esperada:
        raise ValueError("La política del skill no coincide con el contrato congelado")
    return politica


def actualizar_perfiles(personas, resultados, alpha=0.3) -> None:
    validar_personas(personas, publica=True)
    _sin_ocultos(resultados)
    if not isinstance(alpha, (int, float)) or isinstance(alpha, bool) or not math.isfinite(alpha) or not 0 <= alpha <= 1:
        raise ValueError("alpha debe estar entre 0 y 1")
    indice = {p["id"]: p for p in personas}
    actualizaciones = []
    for resultado in resultados:
        miembros = resultado["miembros"]
        if len(set(miembros)) != len(miembros) or set(resultado["feedback"]) != set(miembros):
            raise ValueError("El feedback debe corresponder exactamente a los miembros")
        for identificador, feedback in resultado["feedback"].items():
            if identificador not in indice or set(feedback) != set(RASGOS):
                raise ValueError("Feedback con persona o rasgos desconocidos")
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 1 <= v <= 5 for v in feedback.values()):
                raise ValueError("El feedback debe contener números finitos entre 1 y 5")
            actualizaciones.append((indice[identificador], feedback))
    # Valida todo antes de mutar para no dejar una actualización parcial.
    for persona, feedback in actualizaciones:
        for rasgo in RASGOS:
            persona["estimado"][rasgo] = (1 - alpha) * persona["estimado"][rasgo] + alpha * feedback[rasgo]


def _observaciones(historial, personas, tipo):
    validar_personas(personas, publica=True)
    _sin_ocultos(historial)
    indice = {p["id"]: p["estimado"] for p in personas}
    observaciones = []
    for i, resultado in enumerate(historial):
        if resultado["tipo"] != tipo:
            continue
        snapshot = resultado.get("perfiles_observados")
        perfiles = snapshot if snapshot is not None else indice
        if any(identificador not in perfiles for identificador in resultado["miembros"]):
            raise ValueError("Faltan perfiles observados para reconstruir un resultado")
        score = resultado["score"]
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 100:
            raise ValueError("Score fuera del rango 0–100")
        observaciones.append({
            "id": resultado.get("id", f"resultado-{i}"),
            "score": score,
            "perfiles": [perfiles[identificador] for identificador in resultado["miembros"]],
            "retrospectivo": snapshot is None,
        })
    return observaciones


def _estadisticas(observaciones, leccion):
    cumplen, incumplen = [], []
    for observacion in observaciones:
        cantidad = sum(p[leccion["rasgo"]] >= leccion["umbral"] for p in observacion["perfiles"])
        cumple = cantidad >= leccion["cantidad"] if leccion["operador"] == "min" else cantidad <= leccion["cantidad"]
        (cumplen if cumple else incumplen).append(observacion)
    media_si = fmean(o["score"] for o in cumplen) if cumplen else None
    media_no = fmean(o["score"] for o in incumplen) if incumplen else None
    return {
        "n_cumplen": len(cumplen), "n_incumplen": len(incumplen),
        "media_cumplen": media_si, "media_incumplen": media_no,
        "diferencia": media_si - media_no if media_si is not None and media_no is not None else None,
        "resultados_cumplen": [o["id"] for o in cumplen],
        "resultados_incumplen": [o["id"] for o in incumplen],
        "retrospectivo": any(o["retrospectivo"] for o in observaciones),
        "interpretacion": "Asociación sintética; no demuestra causalidad",
    }


def evidencia_leccion(historial, personas, leccion):
    validar_leccion(leccion)
    tipos = TIPOS_PROYECTO if leccion["tipo_proyecto"] == "todos" else [leccion["tipo_proyecto"]]
    observaciones = [o for tipo in tipos for o in _observaciones(historial, personas, tipo)]
    return {"lesson_id": leccion["id"], **_estadisticas(observaciones, leccion)}


def sacar_lecciones(historial: list[dict], personas, tipo) -> list[dict]:
    if tipo not in TIPOS_PROYECTO:
        raise ValueError(f"Tipo de proyecto desconocido: {tipo}")
    politica = cargar_politica_skill()
    observaciones = _observaciones(historial, personas, tipo)
    lecciones = []
    for rasgo in RASGOS:
        for operador in politica["operadores"]:
            for cantidad in politica["cantidades"]:
                identidad = (tipo, rasgo, operador, politica["umbral"], cantidad)
                identificador = "lec-" + hashlib.sha256(json.dumps(identidad).encode()).hexdigest()[:16]
                leccion = {
                    "id": identificador, "tipo_proyecto": tipo, "rasgo": rasgo,
                    "umbral": politica["umbral"], "operador": operador, "cantidad": cantidad,
                    "texto": "", "veces_vista": 1, "veces_aplicada": 0, "veces_ayudo": 0,
                }
                evidencia = _estadisticas(observaciones, leccion)
                if (evidencia["n_cumplen"] < politica["minimo_por_grupo"]
                        or evidencia["n_incumplen"] < politica["minimo_por_grupo"]
                        or evidencia["diferencia"] <= politica["diferencia_minima"]):
                    continue
                comparador = "al menos" if operador == "min" else "como máximo"
                leccion["texto"] = (
                    f"Hipótesis: {comparador} {cantidad} miembros con {rasgo} >= {politica['umbral']} "
                    f"se asocia a +{evidencia['diferencia']:.2f} puntos en {tipo}; "
                    f"n={evidencia['n_cumplen']}/{evidencia['n_incumplen']}. No demuestra causalidad."
                )
                validar_leccion(leccion)
                lecciones.append(leccion)
    return lecciones
