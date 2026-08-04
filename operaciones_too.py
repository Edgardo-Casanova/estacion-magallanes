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
    
    # Crear carpeta específica para las alertas externas
    os.makedirs('alertas_comunidad', exist_ok=True)
    nombre_archivo = nombre_evento.replace(' ', '_').replace('/', '-')
    
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
    # PLANTILLA 2: REDES EXTRAGALÁCTICAS (ATel) -> SN, Nova, AGN, Blazar
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
            
        texto_alerta = f"""======================================================================
[ESPAÑOL] BORRADOR TELEGRAMA ASTRONÓMICO (ATel) - ESTACIÓN MAGALLANES
======================================================================
TEMA: Análisis Estación Magallanes: Candidato a {tipo_evento.upper()} ({nombre_evento})
OBSERVADORES: Estación Magallanes (Punta Arenas, Chile) - AAVSO: ECDA

Reportamos la evaluación física y fotométrica de un candidato a {tipo_evento.upper()}
ubicado en la entidad anfitriona {galaxia} (z = {z_str}).

[1] INFORMACIÓN DEL OBJETIVO
* ID del Transitorio    : {nombre_evento}
* Coordenadas (ICRS)    : RA {ra:.5f} | Dec {dec:.5f}
* Entidad Anfitriona    : {galaxia}
* Redshift (z)          : {z_str}

[2] SOLICITUD DE OBSERVACIÓN
* Acción Requerida      : SEGUIMIENTO ESPECTROSCÓPICO URGENTE
* Objetivo Científico   : {goal_es}

* NOTA: Este transitorio fue alertado inicialmente por un broker IA y posteriormente
confirmado/reclasificado mediante el filtro de Análisis de la Estación Magallanes, 
detectando desviaciones significativas en su línea base de luminosidad histórica.

----------------------------------------------------------------------
[ENGLISH] ASTRONOMER'S TELEGRAM (ATel) DRAFT - MAGALLANES STATION
----------------------------------------------------------------------
SUBJECT: Magallanes Station Analysis: {tipo_evento.upper()} candidate {nombre_evento}
OBSERVERS: Magallanes Station (Punta Arenas, Chile) - AAVSO: ECDA

We report the physical and photometric evaluation of a highly probable {tipo_evento.upper()} candidate 
located in the host entity {galaxia} (z = {z_str}). 

[1] TARGET INFORMATION
* Transient ID          : {nombre_evento}
* Coordinates (ICRS)    : RA {ra:.5f} | Dec {dec:.5f}
* Host Entity           : {galaxia}
* Redshift (z)          : {z_str}

[2] OBSERVATIONAL REQUEST
* Requested Action      : URGENT SPECTROSCOPIC FOLLOW-UP
* Scientific Goal       : {goal_en}

* NOTE: This transient was initially alerted by an AI broker and subsequently 
confirmed/reclassified through the Magallanes Station Analysis filter, which 
detected significant deviations from its historical luminosity baseline.

Magallanes Station Automated Alert System | AAVSO: ECDA
======================================================================"""
        ruta_txt = f"alertas_comunidad/ALERTA_ATEL_{nombre_archivo}.txt"
        
    # Guardado del archivo generado
    with open(ruta_txt, "w", encoding="utf-8") as f:
        f.write(texto_alerta)
        
    print(f"   [+] ¡Megáfono encendido! Telegrama/Alerta oficial generado en: {ruta_txt}")
    return ruta_txt
