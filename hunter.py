"""
=============================================================================
PROYECTO   : Observatorio Automatizado Estación Magallanes
MÓDULO     : hunter.py (El Cazador Multipropósito)
VERSIÓN    : 26.0 (SINCRONIZACIÓN TNS EN RAM, TAMIZ DE MEMORIA Y RELOJ 4D)
=============================================================================
"""

import os
import io
import csv
import time
import math
import signal
import zipfile
import itertools
import pandas as pd
import numpy as np
import requests
import json
import re
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from alerce.core import Alerce
from datetime import datetime, timedelta, timezone
from astropy.time import Time
from astropy.coordinates import SkyCoord, get_constellation
import astropy.units as u
from astroquery.simbad import Simbad
from astroquery.vizier import Vizier
import pyvo as vo
import warnings
from dotenv import load_dotenv

from laboratorio import ejecutar_pipeline_magallanes

warnings.filterwarnings('ignore')
load_dotenv()

# =====================================================================
# CONFIGURACIÓN DEL ENTORNO LOCAL Y CONTROL DE TIMEOUT
# =====================================================================
ARCHIVO_MJD = "tracker_mjd.txt"
ARCHIVO_BOLETIN = "boletin_tns.txt"
ARCHIVO_TRACKER_TNS = "tracker_tns.txt"
CATALOGO_JSON = "catalogo_maestro.json"
ARCHIVO_HISTORIAL = "historial_vistos.json"

TNS_PUBLIC_BASE_URL = "https://www.wis-tns.org/sites/default/files/tns_public_objects"
TNS_GUEST_HEADERS = {
    "User-Agent": 'tns_marker{"tns_id":0,"type":"user","name":"guest"}'
}
CORTE_INICIAL_TDE = "2026-10-20 13:02:00"
CORTE_INICIAL_GENERAL = "2026-11-05 20:30:00"
CORTE_DESCUBRIMIENTO_SN = "2025-01-01"

diccionario_categorias = {
    "ZTF": ["SNIa", "SNIbc", "SNII", "SLSN", "CV/Nova", "QSO", "Blazar", "TDE", "AGN"],
    "LSST": ["SN", "AGN", "VS"] # Diccionario oficial Stamp Classifier Rubin Beta 20260421
}

for directorio in ["alertas", "data", "alertas_comunidad", "bitacoras"]:
    os.makedirs(directorio, exist_ok=True)

class TimeoutException(Exception):
    pass

def manejador_timeout(signum, frame):
    raise TimeoutException("Timeout crítico: El servidor externo no respondió a tiempo.")

# =====================================================================
# 🛰️ ADAPTADORES QUIRÚRGICOS LSST (IA HTMX + FOTOMETRÍA TAP)
# =====================================================================
def infiltrar_ia_lsst(oid_puro):
    """
    Extrae la clasificación de IA del clúster beta de LSST leyendo el bloque
    JSON embebido en el microservicio HTMX.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    url_htmx = f"https://api-lsst.alerce.online/probability_api/htmx/probabilities/{oid_puro}?survey=lsst"

    try:
        resp = requests.get(url_htmx, headers=headers, timeout=6)
        if resp.status_code == 200:
            match = re.search(r'<script id="probabilities-data" type="application/json">(.*?)</script>', resp.text, re.DOTALL)
            if match:
                datos_crudos = json.loads(match.group(1).strip())
                diccionarios = datos_crudos.get("group_prob_dict", {})
                llave_rubin = next((k for k in diccionarios.keys() if "stamp_classifier_rubin" in k), None)
                if llave_rubin and diccionarios[llave_rubin]:
                    clases = diccionarios[llave_rubin]
                    mejor = max(clases, key=lambda x: x.get('probability', 0))
                    return mejor.get('class_name', None), float(mejor.get('probability', 0.0))
    except Exception:
        pass
    return None, 0.0

def determinar_fid_lsst(fila_obj):
    """
    Determina a qué grupo de banda pertenece la detección de LSST revisando
    las bandas activas en lsst_dia_object:
    fid = 1 -> Azul/Verde (u, g)
    fid = 2 -> Rojo/Infrarrojo cercano (r, i, z, y)
    """
    for b_azul in ['g_psffluxmax', 'u_psffluxmax']:
        if b_azul in fila_obj and pd.notna(fila_obj[b_azul]) and float(fila_obj[b_azul]) > 0:
            return 1
    return 2

def obtener_detecciones_lsst(servicio_tap, oid_puro, fila_obj):
    """
    Descarga las detecciones de LSST vía TAP, convierte flujos (nJy) a
    magnitudes AB (magpsf, sigmapsf) y, si es detección única (Stamp Classifier),
    inyecta el límite base 3-sigma para preservar la cinemática y graficación.
    """
    consulta_det = f"""
    SELECT psfflux, psffluxerr, timeprocessedmjdtai
    FROM alerce_tap.lsst_detection
    WHERE oid = {oid_puro}
    ORDER BY timeprocessedmjdtai ASC
    """
    filas_validas = []
    fid_asignado = determinar_fid_lsst(fila_obj)
    mjd_obj_last = float(fila_obj['lastmjd']) if pd.notna(fila_obj['lastmjd']) else Time(datetime.now(timezone.utc)).mjd
    mjd_obj_first = float(fila_obj['firstmjd']) if pd.notna(fila_obj['firstmjd']) else mjd_obj_last

    try:
        tabla_det = servicio_tap.search(consulta_det).to_table()
        for r in tabla_det:
            flujo = r['psfflux']
            flujo_err = r['psffluxerr']
            mjd_det = r['timeprocessedmjdtai']

            if np.ma.is_masked(flujo) or not np.isfinite(flujo) or float(flujo) <= 0:
                continue
            flujo_f = float(flujo)
            err_f = float(flujo_err) if (not np.ma.is_masked(flujo_err) and np.isfinite(flujo_err) and float(flujo_err) > 0) else (flujo_f * 0.1)
            mjd_f = float(mjd_det) if (not np.ma.is_masked(mjd_det) and np.isfinite(mjd_det)) else mjd_obj_last

            mag = -2.5 * math.log10(flujo_f) + 31.4
            sigma = (2.5 / math.log(10.0)) * (err_f / flujo_f)

            filas_validas.append({
                'mjd': mjd_f,
                'magpsf': mag,
                'sigmapsf': max(sigma, 0.01),
                'fid': fid_asignado,
                'flujo_err_raw': err_f
            })
    except Exception:
        pass

    # Respaldo desde lsst_dia_object si lsst_detection aún no sincronizó la fila
    if not filas_validas:
        for col_f in ['r_psffluxmax', 'g_psffluxmax', 'i_psffluxmax', 'z_psffluxmax', 'u_psffluxmax', 'y_psffluxmax']:
            if col_f in fila_obj and pd.notna(fila_obj[col_f]) and float(fila_obj[col_f]) > 0:
                flujo_f = float(fila_obj[col_f])
                mag = -2.5 * math.log10(flujo_f) + 31.4
                fid_b = 1 if col_f.startswith(('u_', 'g_')) else 2
                filas_validas.append({
                    'mjd': mjd_obj_last,
                    'magpsf': mag,
                    'sigmapsf': 0.05,
                    'fid': fid_b,
                    'flujo_err_raw': flujo_f / 15.0
                })
                break

    if not filas_validas:
        return pd.DataFrame()

    # Si es una detección única del Stamp Classifier, sintetizamos el piso 3-sigma previo
    if len(filas_validas) == 1:
        p0 = filas_validas[0]
        flujo_base_3sigma = max(3.0 * p0['flujo_err_raw'], 1.0)
        mag_base = -2.5 * math.log10(flujo_base_3sigma) + 31.4
        if mag_base <= p0['magpsf']:
            mag_base = p0['magpsf'] + 1.2

        filas_validas.insert(0, {
            'mjd': min(mjd_obj_first, p0['mjd']) - 0.5,
            'magpsf': mag_base,
            'sigmapsf': 0.20,
            'fid': p0['fid'],
            'flujo_err_raw': p0['flujo_err_raw']
        })

    df_out = pd.DataFrame(filas_validas)
    return df_out[['mjd', 'magpsf', 'sigmapsf', 'fid']]

# =====================================================================
# 🛡️ ESCUDO TNS (PROTOTIPO LOCAL INTEGRADO)
# =====================================================================
def consultar_escudo_tns(nombre_interno):
    TNS_BOT_ID = os.getenv("TNS_BOT_ID")
    TNS_API_KEY = os.getenv("TNS_API_KEY")
    if not TNS_BOT_ID or not TNS_API_KEY: return None, None

    headers = {'User-Agent': f'tns_marker{{"tns_id":{TNS_BOT_ID}, "type":"bot", "name":"Magallanes_Bot"}}'}
    payload = {"api_key": TNS_API_KEY, "data": json.dumps({"internal_name": nombre_interno})}

    try:
        respuesta = requests.post('https://www.wis-tns.org/api/get/search', headers=headers, data=payload, timeout=8)
        if respuesta.status_code == 200:
            datos = respuesta.json().get('data', {})
            resultados = datos.get('reply', []) if isinstance(datos, dict) else (datos if isinstance(datos, list) else [])

            if resultados and isinstance(resultados, list) and isinstance(resultados[0], dict):
                hit = resultados[0]
                prefijo = hit.get('prefix', 'AT')
                nombre_oficial = hit.get('objname', '')
                return prefijo, f"{prefijo} {nombre_oficial}".strip()
    except Exception: pass
    return None, None

# =====================================================================
# FUNCIONES DE ALMACENAMIENTO LOCAL Y MEMORIA DE TAMIZ
# =====================================================================
def guardar_archivo_texto(ruta, contenido):
    os.makedirs(os.path.dirname(ruta) if os.path.dirname(ruta) else '.', exist_ok=True)
    try:
        with open(ruta, 'w', encoding='utf-8') as f:
            f.write(contenido)
    except Exception: pass

def guardar_grafico_memoria(fig, ruta_relativa):
    os.makedirs(os.path.dirname(ruta_relativa), exist_ok=True)
    fig.savefig(ruta_relativa, dpi=150, bbox_inches='tight')
    plt.close(fig)

def cargar_catalogo_maestro():
    if os.path.exists(CATALOGO_JSON):
        try:
            with open(CATALOGO_JSON, "r", encoding="utf-8") as f:
                lista = json.load(f)
                return {str(item["oid"]): item for item in lista}
        except Exception:
            pass
    return {}

def guardar_catalogo_maestro(catalogo_dict):
    with open(CATALOGO_JSON, "w", encoding="utf-8") as f:
        json.dump(list(catalogo_dict.values()), f, indent=4, ensure_ascii=False)

def cargar_historial_vistos(mjd_actual, catalogo_dict):
    """
    Carga el registro de objetos ya evaluados (descartados o validados),
    limpia entradas con más de 60 horas (2.5 días) de antigüedad y sincroniza
    con el catálogo maestro actual para evitar reprocesamientos.
    """
    historial = {}
    limite_antiguedad = mjd_actual - 2.5
    if os.path.exists(ARCHIVO_HISTORIAL):
        try:
            with open(ARCHIVO_HISTORIAL, "r", encoding="utf-8") as f:
                datos = json.load(f)
                if isinstance(datos, dict):
                    for k, v in datos.items():
                        try:
                            mjd_val = float(v)
                            if mjd_val >= limite_antiguedad:
                                historial[str(k).strip()] = mjd_val
                        except (ValueError, TypeError):
                            pass
        except Exception:
            pass

    # Sincronizar objetos ya presentes en el catálogo maestro
    for oid_cat, info_cat in catalogo_dict.items():
        try:
            mjd_det = float(info_cat.get("mjd_deteccion", 0.0))
            if mjd_det >= limite_antiguedad:
                oid_str = str(oid_cat).strip()
                if oid_str not in historial or mjd_det > historial[oid_str]:
                    historial[oid_str] = mjd_det
        except (ValueError, TypeError):
            pass

    return historial

def guardar_historial_vistos(historial_dict):
    try:
        with open(ARCHIVO_HISTORIAL, "w", encoding="utf-8") as f:
            json.dump(historial_dict, f, ensure_ascii=False)
    except Exception:
        pass

def obtener_mjd_rastreo():
    if not os.path.exists(ARCHIVO_MJD):
        return round(Time(datetime.now(timezone.utc) - timedelta(days=2)).mjd, 4)
    with open(ARCHIVO_MJD, 'r', encoding='utf-8') as f:
        return round(float(f.read().strip()), 4)

def guardar_mjd_rastreo(mjd):
    with open(ARCHIVO_MJD, 'w', encoding='utf-8') as f:
        f.write(str(round(float(mjd), 4)))

def obtener_tracker_tns():
    if not os.path.exists(ARCHIVO_TRACKER_TNS):
        return None
    try:
        with open(ARCHIVO_TRACKER_TNS, 'r', encoding='utf-8') as f:
            txt = f.read().strip()
            if len(txt) >= 19:
                return txt[:19]
    except Exception:
        pass
    return None

def guardar_tracker_tns(fecha_utc_str):
    try:
        with open(ARCHIVO_TRACKER_TNS, 'w', encoding='utf-8') as f:
            f.write(str(fecha_utc_str).strip())
    except Exception:
        pass

def registrar_log(mensaje, log_file):
    print(mensaje)
    fecha_hora = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{fecha_hora}] {mensaje}\n")

def calcular_distancia_hubble(z):
    try:
        if z is None or str(z).strip() == "": return "Desconocida", "N/A"
        z_float = float(z)
        if z_float <= 0: return "Desconocida", "N/A"
        c = 299792.458
        H0_local, H0_temprano = 73.0, 67.4
        dist_min_mpc, dist_max_mpc = (c * z_float) / H0_local, (c * z_float) / H0_temprano
        dist_min_mly, dist_max_mly = dist_min_mpc * 3.26156, dist_max_mpc * 3.26156
        return f"Entre {dist_min_mpc:.2f} y {dist_max_mpc:.2f} Megaparsecs", f"(Aprox. {dist_min_mly:.2f} a {dist_max_mly:.2f} M Años luz)"
    except (ValueError, TypeError):
        return "Desconocida", "N/A"

def propagar_epoca_gaia(ra_gaia, dec_gaia, pm_ra, pm_dec, paralaje_mas, mjd_alerta):
    if paralaje_mas is None or paralaje_mas <= 0 or pm_ra is None or pm_dec is None: return ra_gaia, dec_gaia
    try:
        dist_pc = 1000.0 / paralaje_mas
        c_gaia = SkyCoord(
            ra=ra_gaia * u.deg, dec=dec_gaia * u.deg, distance=dist_pc * u.pc,
            pm_ra_cosdec=pm_ra * u.mas / u.yr, pm_dec=pm_dec * u.mas / u.yr,
            obstime=Time('2016.0', format='jyear'), frame='icrs'
        )
        t_alerta = Time(mjd_alerta, format='mjd')
        c_alerta = c_gaia.apply_space_motion(new_obstime=t_alerta)
        return c_alerta.ra.deg, c_alerta.dec.deg
    except Exception: return ra_gaia, dec_gaia

def obtener_datos_astronomicos(coordenadas, mjd_alerta):
    nombre, distancia, tipo, metalicidad = "No catalogada", "Desconocida", "Desconocido", "Desconocida"
    es_cuasar, es_estrella, es_galaxia, es_vip = False, False, False, False
    redshift_simbad = 0.0
    try:
        signal.signal(signal.SIGALRM, manejador_timeout)
        signal.alarm(10)
        custom_simbad = Simbad()
        custom_simbad.TIMEOUT = 8
        custom_simbad.add_votable_fields('plx', 'sp', 'fe_h', 'otype', 'rvz_redshift')
        resultado = custom_simbad.query_region(coordenadas, radius=3*u.arcsec)

        if resultado is not None and len(resultado) > 0:
            raw_name = resultado['MAIN_ID'][0]
            nombre = raw_name.decode('utf-8') if hasattr(raw_name, 'decode') else str(raw_name)

            if 'OTYPE' in resultado.colnames:
                raw_otype = resultado['OTYPE'][0]
                if not np.ma.is_masked(raw_otype): tipo = raw_otype.decode('utf-8') if hasattr(raw_otype, 'decode') else str(raw_otype)
            if 'PLX_VALUE' in resultado.colnames:
                plx = resultado['PLX_VALUE'][0]
                if not np.ma.is_masked(plx) and not np.isnan(plx) and float(plx) > 0: distancia = f"~{(1000.0 / float(plx)) * 3.26156:.1f} Años Luz"

            if 'RVZ_REDSHIFT' in resultado.colnames:
                raw_z = resultado['RVZ_REDSHIFT'][0]
                if not np.ma.is_masked(raw_z) and not np.isnan(float(raw_z)):
                    redshift_simbad = float(raw_z)

            tipo_upper = str(tipo).upper()
            es_cuasar = any(x in tipo_upper for x in ["QSO", "AGN", "BLAZAR", "BLLAC", "SEYFERT"])
            es_estrella = any(x in tipo_upper for x in ["STAR", "FLARE", "CV", "NOVA", "WHITE DWARF", "V*"])
            es_galaxia = any(x in tipo_upper for x in ["GALAXY", "GLS", "LSB"])
            if any(x in tipo_upper for x in ["M DWARF", "DM", "FLARE STAR", "UV CETI"]): es_vip = True
    except Exception:
        pass
    finally:
        signal.alarm(0)

    if not es_cuasar and not es_estrella and not es_galaxia:
        try:
            signal.signal(signal.SIGALRM, manejador_timeout)
            signal.alarm(12)
            v = Vizier(columns=['RA_ICRS', 'DE_ICRS', 'pmRA', 'pmDE', 'Plx', 'e_Plx'], catalog="I/355/gaiadr3")
            v.TIMEOUT = 10
            resultado_gaia = v.query_region(coordenadas, radius=15.0*u.arcsec)
            if len(resultado_gaia) > 0:
                for fila in resultado_gaia[0]:
                    plx_gaia = fila['Plx']
                    e_plx_gaia = fila['e_Plx']
                    if not np.ma.is_masked(plx_gaia) and not np.isnan(plx_gaia) and plx_gaia > (3 * e_plx_gaia):
                        ra_futuro, dec_futuro = propagar_epoca_gaia(fila['RA_ICRS'], fila['DE_ICRS'], fila['pmRA'], fila['pmDE'], plx_gaia, mjd_alerta)
                        c_futuro = SkyCoord(ra=ra_futuro*u.deg, dec=dec_futuro*u.deg)
                        if coordenadas.separation(c_futuro) <= 2.0 * u.arcsec:
                            es_estrella = True
                            tipo = "Estrella (Confirmada por Astrometría Gaia DR3 Proyectada)"
                            distancia = f"~{(1000.0 / plx_gaia) * 3.26156:.1f} Años Luz"
                            break
        except Exception:
            pass
        finally:
            signal.alarm(0)

    return nombre, distancia, tipo, metalicidad, es_cuasar, es_estrella, es_galaxia, es_vip, redshift_simbad

def graficar_curva(det, id_evento, red_descubridora, ra_float, dec_float, tipo_evento_final="supernova", es_vip=False):
    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
    fig.patch.set_facecolor('#0f0f0f')
    ax1.set_facecolor('#1a1a1a')
    ax2.set_facecolor('#1a1a1a')

    color_destaque = '#ff00ff' if es_vip else ('cyan' if tipo_evento_final in ["supernova", "agn", "blazar", "tde"] else 'yellow')

    if det is not None and not det.empty:
        if 'fecha_humana' not in det.columns: det['fecha_humana'] = Time(det['mjd'].values, format='mjd').to_datetime()
        banda_g, banda_r = det[det['fid'] == 1], det[det['fid'] == 2]
        if not banda_g.empty: ax1.errorbar(banda_g['fecha_humana'], banda_g['magpsf'], yerr=banda_g['sigmapsf'], fmt='o', color='#39ff14', alpha=0.6, markersize=5, label='Banda g / u')
        if not banda_r.empty: ax1.errorbar(banda_r['fecha_humana'], banda_r['magpsf'], yerr=banda_r['sigmapsf'], fmt='o', color='#ff3333', alpha=0.6, markersize=5, label='Banda r / i / z / y')
        det_sorted = det.sort_values(by='mjd')
        ax1.scatter(det_sorted.iloc[-1]['fecha_humana'], det_sorted.iloc[-1]['magpsf'], color=color_destaque, marker='*', s=400, edgecolor='white', zorder=5, label='¡Última Detección!')
        ax1.invert_yaxis()
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        fig.autofmt_xdate(rotation=45)
        ax1.set_xlabel("Fecha de Observación (UTC)", color='lightgray')
        ax1.set_ylabel("Magnitud Aparente (Brillo)", color='lightgray')
        ax1.legend(facecolor='#0f0f0f', edgecolor='gray')
    else:
        ax1.text(0.5, 0.65, "FOTOMETRÍA RESERVADA", color='#ffcc00', fontsize=22, ha='center', va='center', fontweight='bold')
        ax1.text(0.5, 0.45, "Matriz alojada en el Transient Name Server.", color='lightgray', fontsize=12, ha='center', va='center')
        ax1.set_xticks([]); ax1.set_yticks([])

    ax1.set_title(f"Telemetría Fotométrica: {id_evento}", color='white', pad=15)
    ax1.grid(True, linestyle='-', color='#333333', alpha=0.7)

    try:
        coordenadas = SkyCoord(ra=ra_float*u.degree, dec=dec_float*u.degree, frame='icrs')
        constelacion = get_constellation(coordenadas)
    except Exception: constelacion = "Desconocida"

    ax2.scatter(ra_float, dec_float, color=color_destaque, marker='*', s=400, label=f'Posición {red_descubridora}')
    ax2.set_xlim(ra_float + 1, ra_float - 1)
    ax2.set_ylim(dec_float - 1, dec_float + 1)
    ax2.set_title(f"Coordenadas en {constelacion}", color='white', pad=15)
    ax2.set_xlabel("Ascensión Recta (RA)", color='lightgray')
    ax2.set_ylabel("Declinación (Dec)", color='lightgray')
    ax2.legend(facecolor='#0f0f0f', edgecolor='gray', loc='upper right')
    ax2.grid(True, linestyle=':', color='#444444')

    titulo_vip = "[OBJETIVO VIP ESTACIÓN MAGALLANES]" if es_vip else f"Reporte Astronómico: {tipo_evento_final.upper()}"
    plt.tight_layout(rect=[0, 0.05, 0.82, 0.92])
    plt.suptitle(titulo_vip, fontsize=20, color=color_destaque, fontweight='bold', y=0.98)

    ruta_grafico = f"data/curva_luz_{id_evento.replace(' ', '_')}.png"
    guardar_grafico_memoria(fig, ruta_grafico)

# =====================================================================
# 📡 SINCRONIZACIÓN AUTOMÁTICA TNS EN RAM (CSV PÚBLICOS + RESPALDO MANUAL)
# =====================================================================
def clasificar_tipo_tns(clasificacion_str):
    """
    Filtra las clases objetivo confirmadas en TNS:
    - TDE -> "tde"
    - CV / Nova -> "nova"
    - SN / SLSN (excluyendo Impostor-SN) -> "supernova"
    """
    tu = str(clasificacion_str or "").strip().upper()
    if not tu:
        return None
    if "TDE" in tu:
        return "tde"
    if "CV" in tu or "NOVA" in tu:
        return "nova"
    if (tu.startswith("SN") or tu.startswith("SLSN")) and "IMPOSTOR" not in tu:
        return "supernova"
    return None

def parsear_fecha_tns_a_mjd(fecha_str):
    try:
        txt = str(fecha_str or "").strip()
        if len(txt) >= 19:
            dt = datetime.strptime(txt[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            return float(Time(dt).mjd)
    except Exception:
        pass
    return None

def iterar_zip_tns_en_ram(contenido_bytes):
    """
    Descomprime en RAM un ZIP de TNS y entrega fila por fila como diccionario,
    omitiendo de forma segura la línea de rango horario y los bloques vacíos.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(contenido_bytes)) as zf:
            nombres = zf.namelist()
            if not nombres:
                return
            with zf.open(nombres[0]) as raw_f:
                texto = io.TextIOWrapper(raw_f, encoding="utf-8", errors="ignore")
                primera = texto.readline()
                if not primera:
                    return
                if "objid" in primera.lower():
                    flujo = itertools.chain([primera], texto)
                else:
                    segunda = texto.readline()
                    if not segunda or "objid" not in segunda.lower():
                        return
                    flujo = itertools.chain([segunda], texto)
                for fila in csv.DictReader(flujo):
                    yield fila
    except Exception:
        return

def registrar_evento_tns_en_catalogo(
    client, catalogo_dict, indice_por_codigo, log_file,
    prefijo, objname, ra_float, dec_float, redshift,
    clasificacion, tipo_evento_tns, descubridor,
    fecha_desc="", fecha_mod="", nombres_internos_str=""
):
    """
    Descarga fotometría ALeRCE si existe, genera el gráfico y la circular oficial,
    y promueve el registro en catalogo_maestro.json evitando duplicados por prefijo
    o identificador interno.
    """
    prefijo_limpio = str(prefijo or "").strip()
    if not prefijo_limpio:
        if tipo_evento_tns == "tde":
            prefijo_limpio = "TDE"
        elif tipo_evento_tns == "supernova":
            prefijo_limpio = "SN"
        else:
            prefijo_limpio = "AT"

    id_evento = f"{prefijo_limpio} {objname}".strip()
    codigo_lower = str(objname).strip().lower()

    clave_previa = indice_por_codigo.get(codigo_lower)
    if clave_previa and clave_previa in catalogo_dict:
        if catalogo_dict[clave_previa].get("survey") == "TNS_GLOBAL":
            registrar_log(f"[*] {id_evento} ya existe ({clave_previa}). Actualizando reclasificación a {clasificacion}...", log_file)
        else:
            registrar_log(f"[*] {id_evento} cazado previamente como {clave_previa}. ¡ASCENDIENDO a Confirmada TNS!", log_file)

    registrar_log(f"Descargando ficha técnica oficial para {id_evento} ({clasificacion})...", log_file)
    print(f"    [+] Procesando confirmación oficial IAU: {id_evento} | {clasificacion}")

    rango_mpc, rango_mly = calcular_distancia_hubble(redshift)

    det = None
    try:
        if ra_float != 0.0 or dec_float != 0.0:
            signal.signal(signal.SIGALRM, manejador_timeout)
            signal.alarm(15)

            candidatos_alerce = client.query_objects(ra=ra_float, dec=dec_float, radius=10, format='pandas')
            if candidatos_alerce is not None and not candidatos_alerce.empty:
                if 'lastmjd' in candidatos_alerce.columns:
                    candidatos_alerce = candidatos_alerce.sort_values(by='lastmjd', ascending=False)

                oid_tns = candidatos_alerce.iloc[0]['oid']
                oid_tns = oid_tns.decode('utf-8') if isinstance(oid_tns, bytes) else str(oid_tns)
                det = client.query_detections(oid=oid_tns, format='pandas')

            signal.alarm(0)
    except TimeoutException:
        registrar_log(f"   [-] Timeout: ALeRCE no entregó fotometría para {id_evento} a tiempo. Omitiendo curva.", log_file)
    except Exception as e:
        registrar_log(f"   [-] Fallo menor en extracción fotométrica para {id_evento}: {e}", log_file)
    finally:
        signal.alarm(0)

    try:
        graficar_curva(det, id_evento, descubridor, ra_float, dec_float, tipo_evento_final=tipo_evento_tns)
    except Exception:
        pass

    url_tns = f"https://www.wis-tns.org/object/{objname}"
    z_mostrar = redshift if (redshift is not None and str(redshift).strip() != "") else "Desconocido"

    lineas_fechas = ""
    if fecha_desc:
        lineas_fechas += f"Fecha Descubrimiento  : {fecha_desc} UTC\n"
    if fecha_mod:
        lineas_fechas += f"Actualización TNS     : {fecha_mod} UTC\n"

    texto_tns = f"""======================================================================
[REGISTRO OFICIAL TNS] - EVENTO CONFIRMADO
======================================================================
ID de Evento          : {id_evento}
Clasificación Oficial : {clasificacion}
Red de Descubrimiento : {descubridor}
Coordenadas (ICRS)    : RA {ra_float:.5f} | Dec {dec_float:.5f}
{lineas_fechas}
[CÁLCULO DE DISTANCIA (Basado en z = {z_mostrar})]
{rango_mpc}
{rango_mly}

======================================================================
🔗 ENLACE OFICIAL DEL TRANSIENT NAME SERVER:
{url_tns}
======================================================================
- NOTA: Este evento ya está confirmado por la IAU. No se requiere
  emisión de telegramas ni seguimiento de validación por parte
  de la Estación Magallanes.
======================================================================"""

    ruta_txt = f"alertas/CIRCULAR_{id_evento.replace(' ', '_')}.txt"
    guardar_archivo_texto(ruta_txt, texto_tns)

    if det is not None and not det.empty and 'mjd' in det.columns:
        mjd_obs = float(det['mjd'].max())
    else:
        mjd_obs = (
            parsear_fecha_tns_a_mjd(fecha_mod)
            or parsear_fecha_tns_a_mjd(fecha_desc)
            or float(Time(datetime.now(timezone.utc)).mjd)
        )

    try:
        # Eliminar entrada previa con distinto prefijo (ej. AT -> SN/TDE)
        if clave_previa and clave_previa != id_evento:
            catalogo_dict.pop(clave_previa, None)

        # Eliminar candidatas previas de ZTF/LSST que coincidan por nombre interno
        if nombres_internos_str:
            for nom_int in str(nombres_internos_str).split(","):
                nom_limpio = nom_int.strip()
                if nom_limpio and nom_limpio != id_evento and nom_limpio in catalogo_dict:
                    if catalogo_dict[nom_limpio].get("survey") != "TNS_GLOBAL":
                        catalogo_dict.pop(nom_limpio, None)

        ruta_img = f"data/curva_luz_{id_evento.replace(' ', '_')}.png"
        catalogo_dict[id_evento] = {
            "oid": id_evento,
            "ra": float(ra_float),
            "dec": float(dec_float),
            "tipo": tipo_evento_tns,
            "survey": "TNS_GLOBAL",
            "analisis": clasificacion,
            "vip": False,
            "mjd_deteccion": float(mjd_obs),
            "img_url": ruta_img if os.path.exists(ruta_img) else None
        }
        indice_por_codigo[codigo_lower] = id_evento
        return True
    except Exception as e:
        registrar_log(f"[!] Error al inyectar {id_evento} al catálogo JSON: {e}", log_file)
        return False

def consultar_tns_sur(client, catalogo_dict):
    log_file = "bitacoras/bitacora_TNS_GLOBAL.log"
    ahora_utc = datetime.now(timezone.utc)
    ahora_utc_str = ahora_utc.strftime("%Y-%m-%d %H:%M:%S")

    # Índice en RAM por código base sin prefijo (ej. "2026aetp") para evitar duplicados entre AT/SN/TDE
    indice_por_codigo = {}
    for k_oid in list(catalogo_dict.keys()):
        codigo_base = str(k_oid).strip().split()[-1].lower()
        if codigo_base:
            # Priorizar claves ya confirmadas en TNS_GLOBAL si existiera más de una
            if codigo_base not in indice_por_codigo or catalogo_dict[k_oid].get("survey") == "TNS_GLOBAL":
                indice_por_codigo[codigo_base] = k_oid

    def ya_confirmado_sin_cambios(objname, clasificacion):
        clave = indice_por_codigo.get(str(objname).strip().lower())
        if not clave or clave not in catalogo_dict:
            return False
        info = catalogo_dict[clave]
        if info.get("survey") != "TNS_GLOBAL":
            return False
        return str(info.get("analisis", "")).strip().upper() == str(clasificacion).strip().upper()

    # -----------------------------------------------------------------
    # 1. DETERMINAR MODO DE SINCRONIZACIÓN AUTOMÁTICA EN RAM
    # -----------------------------------------------------------------
    ultimo_tracker = obtener_tracker_tns()
    requiere_volcado_completo = False
    corte_tde = CORTE_INICIAL_TDE
    corte_general = CORTE_INICIAL_GENERAL

    if not ultimo_tracker:
        requiere_volcado_completo = True
        registrar_log(
            f"[*] Primera sincronización TNS en RAM: recuperando TDE (>= {corte_tde}) y SN/CV/Nova (>= {corte_general}).",
            log_file
        )
    else:
        try:
            dt_ultimo = datetime.strptime(ultimo_tracker, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            horas_sin_sync = (ahora_utc - dt_ultimo).total_seconds() / 3600.0
            if horas_sin_sync > 20.0:
                requiere_volcado_completo = True
                margen_str = (dt_ultimo - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
                corte_tde = margen_str
                corte_general = margen_str
                registrar_log(
                    f"[*] Desfase detectado ({horas_sin_sync:.1f} h desde {ultimo_tracker}). Activando volcado diario completo TNS.",
                    log_file
                )
        except Exception:
            requiere_volcado_completo = True

    candidatos_csv = {}
    sesion = requests.Session()
    sesion.headers.update(TNS_GUEST_HEADERS)
    descarga_exitosa = False

    def evaluar_y_acumular_fila(fila, aplicar_cortes_temporales=False):
        clasificacion = (fila.get("type") or "").strip()
        tipo_evento = clasificar_tipo_tns(clasificacion)
        if not tipo_evento:
            return

        objname = (fila.get("name") or "").strip()
        if not objname:
            return

        fecha_mod = (fila.get("lastmodified") or "").strip()
        fecha_desc = (fila.get("discoverydate") or "").strip()

        # Filtrar ediciones bibliográficas antiguas de supernovas previas a 2025
        if tipo_evento == "supernova" and fecha_desc and fecha_desc < CORTE_DESCUBRIMIENTO_SN:
            return

        if aplicar_cortes_temporales:
            if tipo_evento == "tde":
                if fecha_mod < corte_tde:
                    return
            else:
                if fecha_mod < corte_general:
                    return

        if ya_confirmado_sin_cambios(objname, clasificacion):
            return

        clave_cod = objname.lower()
        previo = candidatos_csv.get(clave_cod)
        if not previo or fecha_mod >= (previo.get("lastmodified") or ""):
            candidatos_csv[clave_cod] = fila

    # 1A. Volcado diario completo (solo en rescate inicial o tras > 20 h sin sincronizar)
    if requiere_volcado_completo:
        url_completo = f"{TNS_PUBLIC_BASE_URL}/tns_public_objects.csv.zip"
        try:
            print("    Descargando volcado completo TNS en RAM...")
            resp = sesion.get(url_completo, timeout=45)
            if resp.status_code == 200:
                descarga_exitosa = True
                for fila in iterar_zip_tns_en_ram(resp.content):
                    evaluar_y_acumular_fila(fila, aplicar_cortes_temporales=True)
                print(f"    [TNS Completo] {len(candidatos_csv)} eventos nuevos o reclasificados detectados.")
            else:
                registrar_log(f"[!] No se pudo descargar volcado completo TNS: HTTP {resp.status_code}", log_file)
        except Exception as e:
            registrar_log(f"[!] Error al descargar volcado completo TNS: {e}", log_file)

    # 1B. Barrido del anillo de 24 deltas horarios (_00 a _23) en RAM
    bloques_ok = 0
    for hora in range(24):
        url_delta = f"{TNS_PUBLIC_BASE_URL}/tns_public_objects_{hora:02d}.csv.zip"
        try:
            resp_h = sesion.get(url_delta, timeout=12)
            if resp_h.status_code == 200:
                bloques_ok += 1
                descarga_exitosa = True
                for fila in iterar_zip_tns_en_ram(resp_h.content):
                    evaluar_y_acumular_fila(fila, aplicar_cortes_temporales=False)
        except Exception:
            continue

    sesion.close()
    print(f"    [TNS Deltas RAM] {bloques_ok}/24 bloques horarios leídos | {len(candidatos_csv)} eventos por incorporar.")

    # Ordenar cronológicamente para registro limpio y reanudable
    lista_eventos_csv = sorted(
        candidatos_csv.values(),
        key=lambda x: (x.get("lastmodified") or x.get("discoverydate") or "")
    )

    procesados_csv = 0
    if lista_eventos_csv:
        registrar_log(f"[+] Sincronización TNS en RAM: {len(lista_eventos_csv)} confirmaciones nuevas/reclasificadas por procesar.", log_file)
        for fila in lista_eventos_csv:
            try:
                objname = (fila.get("name") or "").strip()
                prefijo = (fila.get("name_prefix") or "").strip()
                clasificacion = (fila.get("type") or "").strip()
                tipo_evento_tns = clasificar_tipo_tns(clasificacion)
                ra_float = float(fila.get("ra") or 0.0)
                dec_float = float(fila.get("declination") or 0.0)
                redshift = (fila.get("redshift") or "").strip()
                descubridor = (fila.get("reporting_group") or fila.get("source_group") or "Desconocido").strip()
                fecha_desc = (fila.get("discoverydate") or "").strip()
                fecha_mod = (fila.get("lastmodified") or "").strip()
                nombres_internos = (fila.get("internal_names") or "").strip()

                ok = registrar_evento_tns_en_catalogo(
                    client, catalogo_dict, indice_por_codigo, log_file,
                    prefijo, objname, ra_float, dec_float, redshift,
                    clasificacion, tipo_evento_tns, descubridor,
                    fecha_desc=fecha_desc, fecha_mod=fecha_mod,
                    nombres_internos_str=nombres_internos
                )
                if ok:
                    procesados_csv += 1
                    if procesados_csv % 10 == 0:
                        guardar_catalogo_maestro(catalogo_dict)
            except Exception as e:
                registrar_log(f"[!] Error al procesar fila CSV TNS ({fila.get('name', 'desconocido')}): {e}", log_file)

        guardar_catalogo_maestro(catalogo_dict)

    if descarga_exitosa and (not requiere_volcado_completo or bloques_ok > 0):
        guardar_tracker_tns(ahora_utc_str)

    # -----------------------------------------------------------------
    # 2. RESPALDO MANUAL OPCIONAL (boletin_tns.txt si contiene códigos)
    # -----------------------------------------------------------------
    if os.path.exists(ARCHIVO_BOLETIN):
        try:
            with open(ARCHIVO_BOLETIN, 'r', encoding='utf-8') as f:
                lineas = f.read().split('\n')
        except Exception:
            lineas = []

        texto_a_analizar = '\n'.join(lineas[2:]) if len(lineas) > 2 else ""
        if texto_a_analizar.strip():
            patron = r'\b202\d[a-zA-Z]{1,4}\b'
            extraccion = re.findall(patron, texto_a_analizar.lower())
            supernovas_a_buscar = list(set([obj.lower() for obj in extraccion]))

            if supernovas_a_buscar:
                registrar_log(f"[+] Boletín manual leído. Se encontraron {len(supernovas_a_buscar)} eventos adicionales: {supernovas_a_buscar}", log_file)
                TNS_BOT_ID = os.getenv("TNS_BOT_ID")
                TNS_API_KEY = os.getenv("TNS_API_KEY")
                headers_api = {'User-Agent': f'tns_marker{{"tns_id":{TNS_BOT_ID}, "type":"bot", "name":"Magallanes_Bot"}}'}

                for objname in supernovas_a_buscar:
                    try:
                        resp_obj = requests.post(
                            'https://www.wis-tns.org/api/get/object',
                            headers=headers_api,
                            data={"api_key": TNS_API_KEY, "data": json.dumps({"objname": objname})},
                            timeout=10
                        )
                        if resp_obj.status_code == 200:
                            datos_obj = resp_obj.json().get('data', {}).get('reply', {})
                            if not datos_obj:
                                datos_obj = resp_obj.json().get('data', {})

                            prefijo = str(datos_obj.get('name_prefix') or 'SN').strip()
                            ra_float = float(datos_obj.get('radeg') or 0.0)
                            dec_float = float(datos_obj.get('decdeg') or 0.0)
                            redshift = datos_obj.get('redshift')

                            obj_type_dict = datos_obj.get('object_type', {})
                            clasificacion = obj_type_dict.get('name', 'SUPERNOVA') if isinstance(obj_type_dict, dict) else 'SUPERNOVA'
                            tipo_evento_tns = clasificar_tipo_tns(clasificacion) or "supernova"

                            disc_dict = datos_obj.get('discovery_data_source', {})
                            descubridor = str(disc_dict.get('group_name', 'Desconocido')) if isinstance(disc_dict, dict) else 'Desconocido'

                            registrar_evento_tns_en_catalogo(
                                client, catalogo_dict, indice_por_codigo, log_file,
                                prefijo, objname, ra_float, dec_float, redshift,
                                clasificacion, tipo_evento_tns, descubridor,
                                fecha_desc=str(datos_obj.get('discoverydate') or '').strip(),
                                nombres_internos_str=str(datos_obj.get('internal_names') or '').strip()
                            )
                        else:
                            registrar_log(f"[!] Error interno de TNS al pedir objeto {objname}: HTTP {resp_obj.status_code}", log_file)
                    except Exception as e:
                        registrar_log(f"[!] Excepción al pedir objeto {objname}: {e}", log_file)
                    time.sleep(2.5)

            with open(ARCHIVO_BOLETIN, "w", encoding="utf-8") as f:
                f.write("Listado de confirmaciones oficiales TNS\n\n")

    if procesados_csv == 0:
        registrar_log("[-] Sin nuevas confirmaciones TNS en este ciclo. Patrullaje completado.", log_file)
    else:
        registrar_log(f"[+] Procesamiento TNS finalizado ({procesados_csv} confirmaciones integradas). Patrullaje completado.", log_file)

def main():
    print("=== INICIANDO CAZADOR MULTIPROPÓSITO (26.0 - TNS EN RAM, TAMIZ RAM Y RELOJ 4D) ===")
    client = Alerce()
    mjd_reciente = obtener_mjd_rastreo()
    # Capturamos el instante exacto de inicio del patrullaje con precisión de 4 decimales
    mjd_inicio_patrullaje = round(Time(datetime.now(timezone.utc)).mjd, 4)

    url_tap = "https://tap.alerce.online/tap"
    servicio_tap = vo.dal.TAPService(url_tap)

    catalogo_dict = cargar_catalogo_maestro()
    historial_vistos = cargar_historial_vistos(mjd_inicio_patrullaje, catalogo_dict)

    for current_survey in ["ZTF", "LSST", "TNS_GLOBAL"]:
        log_file = f"bitacoras/bitacora_{current_survey}.log"
        print("==================================================")
        print(f"APUNTANDO TELESCOPIO A RED: {current_survey}")
        registrar_log("==================================================", log_file)
        registrar_log(f"APUNTANDO TELESCOPIO A RED: {current_survey}", log_file)

        if current_survey == "TNS_GLOBAL":
            consultar_tns_sur(client, catalogo_dict)
            continue

        target_classes = diccionario_categorias.get(current_survey, [])
        margen_dias = 0.2 if current_survey == "ZTF" else 1.0
        limite_mjd = round(mjd_reciente - margen_dias, 4)

        if current_survey == "ZTF":
            consulta_adql = f"""
            SELECT TOP 1500 oid, meanra, meandec, firstmjd, lastmjd
            FROM ztf.object
            WHERE lastmjd >= {limite_mjd}
            ORDER BY lastmjd DESC
            """
        else:
            # Consulta LSST incluyendo las 6 bandas y filtrando tiempos nulos
            consulta_adql = f"""
            SELECT TOP 1500
                oid,
                ra AS meanra,
                dec AS meandec,
                firstdiasourcemjdtai AS firstmjd,
                lastdiasourcemjdtai AS lastmjd,
                u_psffluxmax,
                g_psffluxmax,
                r_psffluxmax,
                i_psffluxmax,
                z_psffluxmax,
                y_psffluxmax
            FROM alerce_tap.lsst_dia_object
            WHERE lastdiasourcemjdtai >= {limite_mjd}
              AND lastdiasourcemjdtai IS NOT NULL
            ORDER BY lastdiasourcemjdtai DESC
            """

        try:
            print(f"   Extrayendo catálogo masivo de {current_survey} vía TAP ADQL (desde MJD {limite_mjd})...")
            resultados = servicio_tap.search(consulta_adql)

            # --- BLINDAJE ASTROPY NATIVO: Convertir OID a str ANTES de .to_pandas() ---
            tabla_astropy = resultados.to_table()
            if 'oid' in tabla_astropy.colnames:
                tabla_astropy['oid'] = [
                    x.decode('utf-8').strip() if isinstance(x, bytes) else str(x).strip()
                    for x in tabla_astropy['oid']
                ]
            candidatos = tabla_astropy.to_pandas()
            # --------------------------------------------------------------------------

            if 'lastmjd' in candidatos.columns:
                candidatos['lastmjd'] = pd.to_numeric(candidatos['lastmjd'], errors='coerce')
                candidatos = candidatos.dropna(subset=['lastmjd'])

            if candidatos.empty:
                print(f"   (0 candidatos encontrados desde MJD {limite_mjd})")
                registrar_log(f"[+] Patrullaje completado en {current_survey} (0 candidatos nuevos).", log_file)
                continue

            # =====================================================================
            # 🧠 TAMIZ DE MEMORIA EN RAM (FILTRO DE OBJETOS YA ANALIZADOS)
            # =====================================================================
            total_descargados = len(candidatos)
            mascara_nuevos = [
                (str(r_oid).strip() not in historial_vistos) or (float(r_mjd) > (historial_vistos[str(r_oid).strip()] + 1e-4))
                for r_oid, r_mjd in zip(candidatos['oid'], candidatos['lastmjd'])
            ]
            candidatos = candidatos[mascara_nuevos].reset_index(drop=True)
            ya_vistos_omitidos = total_descargados - len(candidatos)

            print(f"   [Tamiz RAM] {total_descargados} descargados | {ya_vistos_omitidos} omitidos (ya evaluados) | {len(candidatos)} NUEVOS a procesar.")

            if candidatos.empty:
                registrar_log(f"[+] Patrullaje completado en {current_survey} (0 objetos nuevos tras tamiz RAM).", log_file)
                continue
            # =====================================================================

            print(f"   ({len(candidatos)} objetos nuevos. Iniciando análisis por paquetes de a 50 para proteger RAM...)")

            tamano_paquete = 50
            for i in range(0, len(candidatos), tamano_paquete):
                paquete = candidatos.iloc[i:i+tamano_paquete]
                print(f"   [Paquete {(i//tamano_paquete) + 1}/{(len(candidatos)//tamano_paquete) + 1}] Procesando lote de {len(paquete)} objetos...")

                for index, fila in paquete.iterrows():
                    oid = str(fila['oid']).strip()
                    mjd_fila = float(fila['lastmjd'])

                    try:
                        # --- CANDADO DE TIEMPO ÁGIL (15s PARA EXTRACCIÓN ALERCE) ---
                        signal.signal(signal.SIGALRM, manejador_timeout)
                        signal.alarm(15)

                        # 1. EXTRACCIÓN DE IA SEGÚN RED (ZTF vs LSST)
                        if current_survey == "ZTF":
                            probs = client.query_probabilities(oid=oid, format='pandas')
                            if probs.empty:
                                signal.alarm(0)
                                historial_vistos[oid] = mjd_fila
                                continue
                            mejor_prediccion = probs.loc[probs['probability'].idxmax()]
                            clase_ia_final, probabilidad = mejor_prediccion['class_name'], float(mejor_prediccion['probability'])
                        else:
                            clase_ia_final, probabilidad = infiltrar_ia_lsst(oid)
                            if not clase_ia_final:
                                signal.alarm(0)
                                historial_vistos[oid] = mjd_fila
                                continue

                        if clase_ia_final in target_classes and probabilidad > 0.60:
                            print(f"      [!] ALERTA AISLADA ({current_survey}): {oid} | IA: {clase_ia_final} ({probabilidad*100:.1f}%)")

                            # 2. EXTRACCIÓN DE FOTOMETRÍA SEGÚN RED (ZTF vs LSST)
                            if current_survey == "ZTF":
                                det = client.query_detections(oid=oid, format='pandas')
                                det = det.dropna(subset=['magpsf', 'mjd'])
                            else:
                                det = obtener_detecciones_lsst(servicio_tap, oid, fila)

                            signal.alarm(0)

                            # El objeto ya fue descargado exitosamente de ALeRCE; lo registramos como visto en esta época
                            historial_vistos[oid] = mjd_fila

                            if det is None or det.empty or len(det) < 2:
                                continue

                            # =================================================================
                            # --- 1. GUILLOTINA FOTOMÉTRICA EN RAM (ANTES DE CONSULTAR SIMBAD/GAIA) ---
                            # =================================================================
                            limite_mag = 18.5 if current_survey == "ZTF" else 23.5
                            mag_pico_absoluto = float(det['magpsf'].min())
                            if mag_pico_absoluto > limite_mag:
                                print(f"      [-] Purgado: {oid} demasiado tenue para {current_survey} (Pico mag {mag_pico_absoluto:.2f} > {limite_mag})")
                                continue

                            # =================================================================
                            # --- 2. CINEMÁTICA CON SEPARACIÓN DE BANDAS EN RAM ---
                            # =================================================================
                            mjd_min_fotometria = float(det['mjd'].min())
                            mjd_max = float(det['mjd'].max())
                            mjd_historico = float(fila['firstmjd']) if pd.notna(fila['firstmjd']) else mjd_min_fotometria
                            edad_dias = max(0.0, mjd_max - mjd_historico)

                            mejor_salto = 0.0
                            mejor_tasa = 0.0
                            mejor_tasa_reciente = 0.0
                            bandas_procesadas = 0

                            for fid in [1, 2]: # 1: g/u, 2: r/i/z/y
                                df_b = det[det['fid'] == fid]
                                if len(df_b) < 2: continue

                                bandas_procesadas += 1
                                amp_b = float(df_b['magpsf'].max() - df_b['magpsf'].min())
                                mjd_pico_b = float(df_b.loc[df_b['magpsf'].idxmin(), 'mjd'])
                                dias_al_pico_b = mjd_pico_b - float(df_b['mjd'].min())
                                if dias_al_pico_b <= 0: dias_al_pico_b = 1.0
                                tasa_b = amp_b / dias_al_pico_b

                                tasa_rec_b = tasa_b
                                if (df_b['mjd'].max() - df_b['mjd'].min()) > 30:
                                    df_rec = df_b[df_b['mjd'] >= df_b['mjd'].max() - 30]
                                    df_ant = df_b[df_b['mjd'] < df_b['mjd'].max() - 30]
                                    if not df_rec.empty and not df_ant.empty:
                                        salto_rec = float(df_ant['magpsf'].median() - df_rec['magpsf'].min())
                                        mjd_p_rec = float(df_rec.loc[df_rec['magpsf'].idxmin(), 'mjd'])
                                        dias_p_rec = mjd_p_rec - float(df_rec['mjd'].min())
                                        if dias_p_rec <= 0: dias_p_rec = 1.0
                                        tasa_rec_b = (salto_rec / dias_p_rec) if salto_rec > 0 else 0.0

                                if amp_b > mejor_salto:
                                    mejor_salto = amp_b
                                    mejor_tasa = tasa_b
                                    mejor_tasa_reciente = tasa_rec_b

                            if bandas_procesadas == 0:
                                mejor_salto = float(det['magpsf'].max() - det['magpsf'].min())
                                dias_pico_tot = float(det.loc[det['magpsf'].idxmin(), 'mjd']) - mjd_min_fotometria
                                if dias_pico_tot <= 0: dias_pico_tot = 1.0
                                mejor_tasa = mejor_salto / dias_pico_tot
                                mejor_tasa_reciente = mejor_tasa

                            salto_luminosidad_delta = mejor_salto
                            tasa_acel = mejor_tasa
                            tasa_acel_reciente = mejor_tasa_reciente
                            amplitud_mag = mejor_salto

                            # Pre-filtro cinemático: si no tiene salto >= 0.5 ni es flare rápido, todas las ramas dan "descarte"
                            if salto_luminosidad_delta < 0.5 and not (edad_dias < 3.0 and tasa_acel_reciente > 1.0):
                                continue

                            # =================================================================
                            # --- 3. CONSULTA A SIMBAD / GAIA SOLO PARA OBJETOS ACTIVOS Y BRILLANTES ---
                            # =================================================================
                            coordenadas = SkyCoord(ra=float(fila['meanra'])*u.degree, dec=float(fila['meandec'])*u.degree, frame='icrs')
                            mjd_alerta_actual = mjd_max
                            nombre_real, distancia_real, tipo_real, metalicidad_real, es_cuasar_cat, es_estrella_cat, es_galaxia_cat, es_vip, redshift_cazado = obtener_datos_astronomicos(coordenadas, mjd_alerta_actual)

                            latitud_b, en_plano, es_viejo = coordenadas.galactic.b.degree, abs(coordenadas.galactic.b.degree) <= 10.0, edad_dias > 150

                            # =========================================================
                            # 🛡️ BLOQUE CORREGIDO: VETO QSO E INTELIGENCIA
                            # =========================================================
                            veto_ia_cv = ("CV" in clase_ia_final.upper() or "NOVA" in clase_ia_final.upper() or "VS" in clase_ia_final.upper()) and probabilidad > 0.90
                            veto_ia_qso = any(x in clase_ia_final.upper() for x in ["QSO", "AGN", "BLAZAR"]) and probabilidad > 0.60
                            analisis_magallanes, tipo_evento_final = "DESCONOCIDO", "descarte"

                            if es_cuasar_cat or veto_ia_qso or (es_viejo and not en_plano and not veto_ia_cv and not es_estrella_cat):
                                if salto_luminosidad_delta > 0.5:
                                    if tasa_acel_reciente > 0.05: analisis_magallanes, tipo_evento_final = "Blazar (Chorro relativista - Alta aceleración)", "blazar"
                                    else: analisis_magallanes, tipo_evento_final = "AGN / Cuásar (Acreción térmica - Lenta)", "agn"
                                else: analisis_magallanes, tipo_evento_final = "Variabilidad rutinaria", "descarte"
                            elif es_estrella_cat or (en_plano or veto_ia_cv):
                                if salto_luminosidad_delta > 0.5: analisis_magallanes, tipo_evento_final = "Variable Cataclísmica / Nova (Erupción activa)", "nova"
                                elif edad_dias < 3.0 and tasa_acel_reciente > 1.0: analisis_magallanes, tipo_evento_final = "Flare (Enana M)", "flare"
                                else: analisis_magallanes, tipo_evento_final = "Variabilidad rutinaria", "descarte"
                            elif clase_ia_final == "TDE":
                                if salto_luminosidad_delta > 0.5: analisis_magallanes, tipo_evento_final = "Disrupción de Marea (Agujero Negro activo)", "tde"
                                else: analisis_magallanes, tipo_evento_final = "Variabilidad rutinaria", "descarte"
                            else:
                                if edad_dias < 3.0 and tasa_acel_reciente > 1.0: analisis_magallanes, tipo_evento_final = "Flare (Enana M)", "flare"
                                elif salto_luminosidad_delta >= 0.5: analisis_magallanes, tipo_evento_final = "Candidata (Esperando confirmación TNS)", "supernova"
                                else: analisis_magallanes, tipo_evento_final = "Ruido / Artefacto", "descarte"

                            if tipo_evento_final == "descarte": continue

                            # =========================================================
                            # 🛡️ INTERCEPCIÓN DEL ESCUDO TNS (INTELIGENTE)
                            # =========================================================
                            prefijo_tns, nombre_oficial_tns = consultar_escudo_tns(str(oid))

                            if nombre_oficial_tns:
                                registrar_log(f"      [🛡️] ALERTA TNS: {oid} interceptado. Ya es {nombre_oficial_tns}.", log_file)
                                oid_para_laboratorio = nombre_oficial_tns

                                if prefijo_tns == "SN":
                                    survey_para_laboratorio = "TNS_GLOBAL"
                                    if tipo_evento_final in ["supernova", "descarte"]:
                                        tipo_evento_final = "supernova"
                                        registrar_log("      -> [!] TNS Confirma: Magallanes acata la clasificación IAU.", log_file)
                                    else:
                                        registrar_log(f"      -> [!] VETO ACTIVO: TNS dice SN, pero la física impone {tipo_evento_final.upper()}.", log_file)
                                elif prefijo_tns == "TDE":
                                    survey_para_laboratorio = "TNS_GLOBAL"
                                    tipo_evento_final = "tde"
                                    registrar_log("      -> [!] TNS Confirma TDE: Magallanes acata la clasificación IAU.", log_file)
                                else:
                                    survey_para_laboratorio = current_survey
                                    registrar_log(f"      -> [i] TNS Huérfano: Sin espectroscopía. Magallanes preserva su predicción: {tipo_evento_final}.", log_file)
                            else:
                                oid_para_laboratorio = str(oid)
                                survey_para_laboratorio = current_survey
                            # =========================================================

                            registrar_log(f"-> Procesando evento de interés: {oid_para_laboratorio} ({tipo_evento_final})", log_file)
                            graficar_curva(det, oid_para_laboratorio, survey_para_laboratorio, coordenadas.ra.deg, coordenadas.dec.deg, tipo_evento_final, es_vip)

                            texto_reporte = f"""
[5] CINÉTICA DE CURVA DE LUZ (EVALUACIÓN MAGALLANES)
    CLASE IA (ALeRCE)    : {clase_ia_final} (Confianza: {probabilidad*100:.1f}%)
    RECLASIFICACIÓN      : {analisis_magallanes}
    EDAD HISTÓRICA       : {edad_dias:.1f} días
    SALTO LUMINOSIDAD    : {salto_luminosidad_delta:.2f} magnitudes
    TASA ACEL. HISTÓRICA : {tasa_acel:.3f} mag/día
    TASA ACEL. RECIENTE  : {tasa_acel_reciente:.3f} mag/día
    RED DE ORIGEN        : {current_survey}
    MJD ÚLTIMA DETEC.    : {mjd_alerta_actual:.4f}
"""
                            datos_cineticos_para_filtro = {
                                "es_vip": es_vip,
                                "edad_dias": edad_dias,
                                "salto_luminosidad": salto_luminosidad_delta,
                                "tasa_acel_reciente": tasa_acel_reciente,
                                "escudo_tns_hit": nombre_oficial_tns,
                                "redshift_cazado": redshift_cazado
                            }

                            ejecutar_pipeline_magallanes(
                                coordenadas.ra.deg,
                                coordenadas.dec.deg,
                                oid_para_laboratorio,
                                tipo_evento_final,
                                distancia_real,
                                mjd_alerta_actual,
                                reporte_matematico=texto_reporte,
                                extra_datos_hunter=datos_cineticos_para_filtro
                            )

                            try:
                                catalogo_dict[str(oid_para_laboratorio)] = {
                                    "oid": str(oid_para_laboratorio),
                                    "ra": float(coordenadas.ra.deg),
                                    "dec": float(coordenadas.dec.deg),
                                    "tipo": tipo_evento_final,
                                    "survey": survey_para_laboratorio,
                                    "analisis": analisis_magallanes + (" [Interceptado por TNS]" if nombre_oficial_tns else ""),
                                    "vip": es_vip,
                                    "mjd_deteccion": float(mjd_alerta_actual),
                                    "img_url": f"data/curva_luz_{oid_para_laboratorio.replace(' ', '_')}.png" if os.path.exists(f"data/curva_luz_{oid_para_laboratorio.replace(' ', '_')}.png") else None
                                }
                            except Exception as e:
                                registrar_log(f"[!] Error al inyectar {oid_para_laboratorio} al catálogo JSON: {e}", log_file)
                        else:
                            signal.alarm(0)
                            # Descartado por IA <= 60% o categoría no objetivo: se registra para no volver a consultarlo
                            historial_vistos[oid] = mjd_fila

                    except TimeoutException:
                        signal.alarm(0)
                        print(f"      [!] Timeout: Servidor no respondió para {oid}. Omitiendo objeto por seguridad.")
                        registrar_log(f"Timeout: El objeto {oid} provocó un atasco de red y fue omitido.", log_file)
                    except Exception as e:
                        signal.alarm(0)
                        print(f"      [!] Error interno al analizar {oid}: {e}")

                # Guardado incremental del historial al cerrar cada paquete de 50
                guardar_historial_vistos(historial_vistos)

            registrar_log(f"[+] Patrullaje completado exitosamente en {current_survey}.", log_file)

        except Exception as e:
            print(f"   [!] Error en exploración TAP: {e}")
            registrar_log(f"Error TAP ADQL: {e}", log_file)

    guardar_catalogo_maestro(catalogo_dict)
    guardar_historial_vistos(historial_vistos)
    print("=== CATÁLOGO MAESTRO E HISTORIAL ACTUALIZADOS Y GUARDADOS ===")

    guardar_mjd_rastreo(mjd_inicio_patrullaje)
    print("=== PATRULLAJE COMPLETADO ===")

if __name__ == "__main__":
    main()
