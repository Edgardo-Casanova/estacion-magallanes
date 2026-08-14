"""
=============================================================================
PROYECTO   : Observatorio Automatizado Estación Magallanes
MÓDULO     : tracker_vip.py (Francotirador de Seguimiento a Largo Plazo)
=============================================================================
"""

import os
from alerce.core import Alerce
from hunter import graficar_curva

# Diccionario VIP: { "OID_ZTF": "ID_CATALOGO_JSON" }
# Usamos los códigos internos de ZTF sacados de los reportes oficiales
OBJETIVOS_VIP = {
    "ZTF26abgtqqr": "SN 2026yqj", # TDE-He (Julio)
    "ZTF26aaximsq": "SN 2026rey"  # TDE-featureless (Mayo)
}

def actualizar_vip():
    print("=== INICIANDO RASTREADOR VIP ESTACIÓN MAGALLANES ===")
    client = Alerce()
    
    for oid_alerce, id_json in OBJETIVOS_VIP.items():
        print(f"[*] Consultando historial completo para {id_json} (OID interno: {oid_alerce})...")
        try:
            # 1. Pedir TODAS las detecciones sin límite temporal
            det = client.query_detections(oid=oid_alerce, format='pandas')
            
            if det is not None and not det.empty:
                print(f"   [+] ¡Datos obtenidos! {len(det)} fotometrías históricas descargadas.")
                
                # 2. Obtener las coordenadas base para el mapa del gráfico
                obj_info = client.query_objects(oid=oid_alerce, format='pandas')
                ra = float(obj_info['meanra'].iloc[0])
                dec = float(obj_info['meandec'].iloc[0])
                
                # 3. Reutilizar la función gráfica de tu Hunter, marcándolo como TDE y VIP
                graficar_curva(det, id_json, "ZTF", ra, dec, tipo_evento_final="tde", es_vip=True)
                print(f"   [+] Gráfica actualizada con éxito: data/curva_luz_{id_json.replace(' ', '_')}.png")
            else:
                print(f"   [-] No se encontraron datos fotométricos para {oid_alerce}.")
        except Exception as e:
            print(f"   [!] Error al actualizar {id_json}: {e}")

    print("=== RASTREO VIP FINALIZADO ===")

if __name__ == "__main__":
    actualizar_vip()
