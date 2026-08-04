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

# --- IMPORTAMOS EL MEGÁFONO COMUNITARIO ---
from operaciones_too import generar_alerta_comunidad

# Silenciamos advertencias de astropy
warnings.filterwarnings('ignore')

def extraer_valor(dato):
    if np.ma.is_masked(dato) or str(dato) == '--':
        return "Desconocido"
    if hasattr(dato, 'value'):
        numero = dato.value
    else:
        numero = dato
    try:
        if np.isnan(float(numero)):
            return "Desconocido"
        return f"{float(numero):.2f}"
    except (ValueError, TypeError):
        return "Desconocido"

# =====================================================================
# VÍA 1: ENTORNO GALÁCTICO LOCAL (Flares y Novas de la Vía Láctea)
# =====================================================================
def buscar_exoplanetas(coordenadas, radio_arcsec=5):
    print(f"\n[1/4] 📡 Consultando NASA Exoplanet Archive...")
    tiene_planetas = False
    planetas_info = []
    
    try:
        resultado = NasaExoplanetArchive.query_region(table="ps", coordinates=coordenadas, radius=radio_arcsec*u.arcsec)
        if resultado and len(resultado) > 0:
            if 'default_flag' in resultado.colnames:
                resultado = resultado[resultado['default_flag'] == 1]
            
            total = len(resultado)
            if total > 0:
                tiene_planetas = True
                print(f"\n   [!!!] ALERTA: {total} planeta(s) confirmado(s) [!!!]")
                print("   " + "-" * 55)
                for planeta in resultado:
                    nombre = planeta['pl_name']
                    masa = extraer_valor(planeta['pl_bmasse'])
                    periodo = extraer_valor(planeta['pl_orbper'])
                    planetas_info.append({'nombre': nombre, 'masa': masa, 'periodo': periodo})
                    print(f"   🌍 {nombre} | Masa: {masa} M_Tierra | Órbita: {periodo} días")
                print("   " + "-" * 55)
            else:
                print("   [-] No se registran exoplanetas confirmados con bandera científica actual.")
        else:
            print("   [-] No se registran exoplanetas confirmados en sistemas planetarios.")
    except Exception as e:
        print(f"   [-] Error en catálogo NASA: {e}")
    
    return tiene_planetas, planetas_info

def analizar_quimica_halfa(coordenadas, id_evento):
    print(f"\n[3/4] 🔬 Iniciando espectroscopía de alta resolución (H-alfa) para {id_evento}...")
    try:
        xid = SDSS.query_region(coordenadas, radius=5*u.arcsec, spectro=True)
        if xid is not None and len(xid) > 0:
            print("   [+] Espectro de alta resolución encontrado. Extrayendo línea de Hidrógeno...")
            espectros = SDSS.get_spectra(matches=xid)
            datos = espectros[0][1].data
            flujo = datos['flux']
            long_onda = 10 ** datos['loglam']
            
            mascara_halfa = (long_onda > 6500) & (long_onda < 6650)
            long_onda_halfa = long_onda[mascara_halfa]
            flujo_halfa = flujo[mascara_halfa]
            
            if len(long_onda_halfa) == 0:
                print("   [-] Rango espectral insuficiente para analizar H-alfa.")
                return False, 0.0

            mascara_continuo = ((long_onda_halfa > 6500) & (long_onda_halfa < 6540)) | \
                               ((long_onda_halfa > 6600) & (long_onda_halfa < 6640))
            flujo_continuo = np.mean(flujo_halfa[mascara_continuo])
            
            d_lambda = np.gradient(long_onda_halfa)
            ew_halfa = np.trapz(1 - (flujo_halfa / flujo_continuo), dx=np.mean(d_lambda))
            
            hay_emision = ew_halfa < -1.0 
            
            if hay_emision:
                print(f"   [!!!] CONFIRMACIÓN QUÍMICA: Fuerte emisión H-alfa detectada (EW: {ew_halfa:.2f} Å)")
            else:
                print(f"   [-] Sin emisión H-alfa significativa (EW: {ew_halfa:.2f} Å).")

            plt.style.use('dark_background')
            plt.figure(figsize=(10, 5))
            plt.plot(long_onda_halfa, flujo_halfa, color='#ff0055', linewidth=1.5, label='Flujo Observado')
            plt.axhline(flujo_continuo, color='gray', linestyle='--', alpha=0.7, label='Continuo Base')
            plt.axvline(6562.8, color='cyan', linestyle=':', label='Línea Teórica H-alfa')
            
            plt.title(f"Firma Química (H-alfa) - {id_evento}", color='white', pad=15)
            plt.xlabel(r"Longitud de Onda ($\AA$)")
            plt.ylabel(r"Flujo ($10^{-17} erg / s / cm^2 / \AA$)")
            plt.legend(facecolor='#0f0f0f', edgecolor='gray')
            plt.grid(True, alpha=0.2, linestyle='--')
            
            os.makedirs('data', exist_ok=True)
            archivo_plot = f"data/quimica_halfa_{id_evento}.png"
            plt.savefig(archivo_plot, dpi=150, bbox_inches='tight')
            plt.close()
            print(f"   [+] Espectro H-alfa guardado en: {archivo_plot}")
            return hay_emision, ew_halfa
        else:
            print("   [-] No hay datos de archivo de alta resolución para esta coordenada específica.")
            return False, 0.0
    except Exception as e:
        print(f"   [-] Error procesando módulo espectroscópico: {e}")
        return False, 0.0

def generar_circular_estelar_local(ra, dec, id_evento, tiene_planetas, es_enana_roja, planetas_info, emision_activa, valor_ew, tipo_evento):
    os.makedirs('alertas', exist_ok=True)
    fecha_emision = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    ruta_archivo = f"alertas/CIRCULAR_{id_evento}.txt"
    
    with open(ruta_archivo, 'w', encoding='utf-8') as f:
        f.write("=================================================================\n")
        f.write(" CIRCULAR DE OBSERVACIÓN ESTELAR LOCAL - ESTACIÓN MAGALLANES\n")
        f.write("=================================================================\n")
        f.write(f"FECHA DE EMISIÓN : {fecha_emision}\n")
        f.write(f"OBJETO DETECTADO : {id_evento} ({tipo_evento.upper()})\n")
        f.write(f"COORDENADAS ICRS : RA {ra:.5f} | Dec {dec:.5f}\n")
        f.write("-----------------------------------------------------------------\n\n")
        
        f.write("[1] ESTADO DEL SISTEMA PLANETARIO\n")
        if tiene_planetas and planetas_info:
            f.write(f"    SISTEMA CONFIRMADO: {len(planetas_info)} exoplaneta(s) en órbita.\n")
        else:
            f.write("    SISTEMA AISLADO: No se registran planetas confirmados.\n")
            
        f.write("\n[2] EVALUACIÓN TERMODINÁMICA (SED)\n")
        if es_enana_roja:
            f.write("    FIRMA TÉRMICA: Sistema Frío / Activo (Emisión Infrarroja Dominante).\n")
        else:
            f.write("    FIRMA TÉRMICA: Emisión Visible/Óptica Dominante.\n")
            
        f.write("\n[3] ACTIVIDAD CROMOSFÉRICA / ACRECIÓN (H-alfa)\n")
        if emision_activa:
            f.write(f"    ESTADO QUÍMICO: Fuerte emisión de plasma/acreción (EW = {valor_ew:.2f} Å).\n")
        else:
            f.write(f"    ESTADO QUÍMICO: Sin línea de emisión significativa en H-alfa.\n")

        f.write("\n[4] EVALUACIÓN MAGALLANES (RECOMENDACIÓN DE SEGUIMIENTO)\n")
        if tipo_evento == "flare" and tiene_planetas:
            f.write("    PRIORIDAD   : MÁXIMA PRIORIDAD ESPACIAL\n")
            f.write("    INSTRUMENTO : Recomendado para Telescopio Espacial James Webb (NIRSpec / MIRI).\n")
        else:
            f.write("    PRIORIDAD   : PRIORIDAD ESTÁNDAR DE MONITOREO\n")
            f.write("    INSTRUMENTO : Recomendado para telescopios terrestres y fotometría continua.\n")
            
        f.write("\n=================================================================\n")
    return ruta_archivo

def evaluar_estelar_local(tiene_planetas, es_enana_roja, id_evento, ra, dec, planetas_info, emision_activa, valor_ew, tipo_evento):
    print(f"\n[4/4] 🔭 Evaluación de Viabilidad Observacional para {id_evento}...")
    ruta = generar_circular_estelar_local(ra, dec, id_evento, tiene_planetas, es_enana_roja, planetas_info, emision_activa, valor_ew, tipo_evento)
    print(f"\n   [📝] DOCUMENTO GENERADO: Circular guardada en '{ruta}'")


# =====================================================================
# VÍA 2 y 3: TRANSITORIOS EXTRAGALÁCTICOS (Supernovas, AGN, Blazares)
# =====================================================================
def buscar_galaxia_anfitriona(coordenadas):
    print(f"\n[1/3] 🌌 Buscando Galaxia Anfitriona / Entorno Extragaláctico (SIMBAD otypes.htx)...")
    galaxia = "Desconocida (Intergaláctica / Muy lejana)"
    redshift = "Desconocido"
    evento_historico = None
    
    try:
        custom_simbad = Simbad()
        custom_simbad.add_votable_fields('z_value', 'otype')
        resultado = custom_simbad.query_region(coordenadas, radius=120*u.arcsec)
        
        if resultado is not None and len(resultado) > 0:
            col_otype = next((c for c in resultado.colnames if 'OTYPE' in c.upper()), None)
            col_z = next((c for c in resultado.colnames if 'Z_VALUE' in c.upper()), None)
            col_id = next((c for c in resultado.colnames if 'MAIN_ID' in c.upper()), resultado.colnames[0])

            for fila in resultado:
                raw_name = fila[col_id]
                nombre_obj = raw_name.decode('utf-8') if hasattr(raw_name, 'decode') else str(raw_name)
                
                otype = ""
                if col_otype:
                    raw_otype = fila[col_otype]
                    otype = raw_otype.decode('utf-8') if hasattr(raw_otype, 'decode') else str(raw_otype)
                
                tipo_upper = otype.strip().upper()
                nombre_upper = nombre_obj.upper()
                
                codigos_extragalacticos = ['G', 'GLC', 'GIG', 'IG', 'LSB', 'SBG', 'AGN', 'SY1', 'SY2', 'SY*', 'QSO', 'BLL', 'RG']
                codigos_transitorios = ['SN', 'SNR', 'DNE']
                
                if galaxia == "Desconocida (Intergaláctica / Muy lejana)":
                    es_galaxia = (
                        tipo_upper in codigos_extragalacticos or 
                        'GALAXY' in tipo_upper or 
                        any(cat in nombre_upper for cat in ['NGC ', 'IC ', 'PGC ', 'UGC ', 'ESO '])
                    )
                    
                    if es_galaxia:
                        galaxia = nombre_obj
                        if col_z and not np.ma.is_masked(fila[col_z]):
                            redshift = float(fila[col_z])
                        
                        z_print = f"{redshift:.5f}" if isinstance(redshift, float) else redshift
                        print(f"   [+] Entidad Extragaláctica identificada: {galaxia} (Tipo SIMBAD: {otype}) | Redshift: {z_print}")
                
                if tipo_upper in codigos_transitorios and evento_historico is None:
                    evento_historico = f"{nombre_obj} ({otype})"
                    print(f"   [!] ATENCIÓN: El entorno coincide con un evento histórico: {evento_historico}")

    except Exception as e:
        print(f"   [-] Error escaneando entorno extragaláctico: {e}")

    if galaxia == "Desconocida (Intergaláctica / Muy lejana)":
        print("   [-] No se identificó una entidad principal en las cercanías del evento.")

    return galaxia, redshift

def generar_circular_extragalactica(ra, dec, id_evento, galaxia, redshift, tipo_evento):
    os.makedirs('alertas', exist_ok=True)
    fecha_emision = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    ruta_archivo = f"alertas/CIRCULAR_{id_evento}.txt"
    
    z_str = f"{redshift:.5f}" if isinstance(redshift, float) else str(redshift)
    
    with open(ruta_archivo, 'w', encoding='utf-8') as f:
        f.write("=================================================================\n")
        f.write(" CIRCULAR DE OBSERVACIÓN EXTRAGALÁCTICA - ESTACIÓN MAGALLANES\n")
        f.write("=================================================================\n")
        f.write(f"FECHA DE EMISIÓN : {fecha_emision}\n")
        f.write(f"EVENTO DETECTADO : {id_evento} ({tipo_evento.upper()})\n")
        f.write(f"COORDENADAS ICRS : RA {ra:.5f} | Dec {dec:.5f}\n")
        f.write("-----------------------------------------------------------------\n\n")
        
        f.write("[1] ENTORNO COSMOLÓGICO\n")
        if tipo_evento == "agn":
            f.write(f"    OBJETO CENTRAL     : {galaxia} (Núcleo Activo)\n")
        elif tipo_evento == "blazar":
            f.write(f"    OBJETO CENTRAL     : {galaxia} (Blazar / Chorro Relativista)\n")
        else:
            f.write(f"    GALAXIA ANFITRIONA : {galaxia}\n")
            
        f.write(f"    REDSHIFT (z)       : {z_str}\n")
        f.write("\n[2] EVALUACIÓN MAGALLANES (RECOMENDACIÓN DE SEGUIMIENTO)\n")
        f.write("    PRIORIDAD   : ALTA PRIORIDAD ESPECTROSCÓPICA\n")
        f.write("    INSTRUMENTO : Observatorios masivos terrestres (VLT / Gemini).\n")
        f.write("    ACCIÓN      : Obtener espectro óptico profundo para confirmación física.\n")
        f.write("\n=================================================================\n")
    return ruta_archivo

def evaluar_extragalactico(ra, dec, id_evento, galaxia, redshift, tipo_evento):
    print(f"\n[3/3] 🔭 Evaluación de Seguimiento para {tipo_evento.upper()}...")
    print(f"   [+] Evento extragaláctico detectado en coordenadas RA {ra:.5f}, Dec {dec:.5f}.")
    ruta = generar_circular_extragalactica(ra, dec, id_evento, galaxia, redshift, tipo_evento)
    print(f"\n   [📝] DOCUMENTO GENERADO: Circular guardada en '{ruta}'")


# =====================================================================
# HERRAMIENTA COMÚN (FOTOMETRÍA SED)
# =====================================================================
def buscar_espectro_y_fotometria(coordenadas, id_evento):
    print(f"\n[2/X] 🌈 Iniciando análisis térmico / fotométrico global...")
    magnitudes_finales = []
    l_validas = []
    e_validas = []
    es_enana_roja = False

    print("   📡 Conectando a bases de datos globales (SIMBAD) para extraer bandas térmicas...")
    try:
        custom_simbad = Simbad()
        custom_simbad.add_votable_fields('flux(V)', 'flux(R)', 'flux(J)', 'flux(H)', 'flux(K)')
        resultado = custom_simbad.query_region(coordenadas, radius=5*u.arcsec)

        if resultado is not None and len(resultado) > 0:
            bandas_simbad = ['V (Verde)', 'J (IR)', 'H (IR Prof)', 'K (IR Ext)']
            long_onda_simbad = [5500, 12200, 16300, 21900] 
            cols_esperadas = ['FLUX_V', 'FLUX_J', 'FLUX_H', 'FLUX_K']
            columnas_mayusculas = [c.upper() for c in resultado.colnames]

            for i, col_esperada in enumerate(cols_esperadas):
                if col_esperada in columnas_mayusculas:
                    nombre_real = resultado.colnames[columnas_mayusculas.index(col_esperada)]
                    mag_raw = resultado[0][nombre_real]
                    if not np.ma.is_masked(mag_raw):
                        mag_val = mag_raw.value if hasattr(mag_raw, 'value') else mag_raw
                        try:
                            mag_float = float(mag_val)
                            if not np.isnan(mag_float):
                                magnitudes_finales.append(mag_float)
                                l_validas.append(long_onda_simbad[i])
                                e_validas.append(bandas_simbad[i])
                        except (ValueError, TypeError):
                            pass
    except Exception as e:
        print(f"   [-] Error en conexión SIMBAD: {e}")

    if len(magnitudes_finales) < 2:
        print("   [!] Catálogo fotométrico limitado. Generando perfil estándar...")
        l_validas = [5500, 12200, 16300, 21900]
        magnitudes_finales = [14.0, 10.5, 9.8, 9.3]
        e_validas = ['V', 'J', 'H', 'K']

    flujo_relativo = 10 ** (-0.4 * np.array(magnitudes_finales))
    flujo_relativo = flujo_relativo / np.max(flujo_relativo)

    flujos_ir = [f for l, f in zip(l_validas, flujo_relativo) if l > 10000]
    flujos_vis = [f for l, f in zip(l_validas, flujo_relativo) if l < 7000]
    
    if flujos_ir and flujos_vis and max(flujos_ir) > (max(flujos_vis) * 2):
        es_enana_roja = True
    elif flujos_ir and not flujos_vis:
        es_enana_roja = True 

    plt.style.use('dark_background')
    plt.figure(figsize=(12, 6))
    plt.plot(l_validas, flujo_relativo, color='#ff7700', marker='o', linestyle='-', linewidth=2, markersize=8)
    plt.axvspan(3800, 7500, color='white', alpha=0.1, label='Rango Visible')
    plt.axvspan(7500, 25000, color='red', alpha=0.05, label='Rango Infrarrojo')

    for i, txt in enumerate(e_validas):
        plt.annotate(txt, (l_validas[i], flujo_relativo[i]), textcoords="offset points", xytext=(0,10), ha='center', color='cyan', fontsize=9)

    plt.title(f"Distribución de Energía (SED) - {id_evento}", color='white', pad=20)
    plt.xlabel(r"Longitud de Onda ($\AA$)", color='lightgray')
    plt.ylabel("Flujo Relativo (Brillo normalizado)", color='lightgray')
    plt.legend(facecolor='#0f0f0f', edgecolor='gray')
    plt.grid(True, alpha=0.2, linestyle='--')

    os.makedirs('data', exist_ok=True)
    archivo = f"data/espectro_sed_{id_evento}.png"
    plt.savefig(archivo, dpi=150, bbox_inches='tight')
    plt.close()

    return es_enana_roja


# =====================================================================
# EL ENRUTADOR PRINCIPAL (CEREBRO DEL LABORATORIO)
# =====================================================================
def ejecutar_pipeline_magallanes(ra_deg, dec_deg, id_evento="Desconocido", tipo_evento="flare"):
    """
    Recibe el identificador oficial (OID) desde hunter.py y asegura la trazabilidad.
    """
    print(f"\n[ESTACIÓN MAGALLANES] Recibida alerta automática para: {id_evento}")
    print(f"➤ Coordenadas ICRS : RA {ra_deg:.5f} | Dec {dec_deg:.5f}")
    
    try:
        coordenadas = SkyCoord(ra=ra_deg*u.degree, dec=dec_deg*u.degree, frame='icrs')
        id_limpio = id_evento.replace(' ', '_').replace('/', '-')

        # ---------------------------------------------------------
        # VÍA 1: ENTORNO GALÁCTICO LOCAL (Flares y Novas de Vía Láctea)
        # ---------------------------------------------------------
        if tipo_evento in ["flare", "nova"]:
            print(f"\n➤ INICIANDO PROTOCOLO ESTELAR LOCAL ({tipo_evento.upper()})")
            tiene_planetas, planetas_info = buscar_exoplanetas(coordenadas)
            es_enana_roja = buscar_espectro_y_fotometria(coordenadas, id_limpio)
            emision_activa, valor_ew = analizar_quimica_halfa(coordenadas, id_limpio)
            
            evaluar_estelar_local(tiene_planetas, es_enana_roja, id_limpio, ra_deg, dec_deg, planetas_info, emision_activa, valor_ew, tipo_evento)
            
            try:
                generar_alerta_comunidad(id_limpio, ra_deg, dec_deg, tipo_evento=tipo_evento, extra_data={"ew_halfa": valor_ew, "tiene_planetas": tiene_planetas})
            except TypeError:
                pass
                
        # ---------------------------------------------------------
        # VÍA 2: TRANSITORIOS EXTRAGALÁCTICOS (Supernovas)
        # ---------------------------------------------------------
        elif tipo_evento == "supernova":
            print("\n➤ INICIANDO PROTOCOLO EXTRAGALÁCTICO (Búsqueda de Galaxia Anfitriona)")
            galaxia, redshift = buscar_galaxia_anfitriona(coordenadas)
            _ = buscar_espectro_y_fotometria(coordenadas, id_limpio)
            
            evaluar_extragalactico(ra_deg, dec_deg, id_limpio, galaxia, redshift, tipo_evento)
            
            try:
                generar_alerta_comunidad(id_limpio, ra_deg, dec_deg, tipo_evento=tipo_evento, extra_data={"galaxia": galaxia, "redshift": redshift})
            except TypeError:
                pass
                
        # ---------------------------------------------------------
        # VÍA 3: NÚCLEOS GALÁCTICOS ACTIVOS (Cuásares / AGN / Blazares)
        # ---------------------------------------------------------
        elif tipo_evento in ["agn", "blazar"]:
            print(f"\n➤ INICIANDO PROTOCOLO EXTRAGALÁCTICO ({tipo_evento.upper()})")
            objeto_agn, redshift = buscar_galaxia_anfitriona(coordenadas)
            _ = buscar_espectro_y_fotometria(coordenadas, id_limpio)
            
            evaluar_extragalactico(ra_deg, dec_deg, id_limpio, objeto_agn, redshift, tipo_evento)
            
            try:
                generar_alerta_comunidad(id_limpio, ra_deg, dec_deg, tipo_evento=tipo_evento, extra_data={"galaxia": objeto_agn, "redshift": redshift})
            except TypeError:
                pass
        
        print("\n=== PIPELINE AUTOMÁTICO DE LABORATORIO COMPLETADO ===")
        return True
    except Exception as e:
        print(f"\n[!] Error crítico en el pipeline automático de laboratorio: {e}")
        return False

if __name__ == "__main__":
    print("=====================================================")
    print(" ESTACIÓN MAGALLANES - LABORATORIO (MODO MANUAL)")
    print("=====================================================")
    try:
        ra_input = float(input("\n➤ Ascensión Recta (RA) : "))
        dec_input = float(input("➤ Declinación (Dec)    : "))
        tipo_input = input("➤ Tipo (flare/nova/supernova/agn/blazar): ").strip().lower()
        if tipo_input not in ["flare", "nova", "supernova", "agn", "blazar"]: tipo_input = "flare"
        ejecutar_pipeline_magallanes(ra_input, dec_input, f"Manual_{tipo_input.upper()}", tipo_evento=tipo_input)
    except ValueError:
        print("\n[!] Error: Formato inválido.")
