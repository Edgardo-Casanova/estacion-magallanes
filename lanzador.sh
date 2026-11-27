#!/bin/bash
# ==========================================================
# AUTOMATIZADOR DE LA ESTACIÓN MAGALLANES (VM -> GITHUB)
# VERSIÓN: FASE 5.1 (SINCRONIZACIÓN BIDIRECCIONAL BLINDADA)
# ==========================================================

cd "$(dirname "$0")" || exit
mkdir -p data alertas alertas_comunidad bitacoras

echo "[SYNC INICIO] $(date '+%Y-%m-%d %H:%M:%S') - Descargando cambios remotos..."
git pull --no-rebase -X ours --no-edit origin main || true

/usr/bin/flock -n /tmp/hunter.lock /home/contacto/proyecto_magallanes/entorno/bin/python -u hunter.py >> cron_log.txt 2>&1

git add -A
git commit -m "Actualización Automática de Telemetría: $(date '+%Y-%m-%d %H:%M:%S')" || true

echo "[SYNC FIN] $(date '+%Y-%m-%d %H:%M:%S') - Integrando cambios remotos y subiendo..."
git pull --no-rebase -X ours --no-edit origin main
git push origin main || (git pull --no-rebase -X ours --no-edit origin main && git push origin main)
