"""Persona 4: panel de evidencia persistida y controles del servicio TEAMFORGE."""
import json

import streamlit as st

from config import ROOT


st.set_page_config(page_title="TEAMFORGE · Laboratorio de equipos", page_icon="⚗️", layout="wide")
st.markdown(
    """<style>
    .stApp {background: #101b20; color: #edf5f2;}
    [data-testid="stSidebar"] {background: #15262b; border-right: 1px solid #2c454a;}
    [data-testid="stHeader"] {background: rgba(16,27,32,.95);}
    .block-container {max-width: 1380px; padding-top: 4rem; padding-bottom: 4rem;}
    .eyebrow {font: 600 .72rem monospace; letter-spacing: .19em; color: #8bd8c5;}
    .hero-title {font-size: clamp(2.2rem,4.5vw,4rem); font-weight: 650; letter-spacing: -.055em;
      line-height: 1.08; margin: .7rem 0 .8rem; color: #f2f6ed;}
    .hero-copy {max-width: 760px; color: #b5c8c9; font-size: 1.08rem; line-height: 1.6;}
    .pill {display: inline-block; padding: .32rem .65rem; margin: 0 .4rem .5rem 0;
      border: 1px solid #3d655e; border-radius: 100px; color: #a9ebd6; font-size: .72rem;}
    [data-testid="stMetric"] {background: #192c31; border: 1px solid #2d474c; border-radius: 12px;
      padding: 1rem 1.2rem;}
    [data-testid="stMetricLabel"] {color: #a9c3c4;}
    [data-testid="stMetricValue"] {color: #c4f6c9;}
    .stTabs [data-baseweb="tab-list"] {gap: 1.3rem; border-bottom: 1px solid #30454a;}
    .stTabs [data-baseweb="tab"] {color: #c2d2d0;}
    .stTabs [aria-selected="true"] {color: #adf0cf;}
    .stTabs [data-baseweb="tab-highlight"] {background: #91ddbc;}
    h2, h3 {letter-spacing: -.025em;}
    div[data-testid="stExpander"] {border-color: #344d51;}
    </style>""",
    unsafe_allow_html=True,
)


def leer_json(ruta):
    """Lee únicamente archivos persistidos; no reemplaza resultados ausentes."""
    archivo = ROOT / ruta
    if not archivo.exists():
        return None
    try:
        return json.loads(archivo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        st.error(f"No se pudo leer {ruta}: {error}")
        return None


def tabla_perfiles(personas, perfil="estimado"):
    return [
        {"ID": p["id"], "Nombre": p["nombre"], **p.get(perfil, {})}
        for p in personas
    ]


def lanzar_servicio(nombre, **kwargs):
    """Los botones delegan al servicio y vuelven a leer las salidas guardadas."""
    import main

    try:
        with st.spinner("Ejecutando el experimento y guardando evidencia…"):
            resultado = getattr(main, nombre)(**kwargs)
        st.session_state["ultimo_servicio"] = {"nombre": nombre, "resultado": resultado}
        st.rerun()
    except (ValueError, OSError, RuntimeError) as error:
        st.error(str(error))


def formato_numero(valor, digitos=2):
    return f"{valor:.{digitos}f}" if isinstance(valor, (int, float)) else "—"


def diferencias_configuracion(anterior, candidata):
    """Presenta diferencias del JSON persistido; no genera nuevas estrategias."""
    cambios = []
    for grupo in ("weights", "lesson_priorities"):
        antes = anterior.get("parameters", {}).get(grupo, {})
        despues = candidata.get("parameters", {}).get(grupo, {})
        for clave in sorted(set(antes) | set(despues)):
            if antes.get(clave) != despues.get(clave):
                cambios.append({"Parámetro": f"{grupo}.{clave}", "Anterior": str(antes.get(clave, "—")), "Candidata": str(despues.get(clave, "—"))})
    if anterior.get("search_budget") != candidata.get("search_budget"):
        cambios.append({"Parámetro": "search_budget", "Anterior": str(anterior.get("search_budget", "—")), "Candidata": str(candidata.get("search_budget", "—"))})
    return cambios


def resumen_comparacion(comparacion):
    if not isinstance(comparacion, dict) or not comparacion:
        st.caption("No hubo comparación externa para esta decisión.")
        return
    antes, despues = comparacion.get("before"), comparacion.get("after")
    media_antes = antes.get("mean") if isinstance(antes, dict) else antes
    media_despues = despues.get("mean") if isinstance(despues, dict) else despues
    columnas = st.columns(4)
    columnas[0].metric("Media anterior", formato_numero(media_antes))
    columnas[1].metric("Media candidata", formato_numero(media_despues))
    columnas[2].metric("Cambio / 100", formato_numero(comparacion.get("delta")))
    columnas[3].metric("Escenarios pareados", comparacion.get("n", "—"))
    st.caption(
        "Dispersión de diferencias (desviación estándar): "
        + formato_numero(comparacion.get("paired_stdev"))
        + ". Los umbrales de esta demo no son una garantía estadística."
    )
    filas = []
    for tipo, datos in comparacion.get("by_type", {}).items():
        if isinstance(datos, dict):
            filas.append({"Proyecto": tipo, **datos})
    if filas:
        st.dataframe(filas, hide_index=True, width="stretch")


metricas = leer_json("resultados/metricas.json")
evolucion = leer_json("resultados/evolucion.json")
aplicacion = leer_json("resultados/aplicacion.json")
lecciones = leer_json("biblioteca/lecciones.json") or []
estado_biblioteca = leer_json("biblioteca/lecciones.estado.json") or {}
if isinstance(lecciones, dict):
    lecciones = lecciones.get("lecciones", [])

with st.sidebar:
    st.markdown("### ⚗ TEAMFORGE")
    st.caption("QUÍMICA · EXPERIMENTO 01")
    st.divider()
    st.markdown("**Laboratorio sintético**")
    st.caption("Formar → observar → reflexionar → contrastar")
    st.markdown("Modo **determinista · sin API**")
    st.caption("Las cifras se leen de ejecuciones guardadas. El modelo no se reentrena.")
    st.divider()
    st.markdown("**Ejecutar**")
    if st.button("Generar demo de 10 rondas", width="stretch"):
        lanzar_servicio("ejecutar_demo")
    if st.button("Evaluar estrategias", width="stretch", type="primary"):
        lanzar_servicio("ejecutar_evolucion")
    st.caption("Una evaluación terminada se vuelve a consultar; no reutiliza la prueba final para ajustar.")
    if evolucion:
        st.caption(f"Experimento: {evolucion.get('experiment_id', '—')}")
        st.caption(f"Actualización: {evolucion.get('updated_at', evolucion.get('created_at', '—'))}")
    st.divider()
    st.caption("Núcleo Python · evaluación fija · memoria auditable")

st.markdown('<div class="eyebrow">TEAMFORGE / LABORATORIO DE EQUIPOS</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-title">La próxima formación,<br>con más evidencia.</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="hero-copy">Un experimento de mejora iterativa autónoma de estrategias: '
    'formar equipos, aprender de feedback simulado y contrastar cada propuesta antes de aceptarla.</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div style="margin: 1.2rem 0 1.8rem"><span class="pill">DATOS SINTÉTICOS</span>'
    '<span class="pill">MODO DETERMINISTA</span><span class="pill">SIN LLAVE DE API</span></div>',
    unsafe_allow_html=True,
)

personas = metricas.get("personas", []) if metricas else []
decisiones = [
    d for d in evolucion.get("decisions", [])
    if not d.get("observed_state", {}).get("mechanism_test")
] if evolucion else []
activa = evolucion.get("active_version") if evolucion else None
id_activa = activa.get("id") if isinstance(activa, dict) else activa
columnas = st.columns(4)
columnas[0].metric("Perfiles en la demo", len(personas) if metricas else "—")
columnas[1].metric("Rondas guardadas", len(metricas.get("con_memoria", [])) if metricas else "—")
columnas[2].metric("Lecciones vigentes", len(lecciones) if metricas else "—")
columnas[3].metric("Candidatas aceptadas", sum(bool(d.get("accepted")) for d in decisiones) if evolucion else "—")
st.write("")

tab_rondas, tab_memoria, tab_versiones, tab_perfiles = st.tabs(
    ["01 · Rondas", "02 · Memoria y evidencia", "03 · Estrategias", "04 · Perfiles"]
)

with tab_rondas:
    st.subheader("El experimento longitudinal")
    st.caption("Estados independientes. La línea base reparte al azar y conserva los perfiles declarados.")
    if not metricas:
        st.info("Aún no hay resultados. Ejecuta la demo desde el panel o usa este comando:")
        st.code("python main.py demo", language="bash")
    else:
        con = metricas.get("con_memoria", [])
        sin = metricas.get("sin_memoria", [])
        by_round = {fila["ronda"]: fila for fila in sin}
        filas = [
            {
                "Ronda": fila["ronda"],
                "Con memoria": fila["score_promedio"],
                "Sin memoria": by_round.get(fila["ronda"], {}).get("score_promedio"),
            }
            for fila in con
        ]
        errores = [
            {
                "Ronda": fila["ronda"],
                "Con memoria": fila["error_perfiles"],
                "Sin memoria": by_round.get(fila["ronda"], {}).get("error_perfiles"),
            }
            for fila in con
        ]
        izquierda, derecha = st.columns(2)
        with izquierda:
            st.markdown("**Resultado externo · score / 100**")
            st.line_chart(filas, x="Ronda", y=["Con memoria", "Sin memoria"], color=["#9debba", "#d1ad83"], height=320)
        with derecha:
            st.markdown("**Error de perfiles · menor es mejor**")
            st.line_chart(errores, x="Ronda", y=["Con memoria", "Sin memoria"], color=["#9debba", "#d1ad83"], height=320)
        st.caption("El error es la media de |estimado − real| en todos los rasgos. Las curvas pueden subir y bajar.")
        with st.expander("Ver las rondas guardadas"):
            st.dataframe([{"Escenario": "Con memoria", **r} for r in con] + [{"Escenario": "Sin memoria", **r} for r in sin], hide_index=True, width="stretch")
        st.download_button("Descargar métricas JSON", json.dumps(metricas, ensure_ascii=False, indent=2), "metricas.json", "application/json")

with tab_memoria:
    st.subheader("Hipótesis con rastro de evidencia")
    st.caption("Las lecciones describen asociaciones observadas; no demuestran causalidad. La ayuda del curador es una heurística histórica.")
    if lecciones:
        st.dataframe(
            [{k: l.get(k) for k in ["id", "tipo_proyecto", "texto", "veces_vista", "veces_aplicada", "veces_ayudo"]} for l in lecciones],
            hide_index=True,
            width="stretch",
        )
        with st.expander("Contratos completos de las lecciones"):
            st.json(lecciones)
        evidencia_base = estado_biblioteca.get("evidencias", {})
        if evidencia_base:
            id_base = st.selectbox("Consultar evidencia de una lección de la demo", [l["id"] for l in lecciones])
            with st.expander("Observación que motivó la lección", expanded=True):
                st.json(evidencia_base.get(id_base, []), expanded=False)
    else:
        st.info("No hay lecciones persistidas en la biblioteca. Ejecuta la demo para obtener observaciones.")
    lecciones_evolucion = evolucion.get("lessons", []) if evolucion else []
    evidencia_por_leccion = evolucion.get("lesson_evidence", {}) if evolucion else {}
    if lecciones_evolucion:
        st.markdown("**Lecciones que motivan las estrategias**")
        indice_leccion = st.selectbox(
            "Lección de descubrimiento",
            range(len(lecciones_evolucion)),
            format_func=lambda i: f"{lecciones_evolucion[i]['id']} · {lecciones_evolucion[i].get('texto', '')}",
        )
        leccion = lecciones_evolucion[indice_leccion]
        st.json(leccion, expanded=False)
        evidencia_leccion = evidencia_por_leccion.get(leccion["id"])
        if evidencia_leccion:
            st.markdown("**Evidencia vinculada a esta lección**")
            st.json(evidencia_leccion, expanded=False)
        else:
            st.caption("No hay evidencia vinculada exportada para esta lección.")
    evidencias = evolucion.get("evidence", []) if evolucion else []
    if isinstance(evidencias, dict):
        evidencias = list(evidencias.values())
    if evidencias:
        st.markdown("**Descubrimiento · observaciones guardadas**")
        seleccion = st.selectbox("Evidencia", range(len(evidencias)), format_func=lambda i: f"{evidencias[i].get('id', i)} · {evidencias[i].get('tipo', 'observación')}")
        evidencia = evidencias[seleccion]
        st.caption("El snapshot conserva los perfiles disponibles al observar el resultado.")
        with st.expander("Observación, equipos, feedback y lecciones", expanded=True):
            st.json(evidencia, expanded=False)
    elif evolucion:
        st.info("Este experimento no contiene evidencia de descubrimiento exportada.")
    else:
        st.caption("La evaluación de estrategias añade snapshots de evidencia y casos de regresión.")

with tab_versiones:
    st.subheader("Una versión cambia solo si pasa los controles")
    st.caption("Se modifica una configuración JSON. El simulador, la métrica externa, las semillas y los controles permanecen fijos.")
    if not evolucion:
        st.info("Todavía no hay una evaluación persistida.")
        st.code("python main.py evolucion", language="bash")
    else:
        st.markdown(f"**Versión vigente:** `{id_activa or 'sin referencia activa'}`")
        manifiesto = evolucion.get("manifest", {})
        politica = manifiesto.get("policy", {})
        st.caption("Política congelada antes de proponer: mejora media ≥ 2 puntos y caída media por tipo ≤ 2; contratos y regresiones obligatorios.")
        with st.expander("Manifiesto y política del experimento"):
            st.json({"id": manifiesto.get("id"), "formula_version": manifiesto.get("formula_version"), "policy": politica}, expanded=True)
        versiones = evolucion.get("versions", [])
        if isinstance(versiones, dict):
            versiones = list(versiones.values())
        por_version = {v["id"]: v for v in versiones if isinstance(v, dict) and "id" in v}
        ciclos = evolucion.get("cycles", [])
        if ciclos:
            st.dataframe(
                [{"Ciclo": c.get("cycle"), "Versión de entrada": c.get("starting_version"), "Versión de salida": c.get("selected_version"), "Propuestas": len(c.get("proposals", [])), "Regresiones nuevas": len(c.get("regressions_added", []))} for c in ciclos],
                hide_index=True, width="stretch",
            )
        if decisiones:
            seleccion = st.selectbox("Decisión de estrategia", range(len(decisiones)), format_func=lambda i: f"{decisiones[i].get('candidate_id', i)} · {'aceptada' if decisiones[i].get('accepted') else 'rechazada'}")
            decision = decisiones[seleccion]
            (st.success if decision.get("accepted") else st.warning)("Aceptada" if decision.get("accepted") else "Rechazada · se conserva la versión anterior")
            razones = decision.get("reasons", [])
            st.write(" · ".join(str(r) for r in razones) if isinstance(razones, list) else razones)
            anterior = por_version.get(decision.get("parent_id"), {})
            candidata = por_version.get(decision.get("candidate_id"), {})
            izq, der = st.columns(2)
            with izq:
                st.markdown("**Configuración anterior**")
                st.json(anterior.get("parameters", anterior), expanded=True)
            with der:
                st.markdown("**Configuración propuesta**")
                st.json(candidata.get("parameters", candidata), expanded=True)
            cambios = diferencias_configuracion(anterior, candidata)
            if cambios:
                st.dataframe(cambios, hide_index=True, width="stretch")
            st.caption(f"Presupuesto de búsqueda: anterior {anterior.get('search_budget', '—')} · candidata {candidata.get('search_budget', '—')}.")
            resumen_comparacion(decision.get("comparison", {}))
            with st.expander("Pruebas, estado observado y motivos completos"):
                st.json(decision)
        else:
            st.info("No se registraron candidatas. Esto no demuestra mejora.")
        casos = evolucion.get("cases", [])
        with st.expander(f"Casos declarativos de regresión · {len(casos)}"):
            st.caption("Hipótesis aplicadas retrospectivamente a perfiles congelados. Se conserva el estado observable histórico; no se reconstruye con estimaciones posteriores.")
            if casos:
                st.json(casos, expanded=False)
            else:
                st.caption("No hay un caso derivado de un fallo en esta ejecución.")
        mecanismo = evolucion.get("mechanism_rejection")
        if mecanismo:
            with st.expander("Rechazo explícito · prueba del mecanismo"):
                st.caption("Configuración inválida preparada para verificar los controles. No es aprendizaje espontáneo.")
                st.json(mecanismo, expanded=False)
        st.markdown("### Prueba final reservada")
        final = evolucion.get("final_result")
        if isinstance(final, dict) and (final.get("executed_once") or final.get("comparison")):
            st.caption("Ejecutada después de elegir la versión; no se usa para volver a ajustarla. Se conserva aunque el resultado sea desfavorable.")
            if isinstance(final, dict) and "before" in final:
                resumen_comparacion(final)
            elif isinstance(final, dict) and isinstance(final.get("comparison"), dict):
                resumen_comparacion(final["comparison"])
                if final["comparison"].get("delta") == 0 and not any(d.get("accepted") for d in decisiones):
                    st.info("Sin candidatas aceptadas: la versión elegida coincide con la inicial. El empate reservado no demuestra una mejora.")
            st.json(final, expanded=False)
        elif isinstance(final, dict) and final.get("status") == "consumed":
            st.warning("La prueba reservada se marcó como consumida, pero no hay un resultado completo guardado. No se vuelve a ejecutar automáticamente.")
        else:
            st.info("La prueba reservada aún no se ha ejecutado.")
        st.download_button("Descargar evaluación JSON", json.dumps(evolucion, ensure_ascii=False, indent=2), "evolucion.json", "application/json")
        st.markdown("### La siguiente formación")
        if aplicacion:
            st.markdown(f"**Versión realmente aplicada:** `{aplicacion.get('strategy_id', '—')}`")
            a, b, c = st.columns(3)
            a.metric("Score de la ejecución", formato_numero(aplicacion.get("score_promedio")))
            b.metric("Proyecto", aplicacion.get("tipo", "—"))
            c.metric("Equipos formados", len(aplicacion.get("equipos", [])))
            st.caption("Ejecución posterior guardada: usa la versión activa y actualiza perfiles con feedback. No cambia la estrategia ni vuelve a usar la prueba reservada.")
            with st.expander("Equipos, feedback y actualización posterior"):
                st.json(aplicacion, expanded=False)
        else:
            st.caption("Para comprobar la aplicación posterior de la versión activa:")
            st.code("python main.py aplicar --id demo-evolucion --tipo creativo --semilla 43", language="bash")

with tab_perfiles:
    st.subheader("Personas sintéticas, lotes reproducibles")
    st.caption("Generar otro lote conserva los anteriores. Las coincidencias de atributos no implican identidades duplicadas.")
    with st.form("nuevo_lote"):
        a, b, c = st.columns([1, 1, 2])
        n_lote = a.selectbox("Perfiles nuevos", [10, 24, 50, 100, 500], index=1)
        semilla_lote = b.number_input("Semilla del lote", min_value=0, value=42, step=1)
        c.caption("Los IDs son únicos por lote. Para formar equipos exactos de cuatro, el grupo seleccionado debe ser divisible entre cuatro.")
        if st.form_submit_button("Generar y guardar lote"):
            lanzar_servicio("generar_lote", n=int(n_lote), semilla=int(semilla_lote))
    ruta_db = ROOT / "datos/teamforge.sqlite3"
    if ruta_db.exists():
        from almacenamiento import Almacen

        almacen = Almacen()
        lotes = almacen.listar_lotes()
        if lotes:
            st.metric("Perfiles registrados en lotes", sum(l.get("n", 0) for l in lotes))
            st.dataframe(lotes, hide_index=True, width="stretch")
            lote_id = st.selectbox("Inspeccionar lote", [l["id"] for l in lotes])
            lote_personas = almacen.personas_lote(lote_id)
            st.dataframe(tabla_perfiles(lote_personas), hide_index=True, width="stretch")
            if len(lote_personas) % 4:
                st.info(f"Este lote contiene {len(lote_personas)} personas y no se puede repartir completo en equipos de 4. No se descarta ni duplica a nadie.")
        else:
            st.info("Todavía no hay lotes registrados.")
    else:
        st.info("Todavía no hay lotes registrados. Genera uno para iniciar el registro SQLite.")
    if personas:
        with st.expander("Perfiles estimados al cierre de la demo"):
            st.dataframe(tabla_perfiles(personas), hide_index=True, width="stretch")
        with st.expander("Revelación para jueces · verdad sintética"):
            st.caption("Solo el simulador y las métricas usan real durante el experimento. Esta revelación de datos ficticios no constituye seguridad para datos humanos.")
            st.dataframe(tabla_perfiles(personas, "real"), hide_index=True, width="stretch")
            for regla in metricas.get("reglas_ocultas", []):
                st.write("• " + str(regla))
