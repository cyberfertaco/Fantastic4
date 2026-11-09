"""Persona 1: contratos JSON estrictos y frontera de datos observables."""
import copy
import hashlib
import json
import math
from config import RASGOS, TIPOS_PROYECTO


def huella(objeto):
    return hashlib.sha256(json.dumps(objeto, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _keys(objeto, keys, nombre):
    if not isinstance(objeto, dict) or set(objeto) != set(keys.split()):
        raise ValueError(f"{nombre}: campos exactos requeridos: {keys}")


def _numero(value, low=None, high=None, entero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Se requiere un número finito")
    if entero and not isinstance(value, int):
        raise ValueError("Se requiere un entero")
    if low is not None and value < low or high is not None and value > high:
        raise ValueError(f"Número fuera de rango [{low}, {high}]")


def _id(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Identificador/texto vacío o inválido")


def _ids(values):
    if not isinstance(values, list):
        raise ValueError("Se requiere una lista de identificadores")
    for value in values:
        _id(value)
    if len(set(values)) != len(values):
        raise ValueError("Referencias duplicadas")


def _header(obj):
    if type(obj["schema_version"]) is not int or obj["schema_version"] != 1:
        raise ValueError("schema_version no compatible")
    _id(obj["id"])
    _id(obj["owner"])


def validar_personas(personas, publica=False):
    if not isinstance(personas, list):
        raise ValueError("Personas debe ser una lista")
    ids = set()
    for persona in personas:
        keys = "id nombre declarado estimado" if publica else "id nombre declarado real estimado"
        _keys(persona, keys, "Persona")
        _id(persona["id"])
        _id(persona["nombre"])
        if persona["id"] in ids:
            raise ValueError("Identificadores de personas duplicados")
        ids.add(persona["id"])
        for perfil in (["declarado", "estimado"] if publica else ["declarado", "real", "estimado"]):
            _keys(persona[perfil], " ".join(RASGOS), perfil)
            for valor in persona[perfil].values():
                _numero(valor, 1, 5, entero=perfil != "estimado")


def vista_publica(personas):
    if not isinstance(personas, list):
        raise ValueError("Personas debe ser una lista")
    # Valida primero para no ocultar campos inesperados o errores de contrato.
    for p in personas:
        validar_personas([p], publica="real" not in p)
    resultado = [{k: copy.deepcopy(p[k]) for k in ("id", "nombre", "declarado", "estimado")}
                 for p in personas]
    validar_personas(resultado, publica=True)
    return resultado


def validar_leccion(leccion):
    _keys(leccion, "id tipo_proyecto rasgo umbral operador cantidad texto veces_vista veces_aplicada veces_ayudo", "Lección")
    _id(leccion["id"])
    _id(leccion["texto"])
    if leccion["tipo_proyecto"] not in TIPOS_PROYECTO + ["todos"]:
        raise ValueError("Tipo de proyecto inválido")
    if leccion["rasgo"] not in RASGOS or leccion["operador"] not in ("min", "max"):
        raise ValueError("Rasgo u operador inválido")
    _numero(leccion["umbral"], 1, 5)
    _numero(leccion["cantidad"], 0, entero=True)
    for k in ("veces_vista", "veces_aplicada", "veces_ayudo"):
        _numero(leccion[k], 0, entero=True)
    if leccion["veces_ayudo"] > leccion["veces_aplicada"]:
        raise ValueError("La ayuda no puede superar el uso")


def validar_estrategia(estrategia):
    _keys(estrategia, "schema_version id parent_id parameters search_budget lesson_ids owner", "Estrategia")
    _header(estrategia)
    if estrategia["parent_id"] is not None:
        _id(estrategia["parent_id"])
        if estrategia["parent_id"] == estrategia["id"]:
            raise ValueError("Una estrategia no puede ser su propio padre")
    _keys(estrategia["parameters"], "weights lesson_priorities", "Parámetros")
    weights = estrategia["parameters"]["weights"]
    _keys(weights, "lessons balance", "Pesos")
    for value in weights.values():
        _numero(value, 0, 1)
    if not math.isclose(sum(weights.values()), 1, abs_tol=1e-9):
        raise ValueError("Los pesos deben sumar uno")
    prioridades = estrategia["parameters"]["lesson_priorities"]
    if not isinstance(prioridades, dict):
        raise ValueError("Prioridades debe ser objeto")
    for key, value in prioridades.items():
        _id(key)
        _numero(value, 0.000001, 1000)
    _numero(estrategia["search_budget"], 1, 10000, entero=True)
    _ids(estrategia["lesson_ids"])


def validar_propuesta(propuesta):
    _keys(propuesta, "schema_version id parent_id strategy evidence_ids case_ids owner", "Propuesta")
    _header(propuesta)
    _id(propuesta["parent_id"])
    validar_estrategia(propuesta["strategy"])
    if propuesta["parent_id"] != propuesta["strategy"]["parent_id"]:
        raise ValueError("Padre de propuesta y estrategia no coincide")
    _ids(propuesta["evidence_ids"])
    _ids(propuesta["case_ids"])


def validar_caso(caso):
    _keys(caso, "schema_version id input condition evidence_ids expected owner", "Caso")
    _header(caso)
    entrada = caso["input"]
    _keys(entrada, "personas tipo lecciones semilla", "Entrada de caso")
    validar_personas(entrada["personas"], publica=True)
    if not entrada["personas"] or len(entrada["personas"]) % 4:
        raise ValueError("El caso necesita una población divisible entre 4")
    if entrada["tipo"] not in TIPOS_PROYECTO:
        raise ValueError("Tipo de proyecto inválido")
    _numero(entrada["semilla"], entero=True)
    if not isinstance(entrada["lecciones"], list):
        raise ValueError("Lecciones debe ser lista")
    for leccion in entrada["lecciones"]:
        validar_leccion(leccion)
    _keys(caso["condition"], "kind max_value", "Condición")
    if caso["condition"]["kind"] != "max_violations":
        raise ValueError("Condición no permitida")
    _numero(caso["condition"]["max_value"], 0, entero=True)
    _keys(caso["expected"], "previous_fails", "Resultado esperado")
    if type(caso["expected"]["previous_fails"]) is not bool:
        raise ValueError("previous_fails debe ser booleano")
    _ids(caso["evidence_ids"])


def validar_decision(decision):
    _keys(decision, "schema_version id proposal_id parent_id candidate_id accepted reasons comparison checks observed_state created_at owner", "Decisión")
    _header(decision)
    for k in ("proposal_id", "parent_id", "candidate_id", "created_at"):
        _id(decision[k])
    if type(decision["accepted"]) is not bool:
        raise ValueError("accepted debe ser booleano")
    if not isinstance(decision["reasons"], list) or not decision["reasons"]:
        raise ValueError("La decisión necesita razones")
    for reason in decision["reasons"]:
        _id(reason)
    for k in ("comparison", "checks", "observed_state"):
        if not isinstance(decision[k], dict):
            raise ValueError(f"{k} debe ser objeto")
