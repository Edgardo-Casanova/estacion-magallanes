#!/bin/bash

# 1. Entrar a la carpeta del proyecto
cd /home/edgardo/Escritorio/rubin_flare_hunter

# 2. Ejecutar el cazador usando la llave maestra de tu entorno virtual
/home/edgardo/Escritorio/rubin_flare_hunter/venv/bin/python hunter.py

# 3. Subir todos los archivos nuevos y gráficos a GitHub automáticamente
git add .
git commit -m "Patrullaje automatico completado: $(date +'%Y-%m-%d %H:%M')"
git push
