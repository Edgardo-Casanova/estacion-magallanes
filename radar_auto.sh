#!/bin/bash

# === 1. INYECCIÓN DE MEMORIA PARA CRON ===
# Esto le dice al proceso fantasma quién eres y dónde buscar tus contraseñas
export HOME=/home/contacto
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# === 2. ENTRAR AL CUARTEL GENERAL ===
cd /home/contacto/proyecto_magallanes/estacion-magallanes || exit

# === 3. DISPARAR EL CAZADOR ===
# Ejecuta tu motor de Python con el entorno virtual
/home/contacto/proyecto_magallanes/entorno/bin/python hunter.py

# === 4. EMPAQUETADO Y ENVÍO A LA NUBE ===
# Usamos rutas absolutas para que Cron no se pierda
/usr/bin/git add .
/usr/bin/git commit -m "Patrullaje automatico completado: $(date +'%Y-%m-%d %H:%M')" || true
/usr/bin/git push origin main
