#!/bin/bash

# === 1. INYECCIÓN DE MEMORIA PARA CRON ===
export HOME=/home/contacto
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# === 2. ENTRAR AL CUARTEL GENERAL ===
cd /home/contacto/proyecto_magallanes/estacion-magallanes || exit

# === 3. ACTUALIZAR CÓDIGO (GitHub solo para código) ===
/usr/bin/git pull origin main

# === 4. DISPARAR EL CAZADOR ===
/home/contacto/proyecto_magallanes/entorno/bin/python hunter.py

# === 5. SINCRONIZAR BASE DE DATOS CON EL BUCKET (Estrategia Cloud) ===
# Extraemos el nombre del bucket de tu archivo .env
BUCKET_NAME=$(grep GCS_BUCKET_NAME .env | cut -d '=' -f2 | tr -d '"')

# Subimos el catálogo maestro y sincronizamos las carpetas
gsutil cp catalogo_maestro.json gs://$BUCKET_NAME/
gsutil -m rsync -d -r alertas/ gs://$BUCKET_NAME/alertas/
gsutil -m rsync -d -r alertas_comunidad/ gs://$BUCKET_NAME/alertas_comunidad/
gsutil -m rsync -d -r data/ gs://$BUCKET_NAME/data/
