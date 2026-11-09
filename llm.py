"""Persona 3: alternativa determinista; integración LLM expresamente pendiente."""
from agentes.reflexionador import sacar_lecciones


def generar_lecciones(historial, personas, tipo, modo="determinista"):
    """No lee llaves ni activa servicios por variables de entorno implícitas."""
    if modo != "determinista":
        raise ValueError("Modo LLM no integrado. Selecciona 'determinista'; no requiere API ni red.")
    return sacar_lecciones(historial, personas, tipo)
