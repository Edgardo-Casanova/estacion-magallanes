import streamlit as st
import os
import glob
import time
import re
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import plotly.graph_objects as go
from dotenv import load_dotenv

# Cargar las variables secretas del archivo .env
load_dotenv()

# Configuración base de la página
st.set_page_config(page_title="Estación Magallanes", layout="wide", page_icon="🔭")

# Estilos visuales
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #c9d1d9; }
    </style>
""", unsafe_allow_html=True)

# --- FUNCIONES AUXILIARES ---
def obtener_estado_red(log_file):
    if not os.path.exists(log_file):
        return "Desconocido", "⚪"
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lineas = f.readlines()

        sesion_actual = []
        for linea in reversed(lineas):
            sesion_actual.insert(0, linea)
            if "APUNTANDO TELESCOPIO" in linea:
                break
                
        contenido_final = "".join(sesion_actual)
        
        if "Error" in contenido_final:
            return "Error API", "🔴"
        elif "Ningún evento superó" in contenido_final or "Procesadas" in contenido_final or "Conexión exitosa" in contenido_final or "Patrullaje" in contenido_final:
            return "Operativa", "🟢"
        else:
            return "En reposo", "🟡"
    except Exception:
        return "Desconocido", "⚪"

def extraer_coordenadas_alertas():
    ra_list, dec_list, nombres, tipos, fechas = [], [], [], [], []
    archivos = glob.glob("alertas/CIRCULAR_*.txt")
    
    for archivo in archivos:
        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                contenido = f.read()
                
                match_fecha = re.search(r"FECHA DE EMISIÓN\s*:\s*(\d{4}-\d{2}-\d{2})", contenido)
                if not match_fecha:
                    continue 
                    
                fecha_emision = datetime.strptime(match_fecha.group(1), "%Y-%m-%d").date()
                
                nombre_actual = "Desconocido"
                tipo_actual = "FLARE"
                match_obj = re.search(r"(?:OBJETO|EVENTO) DETECTADO\s*:\s*(.+?)\s*\((.+?)\)", contenido)
                if match_obj:
                    nombre_actual = match_obj.group(1).strip()
                    tipo_actual = match_obj.group(2).strip().upper()
                
                match_coord = re.search(r"RA\s*([0-9\.\-]+)\s*\|\s*Dec\s*([0-9\.\-]+)", contenido)
                if match_coord:
                    ra = float(match_coord.group(1))
                    dec = float(match_coord.group(2))
                    
                    nombre_archivo_base = nombre_actual.replace(' ', '_')
                    ruta_reporte = f"data/REPORTE_ALERTA_{nombre_archivo_base}.txt"
                    if os.path.exists(ruta_reporte):
                        with open(ruta_reporte, 'r', encoding='utf-8') as f_rep:
                            cont_rep = f_rep.read()
                            
                            # Prioridad 1: Reclasificación Estación Magallanes
                            match_magallanes = re.search(r"Reclasificaci(?:o|ó)n \(An(?:a|á)lisis Estaci(?:o|ó)n Magallanes\):\s*([^\n]+)", cont_rep, re.IGNORECASE)
                            # Prioridad 2: TNS
                            match_tns = re.search(r"Clasificaci(?:o|ó)n \(TNS\):\s*([^\n\(]+)", cont_rep, re.IGNORECASE)
                            
                            clase_fina = None
                            if match_magallanes:
                                clase_fina = match_magallanes.group(1).strip().upper()
                            elif match_tns:
                                clase_fina = match_tns.group(1).strip().upper()
                                
                            if clase_fina and clase_fina != "DESCONOCIDA":
                                # Limpiar descripciones adicionales entre paréntesis para el mapa
                                clase_limpia = clase_fina.split("(")[0].strip()
                                tipo_actual = clase_limpia
                    
                    ra_list.append(ra)
                    dec_list.append(dec)
                    nombres.append(nombre_actual)
                    tipos.append(tipo_actual)
                    fechas.append(fecha_emision)
                    
        except Exception:
            pass
            
    return ra_list, dec_list, nombres, tipos, fechas

def formatear_nombre_circular(ruta_archivo):
    try:
        with open(ruta_archivo, 'r', encoding='utf-8') as f:
            lineas = f.readlines()
            fecha = "Fecha Desconocida"
            objeto = "Objeto Desconocido"
            for linea in lineas:
                if "FECHA DE EMISIÓN" in linea:
                    fecha = linea.split(":", 1)[1].strip()
                if "OBJETO DETECTADO" in linea or "EVENTO DETECTADO" in linea:
                    objeto = linea.split(":", 1)[1].strip()
        return f"🗓️ {fecha} | {objeto}"
    except Exception:
        return os.path.basename(ruta_archivo)

def formatear_nombre_grafico(ruta_archivo):
    nombre_base = os.path.basename(ruta_archivo).replace('.png', '')
    if "curva_luz" in nombre_base:
        obj = nombre_base.replace("curva_luz_", "")
        return f"📉 Curva de Luz y Mapa Celeste | {obj}"
    elif "espectro_sed" in nombre_base:
        obj = nombre_base.replace("espectro_sed_", "")
        return f"🌈 Espectro Térmico (SED) | {obj}"
    elif "quimica_halfa" in nombre_base:
        obj = nombre_base.replace("quimica_halfa_", "")
        return f"🔬 Análisis Químico Cromosférico (H-alfa) | {obj}"
    return nombre_base

# --- BARRA LATERAL DE NAVEGACIÓN ---
st.sidebar.image("logo.jpeg", width="stretch")
st.sidebar.markdown("[⬅️ Volver a la Estación Magallanes](https://www.estacionmagallanes.org)")
st.sidebar.divider()

st.sidebar.title("Panel de Control")
vista = st.sidebar.selectbox(
    "Selecciona una vista:",
    [
        "Dashboard Principal (Telemetría)", 
        "Feed de Alertas y Circulares", 
        "Bitácoras del Sistema", 
        "Mantenimiento del Sistema",
        "Acerca del Observatorio"
    ]
)

st.sidebar.divider()
fecha_hoy = datetime.utcnow().date()
fecha_seleccionada = st.sidebar.date_input("📅 Filtro de Fecha (UTC):", fecha_hoy)


# --- VISTA 1: DASHBOARD PRINCIPAL Y MAPA ESTELAR ---
if vista == "Dashboard Principal (Telemetría)":
    st.title("🛰️ Estación Magallanes - Telemetría")
    
    estado_ztf, icono_ztf = obtener_estado_red("bitacora_ZTF.log")
    estado_lsst, icono_lsst = obtener_estado_red("bitacora_TNS_GLOBAL.log")
    
    ra_full, dec_full, nom_full, tip_full, fec_full = extraer_coordenadas_alertas()
    
    ra_list, dec_list, nombres, tipos = [], [], [], []
    for i in range(len(fec_full)):
        if fec_full[i] == fecha_seleccionada:
            ra_list.append(ra_full[i])
            dec_list.append(dec_full[i])
            nombres.append(nom_full[i])
            tipos.append(tip_full[i])
    
    # Contadores actualizados para coincidir con el análisis físico de Magallanes
    total_flares = sum(1 for t in tipos if "FLARE" in t or "ENANA M" in t)
    total_novas = sum(1 for t in tipos if ("NOVA" in t and "SUPERNOVA" not in t) or "CATACL" in t or "CV" in t)
    total_supernovas = sum(1 for t in tipos if "SUPERNOVA" in t or "SN" in t)
    total_agn = sum(1 for t in tipos if "AGN" in t or "QSO" in t or "BLAZAR" in t or "CUÁSAR" in t)
    
    st.subheader("📡 Estado de la Red de Alertas")
    col_red1, col_red2 = st.columns(2)
    col_red1.metric(f"ZTF (Norte)", estado_ztf, icono_ztf)
    col_red2.metric(f"LSST / TNS (Sur)", estado_lsst, icono_lsst)
    
    st.subheader(f"📊 Detecciones Clasificadas ({fecha_seleccionada.strftime('%d-%m-%Y')})")
    col_det1, col_det2, col_det3, col_det4 = st.columns(4)
    col_det1.metric("Flares (Enanas Rojas)", str(total_flares), "Estelar", delta_color="normal")
    col_det2.metric("Novas (Cataclísmicas)", str(total_novas), "Binaria", delta_color="normal")
    col_det3.metric("Supernovas", str(total_supernovas), "Destrucción", delta_color="normal")
    col_det4.metric("Cuásares / AGN", str(total_agn), "Agujero Negro", delta_color="normal")
    
    with st.expander("📚 Glosario Taxonómico (¿Qué subcategorías incluyen estos contadores?)"):
        st.markdown("""
        *   **Supernovas:** Incluye subcategorías como **Tipo Ia** (Explosiones termonucleares), **Tipo Ib/c y II** (Colapso de núcleo masivo), y **SLSN** (Supernovas Superluminosas).
        *   **Cuásares / AGN:** Incluye **QSO** (Cuásares o Núcleos Galácticos Activos clásicos) y **Blazares** (Variantes extremas con jets relativistas apuntando directamente hacia nuestra línea de visión).
        *   **Novas (Cataclísmicas):** Incluye **CV** (Variables Cataclísmicas, sistemas binarios interactuantes) y **Novas** estelares clásicas de nuestra galaxia.
        *   **Flares (Enanas Rojas):** Destellos súbitos magnéticos provenientes de estrellas de baja masa (**M-dwarf**).
        """)

    st.divider()
    
    col_map1, col_map2 = st.columns([2, 1])
    with col_map1:
        st.subheader("🌌 Mapa Celeste de Impactos (Interactivo)")
    with col_map2:
        categoria_mapa = st.selectbox(
            "Filtrar por Categoría:",
            ["👁️ Ver Todo", "💥 Supernovas", "✨ Novas (Cataclísmicas)", "🕳️ Cuásares / AGN", "🔥 Flares (Enanas Rojas)"],
            label_visibility="collapsed"
        )
    
    if ra_list:
        datos_plotly = {
            "Supernova Ia": {"ra": [], "dec": [], "nombres": [], "tipos": [], "color": "#00FFFF", "symbol": "circle"},
            "Supernova II / Ibc": {"ra": [], "dec": [], "nombres": [], "tipos": [], "color": "#39FF14", "symbol": "square"},
            "Supernova Superluminosa (SLSN)": {"ra": [], "dec": [], "nombres": [], "tipos": [], "color": "#FFD700", "symbol": "diamond"},
            "Supernova (Sin clasificar)": {"ra": [], "dec": [], "nombres": [], "tipos": [], "color": "#FF00FF", "symbol": "cross"},
            "Nova (Clásica)": {"ra": [], "dec": [], "nombres": [], "tipos": [], "color": "#00BFFF", "symbol": "star"},
            "Variable Cataclísmica (CV)": {"ra": [], "dec": [], "nombres": [], "tipos": [], "color": "#00FA9A", "symbol": "star"},
            "Cuásar (QSO)": {"ra": [], "dec": [], "nombres": [], "tipos": [], "color": "#FF4500", "symbol": "triangle-up"},
            "Blazar": {"ra": [], "dec": [], "nombres": [], "tipos": [], "color": "#FF6600", "symbol": "triangle-down"},
            "AGN (Genérico)": {"ra": [], "dec": [], "nombres": [], "tipos": [], "color": "#FF9900", "symbol": "triangle-right"},
            "Flares (Enanas Rojas)": {"ra": [], "dec": [], "nombres": [], "tipos": [], "color": "#FF0055", "symbol": "hexagon"}
        }

        for r, d, n, t in zip(ra_list, dec_list, nombres, tipos):
            t_upper = str(t).upper()
            
            if "CATACL" in t_upper or "CV" in t_upper: cat = "Variable Cataclísmica (CV)"
            elif "NOVA" in t_upper and "SUPERNOVA" not in t_upper: cat = "Nova (Clásica)"
            elif "BLAZAR" in t_upper: cat = "Blazar"
            elif "QSO" in t_upper or "CUÁSAR" in t_upper: cat = "Cuásar (QSO)"
            elif "AGN" in t_upper: cat = "AGN (Genérico)"
            elif "SLSN" in t_upper: cat = "Supernova Superluminosa (SLSN)"
            elif "SN IA" in t_upper or "SNIA" in t_upper: cat = "Supernova Ia"
            elif "SN II" in t_upper or "SNII" in t_upper or "IBC" in t_upper or "SN IBC" in t_upper: cat = "Supernova II / Ibc"
            elif "SUPERNOVA" in t_upper or "SN" in t_upper: cat = "Supernova (Sin clasificar)"
            elif "FLARE" in t_upper or "ENANA M" in t_upper: cat = "Flares (Enanas Rojas)"
            else: continue
            
            if categoria_mapa == "💥 Supernovas" and "Supernova" not in cat: continue
            if categoria_mapa == "✨ Novas (Cataclísmicas)" and cat not in ["Nova (Clásica)", "Variable Cataclísmica (CV)"]: continue
            if categoria_mapa == "🕳️ Cuásares / AGN" and cat not in ["Cuásar (QSO)", "Blazar", "AGN (Genérico)"]: continue
            if categoria_mapa == "🔥 Flares (Enanas Rojas)" and "Flare" not in cat: continue
            
            datos_plotly[cat]["ra"].append(r)
            datos_plotly[cat]["dec"].append(d)
            datos_plotly[cat]["nombres"].append(n)
            datos_plotly[cat]["tipos"].append(t_upper)

        fig = go.Figure()

        for nombre_cat, datos in datos_plotly.items():
            if len(datos["ra"]) > 0:
                textos_hover = [f"<b>{nom}</b><br>Subclase: {tip}<br>RA: {ra:.4f}°<br>Dec: {dec:.4f}°" 
                                for nom, tip, ra, dec in zip(datos["nombres"], datos["tipos"], datos["ra"], datos["dec"])]
                
                fig.add_trace(go.Scatter(
                    x=datos["ra"],
                    y=datos["dec"],
                    mode='markers',
                    name=nombre_cat,
                    text=textos_hover,
                    hoverinfo='text',
                    marker=dict(
                        symbol=datos.get("symbol", "star"),
                        size=14,
                        color=datos["color"],
                        opacity=0.75,
                        line=dict(width=0.5, color='white')
                    )
                ))

        fig.update_layout(
            plot_bgcolor='#0e1117',
            paper_bgcolor='#0e1117',
            font=dict(color='lightgray'),
            xaxis=dict(title='Ascensión Recta (Grados)', range=[0, 360], gridcolor='rgba(255, 255, 255, 0.1)', zerolinecolor='gray'),
            yaxis=dict(title='Declinación (Grados)', range=[-90, 90], gridcolor='rgba(255, 255, 255, 0.1)', zerolinecolor='gray'),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=40, r=40, t=40, b=40),
            hovermode='closest'
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(f"No hay eventos de la categoría seleccionada para el {fecha_seleccionada.strftime('%d-%m-%Y')}.")

# --- VISTA 2: FEED DE ALERTAS ---
elif vista == "Feed de Alertas y Circulares":
    st.title("📋 Historial de Circulares de Observación")
    
    cat_filtro = st.selectbox(
        "Filtro Rápido de Categoría:", 
        ["Todas las Alertas", "Supernovas", "Novas / Cataclísmicas", "Cuásares / AGN", "Flares"]
    )
    
    todas_las_alertas = sorted(glob.glob("alertas/CIRCULAR_*.txt"), reverse=True)
    alertas_filtradas = []
    
    fecha_str_busqueda = fecha_seleccionada.strftime("%Y-%m-%d")
    
    for alerta in todas_las_alertas:
        coincide_fecha = False
        try:
            with open(alerta, 'r', encoding='utf-8', errors='ignore') as f:
                if fecha_str_busqueda in f.read():
                    coincide_fecha = True
        except Exception:
            pass
            
        if not coincide_fecha:
            continue
            
        nombre_fmt = formatear_nombre_circular(alerta).upper()
        
        if cat_filtro == "Todas las Alertas":
            alertas_filtradas.append(alerta)
        elif cat_filtro == "Supernovas" and ("SUPERNOVA" in nombre_fmt or "SN " in nombre_fmt or "(SN" in nombre_fmt):
            alertas_filtradas.append(alerta)
        elif cat_filtro == "Novas / Cataclísmicas" and ("NOVA" in nombre_fmt and "SUPERNOVA" not in nombre_fmt):
            alertas_filtradas.append(alerta)
        elif cat_filtro == "Cuásares / AGN" and any(x in nombre_fmt for x in ["AGN", "QSO", "BLAZAR", "CUÁSAR"]):
            alertas_filtradas.append(alerta)
        elif cat_filtro == "Flares" and "FLARE" in nombre_fmt:
            alertas_filtradas.append(alerta)
            
    todos_los_graficos = sorted(glob.glob("data/*.png"), reverse=True)
    
    if alertas_filtradas:
        alertas_filtradas.sort(key=formatear_nombre_circular, reverse=True)
        
        alerta_sel = st.selectbox("Selecciona un evento para inspeccionar:", alertas_filtradas, format_func=formatear_nombre_circular)
        
        nombre_base = os.path.basename(alerta_sel).replace("CIRCULAR_", "").replace(".txt", "")
        ruta_atel = f"alertas_comunidad/ALERTA_ATEL_{nombre_base}.txt"
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("📄 Documentación del Evento")
            tab1, tab2 = st.tabs(["Circular de Observación", "Borrador Telegrama (ATel)"])
            
            with tab1:
                with open(alerta_sel, "r", encoding="utf-8") as f:
                    st.code(f.read(), language="text")
                    
            with tab2:
                if os.path.exists(ruta_atel):
                    with open(ruta_atel, "r", encoding="utf-8") as f:
                        st.code(f.read(), language="text")
                else:
                    st.info("El borrador ATel no se encuentra disponible para este evento.")
                    
        with col2:
            st.subheader("📊 Evidencia Visual (Gráficos)")
            graficos_del_evento = [g for g in todos_los_graficos if nombre_base in g]
            
            if graficos_del_evento:
                graf_sel = st.selectbox("Selecciona la pestaña de evidencia:", graficos_del_evento, format_func=formatear_nombre_grafico)
                st.image(graf_sel, width="stretch")
            else:
                st.warning("No se generaron gráficos u óptica visual para este evento.")
    else:
        st.info(f"No hay circulares de '{cat_filtro}' registradas para la fecha {fecha_str_busqueda}.")

# --- VISTA 3: BITÁCORAS ---
elif vista == "Bitácoras del Sistema":
    st.title("📜 Monitoreo de Operaciones en Tiempo Real")
    st.info("🕒 **Sincronización:** Registros en Tiempo Universal Coordinado (UTC). Base: Hora Oficial de Magallanes (UTC-3).")
    
    def parse_logs(log_file, red_name):
        parsed = []
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                for linea in f:
                    if "-> Procesadas" in linea or "===" in linea or linea.strip() == "":
                        continue
                    try:
                        if linea.startswith("["):
                            fecha_str = linea[1:11]
                            hora_str = linea[12:20]
                            mensaje = linea[22:].strip()
                            timestamp_str = f"{fecha_str} {hora_str}"
                            parsed.append({
                                'timestamp': timestamp_str,
                                'fecha': fecha_str,
                                'hora': hora_str,
                                'msg': mensaje,
                                'red': red_name
                            })
                    except Exception:
                        pass
        return parsed

    logs_ztf = parse_logs("bitacora_ZTF.log", "ZTF (Norte)")
    logs_tns = parse_logs("bitacora_TNS_GLOBAL.log", "TNS Global (Sur)")
    
    def agrupar_en_ciclos(logs):
        ciclos_agrupados = []
        ciclo_actual = None
        for log in logs:
            if "APUNTANDO TELESCOPIO" in log['msg']:
                if ciclo_actual is not None:
                    ciclos_agrupados.append(ciclo_actual)
                ciclo_actual = {
                    'red': log['red'],
                    'fecha': log['fecha'],
                    'inicio': log['hora'],
                    'timestamp': log['timestamp'],
                    'logs': [log],
                    'candidatos': 0,
                    'errores': 0
                }
            else:
                if ciclo_actual is None:
                    ciclo_actual = {
                        'red': log['red'],
                        'fecha': log['fecha'],
                        'inicio': log['hora'],
                        'timestamp': log['timestamp'],
                        'logs': [],
                        'candidatos': 0,
                        'errores': 0
                    }
                ciclo_actual['logs'].append(log)
                
            if "procesado exitosamente" in log['msg'] or "Descargando ficha" in log['msg'] or "identificado" in log['msg'].lower() or "RECLASIFICADO" in log['msg']:
                ciclo_actual['candidatos'] += 1
            if "Error" in log['msg'] or "denegado" in log['msg'].lower():
                ciclo_actual['errores'] += 1
                
        if ciclo_actual is not None:
            ciclos_agrupados.append(ciclo_actual)
        return ciclos_agrupados

    ciclos_ztf = agrupar_en_ciclos(logs_ztf)
    ciclos_tns = agrupar_en_ciclos(logs_tns)
    
    todos_los_ciclos = ciclos_ztf + ciclos_tns
    todos_los_ciclos.sort(key=lambda x: x['timestamp'], reverse=True)
    
    fecha_str_seleccionada = fecha_seleccionada.strftime("%Y-%m-%d")
    ciclos_del_dia = [c for c in todos_los_ciclos if c['fecha'] == fecha_str_seleccionada]

    total_patrullajes = len(ciclos_del_dia)
    total_candidatos = sum(c['candidatos'] for c in ciclos_del_dia)
    total_errores = sum(c['errores'] for c in ciclos_del_dia)
    
    st.subheader(f"📊 Métricas de Patrullaje ({fecha_str_seleccionada})")
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
                st.markdown(f"#### {color_red} [{ciclo['inicio']} UTC] {ciclo['red']}")
                
                if ciclo['errores'] > 0:
                    st.error(f"⚠️ **Atención:** Se detectaron {ciclo['errores']} errores de conexión. | ⚡ {ciclo['candidatos']} alertas evaluadas.")
                elif ciclo['candidatos'] > 0:
                    st.success(f"✅ Ciclo operativo y sin errores. | ⚡ **{ciclo['candidatos']} candidatas astrofísicas** aisladas y procesadas.")
                else:
                    st.info(f"💤 Ciclo completado. No se detectaron eventos anómalos o de alta prioridad en este patrullaje.")
                    
                with st.expander("👨‍💻 Auditar Registro Técnico (Modo Terminal)"):
                    log_text = ""
                    for log in ciclo['logs']:
                        log_text += f"[{log['hora']}] {log['msg']}\n"
                    st.code(log_text, language="text")
                
                st.write("---")
    else:
        st.warning(f"El observatorio no registró patrullajes para la fecha seleccionada ({fecha_str_seleccionada}).")

# --- VISTA 4: MANTENIMIENTO ---
elif vista == "Mantenimiento del Sistema":
    st.title("⚙️ Mantenimiento y Purga de Datos")
    st.markdown("⚠️ **Área Restringida:** Se requiere autorización del administrador para purgar el disco local.")
    
    password = st.text_input("Código de Autorización:", type="password")
    
    if password == os.getenv("ADMIN_PASSWORD") and password != "":
        st.success("Autorización confirmada. Protocolos de purga desbloqueados.")
        st.markdown("Usa esta herramienta para borrar archivos antiguos o hacer un reseteo de fábrica (0 días).")
        
        dias_limite = st.slider("Borrar archivos más antiguos de (Días) [0 = Reset de Fábrica]:", 0, 90, 0)
        
        if st.button("🚨 EJECUTAR PURGA AHORA", type="primary"):
            tiempo_actual = time.time()
            tiempo_limite = tiempo_actual - (dias_limite * 86400)
            archivos_borrados = 0
            
            carpetas = ["alertas", "data", "alertas_comunidad"]
            
            for carpeta in carpetas:
                if os.path.exists(carpeta):
                    for archivo in os.listdir(carpeta):
                        if archivo == "memoria_tns.txt":
                            continue
                            
                        ruta_completa = os.path.join(carpeta, archivo)
                        if os.path.isfile(ruta_completa) and os.path.getmtime(ruta_completa) <= tiempo_limite:
                            os.remove(ruta_completa)
                            archivos_borrados += 1
                            
            if dias_limite == 0:
                logs_a_borrar = ["bitacora_ZTF.log", "bitacora_LSST.log", "bitacora_TNS_GLOBAL.log", "tracker_mjd.txt", "bitacora_cron.log"]
                for log_file in logs_a_borrar:
                    if os.path.exists(log_file):
                        os.remove(log_file)
                        archivos_borrados += 1
                            
            if archivos_borrados > 0:
                st.success(f"¡Purga completada exitosamente! Se han eliminado {archivos_borrados} archivos.")
                st.rerun() 
            else:
                st.info("No se encontraron archivos para borrar. El sistema está limpio.")
                
    elif password != "":
        st.error("Código de autorización incorrecto. Intento bloqueado.")

# --- VISTA 5: ACERCA DE / CONTACTO (ACTUALIZADA) ---
elif vista == "Acerca del Observatorio":
    st.title("🔭 Estación Magallanes")
    st.success("🟢 **Nodo Activo y Operando** - Punta Arenas, Región de Magallanes, Chile.")
    
    col_texto, col_imagen = st.columns([2, 1])
    
    with col_texto:
        st.markdown("""
        ### Explorando el Universo Dinámico desde el Fin del Mundo
        La **Estación Magallanes** es un nodo de investigación y ciencia ciudadana astrofísica automatizado, operando ininterrumpidamente desde la Patagonia Chilena. 
        
        Nuestro algoritmo rastrea el cielo nocturno en tiempo real, actuando como un **Broker Astrofísico local**. Utilizamos Inteligencia Artificial de frontera para procesar "ríos de datos" masivos y detectar eventos catastróficos o transitorios antes de que se desvanezcan en el cosmos.
        
        *Un proyecto independiente de ciencia ciudadana, desarrollado y mantenido por Edgardo A. Casanova Pino.*
        """)
        
    with col_imagen:
        st.image("logo.jpeg", width="stretch", caption="Sede Virtual Estación Magallanes.")
        
    st.divider()
    st.subheader("Arquitectura del Flujo de Datos")
    
    col_c1, col_c2, col_c3, col_c4 = st.columns(4)
    with col_c1:
        st.info("**🛰️ ZTF (Norte)**\n\nCaptura de explosiones desde el Observatorio Palomar, California.")
    with col_c2:
        st.info("**📡 TNS / IAU**\n\nEl radar global y oficial de descubrimientos de la Unión Astronómica Internacional.")
    with col_c3:
        st.info("**🧠 ALeRCE**\n\nRed neuronal chilena de clasificación predictiva en tiempo real.")
    with col_c4:
        st.info("**🔭 LSST (Rubin)**\n\nPreparación para el aluvión de datos astronómicos más grande de la historia.")

    st.divider()
    st.subheader("Colaboración Científica")
    st.markdown("""
    Este sistema fue construido para tender un puente entre la ciencia de frontera y la observación independiente. Si deseas integrar nuestra telemetría a tu observatorio o colaborar en el análisis espectroscópico de nuestros candidatos, la puerta está abierta.
    """)
    
    col_btn1, col_btn2, _ = st.columns([1.5, 1, 1])
    with col_btn1:
        st.markdown("<div style='padding-top: 5px;'>✉️ <b>Contactar al Proyecto:</b> <code>contacto@estacionmagallanes.org</code></div>", unsafe_allow_html=True)
    with col_btn2:
        st.link_button("💻 Ver Repositorio en GitHub", "https://github.com/Edgardo-Casanova/estacion-magallanes", use_container_width=True)
