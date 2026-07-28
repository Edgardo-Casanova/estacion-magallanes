import os
from datetime import datetime

def generar_alerta_comunidad(nombre_evento, ra, dec, tipo_evento="flare", extra_data=None):
    """
    Genera un reporte de alerta transitoria adaptando el formato y el 
    destinatario según la naturaleza astrofísica del evento.
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
        planetas_str = "Sí (Posible impacto en atmósferas exoplanetarias)" if tiene_planetas else "No detectados"
        
        texto_alerta = f"""======================================================================
ALERTA DE EVENTO TRANSITORIO ESTELAR - ESTACIÓN MAGALLANES
======================================================================
A la comunidad de la Asociación Americana de Observadores de Estrellas Variables (AAVSO)
y red global de observatorios tácticos:

Se solicita seguimiento fotométrico urgente de series temporales para el siguiente objetivo,
debido a la detección automatizada de alta actividad cromosférica (posible mega-flare).

[1] IDENTIFICACIÓN DEL OBJETIVO
* Nombre / ID SIMBAD    : {nombre_evento}
* Coordenadas (ICRS)    : RA {ra:.5f} | Dec {dec:.5f}

[2] JUSTIFICACIÓN ASTROFÍSICA
* Tipo de Estrella      : Enana Roja (Firma infrarroja confirmada)
* Emisión H-alfa        : Activa extrema (Ancho Equivalente: {ew_halfa:.2f} Å)
* Sistema Planetario    : {planetas_str}

[3] SOLICITUD DE OBSERVACIÓN
* Instrumento sugerido  : Telescopios > 0.4m
* Filtros requeridos    : B, V (Johnson) o g, r (Sloan)
* Cadencia              : Continua (exposiciones cortas para evitar saturación)
* Duración de campaña   : Próximas 6 a 8 horas para capturar la curva de enfriamiento.

Por favor, reportar observaciones a la base de datos oficial (AID) bajo el identificador
del objeto para corroborar el desgaste atmosférico.

Atentamente,
Pipeline Automatizado Estación Magallanes
Punta Arenas, Chile
======================================================================"""
        ruta_txt = f"alertas_comunidad/ALERTA_AAVSO_{nombre_archivo}.txt"

    # =================================================================
    # PLANTILLA 2: REDES EXTRAGALÁCTICAS (ATel) -> Para Supernovas/Novas
    # =================================================================
    elif tipo_evento in ["supernova", "nova"]:
        galaxia = extra_data.get("galaxia", "Desconocida")
        redshift = extra_data.get("redshift", 0.0)
        
        texto_alerta = f"""======================================================================
ASTRONOMER'S TELEGRAM (ATel) DRAFT - ESTACIÓN MAGALLANES
======================================================================
SUBJECT: Magallanes Station automated discovery/recovery of {tipo_evento.upper()} candidate {nombre_evento}
OBSERVERS: Pipeline Automatizado (Estación Magallanes, Punta Arenas, Chile)

We report the automated algorithmic detection of a highly probable {tipo_evento} candidate 
located in the host galaxy {galaxia} (z = {redshift:.5f}). 

[1] TARGET INFORMATION
* Transient ID          : {nombre_evento}
* Coordinates (ICRS)    : RA {ra:.5f} | Dec {dec:.5f}
* Host Entity           : {galaxia}
* Redshift (z)          : {redshift:.5f}

[2] OBSERVATIONAL REQUEST
* Requested Action      : URGENT SPECTROSCOPIC FOLLOW-UP
* Target Facilities     : 4m to 8m class telescopes (e.g., SOAR, Gemini, VLT)
* Required Instrument   : Low to medium resolution optical spectrograph
* Scientific Goal       : Confirm exact transient sub-type (Ia, II, Ibc, or Nova) 
                          and measure absolute expansion velocity.

This transient was identified utilizing the ALeRCE / TNS algorithmic broker pipelines. 
Photometric light curve data indicates a significant deviation from the historical baseline.

Estación Magallanes Automated Alert System
======================================================================"""
        ruta_txt = f"alertas_comunidad/ALERTA_ATEL_{nombre_archivo}.txt"
        
    # Guardado del archivo generado
    with open(ruta_txt, "w", encoding="utf-8") as f:
        f.write(texto_alerta)
        
    print(f"   [+] ¡Megáfono encendido! Telegrama/Alerta oficial generado en: {ruta_txt}")
    return ruta_txt
