#!/bin/bash
# =====================================================================
# AUTOMATIZADOR DE LA ESTACIÓN MAGALLANES (VM -> GITHUB)
# VERSIÓN: FASE 4 (SINCRONIZACIÓN TOTAL "TODO O NADA")
# =====================================================================

# 1. Navegar al directorio donde está guardado este script
cd "$(dirname "$0")" || exit

# 2. Crear las carpetas si no existen (evita errores de Git en la primera ejecución limpia)
mkdir -p data alertas alertas_comunidad bitacoras

# 3. Ejecutar el cazador usando el entorno virtual que está afuera de la carpeta
/usr/bin/flock -n /tmp/hunter.lock /home/contacto/proyecto_magallanes/entorno/bin/python -u hunter.py >> cron_log.txt 2>&1

# 4. Sincronización con GitHub (Malla barredera)
# El punto (.) le ordena a Git empaquetar TODO: JSON, bitácoras, boletín, códigos y gráficos.
git add .

# 5. Crear el commit con la fecha y hora de la ejecución (con seguro anti-cuelgues)
git commit -m "Actualización Automática de Telemetría: $(date '+%Y-%m-%d %H:%M:%S')" || true

# 6. Empujar los cambios al repositorio en la nube
git push origin main
