"""
=============================================================================
PROYECTO   : Observatorio Automatizado Estación Magallanes
MÓDULO     : app.py (Visor Web Institucional / Panel de Control)
VERSIÓN    : 21.0 (BÚSQUEDA GLOBAL, RANGO TEMPORAL Y FILTROS UNIFICADOS)
=============================================================================
"""

import streamlit as st
import os
import json
import re
from datetime import datetime, timedelta, timezone
import plotly.graph_objects as go
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Estación Magallanes", layout="wide", page_icon="🔭")
st.markdown(
    """
    <style>
    .stApp {
        background-color: #0e1117;
        color: #c9d1d9;
        font-size: 1.05rem;
    }
    section[data-testid="stSidebar"] {
        font-size: 1.02rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.9rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

EPOCA_MJD = datetime(1858, 11, 17, tzinfo=timezone.utc)

OPCIONES_TIPO = [
    "👁️ Todos los tipos",
    "✅ Supernovas Confirmadas (TNS)",
    "🚨 Supernovas Candidatas (ZTF/LSST)",
    "🌀 Agujeros Negros (TDE)",
    "💥 Novas / Cataclísmicas",
    "🚀 Blazares",
    "🕳️ AGN (Cuásar)",
    "🔥 Flares VIP",
]

OPCIONES_RED = [
    "🌐 Todas las redes",
    "TNS_GLOBAL",
    "LSST",
    "ZTF",
]


# =====================================================================
# FUNCIONES DE LECTURA LOCAL Y NORMALIZACIÓN EN CACHÉ
# =====================================================================
def mjd_a_local(mjd_val):
    if mjd_val is None:
        return None
    try:
        dt_utc = EPOCA_MJD + timedelta(days=float(mjd_val))
        return (dt_utc - timedelta(hours=3)).replace(tzinfo=None)
    except Exception:
        return None


def clasificar_categoria_ui(ev):
    t = str(ev.get("tipo", "")).lower().strip()
    survey = str(ev.get("survey", "")).strip()
    vip = bool(ev.get("vip", False))

    if t == "tde":
        return "🌀 Agujeros Negros (TDE)"
    if t == "nova":
        return "💥 Novas / Cataclísmicas"
    if t == "blazar":
        return "🚀 Blazares"
    if t == "agn":
        return "🕳️ AGN (Cuásar)"
    if t == "flare":
        return "🔥 Flares VIP" if vip else None
    if t == "supernova" and survey == "TNS_GLOBAL":
        return "✅ Supernovas Confirmadas (TNS)"
    if t == "supernova":
        return "🚨 Supernovas Candidatas (ZTF/LSST)"
    return None


@st.cache_data(ttl=300)
def leer_catalogo_maestro():
    if os.path.exists("catalogo_maestro.json"):
        try:
            with open("catalogo_maestro.json", "r", encoding="utf-8") as f:
                datos = json.load(f)
            preparados = []
            for ev in datos:
                item = dict(ev)
                dt_local = mjd_a_local(item.get("mjd_deteccion"))
                item["_dt_local"] = dt_local
                item["_fecha_local"] = dt_local.date() if dt_local else None
                item["_cat_ui"] = clasificar_categoria_ui(item)
                oid_txt = str(item.get("oid", ""))
                texto_busqueda = " ".join(
                    [
                        oid_txt,
                        oid_txt.replace(" ", ""),
                        str(item.get("analisis", "")),
                        str(item.get("tipo", "")),
                        str(item.get("survey", "")),
                        str(item["_cat_ui"] or ""),
                    ]
                ).lower()
                item["_search_blob"] = texto_busqueda
                preparados.append(item)
            return preparados
        except Exception:
            pass
    return []


@st.cache_data(ttl=300)
def leer_archivo_texto(ruta):
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return None


def obtener_estado_red(ruta_log):
    contenido = leer_archivo_texto(ruta_log)
    if not contenido:
        return "Desconocido", "⚪"

    lineas = contenido.split("\n")
    sesion_actual = []
    for linea in reversed(lineas):
        if not linea.strip():
            continue
        sesion_actual.insert(0, linea)
        if "APUNTANDO TELESCOPIO" in linea:
            break

    texto_final = "\n".join(sesion_actual)
    if "Error" in texto_final or "Timeout" in texto_final:
        return "Error / Caída", "🔴"
    elif any(
        x in texto_final
        for x in [
            "Procesadas",
            "Conexión exitosa",
            "Patrullaje",
            "Procesando evento",
            "Sincronización TNS",
            "Procesamiento TNS finalizado",
        ]
    ):
        return "Operativa", "🟢"
    return "En reposo", "🟡"


# =====================================================================
# BARRA LATERAL DE NAVEGACIÓN, BÚSQUEDA GLOBAL Y FILTROS UNIFICADOS
# =====================================================================
try:
    st.sidebar.image("logo.jpeg", width="stretch")
except Exception:
    pass
st.sidebar.markdown("[⬅️ Volver a la Estación Magallanes](https://www.estacionmagallanes.org)")
st.sidebar.divider()

if st.sidebar.button("🔄 Sincronizar Radar", width="stretch"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.title("Panel de Control")
vista = st.sidebar.selectbox(
    "Selecciona una vista:",
    [
        "Dashboard Principal (Telemetría)",
        "Feed de Alertas y Circulares",
        "Bitácoras del Sistema",
        "Acerca del Observatorio",
    ],
)

st.sidebar.divider()
st.sidebar.markdown("### 🔎 Búsqueda y Filtros")

busqueda_global = st.sidebar.text_input(
    "Buscar objeto, subtipo o red:",
    value="",
    placeholder="Ej: 2026akbp, TDE, SN Ia, ZTF18...",
    help="Al escribir un término, la consulta busca automáticamente en todo el historial ignorando el filtro de fecha.",
).strip()

hora_magallanes = (datetime.now(timezone.utc) - timedelta(hours=3)).replace(tzinfo=None)
hoy_local = hora_magallanes.date()

modo_temporal = st.sidebar.radio(
    "📅 Alcance Temporal (Hora Magallanes):",
    ["Día específico", "Rango de fechas", "Todo el historial"],
    index=0,
)

fecha_seleccionada = hoy_local
fecha_inicio = hoy_local - timedelta(days=7)
fecha_fin = hoy_local

if modo_temporal == "Día específico":
    fecha_seleccionada = st.sidebar.date_input("Fecha:", hoy_local)
elif modo_temporal == "Rango de fechas":
    fecha_inicio = st.sidebar.date_input("Desde:", hoy_local - timedelta(days=7))
    fecha_fin = st.sidebar.date_input("Hasta:", hoy_local)
    if fecha_inicio > fecha_fin:
        fecha_inicio, fecha_fin = fecha_fin, fecha_inicio
        st.sidebar.warning("Se invirtió el rango porque la fecha inicial era mayor que la final.")

if busqueda_global:
    st.sidebar.caption("🌐 Búsqueda global activa: consultando todo el historial.")

filtro_tipo_global = st.sidebar.selectbox("Clasificación Astrofísica:", OPCIONES_TIPO)
filtro_red_global = st.sidebar.selectbox("Red de Origen:", OPCIONES_RED)

# =====================================================================
# MOTOR DE FILTRADO UNIFICADO EN RAM
# =====================================================================
catalogo_datos = leer_catalogo_maestro()

tokens_busqueda = [tok for tok in busqueda_global.lower().split() if tok]
catalogo_filtrado = []

for ev in catalogo_datos:
    # 1. Filtro temporal (se omite automáticamente cuando hay búsqueda global escrita)
    if not tokens_busqueda:
        fecha_ev = ev.get("_fecha_local")
        if modo_temporal == "Día específico":
            if fecha_ev != fecha_seleccionada:
                continue
        elif modo_temporal == "Rango de fechas":
            if not fecha_ev or not (fecha_inicio <= fecha_ev <= fecha_fin):
                continue

    # 2. Filtro por texto (todos los términos ingresados deben coincidir)
    if tokens_busqueda:
        blob = ev.get("_search_blob", "")
        if not all(tok in blob for tok in tokens_busqueda):
            continue

    # 3. Filtro por clasificación astrofísica
    if filtro_tipo_global != "👁️ Todos los tipos":
        if ev.get("_cat_ui") != filtro_tipo_global:
            continue

    # 4. Filtro por red de origen
    if filtro_red_global != "🌐 Todas las redes":
        if ev.get("survey") != filtro_red_global:
            continue

    catalogo_filtrado.append(ev)

catalogo_filtrado.sort(key=lambda x: float(x.get("mjd_deteccion") or 0.0), reverse=True)

# Etiqueta descriptiva del alcance activo
if busqueda_global:
    etiqueta_alcance = f'Búsqueda global: "{busqueda_global}"'
elif modo_temporal == "Día específico":
    etiqueta_alcance = fecha_seleccionada.strftime("%Y-%m-%d")
elif modo_temporal == "Rango de fechas":
    etiqueta_alcance = f"{fecha_inicio.strftime('%Y-%m-%d')} al {fecha_fin.strftime('%Y-%m-%d')}"
else:
    etiqueta_alcance = "Historial Completo"

filtros_extra = []
if filtro_tipo_global != "👁️ Todos los tipos":
    filtros_extra.append(filtro_tipo_global)
if filtro_red_global != "🌐 Todas las redes":
    filtros_extra.append(f"Red: {filtro_red_global}")
sufijo_filtros = f" | {' · '.join(filtros_extra)}" if filtros_extra else ""


# =====================================================================
# VISTA 1: DASHBOARD PRINCIPAL Y MAPA ESTELAR
# =====================================================================
if vista == "Dashboard Principal (Telemetría)":
    st.title("🛰️ Estación Magallanes - Telemetría")

    estado_ztf, icono_ztf = obtener_estado_red("bitacoras/bitacora_ZTF.log")
    estado_lsst, icono_lsst = obtener_estado_red("bitacoras/bitacora_LSST.log")
    estado_tns, icono_tns = obtener_estado_red("bitacoras/bitacora_TNS_GLOBAL.log")

    col_red1, col_red2, col_red3 = st.columns(3)
    col_red1.metric("ZTF (Norte)", estado_ztf, icono_ztf)
    col_red2.metric("LSST / Rubin (Sur)", estado_lsst, icono_lsst)
    col_red3.metric("TNS (IAU Global)", estado_tns, icono_tns)

    st.divider()

    total_tns = sum(1 for e in catalogo_filtrado if e.get("survey") == "TNS_GLOBAL" and e.get("tipo") == "supernova")
    total_cand = sum(1 for e in catalogo_filtrado if e.get("survey") != "TNS_GLOBAL" and e.get("tipo") == "supernova")
    total_novas = sum(1 for e in catalogo_filtrado if e.get("tipo") == "nova")
    total_agn = sum(1 for e in catalogo_filtrado if e.get("tipo") in ["agn", "blazar"])
    total_tdes = sum(1 for e in catalogo_filtrado if e.get("tipo") == "tde")
    total_flares = sum(1 for e in catalogo_filtrado if e.get("tipo") == "flare" and e.get("vip", False))

    st.subheader(f"📊 Resumen del Catálogo Activo ({etiqueta_alcance}{sufijo_filtros})")
    col_det1, col_det2, col_det3, col_det4, col_det5, col_det6 = st.columns(6)
    col_det1.metric("✅ Supernovas (TNS)", str(total_tns), "Confirmadas", delta_color="normal")
    col_det2.metric("🚨 Candidatas (ZTF/LSST)", str(total_cand), "Requiere ATel", delta_color="inverse")
    col_det3.metric("💥 Novas", str(total_novas), "Erupción", delta_color="normal")
    col_det4.metric("🕳️ AGN/Blazar", str(total_agn), "Extragaláctico", delta_color="normal")
    col_det5.metric("🌀 Agujeros Negros", str(total_tdes), "Disrupción TDE", delta_color="normal")
    col_det6.metric("🔥 Flares VIP", str(total_flares), "Estelar", delta_color="normal")

    with st.expander("📖 Glosario de Terminología Astrofísica"):
        st.markdown(
            """
- **TNS (Transient Name Server):** Nodo oficial de la IAU para reportar supernovas y transitorios confirmados.
- **ZTF (Zwicky Transient Facility):** Observatorio robótico en el hemisferio norte (Palomar).
- **LSST (Legacy Survey of Space and Time):** Observatorio Vera C. Rubin (hemisferio sur).
- **SN (Supernova):** Explosión termonuclear o colapso de núcleo de una estrella.
- **TDE (Tidal Disruption Event):** Evento de disrupción de marea donde un agujero negro supermasivo destroza y devora una estrella.
- **AGN (Active Galactic Nucleus) / Cuásar:** Núcleo galáctico activo alimentado por un agujero negro supermasivo.
- **Blazar:** Tipo de AGN cuyo chorro relativista apunta directamente hacia la Tierra.
- **Nova / CV (Variable Cataclísmica):** Erupción superficial en una enana blanca por acreción de materia.
- **Flare VIP (Enana M):** Erupción estelar violenta en estrellas frías y pequeñas (Alta prioridad local).
            """
        )

    st.subheader(f"🌌 Mapa Celeste de Detecciones ({len(catalogo_filtrado)} eventos en vista)")

    if catalogo_filtrado:
        datos_plotly = {
            "Confirmada TNS": {"ra": [], "dec": [], "text": [], "color": "#00FF00", "symbol": "star-diamond"},
            "Candidata": {"ra": [], "dec": [], "text": [], "color": "#FF0000", "symbol": "cross"},
            "Blazar (Chorro)": {"ra": [], "dec": [], "text": [], "color": "#FF00FF", "symbol": "triangle-down"},
            "AGN (Cuásar)": {"ra": [], "dec": [], "text": [], "color": "#FF9900", "symbol": "triangle-up"},
            "Agujero Negro (TDE)": {"ra": [], "dec": [], "text": [], "color": "#FFD700", "symbol": "x"},
            "Nova / Cataclísmica": {"ra": [], "dec": [], "text": [], "color": "#00BFFF", "symbol": "star"},
            "Flare (Enana M VIP)": {"ra": [], "dec": [], "text": [], "color": "#FF0055", "symbol": "hexagon"},
        }

        enriquecer_con_circulares = len(catalogo_filtrado) <= 600

        for ev in catalogo_filtrado:
            t, survey, vip = ev.get("tipo", ""), ev.get("survey", ""), ev.get("vip", False)
            cat = None

            if t == "tde":
                cat = "Agujero Negro (TDE)"
            elif t == "nova":
                cat = "Nova / Cataclísmica"
            elif t == "blazar":
                cat = "Blazar (Chorro)"
            elif t == "agn":
                cat = "AGN (Cuásar)"
            elif t == "flare":
                cat = "Flare (Enana M VIP)" if vip else None
            elif t == "supernova" and survey == "TNS_GLOBAL":
                cat = "Confirmada TNS"
            elif t == "supernova":
                cat = "Candidata"

            if not cat:
                continue

            ra_v = ev.get("ra")
            dec_v = ev.get("dec")
            if ra_v is None or dec_v is None:
                continue

            dt_local = ev.get("_dt_local")
            fecha_txt = dt_local.strftime("%Y-%m-%d %H:%M Local") if dt_local else "Fecha no disp."
            mjd_val = ev.get("mjd_deteccion")
            mjd_str = f"MJD: {float(mjd_val):.4f}" if mjd_val else "MJD: No disp."

            extra_info = ""
            if enriquecer_con_circulares:
                oid_limpio = str(ev.get("oid")).replace(" ", "_").replace("/", "-")
                ruta_circular = f"alertas/CIRCULAR_{oid_limpio}.txt"
                cont_circ = leer_archivo_texto(ruta_circular)

                if cont_circ:
                    match_escudo = re.search(r"Nombre Oficial Asignado\s*:\s*(.*)", cont_circ)
                    if match_escudo:
                        nombre_oficial = match_escudo.group(1).strip()
                        extra_info += f"<br><b style='color:#ff3333;'>🛡️ Escudo TNS: {nombre_oficial}</b>"

                    match_z_lab = re.search(r"REDSHIFT \(z\)\s*:\s*(.*)", cont_circ)
                    match_z_tns = re.search(r"z = (.*?)\)", cont_circ)

                    z_val = None
                    if match_z_lab and "Desconocido" not in match_z_lab.group(1):
                        z_val = match_z_lab.group(1).strip()
                    elif match_z_tns and "None" not in str(match_z_tns.group(1)) and "Desconocido" not in str(match_z_tns.group(1)):
                        z_val = match_z_tns.group(1).strip()

                    if z_val:
                        extra_info += f"<br><b>z:</b> {z_val}"

                    match_mpc = re.search(r"(Entre \d+\.\d+ y \d+\.\d+ Megaparsecs)", cont_circ)
                    match_dist_local = re.search(r"^DISTANCIA\s*:\s*(.*)", cont_circ, re.MULTILINE)

                    if match_mpc:
                        dist_limpia = match_mpc.group(1).replace("Megaparsecs", "Mpc")
                        extra_info += f"<br><b>D:</b> {dist_limpia}"
                    elif match_dist_local and "Desconocida" not in match_dist_local.group(1):
                        extra_info += f"<br><b>D:</b> {match_dist_local.group(1).strip()}"

            hover_txt = (
                f"<b>{ev.get('oid')}</b> [{survey}]<br>"
                f"{ev.get('analisis')}<br>"
                f"Fecha: {fecha_txt} | {mjd_str}<br>"
                f"RA: {float(ra_v):.4f}° | Dec: {float(dec_v):.4f}°{extra_info}"
            )

            datos_plotly[cat]["ra"].append(float(ra_v))
            datos_plotly[cat]["dec"].append(float(dec_v))
            datos_plotly[cat]["text"].append(hover_txt)

        total_puntos_mapa = sum(len(d["ra"]) for d in datos_plotly.values())
        usar_webgl = total_puntos_mapa > 1000
        clase_traza = go.Scattergl if usar_webgl else go.Scatter

        fig = go.Figure()
        for nombre_cat, datos in datos_plotly.items():
            if len(datos["ra"]) > 0:
                fig.add_trace(
                    clase_traza(
                        x=datos["ra"],
                        y=datos["dec"],
                        mode="markers",
                        name=f"{nombre_cat} ({len(datos['ra'])})",
                        text=datos["text"],
                        hoverinfo="text",
                        marker=dict(
                            symbol=datos["symbol"],
                            size=14 if ("Candidata" in nombre_cat or "TDE" in nombre_cat) else 11,
                            color=datos["color"],
                            opacity=0.82,
                            line=dict(width=1, color="white"),
                        ),
                    )
                )

        fig.update_layout(
            plot_bgcolor="#0e1117",
            paper_bgcolor="#0e1117",
            font=dict(color="lightgray", size=13),
            xaxis=dict(title="Ascensión Recta (Grados)", range=[0, 360], gridcolor="rgba(255,255,255,0.1)"),
            yaxis=dict(title="Declinación (Grados)", range=[-90, 90], gridcolor="rgba(255,255,255,0.1)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=40, r=40, t=40, b=40),
            hovermode="closest",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(f"No hay eventos astronómicos registrados para la selección actual ({etiqueta_alcance}{sufijo_filtros}).")


# =====================================================================
# VISTA 2: FEED DE ALERTAS Y CIRCULARES
# =====================================================================
elif vista == "Feed de Alertas y Circulares":
    st.title("📋 Alertas y Circulares de Detecciones")
    st.caption(f"Consulta activa: **{etiqueta_alcance}{sufijo_filtros}** — **{len(catalogo_filtrado)}** evento(s) coincidente(s).")

    if catalogo_filtrado:
        with st.expander(f"📑 Tabla rápida de resultados ({len(catalogo_filtrado)} eventos)"):
            filas_tabla = []
            for e in catalogo_filtrado:
                dt_loc = e.get("_dt_local")
                filas_tabla.append(
                    {
                        "Fecha Local": dt_loc.strftime("%Y-%m-%d %H:%M") if dt_loc else "Desconocida",
                        "Objeto": e.get("oid"),
                        "Red": e.get("survey"),
                        "Tipo": str(e.get("tipo", "")).upper(),
                        "Clasificación / Análisis": e.get("analisis"),
                        "RA (°)": round(float(e["ra"]), 4) if e.get("ra") is not None else None,
                        "Dec (°)": round(float(e["dec"]), 4) if e.get("dec") is not None else None,
                    }
                )
            st.dataframe(filas_tabla, use_container_width=True, hide_index=True)

        opciones = {}
        for e in catalogo_filtrado:
            survey_origen = e.get("survey", "Desconocido")
            oid_str = str(e.get("oid", ""))
            oid_para_check = oid_str.replace(" ", "_").replace("/", "-")
            dt_local = e.get("_dt_local")
            fecha_hora_str = dt_local.strftime("%Y-%m-%d %H:%M Local") if dt_local else "Fecha desc."

            if survey_origen == "TNS_GLOBAL":
                prefijo = "✅ [TNS]"
            elif survey_origen == "ZTF":
                prefijo = "🚨 [ZTF]"
            elif survey_origen == "LSST":
                prefijo = "🚨 [LSST]"
            else:
                prefijo = f"🚨 [{survey_origen}]"

            ruta_espectro_check = f"data/quimica_halfa_{oid_para_check}.png"
            indicador_espectro = " 🌈 [Espectro]" if os.path.exists(ruta_espectro_check) else ""
            analisis_corto = str(e.get("analisis", "")).strip()
            etiqueta_clase = analisis_corto if survey_origen == "TNS_GLOBAL" and analisis_corto else str(e.get("tipo", "")).upper()

            clave = f"[{fecha_hora_str}] {prefijo} {oid_str} — {etiqueta_clase}{indicador_espectro}"
            opciones[clave] = e

        seleccion = st.selectbox(f"Selecciona un evento ({len(opciones)} encontrados):", list(opciones.keys()))
        evento_actual = opciones[seleccion]

        oid_limpio = str(evento_actual.get("oid")).replace(" ", "_").replace("/", "-")
        survey = evento_actual.get("survey")

        st.info(
            "💡 **Nota sobre sincronización temporal:** La fecha y hora mostradas en el catálogo corresponden al instante "
            "en que la luz del evento impactó el espejo del observatorio (o la época oficial de actualización en TNS si no "
            "hay fotometría pública). Las bitácoras de la Estación Magallanes reflejan la hora de procesamiento local."
        )

        ruta_circular = f"alertas/CIRCULAR_{oid_limpio}.txt"
        ruta_atel = f"alertas_comunidad/ALERTA_ATEL_{oid_limpio}.txt"
        ruta_aavso = f"alertas_comunidad/ALERTA_AAVSO_{oid_limpio}.txt"

        col1, col2 = st.columns([1, 1])

        with col1:
            st.subheader("📄 Documentación y Telegramas")

            cont_circ_temp = leer_archivo_texto(ruta_circular)
            if cont_circ_temp and "INTERVENCIÓN DEL ESCUDO TNS" in cont_circ_temp:
                st.error(
                    "🛡️ **BLOQUEO ACTIVO:** El Escudo TNS detectó duplicidad astronómica y abortó automáticamente "
                    "la emisión del Telegrama (ATel) para proteger la reputación de la Estación Magallanes."
                )

            if evento_actual.get("tipo") == "flare":
                tab1, tab2 = st.tabs(["Circular Interna (Análisis)", "🚨 Alerta AAVSO (Solicitud)"])
            elif survey == "TNS_GLOBAL":
                tab1, tab2 = st.tabs(["Circular Interna (Análisis)", "✅ Registro TNS (Informativo)"])
            else:
                tab1, tab2 = st.tabs(["Circular Interna (Análisis)", "🚨 Borrador ATel (Urgente)"])

            with tab1:
                cont_circ = leer_archivo_texto(ruta_circular)
                if cont_circ:
                    st.code(cont_circ, language="text")
                else:
                    st.warning("Circular en procesamiento...")

            with tab2:
                ruta_alerta = ruta_aavso if evento_actual.get("tipo") == "flare" else ruta_atel
                cont_alerta = leer_archivo_texto(ruta_alerta)
                if cont_alerta:
                    st.code(cont_alerta, language="text")
                elif survey == "TNS_GLOBAL":
                    st.info("Evento ya confirmado espectroscópicamente por la IAU en TNS; no requiere emisión de telegrama ATel.")
                else:
                    st.info("El borrador comunitario no aplica o no ha sido generado debido a bloqueos del Escudo.")

        with col2:
            st.subheader("📊 Evidencia Fotométrica / Espectroscópica")

            ruta_grafico = f"data/curva_luz_{oid_limpio}.png"
            ruta_halfa = f"data/quimica_halfa_{oid_limpio}.png"

            opciones_evidencia = []
            if os.path.exists(ruta_grafico):
                opciones_evidencia.append("Curva de Luz")
            if os.path.exists(ruta_halfa):
                opciones_evidencia.append("Espectroscopía Taxonómica")

            if not opciones_evidencia:
                st.warning("Gráfica fotométrica reservada o no disponible en la red de origen.")
            else:
                seleccion_evidencia = st.selectbox(
                    "Selecciona evidencia a visualizar:", opciones_evidencia, label_visibility="collapsed"
                )

                if seleccion_evidencia == "Curva de Luz":
                    st.image(ruta_grafico, use_container_width=True)
                elif seleccion_evidencia == "Espectroscopía Taxonómica":
                    st.image(ruta_halfa, use_container_width=True)
    else:
        st.info(f"No hay alertas registradas para la selección actual ({etiqueta_alcance}{sufijo_filtros}).")


# =====================================================================
# VISTA 3: BITÁCORAS DEL SISTEMA
# =====================================================================
elif vista == "Bitácoras del Sistema":
    st.title("📜 Monitoreo de Operaciones en Tiempo Real")
    st.info("🕒 **Sincronización:** El sistema de búsqueda opera en UTC. La visualización ha sido convertida a hora local (Punta Arenas: UTC-3).")

    def parse_logs_con_timezone(ruta_log, red_name, red_code):
        parsed = []
        contenido = leer_archivo_texto(ruta_log)
        if not contenido:
            return parsed

        for linea in contenido.split("\n"):
            if "-> Procesadas" in linea or "===" in linea or not linea.strip():
                continue
            try:
                if linea.startswith("["):
                    fecha_hora_str = linea[1:20]
                    mensaje = linea[22:].strip()
                    dt_utc = datetime.strptime(fecha_hora_str, "%Y-%m-%d %H:%M:%S")
                    dt_local = dt_utc - timedelta(hours=3)

                    parsed.append(
                        {
                            "timestamp_sort": dt_local,
                            "fecha_date": dt_local.date(),
                            "fecha_local": dt_local.strftime("%Y-%m-%d"),
                            "hora_local": dt_local.strftime("%H:%M"),
                            "hora_utc": dt_utc.strftime("%H:%M"),
                            "msg": mensaje,
                            "red": red_name,
                            "red_code": red_code,
                        }
                    )
            except Exception:
                pass
        return parsed

    logs_ztf = parse_logs_con_timezone("bitacoras/bitacora_ZTF.log", "ZTF (Norte)", "ZTF")
    logs_lsst = parse_logs_con_timezone("bitacoras/bitacora_LSST.log", "LSST / Rubin (Sur)", "LSST")
    logs_tns = parse_logs_con_timezone("bitacoras/bitacora_TNS_GLOBAL.log", "TNS Global (Confirmaciones)", "TNS_GLOBAL")

    def agrupar_en_ciclos(logs):
        ciclos_agrupados = []
        ciclo_actual = None
        for log in logs:
            if "APUNTANDO TELESCOPIO" in log["msg"]:
                if ciclo_actual is not None:
                    ciclos_agrupados.append(ciclo_actual)
                ciclo_actual = {
                    "red": log["red"],
                    "red_code": log["red_code"],
                    "fecha_date": log["fecha_date"],
                    "fecha_local": log["fecha_local"],
                    "inicio_local": log["hora_local"],
                    "inicio_utc": log["hora_utc"],
                    "timestamp_sort": log["timestamp_sort"],
                    "logs": [log],
                    "candidatos": 0,
                    "errores": 0,
                }
            else:
                if ciclo_actual is None:
                    ciclo_actual = {
                        "red": log["red"],
                        "red_code": log["red_code"],
                        "fecha_date": log["fecha_date"],
                        "fecha_local": log["fecha_local"],
                        "inicio_local": log["hora_local"],
                        "inicio_utc": log["hora_utc"],
                        "timestamp_sort": log["timestamp_sort"],
                        "logs": [],
                        "candidatos": 0,
                        "errores": 0,
                    }
                ciclo_actual["logs"].append(log)

            msg_low = log["msg"].lower()
            if "procesando evento de interés" in msg_low or "descargando ficha" in msg_low or "reclasificado" in msg_low:
                ciclo_actual["candidatos"] += 1
            if "error" in msg_low or "denegado" in msg_low or "timeout" in msg_low:
                ciclo_actual["errores"] += 1

        if ciclo_actual is not None:
            ciclos_agrupados.append(ciclo_actual)
        return ciclos_agrupados

    todos_los_ciclos = agrupar_en_ciclos(logs_ztf) + agrupar_en_ciclos(logs_lsst) + agrupar_en_ciclos(logs_tns)
    todos_los_ciclos.sort(key=lambda x: x["timestamp_sort"], reverse=True)

    ciclos_filtrados = []
    for c in todos_los_ciclos:
        if filtro_red_global != "🌐 Todas las redes" and c["red_code"] != filtro_red_global:
            continue

        if tokens_busqueda:
            texto_ciclo = (c["red"] + " " + " ".join(l["msg"] for l in c["logs"])).lower()
            if not all(tok in texto_ciclo for tok in tokens_busqueda):
                continue
        else:
            if modo_temporal == "Día específico" and c["fecha_date"] != fecha_seleccionada:
                continue
            if modo_temporal == "Rango de fechas" and not (fecha_inicio <= c["fecha_date"] <= fecha_fin):
                continue

        ciclos_filtrados.append(c)

    total_patrullajes = len(ciclos_filtrados)
    total_candidatos = sum(c["candidatos"] for c in ciclos_filtrados)
    total_errores = sum(c["errores"] for c in ciclos_filtrados)

    st.subheader(f"📊 Métricas de Patrullaje ({etiqueta_alcance})")
    col1, col2, col3 = st.columns(3)
    col1.metric("📡 Ciclos de Patrullaje", str(total_patrullajes))
    col2.metric("🌌 Alertas Analizadas", str(total_candidatos))
    col3.metric("🚨 Errores de Red", str(total_errores))
    st.divider()

    st.subheader("⏱️ Secuencia de Eventos (Timeline)")
    limite_visualizacion = 80
    if len(ciclos_filtrados) > limite_visualizacion:
        st.caption(f"Mostrando los {limite_visualizacion} ciclos más recientes de {len(ciclos_filtrados)} encontrados.")

    if ciclos_filtrados:
        for ciclo in ciclos_filtrados[:limite_visualizacion]:
            with st.container():
                if "ZTF" in ciclo["red"]:
                    color_red = "🔵"
                elif "LSST" in ciclo["red"]:
                    color_red = "🟠"
                else:
                    color_red = "🟣"

                st.markdown(
                    f"#### {color_red} [{ciclo['fecha_local']} · {ciclo['inicio_local']} Local | {ciclo['inicio_utc']} UTC] {ciclo['red']}"
                )

                if ciclo["errores"] > 0:
                    st.error(
                        f"⚠️ **Atención:** Se detectaron {ciclo['errores']} incidentes/errores de conexión. | ⚡ {ciclo['candidatos']} alertas evaluadas."
                    )
                elif ciclo["candidatos"] > 0:
                    st.success(
                        f"✅ Ciclo operativo y sin errores. | ⚡ **{ciclo['candidatos']} anomalías astrofísicas** procesadas."
                    )
                else:
                    st.info("💤 Ciclo completado sin anomalías detectadas ni errores.")

                with st.expander("👨‍💻 Auditar Registro Técnico (Modo Terminal)"):
                    log_text = ""
                    for log in ciclo["logs"]:
                        log_text += f"[{log['hora_local']} Local | {log['hora_utc']} UTC] {log['msg']}\n"
                    st.code(log_text, language="text")
                st.write("---")
    else:
        st.warning(f"El observatorio no registró patrullajes para la selección actual ({etiqueta_alcance}).")


# =====================================================================
# VISTA 4: ACERCA DE
# =====================================================================
elif vista == "Acerca del Observatorio":
    st.title("🔭 Estación Magallanes")
    st.subheader("Laboratorio de Astrofísica y Ciencia Ciudadana")
    st.divider()

    st.header("Explorando el Universo Dinámico desde el Fin del Mundo")
    st.markdown(
        """
    La **Estación Magallanes** es un nodo de investigación independiente y de ciencia ciudadana astrofísica. Operando ininterrumpidamente desde Punta Arenas, en la Patagonia Chilena, nuestro objetivo es transformar inmensos volúmenes de datos crudos en información a disposición de toda la comunidad.
    
    Nuestro motor principal es un algoritmo de minería de datos que actúa como un **Broker Astrofísico local**. Integrando modelos de Inteligencia Artificial de frontera (como ALeRCE), procesamos "ríos de datos" masivos para interceptar alertas astronómicas en tiempo real, cazando eventos cósmicos catastróficos y transitorios milisegundos después de ser detectados, antes de que se desvanezcan en el cielo nocturno.
    """
    )
    st.divider()

    st.header("Nuestros Objetivos Científicos")
    st.markdown(
        """
- **Física Estelar y Habitabilidad Exoplanetaria:** Monitoreamos las llamaradas magnéticas extremas (*Flares*) en estrellas Enanas Rojas (Tipo M). Analizamos en tiempo real cómo estas violentas inyecciones de radiación UV impactan la atmósfera, viabilidad y habitabilidad de los sistemas exoplanetarios confirmados que orbitan estos soles.
- **Evolución y Destrucción Estelar Masiva:** El laboratorio automatizado rastrea y procesa sin descanso alertas de Supernovas (Colapso de núcleo y termonucleares) y Variables Cataclísmicas. Para garantizar la máxima precisión, cruzamos nuestra telemetría extragaláctica directamente con el Servidor de Nombres de Transitorios (TNS), aportando al seguimiento de eventos que actúan como "candelas estándar" para medir la expansión del universo.
- **Astrofísica de Altas Energías (Agujeros Negros Supermasivos):** Monitoreamos los confines del universo observable detectando variabilidad en Núcleos Galácticos Activos (AGN). Nuestro algoritmo aísla y clasifica Cuásares hiperluminosos y Blazares, eventos extremos donde agujeros negros supermasivos devoran materia y emiten chorros de radiación relativista que apuntan directamente hacia la Tierra.
- **Democratización de Datos y Ciencia Ciudadana:** Más allá de la observación pura, nuestro objetivo es actuar como un **Broker Astrofísico local**. Utilizamos Inteligencia Artificial para filtrar el "ruido cósmico", transformando terabytes de datos crudos de observatorios profesionales en conocimiento accesible para astrónomos aficionados, educadores y la comunidad científica independiente.
    """
    )
    st.divider()

    st.header("Arquitectura del Flujo de Datos")
    st.markdown(
        "Nuestros radares barren las corrientes de alertas de las instituciones más prestigiosas del mundo, conectándonos directamente a los grandes sondeos para democratizar el seguimiento astronómico:"
    )
    st.markdown(
        """
- **Zwicky Transient Facility (ZTF):** Captura de explosiones en el hemisferio norte (Palomar, California).
- **ALeRCE:** Nuestra principal red neuronal de clasificación predictiva, desarrollada en Chile.
- **Transient Name Server (TNS) / IAU:** Nuestro radar global oficial de descubrimientos de supernovas.
- **Observatorio Vera C. Rubin (LSST):** En preparación para el aluvión de datos astronómicos más grande de la historia humana (Cerro Pachón, Chile).
    """
    )
    st.info(
        "*Este sistema de automatización de código abierto fue construido para tender un puente sólido entre la ciencia de frontera y la observación independiente. Si deseas integrar nuestra telemetría a tu observatorio o colaborar en el análisis espectroscópico de nuestros candidatos, la puerta está abierta.*"
    )
    st.divider()

    st.header("Glosario Taxonómico: Clasificación de Alertas")
    st.markdown(
        "Los eventos que detectamos siguen una clasificación oficial. Aquí detallamos cada categoría para que puedas interpretar nuestra telemetría de forma independiente:"
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("Eventos Estelares")
        st.markdown(
            """
- **Mdwarf-flare (Llamarada de Enana Roja):** Eventos de extrema inestabilidad magnética en estrellas de baja masa (Tipo M). Son el objetivo principal de la Estación Magallanes para estudiar el impacto de la radiación UV en posibles exoplanetas.
- **CV / Nova (Variable Cataclísmica):** Un sistema estelar binario donde una enana blanca "roba" material de una estrella compañera, generando explosiones termonucleares periódicas **en su superficie sin destruir la estrella.**
- **VS (Variable Star):** Clasificación genérica para cualquier tipo de fluctuación lumínica de origen estelar (utilizado en sondeos iniciales).
        """
        )
    with col2:
        st.subheader("Eventos Extragalácticos")
        st.markdown(
            """
- **SN Ia (Supernova Tipo Ia):** La explosión termonuclear completa de una enana blanca. Son fundamentales en cosmología como "candelas estándar" para medir la expansión del universo.
- **SN II / SN Ibc (Supernovas de Colapso de Núcleo):** La muerte violenta de estrellas supermasivas que agotan su combustible, colapsando bajo su propia gravedad.
- **SLSN (Supernova Superluminosa):** Explosiones estelares extremadamente raras y energéticas, hasta 100 veces más brillantes que una supernova normal.
- **TDE (Tidal Disruption Event):** Evento donde un agujero negro supermasivo destroza y devora una estrella por fuerzas de marea.
        """
        )
    with col3:
        st.subheader("Núcleos Galácticos Activos")
        st.markdown(
            """
- **AGN / QSO (Cuásar):** Un núcleo galáctico extremadamente luminoso impulsado por un agujero negro supermasivo devorando materia.
- **Blazar:** Un tipo de cuásar cuyo chorro de radiación relativista apunta directamente hacia la Tierra.
        """
        )

    st.divider()

    col_foot1, col_foot2 = st.columns(2)
    with col_foot1:
        st.markdown("**Estación Magallanes | Punta Arenas, Chile** (53° 09' S, 70° 54' W)")
        st.markdown("Contacto: contacto@estacionmagallanes.org")
    with col_foot2:
        st.link_button(
            "💻 Ver Repositorio en GitHub",
            "https://github.com/Edgardo-Casanova/estacion-magallanes",
            use_container_width=True,
        )
        st.link_button(
            "🌐 Visitar Sitio Web Oficial",
            "https://www.estacionmagallanes.org",
            use_container_width=True,
        )
