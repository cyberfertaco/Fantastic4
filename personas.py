"""Persona 2: personas sintéticas reproducibles y persistencia JSON base.

La generación no representa una población humana validada. Los identificadores
son locales a una generación; Almacen los cualifica al registrar cada lote.
"""
import json
import random

from config import N_PERSONAS, RASGOS, ruta_proyecto


def generar_personas(n=N_PERSONAS, semilla=42) -> list[dict]:
    """Genera n perfiles; un tercio sobrevalora y un sexto subvalora.

    Se alteran entre uno y tres rasgos en la dirección asignada, con recorte
    1–5. Los grupos se barajan para no asociar el sesgo con el identificador.
    """
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError("n debe ser un entero positivo.")
    if isinstance(semilla, bool) or not isinstance(semilla, int):
        raise ValueError("semilla debe ser un entero.")
    rng = random.Random(semilla)
    estados = [1] * (n // 3) + [-1] * (n // 6)
    estados += [0] * (n - len(estados))
    rng.shuffle(estados)
    personas = []
    for indice, estado in enumerate(estados, 1):
        real = {rasgo: rng.randint(1, 5) for rasgo in RASGOS}
        if estado:
            elegibles = [r for r in RASGOS if (real[r] < 5 if estado > 0 else real[r] > 1)]
            # En los extremos uniformes garantiza un sesgo observable sin
            # generar declaraciones fuera de rango; es parte del generador.
            if not elegibles:
                rasgo = rng.choice(RASGOS)
                real[rasgo] = 4 if estado > 0 else 2
                elegibles = [rasgo]
        declarado = real.copy()
        if estado:
            seleccion = rng.sample(elegibles, rng.randint(1, min(3, len(elegibles))))
            for rasgo in seleccion:
                declarado[rasgo] = min(5, max(1, real[rasgo] + estado * rng.randint(1, 2)))
        personas.append({
            "id": f"p{indice:04d}",
            "nombre": f"Persona sintética {indice:03d}",
            "declarado": declarado,
            "real": real,
            "estimado": declarado.copy(),
        })
    return personas


def guardar(personas, ruta="datos/personas.json"):
    """Guarda la entidad base JSON; no escribe en SQLite."""
    from contratos import validar_personas
    validar_personas(personas)
    destino = ruta_proyecto(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(destino.suffix + ".tmp")
    temporal.write_text(json.dumps(personas, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(destino)


def cargar(ruta="datos/personas.json") -> list[dict]:
    """Carga y valida perfiles; propaga errores de archivo o contrato."""
    from contratos import validar_personas
    personas = json.loads(ruta_proyecto(ruta).read_text(encoding="utf-8"))
    validar_personas(personas)
    return personas
