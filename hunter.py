"""
=============================================================================
PROYECTO   : Observatorio Automatizado Estación Magallanes
MÓDULO     : hunter.py (El Cazador Multipropósito)
VERSIÓN    : 22.4 (RESTAURACIÓN SÓLIDA DEL NÚCLEO V22.1 + TDE NATIVO)
=============================================================================
"""

import os
import io
import time
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
# CONFIGURACIÓN DEL ENTORNO LOCAL
# =====================================================================
ARCHIVO_MJD = "tracker_mjd.txt"
ARCHIVO_BOLETIN = "boletin_tns.txt"
CATALOGO_JSON = "catalogo_maestro.json"

# NÚCLEO SANO RESTAURADO: Solo categorías maduras + TDE (Sin genéricos SN/AGN)
diccionario_categorias = {
    "ZTF": ["SNIa", "SNIbc", "SNII", "SLSN", "CV/Nova", "QSO", "Blazar", "TDE"],
    "LSST": ["SNIa", "SNIbc", "SNII", "SLSN", "Nova", "Mdwarf-flare", "TDE"]
}

for directorio in ["alertas", "data", "alertas_comunidad", "bitacoras"]:
    os.makedirs(directorio, exist_ok=True)

# =====================================================================
# FUNCIONES DE ALMACENAMIENTO LOCAL
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

# =====================================================================
# FUNCIONES DEL CATÁLOGO JSON LOCAL
# =====================================================================
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

# =====================================================================
# FUNCIONES DE SISTEMA Y ASTROMETRÍA
# =====================================================================
def obtener_mjd_rastreo():
    if not os.path.exists(ARCHIVO_MJD):
        return round(Time(datetime.now(timezone.utc) - timedelta(days=2)).mjd, 1)
    with open(ARCHIVO_MJD, 'r', encoding='utf-8') as f:
        return round(float(f.read().strip()), 1)

def guardar_mjd_rastreo(mjd):
    with open(ARCHIVO_MJD, 'w', encoding='utf-8') as f:
        f.write(str(round(float(mjd), 1)))

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
    try:
        custom_simbad = Simbad()
        custom_simbad.TIMEOUT = 25 
        custom_simbad.add_votable_fields('plx', 'sp', 'fe_h', 'otype')
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
            
            tipo_upper = str(tipo).upper()
            es_cuasar = any(x in tipo_upper for x in ["QSO", "AGN", "BLAZAR", "BLLAC", "SEYFERT"])
            es_estrella = any(x in tipo_upper for x in ["STAR", "FLARE", "CV", "NOVA", "WHITE DWARF", "V*"])
            es_galaxia = any(x in tipo_upper for x in ["GALAXY", "GLS", "LSB"])
            if any(x in tipo_upper for x in ["M DWARF", "DM", "FLARE STAR", "UV CETI"]): es_vip = True
    except Exception: pass

    if not es_cuasar and not es_estrella and not es_galaxia:
        try:
            v = Vizier(columns=['RA_ICRS', 'DE_ICRS', 'pmRA', 'pmDE', 'Plx', 'e_Plx'], catalog="I/355/gaiadr3")
            v.TIMEOUT = 45 
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
        except Exception: pass
        
    return nombre, distancia, tipo, metalicidad, es_cuasar, es_estrella, es_galaxia, es_vip

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
        if not banda_g.empty: ax1.errorbar(banda_g['fecha_humana'], banda_g['magpsf'], yerr=banda_g['sigmapsf'], fmt='o', color='#39ff14', alpha=0.6, markersize=5, label='Banda g')
        if not banda_r.empty: ax1.errorbar(banda_r['fecha_humana'], banda_r['magpsf'], yerr=banda_r['sigmapsf'], fmt='o', color='#ff3333', alpha=0.6, markersize=5, label='Banda r')
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
# RUTINA DE CAZA A DEMANDA: TNS (LECTURA DE BOLETÍN)
# =====================================================================
def consultar_tns_sur(client, catalogo_dict):
    log_file = "bitacoras/bitacora_TNS_GLOBAL.log"
    
    if not os.path.exists(ARCHIVO_BOLETIN):
        registrar_log("[!] No se encontró el archivo de boletín (boletin_tns.txt).", log_file)
        return
        
    with open(ARCHIVO_BOLETIN, 'r', encoding='utf-8') as f:
        contenido = f.read()
        
    lineas = contenido.split('\n')
    
    if len(lineas) <= 2:
        registrar_log("[-] El boletín está vacío o en reposo (Línea 3 vacía). Omitiendo búsqueda.", log_file)
        return
        
    texto_a_analizar = '\n'.join(lineas[2:])
    if not texto_a_analizar.strip():
        registrar_log("[-] No hay texto válido desde la línea 3. Omitiendo búsqueda.", log_file)
        return

    patron = r'\b202\d[a-zA-Z]{1,4}\b'
    extraccion = re.findall(patron, texto_a_analizar.lower())
    supernovas_a_buscar = list(set([obj.lower() for obj in extraccion]))
    
    if not supernovas_a_buscar:
        registrar_log("[-] No se encontraron códigos de supernovas válidos en el texto de la línea 3 en adelante.", log_file)
    else:
        registrar_log(f"[+] Boletín leído. Se encontraron {len(supernovas_a_buscar)} eventos para procesar: {supernovas_a_buscar}", log_file)
        
        TNS_BOT_ID = os.getenv("TNS_BOT_ID")
        TNS_API_KEY = os.getenv("TNS_API_KEY")
        headers = {'User-Agent': f'tns_marker{{"tns_id":{TNS_BOT_ID}, "type":"bot", "name":"Magallanes_Bot"}}'}
        
        for objname in supernovas_a_buscar:
            id_evento = f"SN {objname}"
            
            # Verificar si ya está en el catálogo maestro
            if id_evento in catalogo_dict:
                if catalogo_dict[id_evento].get("survey") == "TNS_GLOBAL":
                    registrar_log(f"[*] {id_evento} ya existe. Descargando datos para actualizar posible reclasificación...", log_file)
                    # Eliminamos el 'continue' para permitir que sobreescriba los datos con la info más fresca
                else:
                    registrar_log(f"[*] {id_evento} cazado previamente. ¡ASCENDIENDO a Confirmada TNS!", log_file)
                
            registrar_log(f"Descargando ficha técnica oficial para {id_evento}...", log_file)
            print(f"    [+] Procesando orden oficial de IAU: {id_evento}")
            
            try:
                resp_obj = requests.post('https://www.wis-tns.org/api/get/object', headers=headers, data={"api_key": TNS_API_KEY, "data": json.dumps({"objname": objname})}, timeout=25)
                
                if resp_obj.status_code == 200:
                    datos_obj = resp_obj.json().get('data', {}).get('reply', {})
                    if not datos_obj:
                        datos_obj = resp_obj.json().get('data', {})
                        
                    ra_float = float(datos_obj.get('radeg') or 0.0)
                    dec_float = float(datos_obj.get('decdeg') or 0.0)
                    redshift = datos_obj.get('redshift')
                    
                    obj_type_dict = datos_obj.get('object_type', {})
                    clasificacion = obj_type_dict.get('name', 'SUPERNOVA') if isinstance(obj_type_dict, dict) else 'SUPERNOVA'
                    
                    disc_dict = datos_obj.get('discovery_data_source', {})
                    descubridor = str(disc_dict.get('group_name', 'Desconocido')) if isinstance(disc_dict, dict) else 'Desconocido'
                    
                    rango_mpc, rango_mly = calcular_distancia_hubble(redshift)
                    
                    det = None
                    try:
                        if ra_float != 0.0 and dec_float != 0.0:
                            candidatos_alerce = client.query_objects(ra=ra_float, dec=dec_float, radius=5, page_size=1)
                            if candidatos_alerce:
                                oid_tns = candidatos_alerce[0]['oid']
                                oid_tns = oid_tns.decode('utf-8') if isinstance(oid_tns, bytes) else oid_tns
                                det = client.query_detections(oid=oid_tns, format='pandas')
                    except Exception: pass
                    
                    try:
                        graficar_curva(det, id_evento, descubridor, ra_float, dec_float)
                    except Exception: pass
                        
                    url_tns = f"https://www.wis-tns.org/object/{objname}"
                    
                    texto_tns = f"""======================================================================
[REGISTRO OFICIAL TNS] - EVENTO CONFIRMADO
======================================================================
ID de Evento          : {id_evento}
Clasificación Oficial : {clasificacion}
Red de Descubrimiento : {descubridor}
Coordenadas (ICRS)    : RA {ra_float:.5f} | Dec {dec_float:.5f}

[CÁLCULO DE DISTANCIA (Basado en z = {redshift})]
{rango_mpc}
{rango_mly}

======================================================================
🔗 ENLACE OFICIAL DEL TRANSIENT NAME SERVER:
{url_tns}
======================================================================
* NOTA: Este evento ya está confirmado por la IAU. No se requiere 
  emisión de telegramas ni seguimiento de validación por parte 
  de la Estación Magallanes.
======================================================================"""
                    
                    ruta_txt = f"alertas/CIRCULAR_{id_evento.replace(' ', '_')}.txt"
                    guardar_archivo_texto(ruta_txt, texto_tns)
                    
                    mjd_obs = det['mjd'].max() if det is not None and not det.empty else Time(datetime.utcnow()).mjd

                    try:
                        # CLASIFICACIÓN INTELIGENTE TNS (TDE vs NOVA vs SN)
                        clase_upper = clasificacion.upper()
                        if "TDE" in clase_upper: tipo_evento_tns = "tde"
                        elif "CV" in clase_upper or "NOVA" in clase_upper: tipo_evento_tns = "nova"
                        else: tipo_evento_tns = "supernova"

                        catalogo_dict[id_evento] = {
                            "oid": id_evento,
                            "ra": float(ra_float),
                            "dec": float(dec_float),
                            "tipo": tipo_evento_tns,
                            "survey": "TNS_GLOBAL",
                            "analisis": clasificacion,
                            "vip": False,
                            "mjd_deteccion": float(mjd_obs),
                            "img_url": f"data/curva_luz_{id_evento.replace(' ', '_')}.png" if os.path.exists(f"data/curva_luz_{id_evento.replace(' ', '_')}.png") else None
                        }
                    except Exception as e:
                        registrar_log(f"[!] Error al inyectar {id_evento} al catálogo JSON: {e}", log_file)
                else: 
                    registrar_log(f"[!] Error interno de TNS al pedir objeto {id_evento}: HTTP {resp_obj.status_code}", log_file)
            except Exception as e: 
                registrar_log(f"[!] Excepción al pedir objeto {id_evento}: {e}", log_file)
                
            time.sleep(2.5)

    with open(ARCHIVO_BOLETIN, "w", encoding="utf-8") as f:
        f.write("Listado de confirmaciones oficiales TNS\n\n")
    registrar_log("[+] Procesamiento TNS finalizado. Archivo de boletín purgado desde la línea 3.", log_file)

# =====================================================================
# BUCLE PRINCIPAL (MAIN)
# =====================================================================
def main():
    print("=== INICIANDO CAZADOR MULTIPROPÓSITO (VERSIÓN 22.4 - NÚCLEO V22.1 + TDE NATIVO) ===")
    client = Alerce()
    mjd_reciente = obtener_mjd_rastreo()
    url_tap = "https://tap.alerce.online/tap"
    servicio_tap = vo.dal.TAPService(url_tap)
    
    catalogo_dict = cargar_catalogo_maestro()
    
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
        limite_mjd = mjd_reciente - 0.2
        
        if current_survey == "ZTF":
            consulta_adql = f"""
            SELECT TOP 1500 oid, meanra, meandec, firstmjd, lastmjd
            FROM ztf.object
            WHERE lastmjd >= {limite_mjd}
            ORDER BY lastmjd DESC
            """
        else: 
            consulta_adql = f"""
            SELECT TOP 1500 
                oid, 
                ra AS meanra, 
                dec AS meandec, 
                firstdiasourcemjdtai AS firstmjd, 
                lastdiasourcemjdtai AS lastmjd
            FROM alerce_tap.lsst_dia_object
            WHERE lastdiasourcemjdtai >= {limite_mjd}
            ORDER BY lastdiasourcemjdtai DESC
            """
        
        try:
            print(f"   Extrayendo catálogo masivo de {current_survey} vía TAP ADQL...")
            resultados = servicio_tap.search(consulta_adql)
            candidatos = resultados.to_table().to_pandas()
            
            if candidatos.empty:
                print(f"   (0 candidatos encontrados desde MJD {limite_mjd})")
                continue
                
            print(f"   ({len(candidatos)} objetos capturados. Iniciando análisis por paquetes de a 50 para proteger RAM...)")
            
            tamano_paquete = 50
            for i in range(0, len(candidatos), tamano_paquete):
                paquete = candidatos.iloc[i:i+tamano_paquete]
                print(f"   [Paquete {(i//tamano_paquete) + 1}/{(len(candidatos)//tamano_paquete) + 1}] Procesando lote de {len(paquete)} objetos...")
                
                for index, fila in paquete.iterrows():
                    oid = fila['oid'].decode('utf-8') if isinstance(fila['oid'], bytes) else fila['oid']
                    
                    try:
                        probs = client.query_probabilities(oid=oid, format='pandas')
                        if probs.empty: continue
                            
                        mejor_prediccion = probs.loc[probs['probability'].idxmax()]
                        clase_ia_final, probabilidad = mejor_prediccion['class_name'], mejor_prediccion['probability']
                        
                        if clase_ia_final in target_classes and probabilidad > 0.60:
                            print(f"      [!] ALERTA AISLADA: {oid} | IA: {clase_ia_final} ({probabilidad*100:.1f}%)")
                            det = client.query_detections(oid=oid, format='pandas')
                            det = det.dropna(subset=['magpsf', 'mjd'])
                            if det.empty or len(det) < 2: continue 
                                
                            coordenadas = SkyCoord(ra=fila['meanra']*u.degree, dec=fila['meandec']*u.degree, frame='icrs')
                            mjd_alerta_actual = det['mjd'].max()
                            
                            nombre_real, distancia_real, tipo_real, metalicidad_real, es_cuasar_cat, es_estrella_cat, es_galaxia_cat, es_vip = obtener_datos_astronomicos(coordenadas, mjd_alerta_actual)

                            mjd_min, mjd_max = det['mjd'].min(), det['mjd'].max()
                            edad_dias, amplitud_mag = mjd_max - mjd_min, det['magpsf'].max() - det['magpsf'].min()
                            dias_al_pico = det.loc[det['magpsf'].idxmin(), 'mjd'] - mjd_min
                            if dias_al_pico <= 0: dias_al_pico = 1.0
                            tasa_acel = amplitud_mag / dias_al_pico 

                            latitud_b, en_plano, es_viejo = coordenadas.galactic.b.degree, abs(coordenadas.galactic.b.degree) <= 10.0, edad_dias > 400

                            salto_luminosidad_delta = amplitud_mag
                            tasa_acel_reciente = tasa_acel
                            
                            if edad_dias > 30:
                                recientes, antiguas = det[det['mjd'] >= mjd_max - 30], det[det['mjd'] < mjd_max - 30]
                                if not recientes.empty and not antiguas.empty: 
                                    salto_luminosidad_delta = antiguas['magpsf'].median() - recientes['magpsf'].min()
                                    mjd_pico_reciente = recientes.loc[recientes['magpsf'].idxmin(), 'mjd']
                                    mjd_inicio_reciente = recientes['mjd'].min()
                                    dias_al_pico_rec = mjd_pico_reciente - mjd_inicio_reciente
                                    if dias_al_pico_rec <= 0: dias_al_pico_rec = 1.0 
                                    if salto_luminosidad_delta > 0:
                                        tasa_acel_reciente = salto_luminosidad_delta / dias_al_pico_rec
                                    else:
                                        tasa_acel_reciente = 0.0

                            veto_ia_cv = ("CV" in clase_ia_final.upper() or "NOVA" in clase_ia_final.upper()) and probabilidad > 0.90
                            analisis_magallanes, tipo_evento_final = "DESCONOCIDO", "descarte"

                            # --- CLASIFICACIÓN FÍSICA BASADA EN TASA RECIENTE (V22.1 RESTAURADA + TDE) ---
                            if es_cuasar_cat or (es_viejo and not en_plano and not veto_ia_cv and not es_estrella_cat):
                                if salto_luminosidad_delta > 0.5:
                                    if tasa_acel_reciente > 0.05: analisis_magallanes, tipo_evento_final = "Blazar (Chorro relativista - Alta aceleración)", "blazar"
                                    else: analisis_magallanes, tipo_evento_final = "AGN / Cuásar (Acreción térmica - Lenta)", "agn"
                                else: analisis_magallanes, tipo_evento_final = "Variabilidad rutinaria", "descarte"
                            elif es_estrella_cat or (en_plano or veto_ia_cv):
                                if salto_luminosidad_delta > 0.5: analisis_magallanes, tipo_evento_final = "Variable Cataclísmica / Nova (Erupción activa)", "nova"
                                elif edad_dias < 3.0 and tasa_acel_reciente > 1.0: analisis_magallanes, tipo_evento_final = "Flare (Enana M)", "flare"
                                else: analisis_magallanes, tipo_evento_final = "Variabilidad rutinaria", "descarte"
                            
                            # ---> INSERCIÓN QUIRÚRGICA: FILTRO EXCLUSIVO PARA TDE <---
                            elif clase_ia_final == "TDE":
                                if salto_luminosidad_delta > 0.5: analisis_magallanes, tipo_evento_final = "Disrupción de Marea (Agujero Negro activo)", "tde"
                                else: analisis_magallanes, tipo_evento_final = "Variabilidad rutinaria", "descarte"
                            # ---------------------------------------------------------
                            
                            else:
                                if edad_dias < 3.0 and tasa_acel_reciente > 1.0: analisis_magallanes, tipo_evento_final = "Flare (Enana M)", "flare"
                                elif salto_luminosidad_delta >= 0.5: analisis_magallanes, tipo_evento_final = "Candidata (Esperando confirmación TNS)", "supernova"
                                else: analisis_magallanes, tipo_evento_final = "Ruido / Artefacto", "descarte"

                            if tipo_evento_final == "descarte": continue 
                            
                            registrar_log(f"-> Procesando evento de interés: {oid} ({tipo_evento_final})", log_file)
                            graficar_curva(det, str(oid), current_survey, coordenadas.ra.deg, coordenadas.dec.deg, tipo_evento_final, es_vip)

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
                                "salto_luminosidad": salto_luminosidad_delta
                            }

                            ejecutar_pipeline_magallanes(
                                coordenadas.ra.deg, 
                                coordenadas.dec.deg, 
                                oid, 
                                tipo_evento_final, 
                                distancia_real, 
                                mjd_alerta_actual,
                                reporte_matematico=texto_reporte,
                                extra_datos_hunter=datos_cineticos_para_filtro
                            )
                            
                            try:
                                catalogo_dict[str(oid)] = {
                                    "oid": str(oid),
                                    "ra": float(coordenadas.ra.deg),
                                    "dec": float(coordenadas.dec.deg),
                                    "tipo": tipo_evento_final,
                                    "survey": current_survey,
                                    "analisis": analisis_magallanes,
                                    "vip": es_vip,
                                    "mjd_deteccion": float(mjd_alerta_actual),
                                    "img_url": f"data/curva_luz_{oid}.png" if os.path.exists(f"data/curva_luz_{oid}.png") else None
                                }
                            except Exception as e:
                                registrar_log(f"[!] Error al inyectar {oid} al catálogo JSON: {e}", log_file)

                    except Exception as e: pass 
        except Exception as e:
            print(f"   [!] Error en exploración TAP: {e}")
            registrar_log(f"Error TAP ADQL: {e}", log_file)

    guardar_catalogo_maestro(catalogo_dict)
    print("=== CATÁLOGO MAESTRO ACTUALIZADO Y GUARDADO ===")

    nuevo_mjd = Time(datetime.utcnow()).mjd
    guardar_mjd_rastreo(nuevo_mjd)
    print("=== PATRULLAJE COMPLETADO ===")

if __name__ == "__main__":
    main()
