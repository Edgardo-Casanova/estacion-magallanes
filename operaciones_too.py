"""
=============================================================================
PROYECTO   : Observatorio Automatizado Estación Magallanes
MÓDULO     : operaciones_too.py (Megáfono Comunitario y ATel)
VERSIÓN    : 17.0 (ARQUITECTURA LIMPIA - EXCLUSIVO PARA EVENTOS EN VIVO)

DESCRIPCIÓN:
Redacta reportes bilingües oficiales (AAVSO y Astronomer's Telegram) 
exclusivamente para hallazgos frescos (ZTF/LSST) filtrados por el 
pipeline de la Estación Magallanes. 

Mejoras Implementadas:
1. Sincronización Temporal (MJD/UTC): Exige y publica el tiempo exacto.
2. Lógica Dinámica de Redshift: Indica "Pendiente de seguimiento" si z=0.0.
3. Evasión de Hardcoding: Evalúa booleanos reales para Enanas Rojas.
4. Escudo Cloud: Sistema de guardado híbrido (Local/Bucket).
=============================================================================
"""

import os
from datetime import datetime
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
    except Exception: pass

def guardar_archivo_texto(ruta, contenido):
    if MODO_LOCAL:
        os.makedirs(os.path.dirname(ruta) if os.path.dirname(ruta) else '.', exist_ok=True)
        try:
            with open(ruta, 'w', encoding='utf-8') as f: f.write(contenido)
        except Exception: pass
    else:
        if bucket is None: return
        try:
            blob = bucket.blob(ruta)
            blob.upload_from_string(contenido, content_type='text/plain; charset=utf-8')
        except Exception: pass
    return ruta

# =====================================================================
# REDACCIÓN Y DESPACHO DE TELEGRAMAS
# =====================================================================
def generar_alerta_comunidad(nombre_evento, ra, dec, tipo_evento="flare", extra_data=None):
    if extra_data is None: extra_data = {}
        
    print(f"\n[🚀] INICIANDO PROTOCOLO DE ALERTA COMUNITARIA PARA {nombre_evento} ({tipo_evento.upper()})")
    nombre_archivo = nombre_evento.replace(' ', '_').replace('/', '-')
    
    # 1. EXTRACCIÓN DE DATOS SINCRONIZADOS
    distancia = extra_data.get("distancia", "Desconocida")
    mjd_obs = extra_data.get("mjd_deteccion")
    
    if mjd_obs:
        utc_obs = Time(mjd_obs, format='mjd').to_datetime().strftime("%Y-%m-%d %H:%M:%S UTC")
        tiempo_texto_es = f"{utc_obs} (MJD: {mjd_obs:.4f})"
        tiempo_texto_en = f"{utc_obs} (MJD: {mjd_obs:.4f})"
    else:
        tiempo_texto_es = "Pendiente de confirmación fotométrica estricta"
        tiempo_texto_en = "Pending strict photometric confirmation"

    # =================================================================
    # PLANTILLA 1: REDES ESTELARES (AAVSO) -> Para Flares
    # =================================================================
    if tipo_evento == "flare":
        ew_halfa = extra_data.get("ew_halfa", 0.0)
        tiene_planetas = extra_data.get("tiene_planetas", False)
        es_enana_roja = extra_data.get("es_enana_roja", None)
        fuente_espectro = extra_data.get("fuente_espectro", "Desconocida")
        
        # Lógica dinámica: Tipo de Estrella
        if es_enana_roja is True:
            tipo_estrella_es = "Enana M (Firma infrarroja SED confirmada)"
            tipo_estrella_en = "M-Dwarf (Confirmed SED infrared signature)"
        else:
            tipo_estrella_es = "Estrella Activa (Subtipo espectral por confirmar)"
            tipo_estrella_en = "Active Star (Spectral subtype pending confirmation)"
            
        planetas_es = "Sí (Posible impacto en atmósferas exoplanetarias)" if tiene_planetas else "No detectados en radio cinemático"
        planetas_en = "Yes (Potential impact on exoplanetary atmospheres)" if tiene_planetas else "Not detected in kinematic radius"
        
        texto_alerta = f"""======================================================================
[ESPAÑOL] ALERTA DE EVENTO TRANSITORIO ESTELAR - ESTACIÓN MAGALLANES
======================================================================
A la comunidad de la Asociación Americana de Observadores de Estrellas Variables (AAVSO):

Se solicita seguimiento fotométrico urgente para el siguiente objetivo,
debido a la detección automatizada de alta actividad cromosférica (posible mega-flare).

[1] IDENTIFICACIÓN DEL OBJETIVO Y TIEMPO
* Nombre / ID SIMBAD    : {nombre_evento}
* Coordenadas (ICRS)    : RA {ra:.5f} | Dec {dec:.5f}
* Distancia Estimada    : {distancia}
* Momento de Detección  : {tiempo_texto_es}

[2] JUSTIFICACIÓN ASTROFÍSICA (Análisis Estación Magallanes)
* Tipo de Estrella      : {tipo_estrella_es}
* Actividad Cromosférica: Confirmada vía {fuente_espectro} (Ancho Equivalente H-alfa/CaII aprox: {ew_halfa:.2f})
* Sistema Planetario    : {planetas_es}

[3] SOLICITUD DE OBSERVACIÓN
* Filtros requeridos    : B, V (Johnson) o g, r (Sloan)
* Cadencia              : Continua (exposiciones cortas)

Atentamente,
Pipeline Automatizado Estación Magallanes | Código de Observador AAVSO: ECDA

----------------------------------------------------------------------
[ENGLISH] STELLAR TRANSIENT EVENT ALERT - MAGALLANES STATION
----------------------------------------------------------------------
To the American Association of Variable Star Observers (AAVSO) community:

Urgent time-series photometric follow-up is requested for the following target
due to the automated detection of high chromospheric activity (potential mega-flare).

[1] TARGET IDENTIFICATION & TIMING
* Name / SIMBAD ID      : {nombre_evento}
* Coordinates (ICRS)    : RA {ra:.5f} | Dec {dec:.5f}
* Est. Distance         : {distancia}
* Detection Time (Peak) : {tiempo_texto_en}

[2] ASTROPHYSICAL JUSTIFICATION (Magallanes Station Analysis)
* Star Type             : {tipo_estrella_en}
* Chromospheric Activity: Confirmed via {fuente_espectro} (Equivalent Width H-alpha/CaII approx: {ew_halfa:.2f})
* Planetary System      : {planetas_en}

[3] OBSERVATIONAL REQUEST
* Required Filters      : B, V (Johnson) or g, r (Sloan)
* Cadence               : Continuous (short exposures to avoid saturation)

Best regards,
Magallanes Station Automated Pipeline | AAVSO Observer Code: ECDA
======================================================================"""
        ruta_txt = f"alertas_comunidad/ALERTA_AAVSO_{nombre_archivo}.txt"

    # =================================================================
    # PLANTILLA 2: REDES EXTRAGALÁCTICAS E INTRAGALÁCTICAS (ATel)
    # =================================================================
    elif tipo_evento in ["supernova", "nova", "agn", "blazar"]:
        galaxia = extra_data.get("galaxia", "Desconocida")
        redshift = extra_data.get("redshift", None)
        
        # Inteligencia para Redshifts faltantes en eventos ZTF/LSST vivos
        if redshift is None or redshift == 0.0 or redshift == "Desconocido":
            z_str_es = "Pendiente de seguimiento espectroscópico"
            z_str_en = "Pending spectroscopic follow-up"
        else:
            z_val = f"{redshift:.5f}" if isinstance(redshift, float) else str(redshift)
            z_str_es = z_val
            z_str_en = z_val
        
        if tipo_evento == "blazar":
            goal_es = "Confirmar chorro relativista (jet) apuntando a la Tierra y fotometría de alta cadencia."
            goal_en = "Confirm Earth-pointing relativistic jet and perform high-cadence photometry."
        elif tipo_evento == "agn":
            goal_es = "Confirmar fluctuación de AGN (Cuásar) y medir dinámica de acreción."
            goal_en = "Confirm AGN (Quasar) fluctuation and measure accretion dynamics."
        else:
            goal_es = "Obtener espectro profundo para confirmar subtipo exacto de explosión termonuclear/colapso."
            goal_en = "Obtain deep spectra to confirm exact thermonuclear/core-collapse explosion subtype."
            
        nota_es = "* NOTA: Evento fresco evaluado y clasificado por el motor físico de la Estación Magallanes."
        nota_en = "* NOTE: Fresh event evaluated and classified by the Magallanes Station physical engine."
            
        # LÓGICA BLINDADA PARA NOVAS LOCALES VS EXTRAGALÁCTICAS
        if tipo_evento == "nova":
            entorno_es, entorno_en = "Vía Láctea (Entorno Galáctico Local)", "Milky Way (Local Galactic Environment)"
            dist_param_es = f"* Distancia Est.      : {distancia}"
            dist_param_en = f"* Est. Distance       : {distancia}"
        else:
            entorno_es, entorno_en = galaxia, galaxia
            dist_param_es = f"* Redshift (z)        : {z_str_es}"
            dist_param_en = f"* Redshift (z)        : {z_str_en}"
            
        texto_alerta = f"""======================================================================
[ESPAÑOL] BORRADOR TELEGRAMA ASTRONÓMICO (ATel) - ESTACIÓN MAGALLANES
======================================================================
TEMA: Análisis Estación Magallanes: Candidato a {tipo_evento.upper()} ({nombre_evento})
OBSERVADORES: Estación Magallanes (Punta Arenas, Chile) - AAVSO: ECDA

Reportamos la evaluación física y fotométrica de un candidato a {tipo_evento.upper()}
ubicado en la entidad anfitriona {entorno_es}.

[1] INFORMACIÓN DEL OBJETIVO Y TIEMPO
* ID del Transitorio    : {nombre_evento}
* Coordenadas (ICRS)    : RA {ra:.5f} | Dec {dec:.5f}
* Momento de Detección  : {tiempo_texto_es}
* Entidad Anfitriona    : {entorno_es}
{dist_param_es}

[2] SOLICITUD DE OBSERVACIÓN
* Acción Requerida      : SEGUIMIENTO ESPECTROSCÓPICO URGENTE
* Objetivo Científico   : {goal_es}

{nota_es}

----------------------------------------------------------------------
[ENGLISH] ASTRONOMER'S TELEGRAM (ATel) DRAFT - MAGALLANES STATION
----------------------------------------------------------------------
SUBJECT: Magallanes Station Analysis: {tipo_evento.upper()} candidate {nombre_evento}
OBSERVERS: Magallanes Station (Punta Arenas, Chile) - AAVSO: ECDA

We report the physical and photometric evaluation of a highly probable {tipo_evento.upper()} candidate 
located in the host entity {entorno_en}. 

[1] TARGET INFORMATION & TIMING
* Transient ID          : {nombre_evento}
* Coordinates (ICRS)    : RA {ra:.5f} | Dec {dec:.5f}
* Detection Time (Peak) : {tiempo_texto_en}
* Host Entity           : {entorno_en}
{dist_param_en}

[2] OBSERVATIONAL REQUEST
* Requested Action      : URGENT SPECTROSCOPIC FOLLOW-UP
* Scientific Goal       : {goal_en}

{nota_en}

Magallanes Station Automated Alert System | AAVSO: ECDA
======================================================================"""
        ruta_txt = f"alertas_comunidad/ALERTA_ATEL_{nombre_archivo}.txt"
        
    ruta_guardada = guardar_archivo_texto(ruta_txt, texto_alerta)
    print(f"   [+] ¡Megáfono encendido! Alerta oficial generada en: {ruta_guardada}")
    return ruta_guardada
