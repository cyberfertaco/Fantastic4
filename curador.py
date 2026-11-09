"""Persona 3: biblioteca JSON, identidad completa y ayuda frente al historial previo."""
import copy
import json
from collections import defaultdict
from statistics import fmean

from config import TIPOS_PROYECTO, ruta_proyecto
from contratos import validar_leccion


def _identidad(leccion):
    return tuple(leccion[campo] for campo in ("tipo_proyecto", "rasgo", "operador", "umbral", "cantidad"))


class Biblioteca:
    def __init__(self, ruta="biblioteca/lecciones.json"):
        self.ruta = ruta_proyecto(ruta)
        self.ruta_estado = self.ruta.with_name(self.ruta.stem + ".estado.json")
        self.lecciones = json.loads(self.ruta.read_text(encoding="utf-8")) if self.ruta.exists() else []
        for leccion in self.lecciones:
            validar_leccion(leccion)
        if len({_identidad(l) for l in self.lecciones}) != len(self.lecciones):
            raise ValueError("Biblioteca con identidades de lección duplicadas")
        estado = json.loads(self.ruta_estado.read_text(encoding="utf-8")) if self.ruta_estado.exists() else {}
        self.historial = estado.get("historial", {tipo: {"sum": 0.0, "count": 0} for tipo in TIPOS_PROYECTO})
        self.evidencias = estado.get("evidencias", {})

    def agregar(self, leccion) -> tuple[dict, bool]:
        validar_leccion(leccion)
        for existente in self.lecciones:
            if _identidad(existente) == _identidad(leccion):
                existente["veces_vista"] += 1
                return existente, False
            if existente["id"] == leccion["id"]:
                raise ValueError("Un identificador no puede representar dos reglas diferentes")
        almacenada = copy.deepcopy(leccion)
        self.lecciones.append(almacenada)
        return almacenada, True

    def relevantes(self, tipo) -> list[dict]:
        if tipo not in TIPOS_PROYECTO:
            raise ValueError(f"Tipo de proyecto desconocido: {tipo}")
        return [leccion for leccion in self.lecciones if leccion["tipo_proyecto"] in (tipo, "todos")]

    def agregar_evidencia(self, leccion_id, evidencia):
        if not any(l["id"] == leccion_id for l in self.lecciones):
            raise ValueError("No se puede asociar evidencia a una lección inexistente")
        self.evidencias.setdefault(leccion_id, []).append(copy.deepcopy(evidencia))

    def registrar_uso(self, lecciones, resultados) -> None:
        por_tipo = defaultdict(list)
        for resultado in resultados:
            if resultado["tipo"] not in TIPOS_PROYECTO:
                raise ValueError("Tipo de proyecto desconocido en resultados")
            por_tipo[resultado["tipo"]].append(resultado["score"])
        ids = {leccion["id"] for leccion in lecciones}
        for leccion in self.lecciones:
            if leccion["id"] not in ids:
                continue
            for tipo, scores in por_tipo.items():
                if leccion["tipo_proyecto"] not in (tipo, "todos"):
                    continue
                previo = self.historial[tipo]
                leccion["veces_aplicada"] += 1
                if previo["count"] and fmean(scores) >= previo["sum"] / previo["count"]:
                    leccion["veces_ayudo"] += 1
        # Ningún resultado del batch actual entra en su propio referente.
        for tipo, scores in por_tipo.items():
            self.historial[tipo]["sum"] += sum(scores)
            self.historial[tipo]["count"] += len(scores)

    def podar(self) -> None:
        self.lecciones = [l for l in self.lecciones if not (l["veces_aplicada"] >= 3 and l["veces_ayudo"] == 0)]
        # Se conserva evidencia archivada incluso si se retira la regla.

    def guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        estado = {"schema_version": 1, "historial": self.historial, "evidencias": self.evidencias}
        for destino, contenido in ((self.ruta, self.lecciones), (self.ruta_estado, estado)):
            temporal = destino.with_suffix(destino.suffix + ".tmp")
            temporal.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8")
            temporal.replace(destino)
