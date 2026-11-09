"""Persona 4: recorrido guiado y consulta de evidencia; las escrituras usan main."""
import json
import math
import sqlite3
import threading
from datetime import datetime
from statistics import fmean

import streamlit as st

from contratos import (validar_leccion, validar_personas, validar_estrategia,
                       validar_decision, validar_caso)
from config import ROOT

st.set_page_config(page_title="TEAMFORGE · Equipos con evidencia", page_icon="⚗️", layout="wide")
# Solo clases propias y elementos HTML estándar; sin clases internas de Streamlit.
st.markdown("""<style>
.tf-eyebrow {color:#a9ebd6;font-size:.8rem;font-weight:650;letter-spacing:.13em;margin-top:1rem}
.tf-intro {font-size:1.15rem;line-height:1.65;max-width:760px;color:#d1e0df}
.tf-tag {display:inline-block;border:1px solid #53766d;border-radius:30px;padding:.3rem .7rem;
font-size:.8rem;color:#c6eedc;margin:.3rem .4rem .8rem 0}
button[kind="primary"] {color:#10251c!important}
h1 {letter-spacing:-.04em} h2,h3 {letter-spacing:-.02em}
button:focus-visible,a:focus-visible,input:focus-visible,[role="radio"]:focus-visible,
[role="combobox"]:focus-visible {outline:3px solid #d2ebff!important;outline-offset:3px!important}
@media(max-width:600px){.tf-intro{font-size:1rem}.tf-eyebrow{letter-spacing:.06em}}
</style>""", unsafe_allow_html=True)

PAGES = ["Inicio", "1 · Simular equipos", "2 · Comparar estrategias", "3 · Entender la evidencia", "Perfiles y lotes"]
TIPOS = {"creativo": "Creativo", "tecnico": "Técnico", "entrega_rapida": "Entrega rápida", "todos": "Todos"}
ERRORS = []


def numero(value, digits=2, sign=False):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return (f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}").replace(".", ",")
    return "—"


def fecha(value):
    try:
        # Mantiene zona explícita para que el registro no parezca una hora local.
        return datetime.fromisoformat(value).strftime("%d/%m/%Y · %H:%M UTC")
    except (ValueError, TypeError):
        return "Fecha no disponible"


def fallo(contexto, error, recovery):
    st.error(contexto)
    st.write(recovery)
    with st.expander("Detalles técnicos para el equipo"):
        st.code(f"{type(error).__name__}: {error}", language="text")


def leer_json(path, expected=dict):
    try:
        archivo = ROOT / path
        if not archivo.exists():
            return None
        data = json.loads(archivo.read_text(encoding="utf-8"))
        if not isinstance(data, expected):
            raise ValueError("El formato del archivo no coincide con la vista esperada.")
        if path.endswith("metricas.json"):
            for key in ("con_memoria", "sin_memoria"):
                if not isinstance(data.get(key), list) or not data[key]:
                    raise ValueError("Faltan rondas válidas de la simulación.")
                for row in data[key]:
                    for field in ("ronda", "score_promedio", "error_perfiles", "lecciones"):
                        if not isinstance(row.get(field), (float, int)) or not math.isfinite(row[field]):
                            raise ValueError(f"La ronda no contiene un valor válido de {field}.")
                    if row.get("tipo") not in TIPOS:
                        raise ValueError("Tipo de proyecto desconocido.")
            if not isinstance(data.get("personas"), list) or not isinstance(data.get("reglas_ocultas"), list):
                raise ValueError("Faltan perfiles o reglas de la simulación.")
        if path.endswith("lecciones.json"):
            for lesson in data:
                validar_leccion(lesson)
        if path.endswith("metricas.json"):
            validar_personas(data["personas"])
        if path.endswith("evolucion.json"):
            for key in ("cycles", "decisions", "versions", "lessons", "cases", "evidence"):
                if not isinstance(data.get(key), list) or any(not isinstance(x, dict) for x in data[key]):
                    raise ValueError(f"La evaluación no contiene una lista válida de {key}.")
            for key in ("manifest", "final_result", "lesson_evidence"):
                if not isinstance(data.get(key), dict):
                    raise ValueError(f"La evaluación no contiene un objeto válido de {key}.")
            for version in data["versions"]:
                validar_estrategia(version)
            for decision in data["decisions"]:
                validar_decision(decision)
            for case in data["cases"]:
                validar_caso(case)
            if not isinstance(data["manifest"].get("policy", {}), dict):
                raise ValueError("La política de evaluación tiene un formato inválido.")
            if data.get("active_version"):
                validar_estrategia(data["active_version"])
            for lesson in data["lessons"]:
                validar_leccion(lesson)
        return data
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
        ERRORS.append((path, error))
        return None


def leer_db(query, params=()):
    """Consulta de presentación en modo solo lectura; no crea ni cambia registros."""
    path = ROOT / "datos/teamforge.sqlite3"
    if not path.exists():
        return []
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(query, params)]
    except (sqlite3.Error, OSError) as error:
        ERRORS.append(("datos/teamforge.sqlite3", error))
        return []


def ir(page):
    st.session_state["nav"] = page


def elegir(label, options, key, format_func=str):
    """Estado durable independiente de la limpieza de widgets al cambiar de página."""
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[0]
    widget = "_" + key
    st.session_state[widget] = st.session_state[key]
    def guardar():
        st.session_state[key] = st.session_state[widget]
    return st.selectbox(label, options, key=widget, format_func=format_func, on_change=guardar)


def semilla_input():
    key = "lote_semilla"
    st.session_state.setdefault(key, 42)
    st.session_state["_" + key] = st.session_state[key]
    def guardar():
        st.session_state[key] = st.session_state["_" + key]
    return st.number_input("Semilla para reproducir los perfiles", min_value=0, max_value=2147483647,
                           step=1, key="_" + key, on_change=guardar,
                           help="Un entero como 42. La misma cantidad y semilla repiten atributos; cada lote recibe identificadores nuevos.")


@st.cache_resource
def bloqueo_escritura():
    # Serializa escrituras de esta instancia de la interfaz entre sesiones.
    return threading.Lock()


def servicio(nombre, request, destino, **kwargs):
    """Solo un clic explícito llama al servicio. Nunca se invoca al navegar."""
    completed = st.session_state.setdefault("completed_requests", [])
    if request in completed:
        return
    lock = bloqueo_escritura()
    if not lock.acquire(blocking=False):
        st.session_state["service_error"] = (
            "Hay otra operación guardando resultados.", "Espera a que termine y vuelve a pulsar el botón.", "Operación en curso")
        return
    try:
        import main
        messages = {"ejecutar_demo": "Formando equipos y guardando 10 rondas…",
                    "ejecutar_evolucion": "Consultando el registro o comparando estrategias y guardando decisiones…",
                    "generar_lote": "Generando perfiles y guardando el lote…"}
        with st.spinner(messages[nombre]):
            result = getattr(main, nombre)(**kwargs)
        completed.append(request)
        st.session_state.pop("service_error", None)
        if nombre == "generar_lote":
            st.session_state["lote_seleccionado"] = result["id"]
            message = f"Lote {result['id']} guardado: {result['n']} perfiles. Puedes inspeccionarlo abajo; los lotes anteriores siguen disponibles."
        elif nombre == "ejecutar_demo":
            message = "Simulación guardada. Compara las dos gráficas y después revisa las estrategias."
        else:
            message = "Evaluación disponible. Revisa la configuración vigente y el resultado de la prueba reservada."
        st.session_state["notice"] = message
        st.session_state["nav"] = destino
    except Exception as error:
        # Los servicios pueden dejar un experimento incompleto. No reintentar automáticamente.
        recovery = ("Revisa si el experimento quedó incompleto en esta pantalla. Si aparece así, conserva el registro y usa otro ID desde la terminal."
                    if nombre == "ejecutar_evolucion" else
                    "Comprueba que la carpeta datos y la carpeta de resultados permitan escritura. Revisa los registros guardados antes de volver a intentarlo.")
        st.session_state["service_error"] = ("No se pudo completar la operación.", recovery, f"{type(error).__name__}: {error}")
    finally:
        lock.release()


def descargar(label, data, filename, key):
    st.download_button(label, json.dumps(data, ensure_ascii=False, indent=2), filename,
                       "application/json", key=key, on_click="ignore")


def siguiente(label, page, key):
    st.button(label, key=key, on_click=ir, args=(page,), type="primary")


def perfiles(personas, perfil="estimado"):
    return [{"Persona": p.get("nombre", "—"), "Identificador": p.get("id", "—"),
             **{r.capitalize(): v for r, v in p.get(perfil, {}).items()}} for p in personas]


def comparacion(data, after="Propuesta"):
    if not data:
        st.info("No se realizó una comparación de puntuaciones para esta decisión. Consulta el motivo del rechazo.")
        return
    before = data.get("before", {})
    after_data = data.get("after", {})
    a, b, c = st.columns(3)
    a.metric("Referencia · puntos / 100", numero(before.get("mean")))
    b.metric(f"{after} · puntos / 100", numero(after_data.get("mean")))
    c.metric("Diferencia · puntos", numero(data.get("delta"), sign=True))
    st.caption(f"Más puntuación es mejor. {data.get('n', '—')} escenarios comparados en las mismas condiciones. "
               f"Variación de las diferencias (desviación estándar): {numero(data.get('paired_stdev'))} puntos. No es una garantía estadística.")
    st.dataframe([{"Proyecto": TIPOS.get(t, t), "Referencia / 100": d.get("before"),
                   f"{after} / 100": d.get("after"), "Diferencia en puntos": d.get("delta"),
                   "Escenarios": d.get("n")} for t, d in data.get("by_type", {}).items()], hide_index=True, width="stretch")


metricas = leer_json("resultados/metricas.json")
evolucion = leer_json("resultados/evolucion.json")
aplicacion = leer_json("resultados/aplicacion.json")
lecciones = leer_json("biblioteca/lecciones.json", list) or []
estado_biblioteca = leer_json("biblioteca/lecciones.estado.json") or {}
lotes = leer_db("SELECT id,n,semilla,duplicate_attributes,created_at FROM lotes ORDER BY seq")
registros = leer_db("SELECT id,data FROM experimentos WHERE id=?", ("demo-evolucion",))
registrado = None
try:
    registrado = json.loads(registros[0]["data"]) if registros else None
    if registrado is not None and not isinstance(registrado, dict):
        raise ValueError("El registro de evaluación tiene un formato inválido.")
except (ValueError, TypeError) as error:
    registrado = None
    ERRORS.append(("Registro de evaluación", error))
# La evaluación base puede existir en DB aun si la exportación falta o quedó obsoleta.
incompleto = bool(registrado and not registrado.get("final_result", {}).get("executed_once"))
final = evolucion.get("final_result", {}) if evolucion else {}
decisiones = [d for d in evolucion.get("decisions", []) if not d.get("observed_state", {}).get("mechanism_test")] if evolucion else []
activa = evolucion.get("active_version") or {} if evolucion else {}
versiones = {v["id"]: v for v in evolucion.get("versions", [])} if evolucion else {}
version_nombres = {v: ("Inicial" if not obj.get("parent_id") else f"Configuración {i}") for i, (v, obj) in enumerate(versiones.items())}

def version_label(vid):
    return version_nombres.get(vid, "Configuración sin etiqueta")


def boton_evaluar(key):
    disabled = incompleto or any("sqlite3" in p for p, _ in ERRORS)
    label = "Recuperar evaluación guardada" if registrado else "Comparar estrategias en 2 ciclos"
    request = "evolucion-default"
    # Una exportación eliminada se puede recuperar sin volver a evaluar la reserva.
    if evolucion is None and registrado and not incompleto:
        request += "-recuperar"
    st.button(label, type="primary", key=key, disabled=disabled,
              on_click=servicio, args=("ejecutar_evolucion", request, PAGES[2]))
    if incompleto:
        st.warning("La evaluación guardada quedó incompleta. No se volverá a ejecutar la prueba reservada automáticamente.")
        st.write("Para conservar ese registro y empezar otro experimento, usa un nombre nuevo desde la terminal:")
        st.code("python main.py evolucion --id nuevo-ensayo")
    elif disabled:
        st.caption("La acción está deshabilitada porque no se puede leer la base de datos. Consulta el error de lectura.")
    else:
        st.caption("Usa sus propias poblaciones sintéticas. Si ya terminó, recupera el registro sin repetir la prueba final.")


with st.sidebar:
    st.markdown("### TEAMFORGE")
    st.caption("Equipos con evidencia")
    st.radio("Tu recorrido", PAGES, key="nav")
    st.divider()
    st.markdown("**Datos simulados · sin API**")
    st.caption("No necesitas cargar personas ni configurar una llave para comenzar.")
    st.caption("La herramienta ajusta configuraciones de equipos. No reentrena un modelo.")

page = st.session_state["nav"]
st.markdown('<div class="tf-eyebrow">TEAMFORGE / LABORATORIO DE EQUIPOS</div>', unsafe_allow_html=True)
if st.session_state.get("notice"):
    st.success(st.session_state.pop("notice"))
if st.session_state.get("service_error"):
    title, recovery, technical = st.session_state["service_error"]
    st.error(title)
    st.write(recovery)
    with st.expander("Detalles técnicos de la operación"):
        st.code(technical, language="text")
    st.button("Cerrar aviso de error", on_click=lambda: st.session_state.pop("service_error", None))
for path, error in ERRORS:
    fallo("No se pudo leer un resultado guardado.", error,
          "Conserva una copia del archivo y restaura un respaldo válido. Si solo falta la exportación de evaluación, recupérala desde Comparar estrategias.")
    st.caption(f"Archivo o registro afectado: {path}")

if page == PAGES[0]:
    st.title("Forma equipos. Comprueba qué funciona.")
    st.markdown('<p class="tf-intro">TEAMFORGE forma equipos de personas ficticias, observa cómo les va y prueba nuevas formas de agruparlas antes de cambiar la estrategia.</p>', unsafe_allow_html=True)
    st.markdown('<span class="tf-tag">Datos sintéticos</span><span class="tf-tag">Resultados verificables</span><span class="tf-tag">Sin llave de API</span>', unsafe_allow_html=True)
    with st.container(border=True):
        st.subheader("Empieza con una simulación", anchor=False)
        st.write("La demo prepara 24 personas y compara 10 rondas con y sin memoria. No tienes que introducir datos.")
        if metricas:
            st.caption(f"Ya hay {len(metricas['con_memoria'])} rondas guardadas. Puedes explorarlas sin ejecutar nada otra vez.")
            siguiente("Ver los resultados guardados", PAGES[1], "home_demo")
        else:
            st.button("Simular 10 rondas con 24 personas", type="primary", key="home_run",
                      on_click=servicio, args=("ejecutar_demo", "demo-inicial", PAGES[1]))
    for title, description in [
        ("1 · Observa el resultado", "Compara la puntuación de los equipos y la precisión de sus perfiles."),
        ("2 · Comprueba las propuestas", "Un evaluador fijo decide qué configuraciones cumplen los controles."),
        ("3 · Revisa por qué", "Sigue las observaciones que sustentan cada lección y decisión.")]:
        st.markdown(f"**{title}**")
        st.write(description)
    st.caption("Los lotes son grupos adicionales de perfiles para explorar. No alimentan automáticamente la demo ni la evaluación.")

elif page == PAGES[1]:
    st.title("1 · Observa cómo funcionan los equipos")
    st.write("Con memoria, los perfiles se ajustan con las observaciones del simulador y se guardan lecciones. Sin memoria, los equipos se forman al azar y los perfiles no se ajustan.")
    if not metricas:
        st.info("Aún no hay una simulación que mostrar. La demo genera los datos necesarios.")
        st.button("Simular 10 rondas con 24 personas", type="primary", key="simular",
                  on_click=servicio, args=("ejecutar_demo", "demo-inicial", PAGES[1]))
    else:
        con, sin = metricas["con_memoria"], metricas["sin_memoria"]
        delta = fmean(r["score_promedio"] for r in con) - fmean(r["score_promedio"] for r in sin)
        st.subheader("Qué ocurrió", anchor=False)
        st.write(f"En las {len(con)} rondas guardadas, la diferencia media con memoria fue de **{numero(delta, sign=True)} puntos sobre 100** frente a la referencia sin memoria.")
        st.caption("La comparación combina actualización de perfiles y uso de lecciones; no demuestra por sí sola que una estrategia sea mejor.")
        a, b, c = st.columns(3)
        a.metric("Media con memoria · / 100", numero(fmean(r["score_promedio"] for r in con)))
        b.metric("Media sin memoria · / 100", numero(fmean(r["score_promedio"] for r in sin)))
        c.metric("Personas simuladas", len(metricas["personas"]))
        reference = {r["ronda"]: r for r in sin}
        for field, title, explanation in [
            ("score_promedio", "Puntuación de los equipos", "De 0 a 100 puntos. Más alto es mejor. Cada punto resume una ronda de equipos."),
            ("error_perfiles", "Error de los perfiles estimados", "Diferencia media absoluta entre el perfil estimado y el real sintético, en rasgos de 1 a 5. Más bajo es mejor.")]:
            st.subheader(title, anchor=False)
            st.caption(explanation)
            rows = [{"Ronda": r["ronda"], "Con memoria": r[field], "Sin memoria": reference.get(r["ronda"], {}).get(field)} for r in con]
            st.line_chart(rows, x="Ronda", y=["Con memoria", "Sin memoria"], color=["#9debba", "#d1ad83"], height=270)
        st.caption("Las rondas alternan proyectos creativos, técnicos y de entrega rápida. No se espera una curva que siempre suba.")
        siguiente("Siguiente: comprobar las estrategias", PAGES[2], "sim_next")
        with st.expander("Rondas y exportación"):
            st.dataframe([{"Escenario": label, "Ronda": r["ronda"], "Proyecto": TIPOS[r["tipo"]],
                           "Puntuación / 100": r["score_promedio"], "Error de perfiles": r["error_perfiles"],
                           "Lecciones": r["lecciones"]} for label, rows in [("Con memoria", con), ("Sin memoria", sin)] for r in rows], hide_index=True, width="stretch")
            descargar("Descargar las métricas (JSON)", metricas, "metricas.json", "download_metrics")
        with st.expander("Volver a generar la demo"):
            st.write("Reemplaza las rondas, perfiles y biblioteca de esta demo. Conserva los lotes y las versiones de estrategias.")
            confirm = st.checkbox("Quiero reemplazar los resultados de la demo", key="confirm_demo")
            repeated = "demo-repetida" in st.session_state.get("completed_requests", [])
            st.button("Repetir las 10 rondas", disabled=not confirm or repeated, key="repeat_demo", on_click=servicio,
                      args=("ejecutar_demo", "demo-repetida", PAGES[1]))
            if repeated:
                st.caption("Ya se repitió la demo en esta sesión; los resultados están guardados. Para otra repetición explícita usa python main.py demo desde la terminal.")
            elif not confirm:
                st.caption("Marca la casilla para habilitar la repetición.")

elif page == PAGES[2]:
    st.title("2 · Comprueba si conviene cambiar")
    st.write("Una estrategia es una configuración para formar equipos. Cada propuesta se compara con su versión anterior bajo las mismas condiciones.")
    if not evolucion:
        st.info("Aún no hay una evaluación exportada para mostrar. Este proceso guarda propuestas, pruebas y decisiones.")
        boton_evaluar("evaluate_empty")
    else:
        st.caption(f"Evaluación mostrada: {evolucion.get('experiment_id', '—')} · {fecha(evolucion.get('updated_at'))}")
        st.subheader("Configuración vigente", anchor=False)
        st.markdown(f"**{version_label(activa.get('id'))}**")
        st.caption(f"Identificador: {activa.get('id', 'sin referencia activa')}")
        aptas = [d for d in decisiones if d.get("accepted")]
        if aptas:
            st.write(f"**{len(aptas)} de {len(decisiones)} propuestas pasaron los controles.** En cada ciclo se activa la que tiene mayor mejora entre las aptas.")
        elif decisiones:
            st.info("Ninguna propuesta pasó todos los controles. Se mantuvo la configuración anterior; esta evaluación no demostró la mejora exigida.")
        else:
            st.info("No hay propuestas evaluadas en este registro. No se puede afirmar una mejora.")
        policy = evolucion.get("manifest", {}).get("policy", {})
        st.caption(f"Para pasar: mejora media ≥ {numero(policy.get('min_improvement'))} puntos; caída por tipo ≤ {numero(policy.get('max_type_drop'))} puntos; contratos y pruebas obligatorias aprobados.")
        st.subheader("Resultado en la prueba reservada", anchor=False)
        st.write("Son escenarios apartados de la selección. Se prueban una vez después de elegir; este resultado no se usa para seguir ajustando.")
        if final.get("executed_once") and final.get("comparison"):
            result = final["comparison"]
            st.write(f"La configuración elegida obtuvo **{numero(result.get('delta'), sign=True)} puntos** frente a la inicial en los escenarios reservados. El resultado se conserva aunque sea desfavorable.")
            st.caption(f"Configuración probada en la reserva: {version_label(final.get('strategy_id'))} · {final.get('strategy_id', '—')}")
            comparacion(result, "Elegida")
        elif final.get("status") == "consumed":
            st.warning("La prueba quedó marcada como consumida sin resultado completo. No se reanudará automáticamente.")
        else:
            st.info("La prueba reservada todavía no tiene un resultado completo.")
        siguiente("Siguiente: entender la evidencia", PAGES[3], "strategy_next")
        st.divider()
        st.subheader("Historial de propuestas", anchor=False)
        st.caption("Seleccionar una decisión solo consulta el registro. Una propuesta apta puede no ser la configuración vigente.")
        if decisiones:
            by_id = {d["id"]: d for d in decisiones}
            default = next((d["id"] for d in decisiones if d.get("candidate_id") == activa.get("id")), decisiones[-1]["id"])
            st.session_state.setdefault("decision", default)
            selected = elegir("Decisión que quieres revisar", list(by_id), "decision", lambda v: f"{version_label(by_id[v].get('candidate_id'))} · {'Apta' if by_id[v].get('accepted') else 'Rechazada'}")
            decision = by_id[selected]
            st.markdown(f"**Decisión seleccionada: {'Apta' if decision.get('accepted') else 'Rechazada'}**")
            for reason in decision.get("reasons", []):
                st.write("• " + reason)
            comparacion(decision.get("comparison"), "Propuesta")
            with st.expander("Qué cambió en la configuración"):
                before, candidate = versiones.get(decision.get("parent_id"), {}), versiones.get(decision.get("candidate_id"), {})
                rows = []
                for group, title in [("weights", "Peso"), ("lesson_priorities", "Prioridad de lección")]:
                    aa, bb = before.get("parameters", {}).get(group, {}), candidate.get("parameters", {}).get(group, {})
                    for key in sorted(set(aa) | set(bb)):
                        if aa.get(key) != bb.get(key):
                            rows.append({"Parámetro": title + ": " + {"lessons": "lecciones", "balance": "balance"}.get(key, key), "Anterior": str(aa.get(key, "No definido")), "Propuesta": str(bb.get(key, "No definido"))})
                st.caption("Los pesos indican cuánto influye cada criterio. El presupuesto es el número de repartos que se prueban para elegir equipos.")
                if rows:
                    st.dataframe(rows, hide_index=True, width="stretch")
                st.write(f"Presupuesto: {before.get('search_budget', '—')} → {candidate.get('search_budget', '—')} repartos.")
                st.json({"anterior": before, "propuesta": candidate}, expanded=False)
            with st.expander("Pruebas y estado observado de esta decisión"):
                regressions = decision.get("checks", {}).get("regressions", [])
                st.caption("Una regresión comprueba que no vuelva a aparecer un fallo observado. Estas reglas se aplican retrospectivamente a los mismos equipos y perfiles congelados.")
                if regressions:
                    st.dataframe([{"Caso": r.get("case_id"), "Anterior": "Pasa" if r.get("previous", {}).get("passed") else "Falla", "Propuesta": "Pasa" if r.get("passed") else "Falla", "Incumplimientos": r.get("violations"), "Máximo permitido": r.get("maximum")} for r in regressions], hide_index=True, width="stretch")
                st.json(decision, expanded=False)
        with st.expander("Ciclos, condiciones fijas y casos completos"):
            st.dataframe([{"Ciclo": c.get("cycle"), "Entrada": version_label(c.get("starting_version")), "Salida": version_label(c.get("selected_version")), "Propuestas": len(c.get("proposals", []))} for c in evolucion["cycles"]], hide_index=True, width="stretch")
            st.json({"politica": policy, "formula": evolucion["manifest"].get("formula_version"), "casos": evolucion["cases"]}, expanded=False)
        if evolucion.get("mechanism_rejection"):
            with st.expander("Control preparado: rechazo de una configuración inválida"):
                st.write("Se introdujeron pesos inválidos para comprobar el mecanismo. No fue una propuesta espontánea del aprendizaje.")
                st.json(evolucion["mechanism_rejection"], expanded=False)
        descargar("Descargar la evaluación completa (JSON)", evolucion, "evolucion.json", "download_evolution")
        with st.expander("Ejecución posterior guardada"):
            if aplicacion:
                same = aplicacion.get("experiment_id") == evolucion.get("experiment_id") and aplicacion.get("strategy_id") == activa.get("id")
                st.write("Usó la configuración actualmente mostrada." if same else "Es una ejecución histórica de otra configuración o experimento; no corresponde a la vigente mostrada.")
                st.caption(f"Experimento: {aplicacion.get('experiment_id', '—')} · Versión aplicada: {aplicacion.get('strategy_id', '—')}")
                st.write(f"{len(aplicacion.get('equipos', []))} equipos · {TIPOS.get(aplicacion.get('tipo'), 'Proyecto no disponible')} · {numero(aplicacion.get('score_promedio'))} puntos / 100.")
                st.json(aplicacion, expanded=False)
            else:
                st.write("No hay una aplicación posterior guardada. Puedes crear una desde la terminal:")
                st.code("python main.py aplicar")
        if incompleto:
            boton_evaluar("evaluation_incomplete")

elif page == PAGES[3]:
    st.title("3 · Entiende qué respalda cada decisión")
    st.write("Una lección es una hipótesis sobre cómo agrupar personas. La evidencia reúne las observaciones que la motivaron; una asociación no demuestra causalidad.")
    source = elegir("Información que quieres explorar", ["Simulación de 10 rondas", "Evaluación de estrategias"], "evidence_source")
    selected_lessons = lecciones if source == "Simulación de 10 rondas" else (evolucion or {}).get("lessons", [])
    evidence_map = estado_biblioteca.get("evidencias", {}) if source == "Simulación de 10 rondas" else (evolucion or {}).get("lesson_evidence", {})
    if not selected_lessons:
        st.info("No hay lecciones guardadas en esta fuente. Eso no prueba que exista una mejora.")
        siguiente("Ver la simulación" if source == "Simulación de 10 rondas" else "Ver la evaluación", PAGES[1] if source == "Simulación de 10 rondas" else PAGES[2], "evidence_next")
    else:
        by_id = {l["id"]: l for l in selected_lessons}
        lid = elegir("Lección seleccionada", list(by_id), "lesson_" + source,
                     lambda i: f"{TIPOS.get(by_id[i]['tipo_proyecto'], 'Todos')} · {by_id[i]['rasgo']} · {'mínimo' if by_id[i]['operador'] == 'min' else 'máximo'} {by_id[i]['cantidad']}")
        lesson = by_id[lid]
        st.subheader("Qué se observó", anchor=False)
        st.write(lesson["texto"])
        st.caption(f"Identificador de la lección: {lid}")
        if source == "Simulación de 10 rondas":
            a, b, c = st.columns(3)
            a.metric("Veces observada", lesson["veces_vista"])
            b.metric("Veces aplicada", lesson["veces_aplicada"])
            c.metric("Veces que ayudó", lesson["veces_ayudo"])
            st.caption("«Ayudó» significa que al aplicarla se igualó o superó el promedio histórico previo de ese tipo. Es un indicador orientativo; no decide qué estrategia aceptar.")
        observations = evidence_map.get(lid, [])
        if observations:
            index = elegir("Observación guardada", list(range(len(observations))), "observation_" + lid, lambda i: f"Observación {i + 1}" + (f" · ciclo {observations[i]['cycle']}" if "cycle" in observations[i] else ""))
            observation = observations[index]
            st.dataframe([{"Grupo": "Cumplen la condición", "Equipos": observation.get("n_cumplen"), "Media / 100": observation.get("media_cumplen")},
                          {"Grupo": "No cumplen la condición", "Equipos": observation.get("n_incumplen"), "Media / 100": observation.get("media_incumplen")}], hide_index=True, width="stretch")
            st.write(f"Diferencia observada: **{numero(observation.get('diferencia'), sign=True)} puntos**. No es un efecto causal demostrado.")
            if observation.get("retrospectivo"):
                st.warning("Esta observación está marcada como análisis retrospectivo.")
            with st.expander("Identificadores y evidencia completa de esta observación"):
                st.json(observation, expanded=False)
        else:
            st.info("Esta lección no tiene evidencia exportada disponible. No se puede comprobar su fundamento desde este archivo.")
        with st.expander("Todas las lecciones de esta fuente"):
            st.dataframe([{"Proyecto": TIPOS.get(l["tipo_proyecto"], l["tipo_proyecto"]), "Hipótesis": l["texto"], "ID": l["id"]} for l in selected_lessons], hide_index=True, width="stretch")
            st.json(selected_lessons, expanded=False)
    discoveries = [e for e in (evolucion or {}).get("evidence", []) if e.get("split") == "discovery"]
    if source == "Evaluación de estrategias" and discoveries:
        with st.expander("Equipos y feedback del descubrimiento"):
            st.caption("Cada registro conserva los perfiles disponibles al observar el resultado. Las aplicaciones posteriores se muestran aparte en Estrategias.")
            by_id = {e["id"]: e for e in discoveries}
            eid = elegir("Registro de descubrimiento", list(by_id), "discovery", lambda i: f"{TIPOS.get(by_id[i]['tipo'])} · {i}")
            st.json(by_id[eid], expanded=False)
    st.caption("Puedes explorar personas adicionales en Perfiles y lotes. Ese paso es opcional.")

else:
    st.title("Explora personas sintéticas")
    st.write("Un lote es un grupo de perfiles guardados juntos. Sirve para inspeccionar datos adicionales; crear uno no cambia las poblaciones de la demo ni de la evaluación.")
    if lotes:
        st.subheader("Lote seleccionado", anchor=False)
        by_id = {l["id"]: l for l in lotes}
        lid = elegir("Grupo de personas que quieres inspeccionar", list(by_id), "lote_seleccionado", lambda i: f"{i} · {by_id[i]['n']} personas · semilla {by_id[i]['semilla']}")
        record = by_id[lid]
        st.caption(f"Guardado: {fecha(record['created_at'])}. Perfiles en todos los lotes: {sum(l['n'] for l in lotes)}.")
        error_count = len(ERRORS)
        rows = leer_db("SELECT data FROM personas WHERE lote_id=? ORDER BY id", (lid,))
        if len(ERRORS) > error_count:
            fallo("No se pudo leer el lote seleccionado.", ERRORS[-1][1], "Selecciona otro lote o revisa un respaldo de la base de datos.")
        try:
            people = [json.loads(r["data"]) for r in rows]
            st.dataframe(perfiles(people), hide_index=True, width="stretch")
        except (ValueError, TypeError, AttributeError) as error:
            fallo("No se pudieron mostrar los perfiles de este lote.", error, "Selecciona otro lote o restaura un respaldo de la base de datos.")
        if record["n"] % 4:
            st.info(f"Este lote de {record['n']} personas se puede inspeccionar, pero no repartir completo en equipos de 4. No se descarta ni duplica a nadie.")
        st.caption(f"Perfiles con atributos ya vistos: {record['duplicate_attributes']}. Los identificadores siguen siendo únicos.")
        with st.expander("Historial de lotes"):
            st.dataframe([{"Lote": l["id"], "Personas": l["n"], "Semilla": l["semilla"], "Atributos repetidos": l["duplicate_attributes"], "Creado": fecha(l["created_at"])} for l in lotes], hide_index=True, width="stretch")
    else:
        st.info("No hay lotes disponibles. Puedes crear uno abajo; no hace falta para iniciar la simulación.")
    st.subheader("Crear un lote adicional", anchor=False)
    n = elegir("Cantidad de personas nuevas", [24, 10, 50, 100, 500], "lote_cantidad", str)
    seed = semilla_input()
    st.caption("24 personas permiten 6 equipos completos. Los tamaños 10 y 50 son válidos para explorar perfiles, pero no para repartir todo el lote en equipos de 4.")
    request = f"lote:{n}:{int(seed)}"
    saved = request in st.session_state.get("completed_requests", [])
    st.button(f"Crear y guardar {n} perfiles", type="primary", key="save_batch", disabled=saved,
              on_click=servicio, args=("generar_lote", request, PAGES[4]), kwargs={"n": n, "semilla": int(seed)})
    if saved:
        st.info("Ya guardaste un lote con estos valores en esta sesión. El botón está deshabilitado para evitar duplicados accidentales.")
        st.button("Preparar otro lote con los mismos valores", on_click=lambda: st.session_state["completed_requests"].remove(request))
    if metricas:
        with st.expander("Perfiles estimados al terminar la simulación"):
            st.caption("Estos perfiles pertenecen a la demo de 24 personas, no al lote seleccionado.")
            st.dataframe(perfiles(metricas["personas"]), hide_index=True, width="stretch")
        with st.expander("Para jueces: revelar la verdad sintética"):
            st.caption("Son datos ficticios y reglas del simulador. Esta vista no demuestra privacidad para personas reales.")
            st.dataframe(perfiles(metricas["personas"], "real"), hide_index=True, width="stretch")
            for regla in metricas["reglas_ocultas"]:
                st.write("• " + regla)
