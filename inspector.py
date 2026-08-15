import requests

def inspeccionar_paquete():
    print("=== INICIANDO INSPECTOR FORENSE DE ALERCE (50 OBJETOS) ===")
    url_objects = "https://api.alerce.online/v2/objects"
    
    # Pedimos los últimos 50 objetos ordenados por su detección más reciente
    params = {
        "page_size": 50,
        "order_by": "lastmjd",
        "order_mode": "DESC"
    }

    try:
        response = requests.get(url_objects, params=params, timeout=10)
        response.raise_for_status()
        datos = response.json()
        objetos = datos.get("items", [])

        print(f"[*] Se descargaron {len(objetos)} objetos. Analizando probabilidades...\n")
        
        for obj in objetos:
            oid = obj.get("oid", "Desconocido")
            clase_ia = obj.get("class", "Sin clasificar")
            probabilidad = obj.get("probability", 0.0)
            
            # Recreamos tus umbrales mentales (ajusta el 0.60 si en tu hunter usas otro)
            if probabilidad >= 0.60:
                estado = "🟢 SUPERÓ UMBRAL (Debería ser procesado)"
            else:
                estado = "🔴 DESCARTADO (Probabilidad baja)"
                
            # Formateamos la salida para que sea fácil de leer en la terminal
            print(f"ID: {oid:<15} | Clase: {clase_ia:<10} | Prob: {probabilidad:.3f} | Acción: {estado}")

        print("\n=== FIN DE LA INSPECCIÓN ===")
        print("Revisa si hay algún objeto en 🟢. Si lo hay, y tu hunter.py no lo atrapó, el bug está en tu código.")

    except Exception as e:
        print(f"Error de conexión: {e}")

if __name__ == "__main__":
    inspeccionar_paquete()
