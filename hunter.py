import os
import time
import pandas as pd
import numpy as np
import requests
import json
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

warnings.filterwarnings('ignore')

ARCHIVO_MJD = "tracker_mjd.txt"

# --- DICCIONARIO TAXONÓMICO BILINGÜE ---
diccionario_categorias = {
    "ZTF": ["SNIa", "SNIbc", "SNII", "SLSN", "CV/Nova", "QSO", "Blazar"],
    "LSST": ["SNIa", "SNIbc", "SNII", "SLSN", "Nova", "Mdwarf-flare"]
}

def obtener_mjd_rastreo():
    """Lee el MJD de la última corrida para no repetir análisis."""
    try:
        if os.path.exists(ARCHIVO_MJD):
            with open(ARCHIVO_MJD, "r") as f:
                mjd_guardado = float(f.read().strip())
                return mjd_guardado
    except Exception as e:
        print(f"No se pudo leer el tracker MJD ({e}). Usando ventana por defecto.")
    
    return Time(datetime.utcnow() - timedelta(days=2)).mjd

def guardar_mjd_rastreo(mjd):
    """Guarda el MJD actual al finalizar la corrida para el próximo ciclo."""
    try:
        with open(ARCHIVO_MJD, "w") as f:
            f.write(str(mjd))
    except Exception as e:
        print(f"Error guardando el marcador de tiempo MJD: {e}")

def determinar_tipo_evento(clase_ia):
    """Traduce la etiqueta de la IA en una de las 3 rutas físicas del laboratorio."""
    clase_upper = str(clase_ia).upper()
    if "SN" in clase_upper or "SLSN" in clase_upper:
        return "supernova"
    elif "NOVA" in clase_upper or "CV" in clase_upper:
        return "nova"
    elif "QSO" in clase_upper or "BLAZAR" in clase_upper or "AGN" in clase_upper:
        return "agn" 
    else:
        return "flare"

def registrar_log(mensaje, survey):
    print(mensaje) 
    fecha_hora = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    archivo_log = f"bitacora_{survey}.log"
    try:
        with open(archivo_log, "a") as f:
            f.write(f"[{fecha_hora}] {mensaje}\n")
    except Exception as e:
        print(f"Error escribiendo en bitácora: {e}")

def obtener_datos_astronomicos(coordenadas):
    nombre = "No catalogada"
    distancia = "Desconocida"
    tipo = "Estrella / Transitorio"
    metalicidad = "Desconocida (Sin estudio previo)"
    
    try:
        custom_simbad = Simbad()
        custom_simbad.add_votable_fields('plx', 'sp', 'fe_h')
        resultado = custom_simbad.query_region(coordenadas, radius=3*u.arcsec)
        
        if resultado is not None and len(resultado) > 0:
            raw_name = resultado['MAIN_ID'][0]
            nombre = raw_name.decode('utf-8') if hasattr(raw_name, 'decode') else str(raw_name)
            
            if 'SP_TYPE' in resultado.colnames:
                raw_sp = resultado['SP_TYPE'][0]
                if not np.ma.is_masked(raw_sp) and raw_sp:
                    sp_str = raw_sp.decode('utf-8') if hasattr(raw_sp, 'decode') else str(raw_sp)
                    if sp_str.strip(): tipo = sp_str
                        
            if 'PLX_VALUE' in resultado.colnames:
                plx = resultado['PLX_VALUE'][0]
                if not np.ma.is_masked(plx) and not np.isnan(plx) and float(plx) > 0:
                    dist_pc = 1000.0 / float(plx)
                    distancia = f"~{dist_pc * 3.26156:.1f} Años Luz"
                    
            col_feh = [c for c in resultado.colnames if 'fe_h' in c.lower()]
            if col_feh:
                raw_feh = resultado[col_feh[0]][0]
                if not np.ma.is_masked(raw_feh) and not np.isnan(float(raw_feh)):
                    metalicidad = f"[Fe/H] = {float(raw_feh):.2f}"
                    
    except Exception:
        pass
    
    return nombre, distancia, tipo, metalicidad

def consultar_tns_sur(mjd_reciente):
    registrar_log("="*50, "TNS_GLOBAL")
    registrar_log("APUNTANDO TELESCOPIO A RED: TNS_GLOBAL", "TNS_GLOBAL")
    registrar_log("Hemisferio: Sur (ASAS-SN / ATLAS) | Radar de Supernovas de la IAU", "TNS_GLOBAL")
    registrar_log("="*50, "TNS_GLOBAL")
    registrar_log("1. Contactando servidor central del Transient Name Server...", "TNS_GLOBAL")

    TNS_BOT_ID = os.getenv("TNS_BOT_ID")
    TNS_API_KEY = os.getenv("TNS_API_KEY")
    tns_marker = f'tns_marker{{"tns_id":{TNS_BOT_ID}, "type":"bot", "name":"Magallanes_Bot"}}'
    headers = {'User-Agent': tns_marker}

    search_data = {
        "dec_range": "-90,0", 
        "discovered_period_value": "2", 
        "discovered_period_units": "days",
        "unclassified_at": "0", 
        "classified_sne": "1" 
    }
    payload = {"api_key": TNS_API_KEY, "data": json.dumps(search_data)}

    try:
        url = 'https://www.wis-tns.org/api/get/search'
        response = requests.post(url, headers=headers, data=payload)

        if response.status_code == 200:
            datos = response.json()
            if isinstance(datos, list):
                cantidad = len(datos)
            elif isinstance(datos, dict):
                data_obj = datos.get('data', {})
                if isinstance(data_obj, dict):
                    cantidad = len(data_obj.get('reply', []))
                elif isinstance(data_obj, list):
                    cantidad = len(data_obj)
                else:
                    cantidad = 1
            else:
                cantidad = 0
            registrar_log(f"¡Conexión exitosa! El TNS reporta {cantidad} supernovas recientes en el hemisferio sur.", "TNS_GLOBAL")
            
        elif response.status_code == 403:
            registrar_log("Error 403: Las llaves del Bot ID o API Key son incorrectas. Verifica en la web de TNS.", "TNS_GLOBAL")
        else:
            registrar_log(f"El servidor TNS respondió con código: {response.status_code}", "TNS_GLOBAL")

    except Exception as e:
        registrar_log(f"Error procesando la red TNS_GLOBAL: {e}", "TNS_GLOBAL")
        registrar_log("Modo de Respaldo: El cazador continuará operando con las redes ALeRCE.", "TNS_GLOBAL")

    return None

def main():
    print("=== INICIANDO CAZADOR MULTIPROPÓSITO v11 (Radar Continuo) ===")
    client = Alerce()
    
    mjd_reciente = obtener_mjd_rastreo()
    fecha_legible = Time(mjd_reciente, format='mjd').to_datetime().strftime('%Y-%m-%d %H:%M:%S UTC')
    print(f"➤ Buscando alertas activas desde: {fecha_legible} (MJD: {mjd_reciente:.4f})")

    redes_a_escanear = ["ZTF", "LSST", "TNS_GLOBAL"]

    for current_survey in redes_a_escanear:
        if current_survey == "TNS_GLOBAL":
            consultar_tns_sur(mjd_reciente)
            continue
            
        registrar_log("\n" + "="*50, current_survey)
        registrar_log(f"APUNTANDO TELESCOPIO A RED: {current_survey}", current_survey)
        
        # --- CORRECCIÓN: Rango de tiempo con traslape de seguridad ---
        rango_mjd = [mjd_reciente - 0.2, mjd_reciente + 5.0]

        if current_survey == "ZTF":
            registrar_log("Hemisferio: Norte | Búsqueda Continua (Filtro Taxonómico Abierto)", current_survey)
            filtros = {"lastmjd": rango_mjd, "order_by": "lastmjd", "order_mode": "DESC", "page_size": 1500}
        else:
            registrar_log("Hemisferio: Sur (LSST) | Búsqueda Continua (Filtro Taxonómico Abierto)", current_survey)
            filtros = {"lastmjd": rango_mjd, "order_by": "lastmjd", "order_mode": "DESC", "page_size": 1500, "survey": "lsst"}
        
        registrar_log("="*50, current_survey)

        try:
            registrar_log(f"1. Descargando alertas nuevas de {current_survey}...", current_survey)
            candidatos = client.query_objects(**filtros)
            
            if candidatos.empty:
                registrar_log(f"Sin alertas nuevas en esta ventana de tiempo. (Red en silencio)", current_survey)
                continue

            total_alertas = len(candidatos)
            registrar_log(f"2. Evaluando clasificaciones IA en {total_alertas} candidatos recientes...", current_survey)
            
            mejor_candidato = None
            mejor_prob = 0.0
            mejor_curva = None
            coordenadas = None
            clase_ia_final = "Desconocida"
            tipo_evento_final = "desconocido"
            salto_maximo = 0
            
            target_classes = diccionario_categorias.get(current_survey, [])

            for index, fila in candidatos.iterrows():
                oid = fila['oid']
                if index % 50 == 0 and index > 0:
                    registrar_log(f"   -> Procesadas {index} de {total_alertas} alertas...", current_survey)
                
                try:
                    probs = client.query_probabilities(oid=oid, format='pandas')
                    if probs.empty: continue
                        
                    mejor_prediccion = probs.loc[probs['probability'].idxmax()]
                    temp_ia_class = mejor_prediccion['class_name']
                    temp_ia_prob = mejor_prediccion['probability']
                    
                    if temp_ia_class in target_classes and temp_ia_prob > 0.60:
                        det = client.query_detections(oid=oid, format='pandas')
                        # --- CORRECCIÓN: Filtro relajado a un mínimo de 2 detecciones ---
                        if det.empty or len(det) < 2: continue 
                            
                        if temp_ia_prob > mejor_prob:
                            mejor_prob = temp_ia_prob
                            mejor_candidato = oid
                            mejor_curva = det
                            coordenadas = SkyCoord(ra=fila['meanra']*u.degree, dec=fila['meandec']*u.degree, frame='icrs')
                            clase_ia_final = temp_ia_class
                            tipo_evento_final = determinar_tipo_evento(clase_ia_final)
                            
                            det = det.sort_values(by='mjd')
                            if len(det) > 10:
                                mediana_historica = det.iloc[:-1]['magpsf'].median()
                                mag_anoche = det.iloc[-1]['magpsf']
                                salto_maximo = mediana_historica - mag_anoche
                                
                except Exception:
                    pass
                time.sleep(0.05) 

            if mejor_candidato is None:
                registrar_log(f"Ningún evento superó los filtros taxonómicos de la IA en {current_survey}.", current_survey)
                continue 

            constelacion = get_constellation(coordenadas)
            registrar_log(f"\n¡BINGO! EVENTO ESTELAR VERIFICADO POR IA EN {current_survey}", current_survey)
            registrar_log(f"TIPO IDENTIFICADO: {tipo_evento_final.upper()} ({clase_ia_final})", current_survey)
            registrar_log("Consultando catálogos de Gaia y SIMBAD para análisis físico y químico...", current_survey)
            
            nombre_real, distancia_real, tipo_real, metalicidad_real = obtener_datos_astronomicos(coordenadas)
            
            mejor_curva['fecha_humana'] = Time(mejor_curva['mjd'].values, format='mjd').to_datetime()
            ultima_fecha = mejor_curva.iloc[-1]['fecha_humana']
            ultima_mag = mejor_curva.iloc[-1]['magpsf']
            
            plt.style.use('dark_background')
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
            fig.patch.set_facecolor('#0f0f0f') 
            ax1.set_facecolor('#1a1a1a')
            ax2.set_facecolor('#1a1a1a')
            
            banda_g = mejor_curva[mejor_curva['fid'] == 1]
            banda_r = mejor_curva[mejor_curva['fid'] == 2]

            if not banda_g.empty:
                ax1.errorbar(banda_g['fecha_humana'], banda_g['magpsf'], yerr=banda_g['sigmapsf'], fmt='o', color='#39ff14', alpha=0.6, markersize=5, label='Banda g')
            if not banda_r.empty:
                ax1.errorbar(banda_r['fecha_humana'], banda_r['magpsf'], yerr=banda_r['sigmapsf'], fmt='o', color='#ff3333', alpha=0.6, markersize=5, label='Banda r')

            ax1.scatter(ultima_fecha, ultima_mag, color='cyan' if tipo_evento_final in ["supernova", "agn"] else 'yellow', edgecolor='white', marker='*', s=400, zorder=5, label='¡Detección!')
            ax1.invert_yaxis()
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            fig.autofmt_xdate(rotation=45)
            
            ax1.set_title(f"Curva de Luz: {mejor_candidato}", color='white', pad=15)
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
                f"ID Alerta: {mejor_candidato}\n"
                f"Distancia/Redshift: {distancia_real}\n"
                f"Metalicidad (Fe/H): {metalicidad_real}\n"
                f"Aumento Ref: {salto_maximo:.2f} mag\n"
                f"Fecha (UTC): {ultima_fecha.strftime('%Y-%m-%d %H:%M')}\n"
                "------------------------\n"
                f"Validación IA: {clase_ia_final} ({mejor_prob*100:.1f}%)"
            )
            caja_propiedades = dict(boxstyle='round,pad=0.6', facecolor='#2a2a2a', alpha=0.9, edgecolor='#555555')
            ax2.text(0.05, 0.95, info_text, transform=ax2.transAxes, fontsize=10, verticalalignment='top', color='white', bbox=caja_propiedades)

            plt.tight_layout(rect=[0, 0.05, 1, 0.92])
            plt.suptitle(f"Reporte Astronómico: {tipo_evento_final.upper()}", fontsize=20, color='white', fontweight='bold', y=0.98)
            fig.text(0.5, 0.01, f"Estación Magallanes | Analizado el {datetime.now(timezone.utc).strftime('%Y-%m-%d')} | Red {current_survey}", ha='center', color='gray', fontsize=11)
            
            os.makedirs('data', exist_ok=True)
            archivo_plot = f"data/curva_luz_{mejor_candidato}.png"
            plt.savefig(archivo_plot, dpi=150, bbox_inches='tight') 
            plt.close()
            registrar_log(f"Reporte cartográfico guardado en: {archivo_plot}", current_survey)

            texto_reporte = f"""======================================================================
REPORTE DE ALERTA ({tipo_evento_final.upper()})
======================================================================
ID de Alerta: {mejor_candidato}
Coordenadas (RA / Dec): {coordenadas.ra.deg:.5f} / {coordenadas.dec.deg:.5f}
Catálogo SIMBAD: {nombre_real}
Clasificación IA (ALeRCE): {clase_ia_final} (Confianza: {mejor_prob*100:.1f}%)
Red de Origen: {current_survey}
======================================================================"""
            
            archivo_texto = f"data/REPORTE_ALERTA_{mejor_candidato}.txt"
            with open(archivo_texto, "w", encoding="utf-8") as f:
                f.write(texto_reporte)
                
            registrar_log(f"Plantillas de comunicación básica guardadas.", current_survey)

            registrar_log(f"Disparando pipeline de análisis profundo para {mejor_candidato}...", current_survey)
            try:
                ejecutar_pipeline_magallanes(coordenadas.ra.deg, coordenadas.dec.deg, mejor_candidato, tipo_evento_final)
                registrar_log(f"Análisis de laboratorio completado con éxito para {mejor_candidato}.", current_survey)
            except Exception as e:
                registrar_log(f"Error al ejecutar el laboratorio para {mejor_candidato}: {e}", current_survey)

        except Exception as e:
            registrar_log(f"Error procesando la red {current_survey}: {e}", current_survey)

    nuevo_mjd = Time(datetime.utcnow()).mjd
    guardar_mjd_rastreo(nuevo_mjd)
    print(f"\n=== PATRULLAJE COMPLETADO. MARCADOR DE TIEMPO GUARDADO: {nuevo_mjd:.5f} ===")

if __name__ == "__main__":
    main()
