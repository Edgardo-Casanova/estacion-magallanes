#!/bin/bash

# 1. Entrar a la carpeta del proyecto
cd /home/edgardo/Escritorio/rubin_flare_hunter

# 2. Ejecutar el cazador usando la llave maestra de tu entorno virtual
/home/edgardo/Escritorio/rubin_flare_hunter/venv/bin/python hunter.py

# 3. Preparar todos los archivos nuevos y gráficos para subirlos
git add .

# 4. Amortiguador de errores: Si no hay alertas nuevas, no colapsa el script
git commit -m "Patrullaje automatico completado: $(date +'%Y-%m-%d %H:%M')" || echo "Sin novedades en este ciclo. Continuando..."

# 5. Empuje seguro a la rama principal (soluciona el bloqueo en segundo plano)
git push origin main
