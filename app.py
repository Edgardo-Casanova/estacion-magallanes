import streamlit as st
import os
import glob
import time
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

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

        # Extraer SOLO la última sesión de escaneo buscando la cabecera de inicio
        sesion_actual = []
        for linea in reversed(lineas):
            sesion_actual.insert(0, linea)
            if "APUNTANDO TELESCOPIO" in linea:
                break
                
        contenido_final = "".join(sesion_actual)
        
        if "Error" in contenido_final:
            return "Error ALeRCE", "🔴"
        elif "Ningún evento superó" in contenido_final or "Procesadas" in contenido_final:
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
                tipo_actual = "FLARE" # Por defecto
                
                for linea in lineas:
                    # Detecta tanto el formato de Flare como el de Supernova
                    if "OBJETO DETECTADO" in linea or "EVENTO DETECTADO" in linea:
                        parte_valor = linea.split(":")[1].strip()
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

# --- BARRA LATERAL DE NAVEGACIÓN ---
st.sidebar.image("logo.jpeg", use_container_width=True)
st.sidebar.divider()

st.sidebar.title("Panel de Control")
vista = st.sidebar.selectbox(
    "Selecciona una vista:",
    [
        "Dashboard Principal (Telemetría)", 
        "Feed de Alertas y Circulares", 
        "Bitácoras del Sistema", 
        "Mantenimiento del Sistema",
        "Acerca del Observatorio / Contacto"
    ]
)

# --- VISTA 1: DASHBOARD PRINCIPAL Y MAPA ESTELAR ---
if vista == "Dashboard Principal (Telemetría)":
    st.title("🛰️ Estación Magallanes - Telemetría")
    
    # Lectura del estado de las redes y extracción de datos
    estado_ztf, icono_ztf = obtener_estado_red("bitacora_ZTF.log")
    estado_lsst, icono_lsst = obtener_estado_red("bitacora_LSST.log")
    ra_list, dec_list, nombres, tipos = extraer_coordenadas_alertas()
    
    # Cálculos de telemetría
    total_flares = sum(1 for t in tipos if "FLARE" in t)
    total_supernovas = sum(1 for t in tipos if "SUPERNOVA" in t or "NOVA" in t)
    
    # 1. Panel de Métricas Rápidas
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(f"ZTF (Norte)", estado_ztf, icono_ztf)
    col2.metric(f"LSST / TNS (Sur)", estado_lsst, icono_lsst)
    col3.metric("Flares Registrados", str(total_flares), "Estelar", delta_color="normal")
    col4.metric("Supernovas Cazadas", str(total_supernovas), "Extragaláctico", delta_color="normal")
    
    st.divider()
    
    # 2. Mapa Celeste Multicategoría
    st.subheader("🌌 Mapa Celeste de Impactos (Eventos Transitorios)")
    
    if ra_list:
        fig, ax = plt.subplots(figsize=(12, 5), facecolor='#0e1117')
        ax.set_facecolor('#0e1117')
        
        # Dibujar cada punto con su color respectivo
        for i in range(len(ra_list)):
            color_punto = '#ff0055' if "FLARE" in tipos[i] else '#00ffff'
            ax.scatter(ra_list[i], dec_list[i], color=color_punto, s=150, marker='*', edgecolor='white', zorder=2)
            
            # Etiquetar cada estrella con su nombre y tipo
            etiqueta = f"{nombres[i]}\n({tipos[i]})"
            ax.annotate(etiqueta, (ra_list[i], dec_list[i]), textcoords="offset points", xytext=(0,10), ha='center', color='lightgray', fontsize=8)
        
        ax.set_xlim(0, 360)
        ax.set_ylim(-90, 90)
        ax.axhline(0, color='gray', linestyle='--', alpha=0.3) # Línea del Ecuador
        ax.set_xlabel("Ascensión Recta (Grados)", color='lightgray')
        ax.set_ylabel("Declinación (Grados)", color='lightgray')
        ax.tick_params(colors='lightgray')
        ax.grid(True, alpha=0.1)
        
        # Leyenda personalizada
        red_patch = mpatches.Patch(color='#ff0055', label='Flares (Enanas Rojas)')
        cyan_patch = mpatches.Patch(color='#00ffff', label='Supernovas / Novas')
        ax.legend(handles=[red_patch, cyan_patch], facecolor='#0e1117', edgecolor='gray', loc='upper right')
        
        st.pyplot(fig)
    else:
        st.info("Aún no hay eventos registrados para dibujar en el mapa estelar.")

# --- VISTA 2: FEED DE ALERTAS ---
elif vista == "Feed de Alertas y Circulares":
    st.title("📋 Historial de Circulares de Observación")
    alertas = sorted(glob.glob("alertas/CIRCULAR_*.txt"), reverse=True)
    graficos = sorted(glob.glob("data/*.png"), reverse=True)
    
    if alertas:
        alerta_sel = st.selectbox("Selecciona una circular para inspeccionar:", alertas)
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("📄 Reporte Oficial (Circular)")
            with open(alerta_sel, "r", encoding="utf-8") as f:
                st.code(f.read(), language="text")
        with col2:
            st.subheader("📊 Evidencia Visual (Gráficos)")
            if graficos:
                graf_sel = st.selectbox("Selecciona el gráfico a visualizar:", graficos)
                st.image(graf_sel)
    else:
        st.info("Aún no se han generado circulares de alerta.")

# --- VISTA 3: BITÁCORAS ---
elif vista == "Bitácoras del Sistema":
    st.title("📜 Bitácoras de Operación de las Redes")
    col_ztf, col_lsst = st.columns(2)
    
    with col_ztf:
        st.subheader("Bitácora ZTF (Norte)")
        if os.path.exists("bitacora_ZTF.log"):
            with open("bitacora_ZTF.log", "r", encoding="utf-8") as f:
                st.code(f.read(), language="text")
        else:
            st.info("Sin registros de actividad para ZTF.")
            
    with col_lsst:
        st.subheader("Bitácora LSST / TNS (Sur)")
        if os.path.exists("bitacora_LSST.log"):
            with open("bitacora_LSST.log", "r", encoding="utf-8") as f:
                st.code(f.read(), language="text")
        else:
            st.info("Sin registros de actividad para LSST.")

# --- VISTA 4: MANTENIMIENTO ---
elif vista == "Mantenimiento del Sistema":
    st.title("⚙️ Mantenimiento y Purga de Datos")
    st.markdown("⚠️ **Área Restringida:** Se requiere autorización del administrador para purgar el disco local.")
    
    # Sistema de seguridad para proteger el borrado de archivos
    password = st.text_input("Código de Autorización:", type="password")
    
    # Protegemos la clave usando variables de entorno
    if password == os.getenv("ADMIN_PASSWORD") and password != "":
        st.success("Autorización confirmada. Protocolos de purga desbloqueados.")
        st.markdown("Usa esta herramienta para borrar archivos antiguos o hacer un reseteo de fábrica (0 días).")
        
        # MODIFICACIÓN: Permitir 0 días para borrar TODO de inmediato
        dias_limite = st.slider("Borrar archivos más antiguos de (Días) [0 = Reset de Fábrica]:", 0, 90, 0)
        
        if st.button("🚨 EJECUTAR PURGA AHORA", type="primary"):
            tiempo_actual = time.time()
            tiempo_limite = tiempo_actual - (dias_limite * 86400) # 86400 segundos = 1 día
            archivos_borrados = 0
            
            # Revisamos las 3 carpetas que acumulan datos
            carpetas = ["alertas", "data", "alertas_comunidad"]
            
            for carpeta in carpetas:
                if os.path.exists(carpeta):
                    for archivo in os.listdir(carpeta):
                        ruta_completa = os.path.join(carpeta, archivo)
                        # Se cambió a <= para que cuando sea 0 días, borre todo
                        if os.path.isfile(ruta_completa) and os.path.getmtime(ruta_completa) <= tiempo_limite:
                            os.remove(ruta_completa)
                            archivos_borrados += 1
                            
            # Si el límite es 0, borramos también las bitácoras (logs)
            if dias_limite == 0:
                for log_file in ["bitacora_ZTF.log", "bitacora_LSST.log"]:
                    if os.path.exists(log_file):
                        os.remove(log_file)
                        archivos_borrados += 1
                            
            if archivos_borrados > 0:
                st.success(f"¡Purga completada exitosamente! Se han eliminado {archivos_borrados} archivos.")
            else:
                st.info("No se encontraron archivos para borrar. El sistema está limpio.")
                
    elif password != "":
        st.error("Código de autorización incorrecto. Intento bloqueado.")

# --- VISTA 5: ACERCA DE / CONTACTO ---
elif vista == "Acerca del Observatorio / Contacto":
    st.title("🔭 Acerca de la Estación Magallanes")
    
    col_texto, col_imagen = st.columns([2, 1])
    
    with col_texto:
        st.markdown("""
        ### Proyecto de Ciencia Ciudadana Astrofísica
        La **Estación Magallanes** es un centro de monitoreo astronómico automatizado que opera desde Punta Arenas, en la Patagonia Chilena. 
        
        Nuestro objetivo principal es la vigilancia del cielo nocturno en tiempo real, utilizando Inteligencia Artificial para identificar y clasificar eventos astronómicos transitorios (como supernovas, novas y erupciones estelares extremas) capturados por los telescopios más grandes del mundo.
        
        #### Redes de Observación Conectadas:
        *   **ZTF (Zwicky Transient Facility):** Patrullaje del hemisferio norte desde el Observatorio Palomar, California.
        *   **ALeRCE (Automatic Learning for the Rapid Classification of Events):** Broker chileno que nos provee los modelos predictivos de IA.
        *   **LSST (Legacy Survey of Space and Time):** Preparación y conexión activa para el observatorio Vera C. Rubin (Chile).
        
        #### Contacto y Colaboración
        Este es un proyecto independiente impulsado por la curiosidad científica. Si representas a una institución, eres astrónomo aficionado o deseas colaborar con nuestra iniciativa de ciencia ciudadana, no dudes en ponerte en contacto.
        """)
        
        # MODIFICACIÓN: Cambio de correo al corporativo oficial
        st.info("📧 **Correo Institucional / Administración:** contacto@estacionmagallanes.org")
        
    with col_imagen:
        st.image("logo.jpeg", use_container_width=True, caption="Estación Magallanes, Punta Arenas, Chile.")
