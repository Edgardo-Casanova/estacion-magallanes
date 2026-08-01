import streamlit as st
import os
import glob
import time
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
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
        elif "Ningún evento superó" in contenido_final or "Procesadas" in contenido_final or "Conexión exitosa" in contenido_final:
            return "Operativa", "🟢"
        else:
            return "En reposo", "🟡"
    except Exception:
        return "Desconocido", "⚪"

def extraer_coordenadas_alertas():
    ra_list, dec_list, nombres, tipos = [], [], [], []
    archivos = glob.glob("alertas/CIRCULAR_*.txt")
    for archivo in archivos:
        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                lineas = f.readlines()
                nombre_actual = "Desconocido"
                tipo_actual = "FLARE" 
                
                for linea in lineas:
                    if "OBJETO DETECTADO" in linea or "EVENTO DETECTADO" in linea:
                        parte_valor = linea.split(":", 1)[1].strip()
                        if "(" in parte_valor and ")" in parte_valor:
                            nombre_actual = parte_valor.split("(")[0].strip()
                            tipo_actual = parte_valor.split("(")[1].replace(")", "").strip().upper()
                        else:
                            nombre_actual = parte_valor
                            
                    if "COORDENADAS ICRS" in linea:
                        partes = linea.split("|")
                        ra = float(partes[0].split("RA")[1].strip())
                        dec = float(partes[1].split("Dec")[1].strip())
                        ra_list.append(ra)
                        dec_list.append(dec)
                        nombres.append(nombre_actual)
                        tipos.append(tipo_actual)
        except Exception:
            pass
    return ra_list, dec_list, nombres, tipos

def formatear_nombre_circular(ruta_archivo):
    """Lee una circular y devuelve un nombre bonito para el menú desplegable."""
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
    """Transforma el nombre crudo del gráfico en una etiqueta elegante."""
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

# --- VISTA 1: DASHBOARD PRINCIPAL Y MAPA ESTELAR ---
if vista == "Dashboard Principal (Telemetría)":
    st.title("🛰️ Estación Magallanes - Telemetría")
    
    estado_ztf, icono_ztf = obtener_estado_red("bitacora_ZTF.log")
    estado_lsst, icono_lsst = obtener_estado_red("bitacora_TNS_GLOBAL.log")
    ra_list, dec_list, nombres, tipos = extraer_coordenadas_alertas()
    
    # NUEVA LÓGICA DE CONTADORES SEPARADOS
    total_flares = sum(1 for t in tipos if "FLARE" in t)
    total_novas = sum(1 for t in tipos if "NOVA" in t and "SUPERNOVA" not in t)
    total_supernovas = sum(1 for t in tipos if "SUPERNOVA" in t)
    total_agn = sum(1 for t in tipos if "AGN" in t or "QSO" in t or "BLAZAR" in t)
    
    st.subheader("📡 Estado de la Red de Alertas")
    col_red1, col_red2 = st.columns(2)
    col_red1.metric(f"ZTF (Norte)", estado_ztf, icono_ztf)
    col_red2.metric(f"LSST / TNS (Sur)", estado_lsst, icono_lsst)
    
    st.subheader("📊 Detecciones Clasificadas")
    col_det1, col_det2, col_det3, col_det4 = st.columns(4)
    col_det1.metric("Flares (Enanas Rojas)", str(total_flares), "Estelar", delta_color="normal")
    col_det2.metric("Novas (Cataclísmicas)", str(total_novas), "Binaria", delta_color="normal")
    col_det3.metric("Supernovas", str(total_supernovas), "Destrucción", delta_color="normal")
    col_det4.metric("Cuásares / AGN", str(total_agn), "Agujero Negro", delta_color="normal")
    
    st.divider()
    
    st.subheader("🌌 Mapa Celeste de Impactos (Eventos Transitorios)")
    
    if ra_list:
        fig, ax = plt.subplots(figsize=(12, 5), facecolor='#0e1117')
        ax.set_facecolor('#0e1117')
        
        for i in range(len(ra_list)):
            if "FLARE" in tipos[i]: color_punto = '#ff0055'
            elif "AGN" in tipos[i]: color_punto = '#ffff00'
            else: color_punto = '#00ffff'
                
            ax.scatter(ra_list[i], dec_list[i], color=color_punto, s=150, marker='*', edgecolor='white', zorder=2)
            
            etiqueta = f"{nombres[i]}\n({tipos[i]})"
            ax.annotate(etiqueta, (ra_list[i], dec_list[i]), textcoords="offset points", xytext=(0,10), ha='center', color='lightgray', fontsize=8)
        
        ax.set_xlim(0, 360)
        ax.set_ylim(-90, 90)
        ax.axhline(0, color='gray', linestyle='--', alpha=0.3)
        ax.set_xlabel("Ascensión Recta (Grados)", color='lightgray')
        ax.set_ylabel("Declinación (Grados)", color='lightgray')
        ax.tick_params(colors='lightgray')
        ax.grid(True, alpha=0.1)
        
        red_patch = mpatches.Patch(color='#ff0055', label='Flares (Enanas Rojas)')
        cyan_patch = mpatches.Patch(color='#00ffff', label='Supernovas / Novas')
        yellow_patch = mpatches.Patch(color='#ffff00', label='Cuásares (AGN)')
        ax.legend(handles=[red_patch, cyan_patch, yellow_patch], facecolor='#0e1117', edgecolor='gray', loc='upper right', labelcolor='white')
        
        st.pyplot(fig)
    else:
        st.info("Aún no hay eventos registrados para dibujar en el mapa estelar.")

# --- VISTA 2: FEED DE ALERTAS ---
elif vista == "Feed de Alertas y Circulares":
    st.title("📋 Historial de Circulares de Observación")
    alertas = sorted(glob.glob("alertas/CIRCULAR_*.txt"), reverse=True)
    graficos = sorted(glob.glob("data/*.png"), reverse=True)
    
    if alertas:
        alerta_sel = st.selectbox("Selecciona un evento para inspeccionar:", alertas, format_func=formatear_nombre_circular)
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("📄 Reporte Oficial (Circular)")
            with open(alerta_sel, "r", encoding="utf-8") as f:
                st.code(f.read(), language="text")
        with col2:
            st.subheader("📊 Evidencia Visual (Gráficos)")
            if graficos:
                nombre_base = os.path.basename(alerta_sel).replace("CIRCULAR_", "").replace(".txt", "")
                grafico_recomendado = next((g for g in graficos if nombre_base in g), graficos[0])
                graf_indice = graficos.index(grafico_recomendado) if grafico_recomendado in graficos else 0
                
                graf_sel = st.selectbox("Selecciona la pestaña de evidencia:", graficos, index=graf_indice, format_func=formatear_nombre_grafico)
                st.image(graf_sel, width="stretch")
    else:
        st.info("Aún no se han generado circulares de alerta.")

# --- VISTA 3: BITÁCORAS ---
elif vista == "Bitácoras del Sistema":
    st.title("📜 Bitácoras de Operación de las Redes")
    st.info("🕒 **Nota de Sincronización Temporal:** Los registros de esta bitácora operan bajo el **Tiempo Universal Coordinado (UTC)**. Para la conversión a la hora local de nuestra estación base, rige la Hora Oficial de la **Región de Aysén y Región de Magallanes y la Antártica Chilena** (UTC-3 fija), dictaminada por el [Servicio Hidrográfico y Oceanográfico de la Armada de Chile (SHOA)](https://www.horaoficial.cl/).")
    st.markdown("Registro interactivo del radar automatizado. Expande un día para ver los detalles del patrullaje.")
    
    col_ztf, col_lsst = st.columns(2)
    
    def render_bitacora_visual(ruta):
        if not os.path.exists(ruta): 
            st.info("Sin registros de actividad.")
            return
            
        with open(ruta, "r", encoding="utf-8") as f:
            lineas = f.readlines()
            
        dias = {}
        for linea in lineas:
            if "-> Procesadas" in linea or "===" in linea or linea.strip() == "":
                continue
                
            try:
                if linea.startswith("["):
                    fecha = linea[1:11] 
                    hora = linea[12:20] 
                    mensaje = linea[22:].strip() 
                    
                    if fecha not in dias:
                        dias[fecha] = []
                    dias[fecha].append((hora, mensaje))
            except Exception:
                pass
                
        if not dias:
            st.info("Bitácora limpia. Esperando nuevos eventos.")
            return
            
        for fecha in sorted(dias.keys(), reverse=True):
            es_hoy = (fecha == max(dias.keys()))
            with st.expander(f"📅 Resumen Operativo: {fecha}", expanded=es_hoy):
                for hora, msg in dias[fecha]:
                    if "BINGO" in msg or "éxito" in msg or "identificado" in msg.lower() or "guardado" in msg.lower():
                        st.success(f"**{hora}** | ✅ {msg}")
                    elif "Error" in msg or "denegado" in msg.lower():
                        st.error(f"**{hora}** | 🚨 {msg}")
                    elif "APUNTANDO" in msg or "Contactando" in msg or "Descargando" in msg or "Disparando" in msg:
                        st.info(f"**{hora}** | 📡 {msg}")
                    elif "Sin alertas" in msg or "Ningún evento" in msg or "silencio" in msg.lower():
                        st.warning(f"**{hora}** | 💤 {msg}")
                    else:
                        st.markdown(f"`{hora}` | {msg}")
            
    with col_ztf:
        st.subheader("Bitácora ZTF (Norte)")
        render_bitacora_visual("bitacora_ZTF.log")
            
    with col_lsst:
        st.subheader("Bitácora TNS Global (Sur)")
        render_bitacora_visual("bitacora_TNS_GLOBAL.log")

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

# --- VISTA 5: ACERCA DE / CONTACTO ---
elif vista == "Acerca del Observatorio":
    st.title("🔭 Estación Magallanes")
    
    col_texto, col_imagen = st.columns([2, 1])
    
    with col_texto:
        st.markdown("""
        ### Explorando el Universo Dinámico desde el Fin del Mundo
        La **Estación Magallanes** es un nodo de investigación y ciencia ciudadana astrofísica automatizado operando ininterrumpidamente desde Punta Arenas, en la Patagonia Chilena. 
        
        Nuestro algoritmo rastrea el cielo nocturno en tiempo real, operando como un **Broker Astrofísico local**. Utilizamos Inteligencia Artificial de frontera para procesar "ríos de datos" masivos y detectar eventos catastróficos y transitorios antes de que se desvanezcan.
        
        #### Arquitectura del Flujo de Datos
        Nuestros radares barren las corrientes de alertas de las instituciones más prestigiosas del mundo para democratizar el seguimiento astronómico táctico:
        *   **Zwicky Transient Facility (ZTF):** Captura de explosiones en el hemisferio norte (Palomar, California).
        *   **Transient Name Server (TNS) / IAU:** Radar global oficial de descubrimientos de supernovas.
        *   **ALeRCE:** Nuestra principal red neuronal de clasificación predictiva desarrollada en Chile.
        *   **Vera C. Rubin Observatory (LSST):** En preparación para el aluvión de datos astronómicos más grande de la historia humana (Cerro Pachón, Chile).
        
        #### Colaboración Científica
        Este sistema fue construido para tender un puente entre la ciencia de frontera y la observación independiente. Si deseas integrar nuestra telemetría a tu observatorio o colaborar en el análisis espectroscópico de nuestros candidatos, la puerta está abierta.
        """)
        
        st.info("✉️ **Contacto:** [contacto@estacionmagallanes.org](mailto:contacto@estacionmagallanes.org)")
        
    with col_imagen:
        st.image("logo.jpeg", width="stretch", caption="Sede Virtual Estación Magallanes. Patagonia, Chile.")
