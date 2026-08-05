import os
from datetime import datetime

def generar_alerta_comunidad(nombre_evento, ra, dec, tipo_evento="flare", extra_data=None):
    """
    Genera un reporte de alerta transitoria bilingüe (ES/EN) adaptando el formato 
    y el destinatario según la naturaleza astrofísica del evento.
    """
    if extra_data is None:
        extra_data = {}
        
    print(f"\n[🚀] INICIANDO PROTOCOLO DE ALERTA COMUNITARIA PARA {nombre_evento} ({tipo_evento.upper()})")
    
    os.makedirs('alertas_comunidad', exist_ok=True)
    nombre_archivo = nombre_evento.replace(' ', '_').replace('/', '-')
    
    # Extraemos la distancia oficial enviada desde el motor principal
    distancia = extra_data.get("distancia", "Desconocida")
    
    # =================================================================
    # PLANTILLA 1: REDES ESTELARES (AAVSO) -> Para Flares
    # =================================================================
    if tipo_evento == "flare":
        ew_halfa = extra_data.get("ew_halfa", 0.0)
        tiene_planetas = extra_data.get("tiene_planetas", False)
        
        planetas_es = "Sí (Posible impacto en atmósferas exoplanetarias)" if tiene_planetas else "No detectados"
        planetas_en = "Yes (Potential impact on exoplanetary atmospheres)" if tiene_planetas else "Not detected"
        
        texto_alerta = f"""======================================================================
[ESPAÑOL] ALERTA DE EVENTO TRANSITORIO ESTELAR - ESTACIÓN MAGALLANES
======================================================================
A la comunidad de la Asociación Americana de Observadores de Estrellas Variables (AAVSO):

Se solicita seguimiento fotométrico urgente para el siguiente objetivo,
debido a la detección automatizada de alta actividad cromosférica (posible mega-flare).

[1] IDENTIFICACIÓN DEL OBJETIVO
* Nombre / ID SIMBAD    : {nombre_evento}
* Coordenadas (ICRS)    : RA {ra:.5f} | Dec {dec:.5f}
* Distancia Estimada    : {distancia}

[2] JUSTIFICACIÓN ASTROFÍSICA (Análisis Estación Magallanes)
* Tipo de Estrella      : Enana Roja (Firma infrarroja confirmada)
* Emisión H-alfa        : Activa extrema (Ancho Equivalente: {ew_halfa:.2f} Å)
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

[1] TARGET IDENTIFICATION
* Name / SIMBAD ID      : {nombre_evento}
* Coordinates (ICRS)    : RA {ra:.5f} | Dec {dec:.5f}
* Est. Distance         : {distancia}

[2] ASTROPHYSICAL JUSTIFICATION (Magallanes Station Analysis)
* Star Type             : Red Dwarf (Confirmed infrared signature)
* H-alpha Emission      : Extreme activity (Equivalent Width: {ew_halfa:.2f} Å)
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
        redshift = extra_data.get("redshift", "Desconocido")
        
        if redshift == 0.0: 
            redshift = "Desconocido"
            
        z_str = f"{redshift:.5f}" if isinstance(redshift, float) else str(redshift)
        
        # Bifurcación dinámica de los objetivos científicos del Telegrama
        if tipo_evento == "blazar":
            goal_es = "Confirmar chorro relativista (jet) apuntando a la Tierra y fotometría de alta cadencia."
            goal_en = "Confirm Earth-pointing relativistic jet and perform high-cadence photometry."
        elif tipo_evento == "agn":
            goal_es = "Confirmar fluctuación lenta de AGN (Cuásar) y medir dinámica de acreción."
            goal_en = "Confirm slow AGN (Quasar) fluctuation and measure accretion dynamics."
        else:
            goal_es = "Obtener espectro para confirmar subtipo exacto de explosión termonuclear/colapso."
            goal_en = "Obtain spectra to confirm exact thermonuclear/core-collapse explosion subtype."
            
        origen = extra_data.get("red_origen", "ZTF")
        
        if origen == "TNS_GLOBAL":
            nota_es = "* NOTA: Este transitorio es una confirmación oficial extraída directamente del catálogo del Transient Name Server (IAU)."
            nota_en = "* NOTE: This transient is an official confirmation retrieved directly from the Transient Name Server (IAU) catalog."
        else:
            nota_es = "* NOTA: Este transitorio fue alertado inicialmente por un broker IA y posteriormente evaluado/confirmado por el filtro astrofísico de la Estación Magallanes."
            nota_en = "* NOTE: This transient was initially alerted by an AI broker and subsequently evaluated/confirmed by the Magallanes Station astrophysical filter."
            
        # LÓGICA CONDICIONAL: REDSHIFT VS AÑOS LUZ
        if tipo_evento == "nova":
            entorno_es = "Vía Láctea (Entorno Galáctico Local)"
            entorno_en = "Milky Way (Local Galactic Environment)"
            dist_param_es = f"* Distancia Est.      : {distancia}"
            dist_param_en = f"* Est. Distance       : {distancia}"
        else:
            entorno_es = galaxia
            entorno_en = galaxia
            dist_param_es = f"* Redshift (z)        : {z_str}"
            dist_param_en = f"* Redshift (z)        : {z_str}"
            
        texto_alerta = f"""======================================================================
[ESPAÑOL] BORRADOR TELEGRAMA ASTRONÓMICO (ATel) - ESTACIÓN MAGALLANES
======================================================================
TEMA: Análisis Estación Magallanes: Candidato a {tipo_evento.upper()} ({nombre_evento})
OBSERVADORES: Estación Magallanes (Punta Arenas, Chile) - AAVSO: ECDA

Reportamos la evaluación física y fotométrica de un candidato a {tipo_evento.upper()}
ubicado en la entidad anfitriona {entorno_es}.

[1] INFORMACIÓN DEL OBJETIVO
* ID del Transitorio    : {nombre_evento}
* Coordenadas (ICRS)    : RA {ra:.5f} | Dec {dec:.5f}
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

[1] TARGET INFORMATION
* Transient ID          : {nombre_evento}
* Coordinates (ICRS)    : RA {ra:.5f} | Dec {dec:.5f}
* Host Entity           : {entorno_en}
{dist_param_en}

[2] OBSERVATIONAL REQUEST
* Requested Action      : URGENT SPECTROSCOPIC FOLLOW-UP
* Scientific Goal       : {goal_en}

{nota_en}

Magallanes Station Automated Alert System | AAVSO: ECDA
======================================================================"""
        ruta_txt = f"alertas_comunidad/ALERTA_ATEL_{nombre_archivo}.txt"
        
    with open(ruta_txt, "w", encoding="utf-8") as f:
        f.write(texto_alerta)
        
    print(f"   [+] ¡Megáfono encendido! Telegrama/Alerta oficial generado en: {ruta_txt}")
    return ruta_txt
