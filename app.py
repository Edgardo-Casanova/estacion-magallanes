"""
=============================================================================
PROYECTO   : Observatorio Automatizado Estación Magallanes
MÓDULO     : app.py (Visor Web Institucional / Panel de Control)
VERSIÓN    : 17.0 (MJD CRONOLÓGICO, UX DINÁMICO Y FIX STREAMLIT WIDTH)
=============================================================================
"""

import streamlit as st
import os
import json
import time
from datetime import datetime, timedelta, timezone
import plotly.graph_objects as go
from astropy.time import Time
from dotenv import load_dotenv

load_dotenv()

# =====================================================================
# CONFIGURACIÓN DEL ENTORNO (INTERRUPTOR HÍBRIDO)
# =====================================================================
MODO_LOCAL = False  # <--- CAMBIAR A False ANTES DE SUBIR A GOOGLE CLOUD

BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "estacion-magallanes-bucket")
bucket = None

if not MODO_LOCAL:
    try:
        from google.cloud import storage
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
    except Exception as e: pass

st.set_page_config(page_title="Estación Magallanes", layout="wide", page_icon="🔭")
st.markdown("<style>.stApp { background-color: #0e1117; color: #c9d1d9; }</style>", unsafe_allow_html=True)

# =====================================================================
# FUNCIONES PUENTE (LECTURA DE NUBE/LOCAL)
# =====================================================================
@st.cache_data(ttl=300)
def leer_catalogo_maestro():
    catalogo = []
    if MODO_LOCAL:
        if os.path.exists("catalogo_maestro.json"):
            try:
                with open("catalogo_maestro.json", "r", encoding="utf-8") as f: catalogo = json.load(f)
            except Exception: pass
    else:
        if bucket:
            blob = bucket.blob("catalogo_maestro.json")
            if blob.exists():
                try: catalogo = json.loads(blob.download_as_text())
                except Exception: pass
    return catalogo

@st.cache_data(ttl=300)
def leer_archivo_texto(ruta):
    if MODO_LOCAL:
        if os.path.exists(ruta):
            with open(ruta, 'r', encoding='utf-8') as f: return f.read()
    else:
        if bucket:
            blob = bucket.blob(ruta)
            if blob.exists(): return blob.download_as_text()
    return None

def obtener_estado_red(ruta_log):
    contenido = leer_archivo_texto(ruta_log)
    if not contenido: return "Desconocido", "⚪"
    
    lineas = contenido.split('\n')
    sesion_actual = []
    for linea in reversed(lineas):
        if not linea.strip(): continue
        sesion_actual.insert(0, linea)
        if "APUNTANDO TELESCOPIO" in linea: break
            
    texto_final = "\n".join(sesion_actual)
    if "Error" in texto_final: return "Error API", "🔴"
    elif any(x in texto_final for x in ["Procesadas", "Conexión exitosa", "Patrullaje", "Procesando evento"]): return "Operativa", "🟢"
    return "En reposo", "🟡"

# =====================================================================
# BARRA LATERAL DE NAVEGACIÓN
# =====================================================================
st.sidebar.image("logo.jpeg", width="stretch")
st.sidebar.markdown("[⬅️ Volver a la Estación Magallanes](https://www.estacionmagallanes.org)")
st.sidebar.divider()

if st.sidebar.button("🔄 Sincronizar Radar", width="stretch"):
    st.rerun()

st.sidebar.title("Panel de Control")
vista = st.sidebar.selectbox("Selecciona una vista:", [
    "Dashboard Principal (Telemetría)", 
    "Feed de Alertas y Circulares", 
    "Bitácoras del Sistema", 
    "Mantenimiento del Sistema",
    "Acerca del Observatorio"
])

st.sidebar.divider()
# Ajuste de Zona Horaria (UTC-3 para Punta Arenas)
hora_magallanes = datetime.now(timezone.utc) - timedelta(hours=3)
fecha_seleccionada = st.sidebar.date_input("📅 Filtro de Fecha (Local - Magallanes):", hora_magallanes.date())

catalogo_datos = leer_catalogo_maestro()

# =====================================================================
# VISTA 1: DASHBOARD PRINCIPAL Y MAPA ESTELAR
# =====================================================================
if vista == "Dashboard Principal (Telemetría)":
    st.title("🛰️ Estación Magallanes - Telemetría")
    
    estado_ztf, icono_ztf = obtener_estado_red("bitacoras/bitacora_ZTF.log")
    estado_lsst, icono_lsst = obtener_estado_red("bitacoras/bitacora_TNS_GLOBAL.log")
    
    col_red1, col_red2 = st.columns(2)
    col_red1.metric("ZTF (Norte)", estado_ztf, icono_ztf)
    col_red2.metric("LSST / TNS (Sur)", estado_lsst, icono_lsst)
    
    st.divider()
    
    total_tns = sum(1 for e in catalogo_datos if e.get("survey") == "TNS_GLOBAL")
    total_ztf_cand = sum(1 for e in catalogo_datos if e.get("survey") != "TNS_GLOBAL" and "supernova" in e.get("tipo", "").lower())
    total_novas = sum(1 for e in catalogo_datos if e.get("tipo") == "nova")
    total_agn = sum(1 for e in catalogo_datos if e.get("tipo") in ["agn", "blazar"])
    total_flares = sum(1 for e in catalogo_datos if e.get("tipo") == "flare" and e.get("vip", False))
    
    st.subheader("📊 Resumen del Catálogo Activo")
    col_det1, col_det2, col_det3, col_det4, col_det5 = st.columns(5)
    col_det1.metric("✅ Supernovas Confirmadas (TNS)", str(total_tns), "Históricas", delta_color="normal")
    col_det2.metric("🚨 Supernovas Candidatas (ZTF)", str(total_ztf_cand), "Requiere ATel", delta_color="inverse")
    col_det3.metric("💥 Novas", str(total_novas), "Erupción", delta_color="normal")
    col_det4.metric("🕳️ AGN/Blazares", str(total_agn), "Extragaláctico", delta_color="normal")
    col_det5.metric("🔥 Flares VIP", str(total_flares), "Estelar", delta_color="normal")
    
    with st.expander("📖 Glosario de Terminología Astrofísica"):
        st.markdown("""
        * **TNS (Transient Name Server):** Nodo oficial de la IAU para reportar supernovas.
        * **ZTF (Zwicky Transient Facility):** Observatorio robótico en el hemisferio norte (Palomar).
        * **LSST (Legacy Survey of Space and Time):** Observatorio Vera C. Rubin (hemisferio sur).
        * **SN (Supernova):** Explosión termonuclear o colapso de núcleo de una estrella.
        * **AGN (Active Galactic Nucleus) / Cuásar:** Núcleo galáctico activo alimentado por un agujero negro supermasivo.
        * **Blazar:** Tipo de AGN cuyo chorro relativista apunta directamente hacia la Tierra.
        * **Nova / CV (Variable Cataclísmica):** Erupción superficial en una enana blanca por acreción de materia.
        * **Flare VIP (Enana M):** Erupción estelar violenta en estrellas frías y pequeñas (Alta prioridad local).
        * **MJD (Modified Julian Date):** Sistema de cronometraje continuo usado en astronomía.
        * **ATel (Astronomer's Telegram):** Boletín rápido para alertar a la comunidad sobre nuevos eventos.
        """)
    
    col_map1, col_map2 = st.columns([2, 1])
    with col_map1: st.subheader("🌌 Mapa Celeste de Impactos")
    with col_map2:
        cat_mapa = st.selectbox("Filtrar Mapa:", [
            "👁️ Ver Todo", 
            "✅ Supernovas Confirmadas (TNS)", 
            "🚨 Supernovas Candidatas (ZTF)", 
            "💥 Novas", 
            "🕳️ AGN/Blazares", 
            "🔥 Flares VIP"
        ], label_visibility="collapsed")
    
    if catalogo_datos:
        datos_plotly = {
            "Confirmada TNS": {"ra": [], "dec": [], "text": [], "color": "#00FF00", "symbol": "star-diamond"},
            "Candidata ZTF (Acción)": {"ra": [], "dec": [], "text": [], "color": "#FF0000", "symbol": "cross"},
            "Blazar (Chorro)": {"ra": [], "dec": [], "text": [], "color": "#FF00FF", "symbol": "triangle-down"},
            "AGN (Cuásar)": {"ra": [], "dec": [], "text": [], "color": "#FF9900", "symbol": "triangle-up"},
            "Nova / Cataclísmica": {"ra": [], "dec": [], "text": [], "color": "#00BFFF", "symbol": "star"},
            "Flare (Enana M VIP)": {"ra": [], "dec": [], "text": [], "color": "#FF0055", "symbol": "hexagon"}
        }

        for ev in catalogo_datos:
            t, survey, vip = ev.get("tipo", ""), ev.get("survey", ""), ev.get("vip", False)
            cat = None
            
            if survey == "TNS_GLOBAL": cat = "Confirmada TNS"
            elif t == "supernova": cat = "Candidata ZTF (Acción)"
            elif t == "blazar": cat = "Blazar (Chorro)"
            elif t == "agn": cat = "AGN (Cuásar)"
            elif t == "nova": cat = "Nova / Cataclísmica"
            elif t == "flare": cat = "Flare (Enana M VIP)" if vip else None
            
            if not cat: continue
            
            if cat_mapa == "✅ Supernovas Confirmadas (TNS)" and cat != "Confirmada TNS": continue
            if cat_mapa == "🚨 Supernovas Candidatas (ZTF)" and cat != "Candidata ZTF (Acción)": continue
            if cat_mapa == "💥 Novas" and cat != "Nova / Cataclísmica": continue
            if cat_mapa == "🕳️ AGN/Blazares" and cat not in ["Blazar (Chorro)", "AGN (Cuásar)"]: continue
            if cat_mapa == "🔥 Flares VIP" and cat != "Flare (Enana M VIP)": continue
            
            mjd_val = ev.get('mjd_deteccion')
            if mjd_val: mjd_str = f"MJD: {float(mjd_val):.4f}"
            else: mjd_str = "MJD: No disp."

            hover_txt = f"<b>{ev.get('oid')}</b><br>{ev.get('analisis')}<br>RA: {ev.get('ra'):.4f}° | Dec: {ev.get('dec'):.4f}°<br>{mjd_str}"
            
            datos_plotly[cat]["ra"].append(ev.get("ra"))
            datos_plotly[cat]["dec"].append(ev.get("dec"))
            datos_plotly[cat]["text"].append(hover_txt)

        fig = go.Figure()
        for nombre_cat, datos in datos_plotly.items():
            if len(datos["ra"]) > 0:
                fig.add_trace(go.Scatter(
                    x=datos["ra"], y=datos["dec"], mode='markers', name=nombre_cat,
                    text=datos["text"], hoverinfo='text',
                    marker=dict(symbol=datos["symbol"], size=16 if "Candidata" in nombre_cat else 12, color=datos["color"], opacity=0.8, line=dict(width=1, color='white'))
                ))

        fig.update_layout(
            plot_bgcolor='#0e1117', paper_bgcolor='#0e1117', font=dict(color='lightgray'),
            xaxis=dict(title='Ascensión Recta (Grados)', range=[0, 360], gridcolor='rgba(255,255,255,0.1)'),
            yaxis=dict(title='Declinación (Grados)', range=[-90, 90], gridcolor='rgba(255,255,255,0.1)'),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=40, r=40, t=40, b=40), hovermode='closest'
        )
        st.plotly_chart(fig, width="stretch")

# =====================================================================
# VISTA 2: FEED DE ALERTAS (CORREGIDO CRONOLOGÍA Y SELECTOR GRÁFICO)
# =====================================================================
elif vista == "Feed de Alertas y Circulares":
    st.title("📋 Terminal de Resoluciones Científicas")
    
    if catalogo_datos:
        catalogo_ordenado = sorted(catalogo_datos, key=lambda x: float(x.get('mjd_deteccion', 0)), reverse=True)
        
        opciones = {}
        for e in catalogo_ordenado:
            survey_origen = e.get('survey', 'Desconocido')
            mjd_val = e.get('mjd_deteccion', 0)
            
            try:
                dt_utc = Time(float(mjd_val), format='mjd').to_datetime()
                dt_local = dt_utc - timedelta(hours=3)
                hora_str = dt_local.strftime("%H:%M Local")
            except Exception:
                hora_str = "Hora desc."
            
            if survey_origen == 'TNS_GLOBAL': prefijo = "✅ [TNS]"
            elif survey_origen == 'ZTF': prefijo = "🚨 [ZTF]"
            elif survey_origen == 'LSST': prefijo = "🚨 [LSST]"
            else: prefijo = f"🚨 [{survey_origen}]"
                
            clave = f"[{hora_str}] {prefijo} {e.get('oid')} - {e.get('tipo').upper()}"
            opciones[clave] = e
            
        seleccion = st.selectbox("Selecciona un evento del catálogo:", list(opciones.keys()))
        evento_actual = opciones[seleccion]
        
        oid_limpio = str(evento_actual.get('oid')).replace(' ', '_').replace('/', '-')
        survey = evento_actual.get('survey')
        
        ruta_circular = f"alertas/CIRCULAR_{oid_limpio}.txt"
        ruta_atel = f"alertas_comunidad/ALERTA_ATEL_{oid_limpio}.txt"
        ruta_aavso = f"alertas_comunidad/ALERTA_AAVSO_{oid_limpio}.txt"
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("📄 Documentación y Telegramas")
            if survey == "TNS_GLOBAL": tab1, tab2 = st.tabs(["Circular Interna (Análisis)", "✅ Registro TNS (Informativo)"])
            elif evento_actual.get('tipo') == "flare": tab1, tab2 = st.tabs(["Circular Interna (Análisis)", "🚨 Alerta AAVSO (Solicitud)"])
            else: tab1, tab2 = st.tabs(["Circular Interna (Análisis)", "🚨 Borrador ATel (Urgente)"])
            
            with tab1:
                cont_circ = leer_archivo_texto(ruta_circular)
                if cont_circ: st.code(cont_circ, language="text")
                else: st.warning("Circular en procesamiento...")
                    
            with tab2:
                ruta_alerta = ruta_aavso if evento_actual.get('tipo') == "flare" else ruta_atel
                cont_alerta = leer_archivo_texto(ruta_alerta)
                if cont_alerta: st.code(cont_alerta, language="text")
                else: st.info("El borrador comunitario no aplica o no ha sido generado.")
                    
        with col2:
            st.subheader("📊 Evidencia Fotométrica / Espectroscópica")
            
            ruta_grafico = f"data/curva_luz_{oid_limpio}.png"
            ruta_halfa = f"data/quimica_halfa_{oid_limpio}.png"
            
            opciones_evidencia = []
            
            if MODO_LOCAL:
                if os.path.exists(ruta_grafico): opciones_evidencia.append("Curva de Luz")
                if os.path.exists(ruta_halfa): opciones_evidencia.append("Espectro (Química H-alfa)")
            else:
                if bucket and bucket.blob(ruta_grafico).exists(): opciones_evidencia.append("Curva de Luz")
                if bucket and bucket.blob(ruta_halfa).exists(): opciones_evidencia.append("Espectro (Química H-alfa)")
                
            if not opciones_evidencia:
                st.warning("Gráfica fotométrica reservada o no disponible en la red de origen.")
            else:
                seleccion_evidencia = st.selectbox("Selecciona evidencia a visualizar:", opciones_evidencia, label_visibility="collapsed")
                
                if seleccion_evidencia == "Curva de Luz":
                    if MODO_LOCAL: st.image(ruta_grafico, width="stretch")
                    else: st.image(bucket.blob(ruta_grafico).download_as_bytes(), width="stretch")
                        
                elif seleccion_evidencia == "Espectro (Química H-alfa)":
                    if MODO_LOCAL: st.image(ruta_halfa, width="stretch")
                    else: st.image(bucket.blob(ruta_halfa).download_as_bytes(), width="stretch")
                    
    else:
        st.info("El catálogo maestro está vacío. Esperando la primera detección del cazador.")

# =====================================================================
# VISTA 3: BITÁCORAS DEL SISTEMA (CONVERSIÓN DE ZONA HORARIA)
# =====================================================================
elif vista == "Bitácoras del Sistema":
    st.title("📜 Monitoreo de Operaciones en Tiempo Real")
    st.info("🕒 **Sincronización:** El sistema de búsqueda opera en UTC. La visualización ha sido convertida a su hora local (Punta Arenas: UTC-3).")
    
    def parse_logs_con_timezone(ruta_log, red_name):
        parsed = []
        contenido = leer_archivo_texto(ruta_log)
        if not contenido: return parsed
        
        for linea in contenido.split('\n'):
            if "-> Procesadas" in linea or "===" in linea or not linea.strip(): continue
            try:
                if linea.startswith("["):
                    fecha_hora_str = linea[1:20]
                    mensaje = linea[22:].strip()
                    dt_utc = datetime.strptime(fecha_hora_str, "%Y-%m-%d %H:%M:%S")
                    dt_local = dt_utc - timedelta(hours=3)
                    
                    parsed.append({
                        'timestamp_sort': dt_local,
                        'fecha_local': dt_local.strftime("%Y-%m-%d"),
                        'hora_local': dt_local.strftime("%H:%M"),
                        'hora_utc': dt_utc.strftime("%H:%M"),
                        'msg': mensaje,
                        'red': red_name
                    })
            except Exception: pass
        return parsed

    logs_ztf = parse_logs_con_timezone("bitacoras/bitacora_ZTF.log", "ZTF (Norte)")
    logs_tns = parse_logs_con_timezone("bitacoras/bitacora_TNS_GLOBAL.log", "TNS Global (Sur)")
    
    def agrupar_en_ciclos(logs):
        ciclos_agrupados = []
        ciclo_actual = None
        for log in logs:
            if "APUNTANDO TELESCOPIO" in log['msg']:
                if ciclo_actual is not None: ciclos_agrupados.append(ciclo_actual)
                ciclo_actual = {
                    'red': log['red'], 'fecha_local': log['fecha_local'],
                    'inicio_local': log['hora_local'], 'inicio_utc': log['hora_utc'],
                    'timestamp_sort': log['timestamp_sort'], 'logs': [log],
                    'candidatos': 0, 'errores': 0
                }
            else:
                if ciclo_actual is None:
                    ciclo_actual = {
                        'red': log['red'], 'fecha_local': log['fecha_local'],
                        'inicio_local': log['hora_local'], 'inicio_utc': log['hora_utc'],
                        'timestamp_sort': log['timestamp_sort'], 'logs': [],
                        'candidatos': 0, 'errores': 0
                    }
                ciclo_actual['logs'].append(log)
                
            msg_low = log['msg'].lower()
            if "procesando evento de interés" in msg_low or "descargando ficha" in msg_low or "reclasificado" in msg_low:
                ciclo_actual['candidatos'] += 1
            if "error" in msg_low or "denegado" in msg_low:
                ciclo_actual['errores'] += 1
                
        if ciclo_actual is not None: ciclos_agrupados.append(ciclo_actual)
        return ciclos_agrupados

    todos_los_ciclos = agrupar_en_ciclos(logs_ztf) + agrupar_en_ciclos(logs_tns)
    todos_los_ciclos.sort(key=lambda x: x['timestamp_sort'], reverse=True)
    
    fecha_str_busqueda = fecha_seleccionada.strftime("%Y-%m-%d")
    ciclos_del_dia = [c for c in todos_los_ciclos if c['fecha_local'] == fecha_str_busqueda]

    total_patrullajes = len(ciclos_del_dia)
    total_candidatos = sum(c['candidatos'] for c in ciclos_del_dia)
    total_errores = sum(c['errores'] for c in ciclos_del_dia)
    
    st.subheader(f"📊 Métricas de Patrullaje ({fecha_str_busqueda})")
    col1, col2, col3 = st.columns(3)
    col1.metric("📡 Ciclos de Patrullaje", str(total_patrullajes))
    col2.metric("🌌 Alertas Analizadas", str(total_candidatos))
    col3.metric("🚨 Errores de Red", str(total_errores))
    st.divider()

    st.subheader("⏱️ Secuencia de Eventos (Timeline)")
    if ciclos_del_dia:
        for ciclo in ciclos_del_dia:
            with st.container():
                color_red = "🔵" if "ZTF" in ciclo['red'] else "🟣"
                st.markdown(f"#### {color_red} [{ciclo['inicio_local']} Local | {ciclo['inicio_utc']} UTC] {ciclo['red']}")
                
                if ciclo['errores'] > 0: st.error(f"⚠️ **Atención:** Se detectaron {ciclo['errores']} errores de conexión. | ⚡ {ciclo['candidatos']} alertas evaluadas.")
                elif ciclo['candidatos'] > 0: st.success(f"✅ Ciclo operativo y sin errores. | ⚡ **{ciclo['candidatos']} candidatas astrofísicas** aisladas.")
                else: st.info(f"💤 Ciclo completado. No se detectaron eventos anómalos o de alta prioridad.")
                    
                with st.expander("👨‍💻 Auditar Registro Técnico (Modo Terminal)"):
                    log_text = ""
                    for log in ciclo['logs']:
                        log_text += f"[{log['hora_local']} Local | {log['hora_utc']} UTC] {log['msg']}\n"
                    st.code(log_text, language="text")
                st.write("---")
    else:
        st.warning(f"El observatorio no registró patrullajes para tu fecha local ({fecha_str_busqueda}).")

# =====================================================================
# VISTA 4: MANTENIMIENTO DEL SISTEMA
# =====================================================================
elif vista == "Mantenimiento del Sistema":
    st.title("⚙️ Mantenimiento y Purga")
    st.markdown("⚠️ **Área Restringida:** Autorización requerida.")
    password = st.text_input("Código de Autorización:", type="password")
    
    if password == os.getenv("ADMIN_PASSWORD", "admin123") and password != "":
        st.success(f"Autorización confirmada. Conectado en MODO: {'LOCAL (Disco Duro)' if MODO_LOCAL else 'CLOUD (Bucket GCS)'}")
        if st.button("🚨 PURGAR TODO EL HISTORIAL (RESET DE FÁBRICA)", type="primary", width="stretch"):
            if MODO_LOCAL:
                for carpeta in ["alertas", "data", "alertas_comunidad", "bitacoras"]:
                    if os.path.exists(carpeta):
                        for arch in os.listdir(carpeta):
                            if "memoria_tns" not in arch: os.remove(os.path.join(carpeta, arch))
                if os.path.exists("catalogo_maestro.json"): os.remove("catalogo_maestro.json")
            else:
                if bucket:
                    blobs = bucket.list_blobs()
                    for blob in blobs:
                        if "memoria_tns" not in blob.name: blob.delete()
            st.success("¡Base de datos formateada con éxito!")
            time.sleep(2)
            st.rerun()

# =====================================================================
# VISTA 5: ACERCA DE
# =====================================================================
elif vista == "Acerca del Observatorio":
    st.title("🔭 Estación Magallanes")
    st.subheader("Laboratorio de Astrofísica y Ciencia Ciudadana")
    
    st.divider()
    
    st.header("Explorando el Universo Dinámico desde el Fin del Mundo")
    st.markdown("""
    La **Estación Magallanes** es un nodo de investigación independiente y de ciencia ciudadana astrofísica. Operando ininterrumpidamente desde Punta Arenas, en la Patagonia Chilena, nuestro objetivo es transformar inmensos volúmenes de datos crudos en información a disposición de toda la comunidad.
    
    Nuestro motor principal es un algoritmo de minería de datos que actúa como un **Broker Astrofísico local**. Integrando modelos de Inteligencia Artificial de frontera (como ALeRCE), procesamos "ríos de datos" masivos para interceptar alertas astronómicas en tiempo real, cazando eventos cósmicos catastróficos y transitorios milisegundos después de ser detectados, antes de que se desvanezcan en el cielo nocturno.
    """)
    
    st.divider()
    
    st.header("Nuestros Objetivos Científicos")
    st.markdown("""
    * **Física Estelar y Habitabilidad Exoplanetaria:** Nuestra especialidad radica en el monitoreo de llamaradas magnéticas extremas (*Flares*) en estrellas Enanas Rojas (Tipo M). Analizamos en tiempo real cómo estas violentas inyecciones de radiación UV impactan la atmósfera, viabilidad y habitabilidad de los sistemas exoplanetarios confirmados que orbitan estos soles.
    * **Evolución y Destrucción Estelar Masiva:** El laboratorio automatizado rastrea y procesa sin descanso alertas de Supernovas (Colapso de núcleo y termonucleares) y Variables Cataclísmicas. Para garantizar la máxima precisión, cruzamos nuestra telemetría extragaláctica directamente con el Servidor de Nombres de Transitorios (TNS), aportando al seguimiento de eventos que actúan como "candelas estándar" para medir la expansión del universo.
    * **Astrofísica de Altas Energías (Agujeros Negros Supermasivos):** Monitoreamos los confines del universo observable detectando variabilidad en Núcleos Galácticos Activos (AGN). Nuestro algoritmo aísla y clasifica Cuásares hiperluminosos y Blazares, eventos extremos donde agujeros negros supermasivos devoran materia y emiten chorros de radiación relativista que apuntan directamente hacia la Tierra.
    * **Democratización de Datos y Ciencia Ciudadana:** Más allá de la observación pura, nuestro objetivo es actuar como un **Broker Astrofísico local**. Utilizamos Inteligencia Artificial para filtrar el "ruido cósmico", transformando terabytes de datos crudos de observatorios profesionales en conocimiento accesible para astrónomos aficionados, educadores y la comunidad científica independiente.
    """)
    
    st.divider()
    
    st.header("Arquitectura del Flujo de Datos")
    st.markdown("Nuestros radares barren las corrientes de alertas de las instituciones más prestigiosas del mundo, conectándonos directamente a los grandes sondeos para democratizar el seguimiento astronómico:")
    st.markdown("""
    * **Zwicky Transient Facility (ZTF):** Captura de explosiones en el hemisferio norte (Palomar, California).
    * **ALeRCE:** Nuestra principal red neuronal de clasificación predictiva, desarrollada en Chile.
    * **Transient Name Server (TNS) / IAU:** Nuestro radar global oficial de descubrimientos de supernovas.
    * **Observatorio Vera C. Rubin (LSST):** En preparación para el aluvión de datos astronómicos más grande de la historia humana (Cerro Pachón, Chile).
    """)
    st.info("*Este sistema de automatización de código abierto fue construido para tender un puente sólido entre la ciencia de frontera y la observación independiente. Si deseas integrar nuestra telemetría a tu observatorio o colaborar en el análisis espectroscópico de nuestros candidatos, la puerta está abierta.*")
    
    st.divider()
    
    st.header("Glosario Taxonómico: Clasificación de Alertas")
    st.markdown("Los eventos que detectamos siguen una clasificación oficial. Aquí detallamos cada categoría para que puedas interpretar nuestra telemetría de forma independiente:")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("Eventos Estelares")
        st.markdown("""
        * **Mdwarf-flare (Llamarada de Enana Roja):** Eventos de extrema inestabilidad magnética en estrellas de baja masa (Tipo M). Son el objetivo principal de la Estación Magallanes para estudiar el impacto de la radiación UV en posibles exoplanetas.
        * **CV / Nova (Variable Cataclísmica):** Un sistema estelar binario donde una enana blanca "roba" material de una estrella compañera, generando explosiones termonucleares periódicas **en su superficie sin destruir la estrella.**
        """)
    with col2:
        st.subheader("Eventos Extragalácticos")
        st.markdown("""
        * **SN Ia (Supernova Tipo Ia):** La explosión termonuclear completa de una enana blanca. Son fundamentales en cosmología como "candelas estándar" para medir la expansión del universo.
        * **SN II / SN Ibc (Supernovas de Colapso de Núcleo):** La muerte violenta de estrellas supermasivas que agotan su combustible, colapsando bajo su propia gravedad.
        * **SLSN (Supernova Superluminosa):** Explosiones estelares extremadamente raras y energéticas, hasta 100 veces más brillantes que una supernova normal.
        """)
    with col3:
        st.subheader("Núcleos Galácticos Activos")
        st.markdown("""
        * **QSO (Cuásar):** Un núcleo galáctico extremadamente luminoso impulsado por un agujero negro supermasivo devorando materia.
        * **Blazar:** Un tipo de cuásar cuyo chorro de radiación relativista apunta directamente hacia la Tierra.
        """)
        
    st.divider()
    
    col_foot1, col_foot2 = st.columns(2)
    with col_foot1:
        st.markdown("**Estación Magallanes | Punta Arenas, Chile** (53° 09' S, 70° 54' W)")
        st.markdown("Contacto: contacto@estacionmagallanes.org")
    with col_foot2:
        st.link_button("💻 Ver Repositorio en GitHub", "https://github.com/Edgardo-Casanova/estacion-magallanes", width="stretch")
        st.link_button("🌐 Visitar Sitio Web Oficial", "https://www.estacionmagallanes.org", width="stretch")
