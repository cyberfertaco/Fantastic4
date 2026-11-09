# TEAMFORGE / Química

Responsable de documentación: Persona 4.

Demo de mejora iterativa autónoma de estrategias de formación de equipos. Usa
personas sintéticas, feedback de un simulador fijo y configuraciones JSON. No
reentrena un modelo, no modifica su código y no garantiza mejora fuera de estos
supuestos. El núcleo funciona sin API, red ni dependencias externas.

## Arranque

Requiere Python 3.11 o posterior. Ejecuta los comandos dentro de esta carpeta.
La instalación de Streamlit necesita red; después, la demo y la interfaz
funcionan localmente. Para ejecutar solo el núcleo, omite la instalación de UI.

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-ui.txt
python main.py demo
python main.py evolucion
python main.py aplicar --id demo-evolucion --tipo creativo --semilla 43
python -m unittest discover -s tests
streamlit run app.py
```

macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-ui.txt
python main.py demo
python main.py evolucion
python main.py aplicar --id demo-evolucion --tipo creativo --semilla 43
python -m unittest discover -s tests
streamlit run app.py
```

La interfaz se abre en `http://localhost:8501`. Si PowerShell impide activar un
script, ejecuta los comandos con `.\.venv\Scripts\python.exe` y abre la UI con
`.\.venv\Scripts\python.exe -m streamlit run app.py`; no es necesario cambiar
la política de ejecución.

```bash
python main.py lote --cantidad 50 --semilla 42
python main.py inspeccionar-lote ID_DEL_LOTE
python main.py inspeccionar-lote ID_DEL_LOTE --validar-equipos
python main.py lotes
python main.py --help
```

La UI también permite generar e inspeccionar lotes de 10, 24, 50, 100 y 500.
Los lotes se agregan; no reemplazan otros registros. Para repartir un grupo
completo en equipos de cuatro, su tamaño debe ser divisible entre cuatro.

## Qué queda guardado

- `resultados/metricas.json`: diez rondas con/sin memoria, perfiles finales y
  revelación de reglas sintéticas; mantiene exactamente las cuatro claves base.
- `biblioteca/lecciones.json`: reglas activas; `lecciones.estado.json` contiene
  historial previo y evidencia fuera del contrato de la lección.
- `datos/teamforge.sqlite3`: fuente de verdad para lotes, experimentos,
  evidencia, decisiones y versiones de la extensión.
- `resultados/evolucion.json`: exportación SQLite → JSON para el panel. Incluye
  manifiesto, candidatos aceptados y rechazados, pruebas y resultado reservado.
- `resultados/aplicacion.json`: una ejecución posterior con la versión activa,
  equipos formados, feedback y perfiles actualizados; no reabre la prueba final.

Una evaluación terminada se recupera del registro al ejecutar otra vez el
comando. No se ajustan estrategias con la prueba final. La comparación usa
poblaciones, perfiles congelados, semillas, lecciones y presupuesto iguales.
Si ninguna candidata pasa, se mantiene la versión anterior y se informa.

`.env.example` documenta el modo determinista. No se carga `.env`
automáticamente: las variables se definen en el proceso o la terminal. Esta
entrega no integra el SDK/API de OpenAI ni MCP; no requiere secretos.

## Propiedad y pruebas

| Persona | Archivos principales | Comprobaciones |
| --- | --- | --- |
| 1 | `config.py`, `contratos.py`, `main.py`, `agentes/constructor.py`, `agentes/evaluador.py`, `evolucion/motor.py`, `evolucion/validador.py` | Contratos, reparto, aislamiento, orquestación, aceptación/rechazo |
| 2 | `personas.py`, `simulador.py`, `almacenamiento.py`, `benchmark.py` | Rangos, RNG local, reproducción, persistencia, evaluación fija |
| 3 | `llm.py`, `agentes/reflexionador.py`, `agentes/curador.py`, `evolucion/builder.py`, `skills/formar-equipos/SKILL.md` | Feedback, identidad de lecciones, memoria previa, candidatos y regresiones |
| 4 | `app.py`, `.streamlit/config.toml`, `README.md`, `docs/demo.md` | Arranque de UI, gráficas y consulta de evidencia persistida |

Las pruebas del núcleo son `unittest` y se ejecutan sin instalar Streamlit.
Para un componente usa, por ejemplo, `python -m unittest tests.test_synthetic`.
Los módulos son `test_synthetic` (personas/simulador), `test_learning`
(constructor/reflexión/curador), `test_persistence` (SQLite), `test_benchmark`
(evaluación), `test_evolution` (motor/builder/validador) y `test_integration`
(contratos/orquestación).
Consulta [contratos](docs/contratos.md), [protocolo de evaluación](docs/evaluacion.md)
y [guion de demo](docs/demo.md). La interfaz muestra el tamaño de muestra y la
dispersión; los umbrales de esta demo no son garantías estadísticas universales.

## Trabajo en equipo

Antes de editar, lee `AGENTS.md` y los contratos congelados. Coordina cambios de
interfaces con Persona 1, trabaja en ramas por responsabilidad y vuelve a
ejecutar las pruebas al integrar. Un repositorio local no está publicado: el
equipo debe acordar y configurar su propio remoto, subir la rama inicial y
compartir su URL. No se incluye ni se supone ningún remoto. No se versionan
entornos virtuales, secretos ni bases SQLite generadas.

Las ampliaciones de perfiles, feedback humano, privacidad individual, LLM y
MCP quedan pendientes. Los resultados del simulador de cinco rasgos no validan
esas capacidades.
