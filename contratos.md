# Contratos congelados — esquema 1

Propietario e integración: Persona 1. Fecha: 2026-11-09.
La interfaz Química del encargo se conserva. Persona tiene exactamente id,
nombre, declarado, real, estimado. La vista observable omite real y contiene
copias independientes. Lección tiene exactamente los diez campos originales.
Su identidad corregida es (tipo_proyecto, rasgo, operador, umbral, cantidad).
`Biblioteca.agregar` devuelve (lección almacenada, es_nueva). No había consumidor
v1 en este proyecto vacío. Evidencia se almacena fuera de la lección.

## Interfaces nuevas compartidas

Todas las entidades siguientes son JSON, con schema_version=1 y owner. Los
identificadores son strings no vacíos; no se incluye código ejecutable.

- Estrategia (Persona 3): `schema_version, id, parent_id, parameters,
  search_budget, lesson_ids, owner`. parent_id es string o null. parameters
  contiene exactamente `weights: {lessons, balance}` (no negativos, suma 1)
  y `lesson_priorities: {id_leccion: numero_positivo}`. search_budget=300 en
  comparaciones. lesson_ids lista de referencias; no filtra las lecciones
  disponibles: documenta la motivación. El motor consume prioridades y pesos.
- Propuesta (Persona 3): `schema_version, id, parent_id, strategy, evidence_ids,
  case_ids, owner`. strategy es la configuración completa; parent_id coincide.
- Caso (Persona 3): `schema_version, id, input, condition, evidence_ids, expected,
  owner`. input contiene `personas` observables, `tipo`, `lecciones`, `semilla`.
  condition = `{kind: "max_violations", max_value: entero>=0}`; expected =
  `{previous_fails: bool}`. Ejecutor fijo; cuenta incumplimientos por equipo.
- Decisión (Persona 1): `schema_version, id, proposal_id, parent_id,
  candidate_id, accepted, reasons, comparison, checks, observed_state,
  created_at, owner`. comparison incluye n, medias, dispersión, delta y
  por_tipo. checks registra contratos, presupuesto y regresiones. El estado
  observado incluye escenarios y huellas de perfiles; los snapshots completos
  se persisten con los experimentos/evidencias.

Funciones compartidas (no deben cambiar sin coordinar):

```python
# contratos.py
vista_publica(personas) -> list[dict]
validar_personas(personas, publica=False) -> None  # ValueError si inválido
validar_leccion(leccion) -> None
validar_estrategia(estrategia) -> None
validar_propuesta(propuesta) -> None
validar_caso(caso) -> None
validar_decision(decision) -> None
huella(objeto) -> str  # sha256 JSON canónico

# evolucion/motor.py: usa solo estimado; sin estado global de versión
estrategia_inicial() -> dict
formar_equipos(personas, tipo, lecciones, estrategia, tam=4, semilla=0) -> list[list[dict]]
contar_incumplimientos(equipos, lecciones) -> int
# evolucion/builder.py: no importa benchmark ni simulador
proponer(estrategia, evidencias, lecciones, ciclo=1) -> tuple[list[dict], list[dict]]
# evidencias son snapshots públicos de descubrimiento con campos:
# id,tipo,semilla,personas,lecciones,equipos(ids),resultados,strategy_id
# resultados son feedback observable; nunca reglas ocultas o real.
# evolucion/validador.py: importa benchmark para la comparación externa fija
ejecutar_caso(caso, estrategia) -> dict  # passed, violations, ...
validar(propuesta, anterior, escenarios, lecciones, casos, observed_state) -> dict
# no persistencia dentro del validador; caller guarda decisión

# benchmark.py (Persona 2)
crear_manifiesto(semilla=2026) -> dict
# manifest contiene schema_version,id,formula_version,policy,cycles,final
# cycles es lista de dos {cycle,discovery:[escenario],validation:[escenario]}
# escenario contiene id,split,tipo,semilla,personas (completas)
# discovery: >=5 semillas/tipo; validation: >=5 semillas/tipo; final >=5/tipo
# cada split usa poblaciones y semillas independientes prefijadas
evaluar_estrategia(estrategia, escenarios, lecciones) -> dict
# devuelve n,mean,stdev,by_type:{tipo:{n,mean,stdev}},scores:[{scenario_id,tipo,score}]
comparar(anterior, candidata, escenarios, lecciones) -> dict
# devuelve n,before,after,delta,by_type:{tipo:{before,after,delta,n}},paired_stdev

# almacenamiento.py (Persona 2): SQLite manda sobre extensión; exportación solo DB→JSON
class Almacen:
    def __init__(self, ruta="datos/teamforge.sqlite3"): ...
    def registrar_lote(self, n, semilla) -> dict: ...
    # retorno id,n,semilla,duplicate_attributes,created_at,personas
    def listar_lotes(self) -> list[dict]: ...  # metadatos, sin personas
    def personas_lote(self, lote_id) -> list[dict]: ...
    def guardar_experimento(self, experimento_id, datos) -> None: ...
    def cargar_experimento(self, experimento_id) -> dict | None: ...
    def guardar_evidencia(self, experimento_id, evidencia) -> None: ...
    def listar_evidencias(self, experimento_id) -> list[dict]: ...
    def guardar_version(self, estrategia) -> None: ...  # inmutable
    def listar_versiones(self) -> list[dict]: ...
    def activar_version(self, experimento_id, version_id) -> None: ...
    def version_activa(self, experimento_id) -> dict | None: ...
    def guardar_decision(self, experimento_id, decision) -> None: ...
    def listar_decisiones(self, experimento_id) -> list[dict]: ...
    def exportar_experimento(self, experimento_id, ruta="resultados/evolucion.json") -> None: ...
```

La política fija vive en benchmark: mejora >=2, caída por tipo <=2, presupuesto
300, máximo 3 candidatos/ciclo, máximo 2 ciclos. La prueba final se consume una
vez después de elegir. No es entrada del builder. La comparación congela los
perfiles observables y usa misma población, lecciones, RNG y presupuesto.

El JSON base tiene exactamente con_memoria, sin_memoria, personas,
reglas_ocultas. Evolución es una exportación separada con schema_version,
experiment_id, mode, manifest, cycles, active_version, versions, decisions,
evidence, cases, final_result, mechanism_rejection, created_at, updated_at.
El JSON base es la salida del experimento longitudinal; los JSON base de
personas y biblioteca conservan sus funciones públicas. SQLite manda sobre
lotes, experimentos, evidencia, decisiones y versiones de la extensión.

Servicio (main.py, Persona 1): `ejecutar_demo(semilla=42)`,
`ejecutar_evolucion(experimento_id="demo-evolucion", semilla=2026, reiniciar=False)`,
`generar_lote(n, semilla)`. app.py llama este servicio y vuelve a leer JSON/DB.

Aplicación posterior (Persona 1): `aplicar_vigente(experimento_id="demo-evolucion",
tipo="creativo", semilla=43, lote_id=None)` carga la referencia activa desde
SQLite y forma equipos nuevos. Guarda un registro de evidencia con
schema_version=1, id, experiment_id, split="application", strategy_id, tipo,
semilla, personas observables previas, lecciones, equipos (IDs), resultados,
updated_profiles, observed_at, updated_at, simulation_seeds, score_promedio
e interpretation. `resultados/aplicacion.json` exporta ese registro.
La actualización de perfiles vive en el registro de ejecución; no sobrescribe
el lote original. Esta aplicación no usa la prueba reservada ni selecciona
otra estrategia. Cada experimento de evaluación conserva el límite de dos
ciclos; `--id` nuevo permite una repetición independiente, `--reiniciar` repite
explícitamente solo el experimento nombrado.
