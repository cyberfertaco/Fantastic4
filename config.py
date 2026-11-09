"""Persona 1: constantes compartidas y rutas relativas al proyecto."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RASGOS = ["creatividad", "organizacion", "liderazgo", "extroversion", "cumplimiento"]
TIPOS_PROYECTO = ["creativo", "tecnico", "entrega_rapida"]
TAM_EQUIPO = 4
N_PERSONAS = 24
RONDAS = 10
SCHEMA_VERSION = 1
SEARCH_BUDGET = 300

def ruta_proyecto(ruta):
    ruta = Path(ruta)
    return ruta if ruta.is_absolute() else ROOT / ruta
