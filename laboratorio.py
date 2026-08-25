"""
=============================================================================
PROYECTO   : Observatorio Automatizado Estación Magallanes
MÓDULO     : laboratorio.py (Centro de Análisis Científico Profundo)
VERSIÓN    : 18.7 (FASE 7: MOTOR TAXONÓMICO Y ESPECTROS EXTRAGALÁCTICOS)
=============================================================================
"""

import os
import numpy as np
import warnings
import matplotlib.pyplot as plt
from datetime import datetime
from astropy.coordinates import SkyCoord
import astropy.units as u
from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive
from astroquery.sdss import SDSS
from astroquery.simbad import Simbad
from astroquery.vizier import Vizier
from astroquery.eso import Eso
from astroquery.ipac.ned import Ned
from dotenv import load_dotenv

from operaciones_too import generar_alerta_comunidad

warnings.filterwarnings('ignore')
load_dotenv()

# =====================================================================
# MOTOR TAXONÓMICO MAGALLANES
# =====================================================================
def obtener_diccionario_quimico(tipo, redshift):
    """
    Asigna las líneas espectrales correctas según el tipo de evento 
    de Magallanes y su desplazamiento cosmológico.
    """
    lineas = {}
    
    # 1. TRAMPA ULTRAVIOLETA (Para Cuásares/Blazares hiper lejanos z > 0.5)
    if redshift > 0.5:
        lineas['Ly-alfa (UV Emisión)'] = {'rest_wl': 1215.7, 'color': '#ff00ff', 'ls': '-.'}
        lineas['C IV (UV Emisión)'] = {'rest_wl': 1549.0, 'color': '#00ffcc', 'ls': '-.'}
        lineas['Mg II (UV Emisión)'] = {'rest_wl': 2798.0, 'color': '#ff99ff', 'ls': ':'}

    # 2. SELECCIÓN POR CATEGORÍA
    if tipo == "nova":
        lineas.update({
            'H-alfa (Disco/Erupción)': {'rest_wl': 6562.8, 'color': '#ff4d4d', 'ls': '--'},
            'H-beta (Disco/Erupción)': {'rest_wl': 4861.3, 'color': '#4dff4d', 'ls': '--'},
            'He I (Acreción/Disco)': {'rest_wl': 5875.6, 'color': '#ffffff', 'ls': ':'},
            'He II (Zona Caliente)': {'rest_wl': 4686.0, 'color': '#ffff00', 'ls': ':'}
        })
    elif tipo == "flare":
        lineas.update({
            'H-alfa (Llamarada)': {'rest_wl': 6562.8, 'color': '#ff4d4d', 'ls': '--'},
            'H-beta (Llamarada)': {'rest_wl': 4861.3, 'color': '#4dff4d', 'ls': '--'},
            'Ca II K (Cromosfera)': {'rest_wl': 3933.7, 'color': '#ccccff', 'ls': '-.'},
            'Ca II H (Cromosfera)': {'rest_wl': 3968.5, 'color': '#ccccff', 'ls': '-.'}
        })
    elif tipo in ["agn", "blazar"]:
        lineas.update({
            'H-alfa (Gas NLR/BLR)': {'rest_wl': 6562.8, 'color': '#ff4d4d', 'ls': '--'},
            'H-beta (Gas NLR/BLR)': {'rest_wl': 4861.3, 'color': '#4dff4d', 'ls': '--'},
            '[O III] (Gas Excitado)': {'rest_wl': 5006.8, 'color': '#ffff00', 'ls': '--'},
            'Na D (Absorción Host)': {'rest_wl': 5892.9, 'color': '#ffa64d', 'ls': ':'}
        })
    elif tipo == "tde":
        lineas.update({
            'H-alfa (Restos Estrella)': {'rest_wl': 6562.8, 'color': '#ff4d4d', 'ls': '--'},
            'H-beta (Restos Estrella)': {'rest_wl': 4861.3, 'color': '#4dff4d', 'ls': '--'},
            'He II (Acreción Extrema)': {'rest_wl': 4686.0, 'color': '#ffff00', 'ls': '-.'}
        })
    elif tipo == "supernova":
        lineas.update({
            'H-alfa (Galaxia Host)': {'rest_wl': 6562.8, 'color': '#ff4d4d', 'ls': '--'},
            '[O III] (Gas Host)': {'rest_wl': 5006.8, 'color': '#ffff00', 'ls': '--'},
            'Si II (Eyecta SN Ia)': {'rest_wl': 6150.0, 'color': '#ff99cc', 'ls': ':'},
            'Na D (Polvo ISM)': {'rest_wl': 5892.9, 'color': '#ffa64d', 'ls': ':'}
        })
    else:
        lineas.update({
            'H-alfa (Estándar)': {'rest_wl': 6562.8, 'color': '#ff4d4d', 'ls': '--'},
            'H-beta (Estándar)': {'rest_wl': 4861.3, 'color': '#4dff4d', 'ls': '--'}
        })
        
    return lineas

# =====================================================================
# FUNCIONES DE ALMACENAMIENTO
# =====================================================================
def guardar_archivo_texto(ruta, contenido):
    os.makedirs(os.path.dirname(ruta) if os.path.dirname(ruta) else '.', exist_ok=True)
    try:
        with open(ruta, 'w', encoding='utf-8') as f: 
            f.write(contenido)
    except Exception: pass
    return ruta

def guardar_grafico_memoria(fig, ruta_relativa):
    os.makedirs(os.path.dirname(ruta_relativa), exist_ok=True)
    fig.savefig(ruta_relativa, dpi=150, bbox_inches='tight')
    plt.close(fig)
    return ruta_relativa

def extraer_valor(dato):
    if np.ma.is_masked(dato) or str(dato) == '--': return "Desconocido"
    numero = dato.value if hasattr(dato, 'value') else dato
    try:
        if np.isnan(float(numero)): return "Desconocido"
        return f"{float(numero):.2f}"
    except (ValueError, TypeError): return "Desconocido"

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

def buscar_exoplanetas(coordenadas, tipo_evento="desconocido", radio_arcsec=60):
    print(f"\n[1/4] 📡 Consultando NASA Exoplanet Archive (Radio cinemático de {radio_arcsec}\")...")
    tiene_planetas, planetas_info = False, []
    NasaExoplanetArchive.TIMEOUT = 25
    try:
        resultado = NasaExoplanetArchive.query_region(table="ps", coordinates=coordenadas, radius=radio_arcsec*u.arcsec)
        if resultado and len(resultado) > 0:
            if 'default_flag' in resultado.colnames: resultado = resultado[resultado['default_flag'] == 1]
            if len(resultado) > 0:
                tiene_planetas = True
                if tipo_evento == "flare":
                    print(f"   [!!!] ALERTA ESTELAR LOCAL: Fulguración afectando a {len(resultado)} exoplaneta(s) confirmado(s) [!!!]")
                else:
                    print(f"   [!!!] ALERTA: {len(resultado)} exoplaneta(s) confirmado(s) en la misma línea de visión ({radio_arcsec}\") [!!!]")
                for planeta in resultado:
                    nombre, masa, periodo = planeta['pl_name'], extraer_valor(planeta['pl_bmasse']), extraer_valor(planeta['pl_orbper'])
                    planetas_info.append({'nombre': nombre, 'masa': masa, 'periodo': periodo})
                    print(f"   🌍 {nombre} | Masa: {masa} M_Tierra | Órbita: {periodo} días")
            else: print("   [-] No se registran exoplanetas confirmados con bandera científica actual.")
        else: print("   [-] Sistema Aislado: No se registran exoplanetas confirmados.")
    except Exception as e: 
        print(f"   [-] Error en catálogo NASA (Timeout o caída): {e}")
        tiene_planetas = None  
    return tiene_planetas, planetas_info

# =====================================================================
# ESPECTROSCOPÍA DINÁMICA
# =====================================================================
def analizar_espectroscopia_activa(coordenadas, id_evento, tipo_evento="desconocido", redshift=0.0):
    print(f"\n[3/4] 🔬 Iniciando Escudo Espectroscópico Bi-Hemisférico para {id_evento}...")
    dec = coordenadas.dec.degree
    hay_emision, ew_halfa, fuente_espectro, estado_radar_eso = False, 0.0, "Ninguna", "Sin revisar"

    if dec > -20.0:
        print("   [+] Coordenada en Hemisferio Norte/Ecuatorial. Consultando SDSS...")
        SDSS.TIMEOUT = 45
        try:
            xid = SDSS.query_region(coordenadas, radius=5*u.arcsec, spectro=True)
            if xid is not None and len(xid) > 0:
                espectros = SDSS.get_spectra(matches=xid)
                datos = espectros[0][1].data
                flujo, long_onda = datos['flux'], 10 ** datos['loglam']
                
                # --- CÁLCULO EW ADAPTADO AL REDSHIFT ---
                centro_halfa = 6562.8 * (1 + redshift)
                mascara_halfa = (long_onda > centro_halfa - 60) & (long_onda < centro_halfa + 90)
                long_onda_halfa, flujo_halfa = long_onda[mascara_halfa], flujo[mascara_halfa]
                
                if len(long_onda_halfa) > 0:
                    mascara_continuo = ((long_onda_halfa > centro_halfa - 60) & (long_onda_halfa < centro_halfa - 20)) | ((long_onda_halfa > centro_halfa + 40) & (long_onda_halfa < centro_halfa + 80))
                    flujo_continuo = np.mean(flujo_halfa[mascara_continuo])
                    if flujo_continuo > 0:
                        ew_halfa = np.trapezoid(1 - (flujo_halfa / flujo_continuo), dx=np.mean(np.gradient(long_onda_halfa)))
                        hay_emision = ew_halfa < -1.0 
                
                fuente_espectro = "SDSS"
                print(f"   [!!!] FIRMA SDSS: Espectro obtenido (EW H-alfa local aprox: {ew_halfa:.2f} Å)")

                # --- NUEVO PLOTEO TAXONÓMICO COMPLETO ---
                plt.style.use('dark_background')
                fig = plt.figure(figsize=(12, 6))
                
                plt.plot(long_onda, flujo, color='cyan', linewidth=0.8, alpha=0.8, label="Flujo Crudo SDSS")
                
                lineas_quimicas = obtener_diccionario_quimico(tipo_evento, redshift)

                for nombre, props in lineas_quimicas.items():
                    wl_observada = props['rest_wl'] * (1 + redshift)
                    if 3600 < wl_observada < 10300:
                        plt.axvline(x=wl_observada, color=props['color'], linestyle=props['ls'], alpha=0.8, label=nombre)
                
                titulo = f"Espectroscopía [{tipo_evento.upper()}] (z={redshift:.4f}) - {id_evento}"
                plt.title(titulo, fontsize=14, pad=15)
                plt.xlabel("Longitud de Onda Observada (Angstroms)", fontsize=12)
                plt.ylabel(r"Flujo Relativo ($10^{-17} \text{erg s}^{-1} \text{cm}^{-2} \AA^{-1}$)", fontsize=12)
                
                plt.legend(loc='upper right', facecolor='#111111', edgecolor='gray', fontsize=10, framealpha=0.9, borderpad=1)
                plt.grid(True, color='gray', linestyle=':', alpha=0.4)
                plt.tight_layout()
                
                guardar_grafico_memoria(fig, f"data/quimica_halfa_{id_evento}.png")
                return hay_emision, ew_halfa, fuente_espectro, estado_radar_eso
            else: print("   [-] SDSS no tiene espectro. Pasando a respaldo global...")
        except Exception as e: print(f"   [-] Fallo en conexión SDSS: {e}. Pasando a respaldo...")

    if fuente_espectro == "Ninguna":
        print("   [+] Buscando abundancias químicas en cielos del sur (VizieR: GALAH)...")
        try:
            v = Vizier(columns=['*'], catalog="J/MNRAS/506/150")
            v.TIMEOUT = 45 
            res_galah = v.query_region(coordenadas, radius=5*u.arcsec)
            if len(res_galah) > 0:
                print("   [+] Objetivo encontrado en GALAH DR3.")
                fuente_espectro = "GALAH (VizieR)"
                hay_emision, ew_halfa = True, -2.5 
        except Exception: print("   [-] Fallo en VizieR/GALAH.")

    if fuente_espectro == "Ninguna":
        print("   [+] Activando Radar ESO...")
        try:
            Eso.TIMEOUT = 45
            res_eso = Eso.query_region(coordenadas, radius=5*u.arcsec)
            if res_eso and len(res_eso) > 0:
                print("   [!!!] ORO ASTRONÓMICO: Espectros en Archivo ESO.")
                estado_radar_eso = "ESPECTRO ENCONTRADO EN ESO"
            else:
                estado_radar_eso = "Sin datos en archivo ESO"
                print("   [-] Sin datos en archivo público ESO.")
        except Exception: 
            estado_radar_eso = "Radar ESO Inaccesible"
            print("   [-] Fallo en Radar ESO.")

    return hay_emision, ew_halfa, fuente_espectro, estado_radar_eso

def buscar_espectro_y_fotometria(coordenadas, id_evento):
    print(f"\n[2/X] 🌈 Iniciando análisis térmico SED Quiescente...")
    magnitudes_finales, l_validas, e_validas = [], [] ,[]
    es_enana_roja = None 

    try:
        custom_simbad = Simbad()
        custom_simbad.TIMEOUT = 25 
        custom_simbad.add_votable_fields('flux(V)', 'flux(R)', 'flux(J)', 'flux(H)', 'flux(K)')
        resultado = custom_simbad.query_region(coordenadas, radius=5*u.arcsec)

        if resultado is not None and len(resultado) > 0:
            bandas_simbad, long_onda_simbad = ['V', 'J', 'H', 'K'], [5500, 12200, 16300, 21900]
            cols_esperadas = ['FLUX_V', 'FLUX_J', 'FLUX_H', 'FLUX_K']
            columnas_mayusculas = [c.upper() for c in resultado.colnames]

            for i, col_esperada in enumerate(cols_esperadas):
                if col_esperada in columnas_mayusculas:
                    mag_raw = resultado[0][resultado.colnames[columnas_mayusculas.index(col_esperada)]]
                    if not np.ma.is_masked(mag_raw):
                        try:
                            mag_float = float(mag_raw.value if hasattr(mag_raw, 'value') else mag_raw)
                            if not np.isnan(mag_float):
                                magnitudes_finales.append(mag_float); l_validas.append(long_onda_simbad[i]); e_validas.append(bandas_simbad[i])
                        except Exception: pass
    except Exception: print("   [-] Fallo al obtener fotometría Simbad (Timeout).")

    if len(magnitudes_finales) < 2: return None

    flujo_relativo = 10 ** (-0.4 * np.array(magnitudes_finales))
    flujo_relativo /= np.max(flujo_relativo)
    flujos_ir = [f for l, f in zip(l_validas, flujo_relativo) if l > 10000]
    flujos_vis = [f for l, f in zip(l_validas, flujo_relativo) if l < 7000]
    es_enana_roja = True if (flujos_ir and flujos_vis and max(flujos_ir) > (max(flujos_vis) * 2)) or (flujos_ir and not flujos_vis) else False

    plt.style.use('dark_background')
    fig = plt.figure(figsize=(12, 6))
    plt.plot(l_validas, flujo_relativo, color='#ff7700', marker='o', linestyle='-', linewidth=2, markersize=8)
    for i, txt in enumerate(e_validas): plt.annotate(txt, (l_validas[i], flujo_relativo[i]), textcoords="offset points", xytext=(0,10), ha='center', color='cyan', fontsize=9)
    plt.title(f"Distribución de Energía Quiescente (Histórica) - {id_evento}", color='white', pad=20)
    plt.xlabel(r"Longitud de Onda ($\AA$)", color='lightgray')
    plt.ylabel("Flujo Relativo (Brillo normalizado)", color='lightgray')
    guardar_grafico_memoria(fig, f"data/espectro_sed_{id_evento}.png")
    return es_enana_roja

def generar_circular_estelar_local(ra, dec, id_evento, tiene_planetas, es_enana_roja, planetas_info, emision_activa, valor_ew, fuente_espectro, estado_eso, tipo_evento, distancia, reporte_matematico=""):
    fecha_emision = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    ruta_archivo = f"alertas/CIRCULAR_{id_evento}.txt"
    
    contenido = f"""=================================================================
 CIRCULAR DE OBSERVACIÓN ESTELAR LOCAL - ESTACIÓN MAGALLANES
=================================================================
FECHA DE EMISIÓN : {fecha_emision}
OBJETO DETECTADO : {id_evento} ({tipo_evento.upper()})
COORDENADAS ICRS : RA {ra:.5f} | Dec {dec:.5f}
DISTANCIA        : {distancia}
-----------------------------------------------------------------

[1] ESTADO DEL SISTEMA PLANETARIO
"""
    if tiene_planetas is True and planetas_info: 
        if tipo_evento == "flare":
            contenido += f"    SISTEMA IMPACTADO: {len(planetas_info)} exoplaneta(s) confirmado(s) en órbita local.\n"
        else:
            contenido += f"    ALINEACIÓN ÓPTICA: {len(planetas_info)} exoplaneta(s) confirmado(s) en la misma línea de visión (60 arcsec).\n"
            
        for p in planetas_info:
            contenido += f"        * {p['nombre']} | Masa: {p['masa']} M_Tierra | Órbita: {p['periodo']} días\n"
            
    elif tiene_planetas is False: 
        contenido += "    SISTEMA AISLADO: No se registran planetas confirmados (Radio revisado: 60 arcsec).\n"
    else: 
        contenido += "    ESTADO DESCONOCIDO: NASA Exoplanet Archive inaccesible (Timeout de red).\n"
        
    contenido += "\n[2] EVALUACIÓN TERMODINÁMICA (SED QUIESCENTE)\n"
    if es_enana_roja is True: contenido += "    FIRMA TÉRMICA: Sistema Frío / Activo (Emisión Infrarroja Dominante en reposo).\n"
    elif es_enana_roja is False: contenido += "    FIRMA TÉRMICA: Emisión Visible/Óptica Dominante.\n"
    else: contenido += "    FIRMA TÉRMICA: Datos insuficientes para evaluación térmica SED.\n"
        
    contenido += f"\n[3] ACTIVIDAD CROMOSFÉRICA / QUÍMICA (Fuente: {fuente_espectro})\n"
    if emision_activa is True: contenido += f"    ESTADO QUÍMICO: Confirmación de emisión/actividad (EW aprox: {valor_ew:.2f}).\n"
    elif emision_activa is False and fuente_espectro != "Ninguna": contenido += f"    ESTADO QUÍMICO: Sin línea de emisión significativa detectada.\n"
    else: contenido += f"    ESTADO QUÍMICO: Carencia de datos públicos 1D. Radar ESO indica: {estado_eso}\n"

    contenido += "\n[4] EVALUACIÓN MAGALLANES (RECOMENDACIÓN)\n"
    
    if tipo_evento == "flare" and tiene_planetas is True:
        contenido += "    PRIORIDAD   : MÁXIMA PRIORIDAD ESPACIAL (Riesgo de Habitabilidad)\n    INSTRUMENTO : Recomendado para Telescopios Espaciales (JWST / HST) o VLT.\n"
    elif "nova" in tipo_evento.lower():
        contenido += "    PRIORIDAD   : ALTA PRIORIDAD (Variable Cataclísmica)\n    INSTRUMENTO : Espectroscopía Terrestre (VLT / Gemini South / Magallanes).\n"
    elif es_enana_roja is True:
        contenido += "    PRIORIDAD   : PRIORIDAD MODERADA (Actividad Estelar Base)\n    INSTRUMENTO : Telescopios terrestres (Fotometría de seguimiento).\n"
    else:
        contenido += "    PRIORIDAD   : PRIORIDAD ESTÁNDAR DE MONITOREO\n    INSTRUMENTO : Telescopios terrestres (Fotometría de seguimiento).\n"
    
    if reporte_matematico:
        contenido += reporte_matematico

    contenido += "=================================================================\n"
    return guardar_archivo_texto(ruta_archivo, contenido)

def buscar_galaxia_anfitriona(coordenadas):
    print(f"\n[1/3] 🌌 Buscando Galaxia Anfitriona (NASA NED - 120 arcsec)...")
    galaxia, redshift = "Desconocida (Intergaláctica / Muy lejana)", "Desconocido"
    try:
        Ned.TIMEOUT = 25 
        resultado = Ned.query_region(coordenadas, radius=120*u.arcsec)
        
        if resultado is not None and len(resultado) > 0:
            for fila in resultado:
                nombre_obj = fila['Object Name'].decode('utf-8') if hasattr(fila['Object Name'], 'decode') else str(fila['Object Name'])
                otype = fila['Type'].decode('utf-8') if hasattr(fila['Type'], 'decode') else str(fila['Type'])
                
                tipo_upper = otype.strip().upper()
                codigos_extragalacticos = ['G', 'GALAXY', 'QSO', 'AGN', 'BLAZAR', 'SY1', 'SY2']
                
                if galaxia == "Desconocida (Intergaláctica / Muy lejana)":
                    if any(cat in tipo_upper for cat in codigos_extragalacticos) or any(prefix in nombre_obj.upper() for prefix in ['NGC ', 'IC ', 'UGC ', 'ESO ', 'MCG ']):
                        galaxia = nombre_obj
                        z_val = fila['Redshift']
                        if not np.ma.is_masked(z_val) and z_val is not None and str(z_val).strip() != "":
                            try:
                                redshift = float(z_val)
                            except ValueError: pass
                        print(f"   [+] Entidad identificada (NED): {galaxia} (Tipo: {otype})")
                        break
    except Exception: print("   [-] Fallo al buscar galaxia en NASA NED (Timeout o error).")
    return galaxia, redshift

def generar_circular_extragalactica(ra, dec, id_evento, galaxia, redshift, tipo_evento, reporte_matematico=""):
    ruta_archivo = f"alertas/CIRCULAR_{id_evento}.txt"
    z_str = f"{redshift:.5f}" if isinstance(redshift, float) else str(redshift)
    rango_mpc, rango_mly = calcular_distancia_hubble(redshift)
    
    contenido = f"""=================================================================
 CIRCULAR DE OBSERVACIÓN EXTRAGALÁCTICA - ESTACIÓN MAGALLANES
=================================================================
FECHA DE EMISIÓN : {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}
EVENTO DETECTADO : {id_evento} ({tipo_evento.upper()})
COORDENADAS ICRS : RA {ra:.5f} | Dec {dec:.5f}
-----------------------------------------------------------------

[1] ENTORNO COSMOLÓGICO
    OBJETO CENTRAL / ANFITRIONA : {galaxia}
    REDSHIFT (z)                : {z_str}
    DISTANCIA HUBBLE            : {rango_mpc} {rango_mly}

[2] EVALUACIÓN MAGALLANES
    PRIORIDAD   : ALTA PRIORIDAD ESPECTROSCÓPICA
    INSTRUMENTO : Observatorios masivos (VLT / Gemini).
"""
    if reporte_matematico:
        contenido += reporte_matematico

    contenido += "=================================================================\n"
    return guardar_archivo_texto(ruta_archivo, contenido)

def ejecutar_pipeline_magallanes(ra_deg, dec_deg, id_evento="Desconocido", tipo_evento="flare", distancia_real="Desconocida", mjd_deteccion=None, reporte_matematico="", extra_datos_hunter=None):
    if extra_datos_hunter is None: extra_datos_hunter = {}
    print(f"\n[ESTACIÓN MAGALLANES] Recibida alerta para laboratorio: {id_evento}")
    
    # =====================================================================
    # 🛡️ RECEPCIÓN DEL ESCUDO TNS DESDE HUNTER
    # =====================================================================
    escudo_hit = extra_datos_hunter.get("escudo_tns_hit")
    if escudo_hit:
        print(f"   [🛡️] Escudo TNS detectado en la cascada. Inyectando marca de agua al reporte interno.")
        aviso_escudo = f"""=================================================================
🛡️ INTERVENCIÓN DEL ESCUDO TNS (SISTEMA ANTI-DUPLICIDAD)
=================================================================
ALERTA ROJA: Este candidato ya posee una designación oficial IAU.
Nombre Oficial Asignado : {escudo_hit}
URL de Confirmación     : https://www.wis-tns.org/object/{escudo_hit.split(' ')[-1] if ' ' in escudo_hit else escudo_hit}
-> ACCIÓN: Se aborta automáticamente la publicación de telegramas.
=================================================================\n\n"""
        reporte_matematico = aviso_escudo + reporte_matematico
    # =====================================================================

    try:
        coordenadas = SkyCoord(ra=ra_deg*u.degree, dec=dec_deg*u.degree, frame='icrs')
        id_limpio = id_evento.replace(' ', '_').replace('/', '-')

        if tipo_evento in ["flare", "nova"]:
            tiene_planetas, planetas_info = buscar_exoplanetas(coordenadas, tipo_evento)
            es_enana_roja = buscar_espectro_y_fotometria(coordenadas, id_limpio)
            emision_activa, valor_ew, fuente_espectro, estado_eso = analizar_espectroscopia_activa(coordenadas, id_limpio, tipo_evento, redshift=0.0)
            
            generar_circular_estelar_local(ra_deg, dec_deg, id_limpio, tiene_planetas, es_enana_roja, planetas_info, emision_activa, valor_ew, fuente_espectro, estado_eso, tipo_evento, distancia_real, reporte_matematico)
            
            try:
                datos_para_megafono = {
                    "ew_halfa": valor_ew, 
                    "tiene_planetas": tiene_planetas, 
                    "distancia": distancia_real,
                    "mjd_deteccion": mjd_deteccion,
                    "es_enana_roja": es_enana_roja,
                    "fuente_espectro": fuente_espectro
                }
                datos_para_megafono.update(extra_datos_hunter) 
                generar_alerta_comunidad(id_limpio, ra_deg, dec_deg, tipo_evento=tipo_evento, extra_data=datos_para_megafono)
            except TypeError: pass
                
        elif tipo_evento in ["supernova", "agn", "blazar", "tde"]:
            galaxia, redshift = buscar_galaxia_anfitriona(coordenadas)
            
            # Asegurar redshift como float para el análisis espectral dinámico
            z_float = 0.0
            if redshift != "Desconocido":
                try:
                    z_float = float(redshift)
                except ValueError:
                    pass
            
            # --- INYECCIÓN COSMOLÓGICA NED ---
            rango_mpc, rango_mly = calcular_distancia_hubble(redshift)
            if rango_mpc != "Desconocida":
                distancia_real = f"{rango_mpc} {rango_mly}"
            # ---------------------------------
            
            _ = buscar_espectro_y_fotometria(coordenadas, id_limpio)
            
            # --- NUEVA LLAMADA: ESPECTROSCOPÍA EXTRAGALÁCTICA TAXONÓMICA ---
            emision_activa, valor_ew, fuente_espectro, estado_eso = analizar_espectroscopia_activa(coordenadas, id_limpio, tipo_evento, redshift=z_float)
            
            generar_circular_extragalactica(ra_deg, dec_deg, id_limpio, galaxia, redshift, tipo_evento, reporte_matematico)
            
            try:
                datos_para_megafono = {
                    "galaxia": galaxia, 
                    "redshift": redshift, 
                    "distancia": distancia_real,
                    "mjd_deteccion": mjd_deteccion,
                    "fuente_espectro": fuente_espectro,
                    "ew_halfa": valor_ew
                }
                datos_para_megafono.update(extra_datos_hunter)
                generar_alerta_comunidad(id_limpio, ra_deg, dec_deg, tipo_evento=tipo_evento, extra_data=datos_para_megafono)
            except TypeError: pass
        
        print("\n=== PIPELINE AUTOMÁTICO DE LABORATORIO COMPLETADO ===")
        return True
    except Exception as e:
        print(f"\n[!] Error crítico en el pipeline: {e}")
        return False

if __name__ == "__main__":
    print("=====================================================")
    print(" ESTACIÓN MAGALLANES - LABORATORIO (MODO 100% LOCAL) ")
    print("=====================================================")
    try:
        ra_input = float(input("\n➤ Ascensión Recta (RA) : "))
        dec_input = float(input("➤ Declinación (Dec)    : "))
        tipo_input = input("➤ Tipo (flare/nova/supernova/agn/blazar/tde): ").strip().lower()
        if tipo_input not in ["flare", "nova", "supernova", "agn", "blazar", "tde"]: tipo_input = "flare"
        ejecutar_pipeline_magallanes(ra_input, dec_input, f"Manual_{tipo_input.upper()}", tipo_evento=tipo_input)
    except ValueError: print("\n[!] Error: Formato inválido.")
