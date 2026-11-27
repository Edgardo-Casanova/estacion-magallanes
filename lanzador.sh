#!/bin/bash
# ==========================================================
# AUTOMATIZADOR DE LA ESTACIÓN MAGALLANES (VM -> GITHUB)
# VERSIÓN: FASE 5 (SINCRONIZACIÓN BIDIRECCIONAL SEGURA)
# ==========================================================

# 1. Navegar al directorio donde está guardado este script
cd "$(dirname "$0")" || exit

# 2. Crear las carpetas si no existen (evita errores de Git en la primera ejecución limpia)
mkdir -p data alertas alertas_comunidad bitacoras

# 3. Descargar actualizaciones de código desde GitHub antes de patrullar
git pull origin main -X ours --no-edit || true

# 4. Ejecutar el cazador usando el entorno virtual que está afuera de la carpeta
/usr/bin/flock -n /tmp/hunter.lock /home/contacto/proyecto_magallanes/entorno/bin/python -u hunter.py >> cron_log.txt 2>&1

# 5. Sincronización con GitHub (Malla barredera)
# El punto (.) le ordena a Git empaquetar TODO: JSON, bitácoras, boletín, códigos y gráficos.
git add .

# 6. Crear el commit con la fecha de la ejecución (con seguro anti-cuelgues)
git commit -m "Actualización Automática de Telemetría: $(date '+%Y-%m-%d %H:%M:%S')" || true

# 7. Integrar cambios remotos ocurridos durante el patrullaje (priorizando telemetría local) y subir
git pull origin main -X ours --no-edit && git push origin main
