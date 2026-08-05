#!/bin/bash

# === 1. INYECCIÓN DE MEMORIA PARA CRON ===
export HOME=/home/contacto
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# === 2. ENTRAR AL CUARTEL GENERAL ===
cd /home/contacto/proyecto_magallanes/estacion-magallanes || exit

# === 3. DESCARGAR ÚLTIMOS CAMBIOS DE CÓDIGO (Desde GitHub) ===
/usr/bin/git pull origin main

# === 4. DISPARAR EL CAZADOR ===
/home/contacto/proyecto_magallanes/entorno/bin/python hunter.py

# === 5. EMPAQUETADO Y ENVÍO DE NUEVAS ALERTAS Y LOGS A GITHUB ===
/usr/bin/git add .
/usr/bin/git commit -m "Patrullaje automatico completado: $(date +'%Y-%m-%d %H:%M')" || true
/usr/bin/git push origin main
