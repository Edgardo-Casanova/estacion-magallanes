import os
import time
import pandas as pd
import numpy as np
import requests
import json
import matplotlib.subplots as plt_subplots
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from alerce.core import Alerce
from datetime import datetime, timedelta, timezone
from astropy.time import Time
from astropy.coordinates import SkyCoord, get_constellation
import astropy.units as u
from astroquery.simbad import Simbad
import warnings
from dotenv import load_dotenv
load_dotenv()

# --- INTEGRACIÓN CON ESTACIÓN MAGALLANES ---
from laboratorio import ejecutar_pipeline_magallanes
from operaciones_too import generar_alerta_comunidad

warnings.filterwarnings('ignore')

ARCHIVO_MJD = "tracker_mjd.txt"
MEMORIA_TNS = "memoria_tns.txt"  # EL LIBRO MAYOR DE SUPERNOVAS

# EL ESCUDO TAXONÓMICO ESTRICTO
diccionario_categorias = {
    "ZTF": ["SNIa", "SNIbc", "SNII", "SLSN", "CV/Nova", "QSO", "Blazar"],
    "LSST": ["SNIa", "SNIbc", "SNII", "SLSN", "Nova", "Mdwarf-flare"]
}

# --- FUNCIONES DE MEMORIA TNS (EL LIBRO MAYOR) ---
def leer_memoria_tns():
    """Lee el libro mayor para saber qué supernovas ya fueron procesadas en el pasado."""
    if not os.path.exists(MEMORIA_TNS):
        return set()
    try:
        with open(MEMORIA_TNS, 'r', encoding='utf-8') as f:
            return set(linea.strip() for linea in f if linea.strip())
    except Exception:
        return set()

def guardar_en_memoria_tns(id_evento):
    """Anota una nueva supernova en el libro mayor de forma permanente."""
    try:
        with open(MEMORIA_TNS, 'a', encoding='utf-8') as f:
            f.write(f"{id_evento}\n")
    except Exception:
        pass

# --- FUNCIONES ASTRONÓMICAS Y AUXILIARES ---
def calcular_distancia_hubble(z):
    try:
        if z is None or str(z).strip() == "": return "Desconocida", "N/A"
        z_float = float(z)
        if z_float <= 0: return "Desconocida", "N/A"
        c = 299792.458 
        H0_local, H0_temprano = 73.0, 67.4 
        dist_min_mpc, dist_max_mpc = (c * z_float) / H0_local, (c * z_float) / H0_temprano
        dist_min_mly, dist_max_mly = dist_min_mpc * 3.26156, dist_max_mpc * 3.26156
        return f"Entre {dist_min_mpc:.2f} y {dist_max_mpc:.2f} Megaparsecs", f"(Aprox. {dist_min_mly:.2f} a {dist_max_mly:.2f} Millones de años luz)"
    except (ValueError, TypeError):
        return "Desconocida", "N/A"

def obtener_mjd_rastreo():
    try:
        if os.path.exists(ARCHIVO_MJD):
            with open(ARCHIVO_MJD, "r") as f: return round(float(f.read().strip()), 1)
    except Exception as e:
        print(f"No se pudo leer el tracker MJD ({e}). Usando ventana por defecto.")
    # MODO PRODUCCIÓN: Respaldo de 2 días para ZTF/LSST
    return round(Time(datetime.now(timezone.utc) - timedelta(days=2)).mjd, 1)

def guardar_mjd_rastreo(mjd):
    try:
        with open(ARCHIVO_MJD, "w") as f: f.write(str(round(float(mjd), 1)))
    except Exception: pass

def determinar_tipo_evento(clase_ia):
    clase_upper = str(clase_ia).upper()
    if "SN" in clase_upper or "SLSN" in clase_upper: return "supernova"
    elif "NOVA" in clase_upper or "CV" in clase_upper: return "nova"
    elif "QSO" in clase_upper or "BLAZAR" in clase_upper or "AGN" in clase_upper: return "agn" 
    else: return "flare"

def registrar_log(mensaje, survey):
    print(mensaje) 
    fecha_hora = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    try:
        with open(f"bitacora_{survey}.log", "a") as f: f.write(f"[{fecha_hora}] {mensaje}\n")
    except Exception: pass

def obtener_datos_astronomicos(coordenadas):
    nombre, distancia, tipo, metalicidad = "No catalogada", "Desconocida", "Estrella / Transitorio", "Desconocida (Sin estudio previo)"
    try:
        custom_simbad = Simbad()
        custom_simbad.add_votable_fields('plx', 'sp', 'fe_h')
        resultado = custom_simbad.query_region(coordenadas, radius=3*u.arcsec)
        if resultado is not None and len(resultado) > 0:
            raw_name = resultado['MAIN_ID'][0]
            nombre = raw_name.decode('utf-8') if hasattr(raw_name, 'decode') else str(raw_name)
            if 'SP_TYPE' in resultado.colnames:
                raw_sp = resultado['SP_TYPE'][0]
                if not np.ma.is_masked(raw_sp) and raw_sp: tipo = raw_sp.decode('utf-8') if hasattr(raw_sp, 'decode') else str(raw_sp)
            if 'PLX_VALUE' in resultado.colnames:
                plx = resultado['PLX_VALUE'][0]
                if not np.ma.is_masked(plx) and not np.isnan(plx) and float(plx) > 0: distancia = f"~{(1000.0 / float(plx)) * 3.26156:.1f} Años Luz"
            col_feh = [c for c in resultado.colnames if 'fe_h' in c.lower()]
            if col_feh:
                raw_feh = resultado[col_feh[0]][0]
                if not np.ma.is_masked(raw_feh) and not np.isnan(float(raw_feh)): metalicidad = f"[Fe/H] = {float(raw_feh):.2f}"
    except Exception: pass
    return nombre, distancia, tipo, metalicidad

def graficar_reporte_tns(det, id_evento, red_descubridora, ra_float, dec_float):
    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
    fig.patch.set_facecolor('#0f0f0f') 
    ax1.set_facecolor('#1a1a1a')
    ax2.set_facecolor('#1a1a1a')
    
    if det is not None and not det.empty:
        if 'fecha_humana' not in det.columns: det['fecha_humana'] = Time(det['mjd'].values, format='mjd').to_datetime()
        banda_g, banda_r = det[det['fid'] == 1], det[det['fid'] == 2]
        if not banda_g.empty: ax1.errorbar(banda_g['fecha_humana'], banda_g['magpsf'], yerr=banda_g['sigmapsf'], fmt='o', color='#39ff14', alpha=0.6, markersize=5, label='Banda g')
        if not banda_r.empty: ax1.errorbar(banda_r['fecha_humana'], banda_r['magpsf'], yerr=banda_r['sigmapsf'], fmt='o', color='#ff3333', alpha=0.6, markersize=5, label='Banda r')
        det_sorted = det.sort_values(by='mjd')
        ax1.scatter(det_sorted.iloc[-1]['fecha_humana'], det_sorted.iloc[-1]['magpsf'], color='cyan', marker='*', s=400, edgecolor='white', zorder=5, label='¡Última Detección!')
        ax1.invert_yaxis()
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        fig.autofmt_xdate(rotation=45)
        ax1.set_xlabel("Fecha de Observación (UTC)", color='lightgray')
        ax1.set_ylabel("Magnitud Aparente (Brillo)", color='lightgray')
        ax1.legend(facecolor='#0f0f0f', edgecolor='gray')
    else:
        ax1.text(0.5, 0.65, "FOTOMETRÍA RESERVADA", color='#ffcc00', fontsize=22, ha='center', va='center', fontweight='bold')
        ax1.text(0.5, 0.45, "La matriz de curva de luz y espectrometría se encuentra\nalojada en el catálogo privado del Transient Name Server.", color='lightgray', fontsize=12, ha='center', va='center', linespacing=1.5)
        ax1.text(0.5, 0.25, f"ID Objetivo: {id_evento}\nCanal Base: {red_descubridora}", color='cyan', fontsize=11, ha='center', va='center', bbox=dict(boxstyle='round', facecolor='#2a2a2a', alpha=0.8, edgecolor='cyan'))
        ax1.set_xticks([])
        ax1.set_yticks([])
        ax1.axhline(0.5, color='#333333', linestyle='--', alpha=0.5)
        ax1.axvline(0.5, color='#333333', linestyle='--', alpha=0.5)
        
    ax1.set_title(f"Telemetría Fotométrica: {id_evento}", color='white', pad=15)
    ax1.grid(True, linestyle='-', color='#333333', alpha=0.7)
    
    try:
        coordenadas = SkyCoord(ra=ra_float*u.degree, dec=dec_float*u.degree, frame='icrs')
        constelacion = get_constellation(coordenadas)
    except Exception: constelacion = "Desconocida"

    ax2.scatter(ra_float, dec_float, color='cyan', marker='*', s=400, label=f'Posición {red_descubridora}')
    ax2.set_xlim(ra_float + 1, ra_float - 1) 
    ax2.set_ylim(dec_float - 1, dec_float + 1)
    ax2.set_title(f"Coordenadas en {constelacion}", color='white', pad=15)
    ax2.set_xlabel("Ascensión Recta (RA)", color='lightgray')
    ax2.set_ylabel("Declinación (Dec)", color='lightgray')
    ax2.legend(facecolor='#0f0f0f', edgecolor='gray', loc='upper right')
    ax2.grid(True, linestyle=':', color='#444444')
    
    estado_datos = f"Mediciones: {len(det)}" if det is not None and not det.empty else "Datos: TNS Restringido"
    info_text = f"ESTADÍSTICAS DEL EVENTO (SUPERNOVA)\n------------------------\nID Alerta: {id_evento}\nRed Base: {red_descubridora}\n{estado_datos}\nValidación: Transient Name Server (IAU)"
    ax2.text(0.05, 0.95, info_text, transform=ax2.transAxes, fontsize=10, verticalalignment='top', color='white', bbox=dict(boxstyle='round,pad=0.6', facecolor='#2a2a2a', alpha=0.9, edgecolor='#555555'))
    
    plt.tight_layout(rect=[0, 0.05, 1, 0.92])
    plt.suptitle(f"Reporte Astronómico: SUPERNOVA", fontsize=20, color='white', fontweight='bold', y=0.98)
    fig.text(0.5, 0.01, f"Estación Magallanes | Analizado el {datetime.now(timezone.utc).strftime('%Y-%m-%d')} | Red TNS", ha='center', color='gray', fontsize=11)
    
    os.makedirs('data', exist_ok=True)
    plt.savefig(f"data/curva_luz_{id_evento.replace(' ', '_')}.png", dpi=150, bbox_inches='tight') 
    plt.close()
    return True

def consultar_tns_sur(mjd_reciente, client):
    registrar_log("="*50, "TNS_GLOBAL")
    registrar_log("APUNTANDO TELESCOPIO A RED: TNS_GLOBAL", "TNS_GLOBAL")
    registrar_log("Hemisferio: Sur (ASAS-SN / ATLAS) | Radar de Supernovas de la IAU", "TNS_GLOBAL")
    registrar_log("="*50, "TNS_GLOBAL")

    TNS_BOT_ID = os.getenv("TNS_BOT_ID")
    TNS_API_KEY = os.getenv("TNS_API_KEY")
    headers = {'User-Agent': f'tns_marker{{"tns_id":{TNS_BOT_ID}, "type":"bot", "name":"Magallanes_Bot"}}'}

    # Cargar la memoria inquebrantable
    supernovas_procesadas = leer_memoria_tns()

    # Lógica táctica: Sin filtros de fecha problemáticos. Traemos las clasificadas.
    payload = {"api_key": TNS_API_KEY, "data": json.dumps({
        "dec_range": "-90,0", 
        "unclassified_at": 0, 
        "classified_sne": 1
    })}

    try:
        response = requests.post('https://www.wis-tns.org/api/get/search', headers=headers, data=payload)
        if response.status_code == 200:
            datos = response.json()
            lista_eventos = []
            
            if isinstance(datos, list): lista_eventos = datos
            elif isinstance(datos, dict):
                data_obj = datos.get('data', {})
                if isinstance(data_obj, dict): lista_eventos = data_obj.get('reply', [])
                elif isinstance(data_obj, list): lista_eventos = data_obj
            
            if len(lista_eventos) > 0:
                os.makedirs('alertas', exist_ok=True)
                os.makedirs('data', exist_ok=True)
                os.makedirs('alertas_comunidad', exist_ok=True)
                
                # Ordenar para procesar desde la más reciente y tomar una ventana segura (últimas 20)
                lista_eventos = sorted(lista_eventos, key=lambda x: str(x.get('objname', '')), reverse=True)[:20]
                
                for evento in lista_eventos:
                    if isinstance(evento, dict):
                        objname = str(evento.get('objname', ''))
                        prefix = str(evento.get('prefix', 'SN'))
                        if not objname: continue
                        
                        id_evento = f"{prefix} {objname}".strip()
                        
                        # =========================================================
                        # EL ESCUDO DEL LIBRO MAYOR (INDISPENSABLE)
                        # Compara directo con la memoria, no importa si se purgó el .txt
                        # =========================================================
                        if id_evento in supernovas_procesadas:
                            continue
                            
                        registrar_log(f"¡Nueva Supernova detectada! Descargando ficha para {id_evento}...", "TNS_GLOBAL")
                        try:
                            resp_obj = requests.post('https://www.wis-tns.org/api/get/object', headers=headers, data={"api_key": TNS_API_KEY, "data": json.dumps({"objname": objname})})
                            if resp_obj.status_code == 200 and resp_obj.json().get('id_code') == 200:
                                datos_obj = resp_obj.json().get('data', {})
                                if isinstance(datos_obj, dict): datos_obj = datos_obj.get('object') or datos_obj.get('reply') or datos_obj
                                
                                ra_str, dec_str = str(datos_obj.get('ra', 'Desconocida')), str(datos_obj.get('dec', 'Desconocida'))
                                ra_float, dec_float = float(datos_obj.get('radeg') or evento.get('radeg') or 0.0), float(datos_obj.get('decdeg') or evento.get('decdeg') or 0.0)
                                redshift = datos_obj.get('redshift') or evento.get('redshift')
                                clasificacion = (datos_obj.get('object_type', {}) or {}).get('name', 'SUPERNOVA') if isinstance(datos_obj.get('object_type'), dict) else 'SUPERNOVA'
                                fecha_descubrimiento, mag_descubrimiento = datos_obj.get('discoverydate', 'Desconocida'), datos_obj.get('discoverymag', 'Desconocida')
                                descubridor = str((datos_obj.get('discovery_data_source', {}) or {}).get('group_name', 'Desconocido')) if isinstance(datos_obj.get('discovery_data_source'), dict) else 'Desconocido'
                            else:
                                raise Exception("Fallo en la consulta profunda TNS.")
                        except Exception as e:
                            registrar_log(f"   [-] Error extrayendo detalles: {e}", "TNS_GLOBAL")
                            continue
                        
                        rango_mpc, rango_mly = calcular_distancia_hubble(redshift)
                        fecha_reporte_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                        
                        det = None
                        try:
                            if ra_float != 0.0 and dec_float != 0.0:
                                candidatos_alerce = client.query_objects(ra=ra_float, dec=dec_float, radius=5, page_size=1)
                                if not candidatos_alerce.empty: det = client.query_detections(oid=candidatos_alerce.iloc[0]['oid'], format='pandas')
                        except Exception: pass
                        
                        graficar_reporte_tns(det, id_evento, descubridor, ra_float, dec_float)
                        
                        texto_reporte_tns = f"""=================================================================
 CIRCULAR DE OBSERVACIÓN EXTRAGALÁCTICA - ESTACIÓN MAGALLANES
=================================================================
FECHA DE EMISIÓN : {fecha_reporte_utc}
EVENTO DETECTADO : {id_evento} (SUPERNOVA)
COORDENADAS ICRS : RA {ra_float:.5f} | Dec {dec_float:.5f}
-----------------------------------------------------------------

[1] ASTROMETRÍA Y CLASIFICACIÓN (TNS OFICIAL)
    CLASIFICACIÓN IA   : {clasificacion}
    COORDENADAS IAU    : RA {ra_str} | Dec {dec_str}

[2] REGISTRO DE DESCUBRIMIENTO
    FECHA (UTC)        : {fecha_descubrimiento}
    MAGNITUD INICIAL   : {mag_descubrimiento}
    GRUPO DESCUBRIDOR  : {descubridor}

[3] ENTORNO COSMOLÓGICO Y CÁLCULO DE HUBBLE
    REDSHIFT (z)       : {redshift if redshift else 'Desconocido'}
    DISTANCIA ESTIMADA : {rango_mpc}
                         {rango_mly}
                         
    * NOTA DE ASTROFÍSICA:
    El universo se expande, pero la velocidad de esa expansión 
    (Constante H0) varía según cómo se mida. El rango entregado 
    abarca los dos valores científicos vigentes: 
    H0 = 73.0 km/s/Mpc (Universo local) y 
    H0 = 67.4 km/s/Mpc (Universo temprano).

[4] TRAZABILIDAD Y ESPECTROSCOPÍA
    EXPEDIENTE TNS     : https://www.wis-tns.org/object/{objname}
================================================================="""
                        archivo_circular = f"alertas/CIRCULAR_{id_evento.replace(' ', '_')}.txt"
                        with open(archivo_circular, "w", encoding="utf-8") as f: f.write(texto_reporte_tns)
                        
                        texto_reporte_basico = f"""======================================================================
REPORTE DE ALERTA (SUPERNOVA)
======================================================================
ID de Alerta: {id_evento}
Coordenadas (RA / Dec): {ra_float:.5f} / {dec_float:.5f}
Catálogo SIMBAD: No catalogada
Clasificación (TNS): {clasificacion} (Confirmada)
Red de Origen: TNS_GLOBAL
======================================================================"""
                        with open(f"data/REPORTE_ALERTA_{id_evento.replace(' ', '_')}.txt", "w", encoding="utf-8") as f: f.write(texto_reporte_basico)
                        
                        try:
                            z_val = float(redshift) if redshift else 0.0
                            generar_alerta_comunidad(id_evento, ra_float, dec_float, tipo_evento="supernova", extra_data={"galaxia": "Desconocida (Intergaláctica)", "redshift": z_val})
                        except Exception as e:
                            registrar_log(f"   [-] Error generando ATel para {id_evento}: {e}", "TNS_GLOBAL")

                        registrar_log(f"Procesamiento completo y blindado para: {id_evento}", "TNS_GLOBAL")
                        
                        # Anotar permanentemente en el libro mayor
                        guardar_en_memoria_tns(id_evento)
                        time.sleep(2.5)

    except Exception as e:
        registrar_log(f"Error procesando la red TNS_GLOBAL: {e}", "TNS_GLOBAL")

    return None

def main():
    print("=== INICIANDO CAZADOR MULTIPROPÓSITO v11 (Radar Continuo) ===")
    client = Alerce()
    mjd_reciente = obtener_mjd_rastreo()
    print(f"➤ Buscando alertas activas desde: {Time(mjd_reciente, format='mjd').to_datetime().strftime('%Y-%m-%d %H:%M:%S UTC')} (MJD: {mjd_reciente:.4f})")

    for current_survey in ["ZTF", "LSST", "TNS_GLOBAL"]:
        if current_survey == "TNS_GLOBAL":
            consultar_tns_sur(mjd_reciente, client)
            continue
            
        registrar_log("\n" + "="*50, current_survey)
        registrar_log(f"APUNTANDO TELESCOPIO A RED: {current_survey}", current_survey)
        
        # MODO PRODUCCIÓN: Mantener la ventana acotada
        rango_mjd = [mjd_reciente - 0.2, mjd_reciente + 5.0]

        filtros = {"lastmjd": rango_mjd, "order_by": "lastmjd", "order_mode": "DESC", "page_size": 1500}
        if current_survey == "LSST": filtros["survey"] = "lsst"
        
        try:
            candidatos = client.query_objects(**filtros)
            if candidatos.empty: continue
            
            target_classes = diccionario_categorias.get(current_survey, [])
            total_alertas = len(candidatos)

            for index, fila in candidatos.iterrows():
                # BARRA DE PROGRESO Y RESPIRACIÓN DE API
                if index % 50 == 0 and index > 0:
                    registrar_log(f"   -> Procesadas {index} de {total_alertas} alertas...", current_survey)
                time.sleep(0.05)
                
                # ========================================================
                # ESCUDO ANTI-DUPLICADOS (ALeRCE) - MODO TURBO
                # ========================================================
                if os.path.exists(f"data/REPORTE_ALERTA_{fila['oid']}.txt"):
                    continue
                
                try:
                    probs = client.query_probabilities(oid=fila['oid'], format='pandas')
                    if probs.empty: continue
                        
                    mejor_prediccion = probs.loc[probs['probability'].idxmax()]
                    clase_ia_final = mejor_prediccion['class_name']
                    probabilidad = mejor_prediccion['probability']
                    
                    # FILTRO ESTRICTO DE TAXONOMÍA
                    if clase_ia_final in target_classes and probabilidad > 0.60:
                        
                        det = client.query_detections(oid=fila['oid'], format='pandas')
                        if det.empty or len(det) < 2: continue 
                            
                        coordenadas = SkyCoord(ra=fila['meanra']*u.degree, dec=fila['meandec']*u.degree, frame='icrs')
                        tipo_evento_final = determinar_tipo_evento(clase_ia_final)
                        
                        det = det.sort_values(by='mjd')
                        salto_maximo = 0
                        if len(det) > 10:
                            mediana_historica = det.iloc[:-1]['magpsf'].median()
                            mag_anoche = det.iloc[-1]['magpsf']
                            salto_maximo = mediana_historica - mag_anoche
                                
                        constelacion = get_constellation(coordenadas)
                        nombre_real, distancia_real, tipo_real, metalicidad_real = obtener_datos_astronomicos(coordenadas)
                        
                        det['fecha_humana'] = Time(det['mjd'].values, format='mjd').to_datetime()
                        ultima_fecha = det.iloc[-1]['fecha_humana']
                        ultima_mag = det.iloc[-1]['magpsf']
                        
                        plt.style.use('dark_background')
                        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
                        fig.patch.set_facecolor('#0f0f0f') 
                        ax1.set_facecolor('#1a1a1a')
                        ax2.set_facecolor('#1a1a1a')
                        
                        banda_g = det[det['fid'] == 1]
                        banda_r = det[det['fid'] == 2]

                        if not banda_g.empty: ax1.errorbar(banda_g['fecha_humana'], banda_g['magpsf'], yerr=banda_g['sigmapsf'], fmt='o', color='#39ff14', alpha=0.6, markersize=5, label='Banda g')
                        if not banda_r.empty: ax1.errorbar(banda_r['fecha_humana'], banda_r['magpsf'], yerr=banda_r['sigmapsf'], fmt='o', color='#ff3333', alpha=0.6, markersize=5, label='Banda r')

                        ax1.scatter(ultima_fecha, ultima_mag, color='cyan' if tipo_evento_final in ["supernova", "agn"] else 'yellow', edgecolor='white', marker='*', s=400, zorder=5, label='¡Detección!')
                        ax1.invert_yaxis()
                        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
                        fig.autofmt_xdate(rotation=45)
                        
                        ax1.set_title(f"Curva de Luz: {fila['oid']}", color='white', pad=15)
                        ax1.set_xlabel("Fecha de Observación (UTC)", color='lightgray')
                        ax1.set_ylabel("Magnitud Aparente (Brillo)", color='lightgray')
                        ax1.legend(facecolor='#0f0f0f', edgecolor='gray')
                        ax1.grid(True, linestyle='-', color='#333333', alpha=0.7)

                        ax2.scatter(coordenadas.ra.deg, coordenadas.dec.deg, color='cyan' if tipo_evento_final in ["supernova", "agn"] else 'yellow', marker='*', s=400, label=f'Posición {current_survey}')
                        ax2.set_xlim(coordenadas.ra.deg + 1, coordenadas.ra.deg - 1) 
                        ax2.set_ylim(coordenadas.dec.deg - 1, coordenadas.dec.deg + 1)
                        ax2.set_title(f"Coordenadas en {constelacion}", color='white', pad=15)
                        ax2.set_xlabel("Ascensión Recta (RA)", color='lightgray')
                        ax2.set_ylabel("Declinación (Dec)", color='lightgray')
                        ax2.legend(facecolor='#0f0f0f', edgecolor='gray', loc='upper right')
                        ax2.grid(True, linestyle=':', color='#444444')

                        info_text = (
                            f"ESTADÍSTICAS DEL EVENTO ({tipo_evento_final.upper()})\n"
                            "------------------------\n"
                            f"Objeto: {nombre_real}\n"
                            f"ID Alerta: {fila['oid']}\n"
                            f"Distancia/Redshift: {distancia_real}\n"
                            f"Metalicidad (Fe/H): {metalicidad_real}\n"
                            f"Aumento Ref: {salto_maximo:.2f} mag\n"
                            f"Fecha (UTC): {ultima_fecha.strftime('%Y-%m-%d %H:%M')}\n"
                            "------------------------\n"
                            f"Validación IA: {clase_ia_final} ({probabilidad*100:.1f}%)"
                        )
                        ax2.text(0.05, 0.95, info_text, transform=ax2.transAxes, fontsize=10, verticalalignment='top', color='white', bbox=dict(boxstyle='round,pad=0.6', facecolor='#2a2a2a', alpha=0.9, edgecolor='#555555'))

                        plt.tight_layout(rect=[0, 0.05, 1, 0.92])
                        plt.suptitle(f"Reporte Astronómico: {tipo_evento_final.upper()}", fontsize=20, color='white', fontweight='bold', y=0.98)
                        fig.text(0.5, 0.01, f"Estación Magallanes | Analizado el {datetime.now(timezone.utc).strftime('%Y-%m-%d')} | Red {current_survey}", ha='center', color='gray', fontsize=11)
                        
                        os.makedirs('data', exist_ok=True)
                        plt.savefig(f"data/curva_luz_{fila['oid']}.png", dpi=150, bbox_inches='tight') 
                        plt.close()

                        texto_reporte = f"""======================================================================
REPORTE DE ALERTA ({tipo_evento_final.upper()})
======================================================================
ID de Alerta: {fila['oid']}
Coordenadas (RA / Dec): {coordenadas.ra.deg:.5f} / {coordenadas.dec.deg:.5f}
Catálogo SIMBAD: {nombre_real}
Clasificación IA (ALeRCE): {clase_ia_final} (Confianza: {probabilidad*100:.1f}%)
Red de Origen: {current_survey}
======================================================================"""
                        
                        with open(f"data/REPORTE_ALERTA_{fila['oid']}.txt", "w", encoding="utf-8") as f: f.write(texto_reporte)
                            
                        ejecutar_pipeline_magallanes(coordenadas.ra.deg, coordenadas.dec.deg, fila['oid'], tipo_evento_final)
                        
                        registrar_log(f"Candidato {fila['oid']} procesado exitosamente ({clase_ia_final}).", current_survey)

                except Exception: pass
        except Exception: pass

    nuevo_mjd = Time(datetime.utcnow()).mjd
    guardar_mjd_rastreo(nuevo_mjd)
    print(f"\n=== PATRULLAJE COMPLETADO. MARCADOR DE TIEMPO GUARDADO: {nuevo_mjd:.5f} ===")

if __name__ == "__main__":
    main()
