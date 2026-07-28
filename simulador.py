import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from astropy.coordinates import SkyCoord, get_constellation
from astropy.time import Time
import astropy.units as u
import os
from datetime import datetime

print("Generando simulación de flare con formato de divulgación...")

# --- 1. CREACIÓN DE DATOS FICTICIOS ---
mejor_candidato = "ZTF26_SimulacionAlfa"
mejor_sigma = 0.08
salto_maximo = 3.2

# Generar 20 días de historia y 1 día de estallido (MJD)
mjd_base = 60100 
mjds = np.linspace(mjd_base, mjd_base + 30, 20)
mjds = np.append(mjds, mjd_base + 31)

mags = np.random.normal(18.0, mejor_sigma, 20)
mags = np.append(mags, 14.8)
sigmas = np.random.uniform(0.01, 0.05, 21)
fids = np.random.choice([1, 2], 21) 

mejor_curva = pd.DataFrame({'mjd': mjds, 'magpsf': mags, 'sigmapsf': sigmas, 'fid': fids})
coordenadas = SkyCoord(ra=201.365*u.degree, dec=-43.019*u.degree, frame='icrs')
constelacion = get_constellation(coordenadas)

# --- TRADUCCIÓN DE TIEMPO (MJD a Calendario) ---
# Convertimos toda la columna MJD a formato datetime (Fechas humanas)
mejor_curva['fecha_humana'] = Time(mejor_curva['mjd'].values, format='mjd').to_datetime()

# --- 2. CARTOGRAFÍA Y RESULTADOS (VERSIÓN DIVULGACIÓN) ---
plt.style.use('dark_background')
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
fig.patch.set_facecolor('#0f0f0f') 
ax1.set_facecolor('#1a1a1a')
ax2.set_facecolor('#1a1a1a')

banda_g = mejor_curva[mejor_curva['fid'] == 1]
banda_r = mejor_curva[mejor_curva['fid'] == 2]

# Graficar usando las 'fechas_humanas' en el eje X
if not banda_g.empty:
    ax1.errorbar(banda_g['fecha_humana'], banda_g['magpsf'], yerr=banda_g['sigmapsf'], fmt='o', color='#39ff14', alpha=0.6, markersize=5, label='Banda g (Histórico)')
if not banda_r.empty:
    ax1.errorbar(banda_r['fecha_humana'], banda_r['magpsf'], yerr=banda_r['sigmapsf'], fmt='o', color='#ff3333', alpha=0.6, markersize=5, label='Banda r (Histórico)')

ultima_fecha = mejor_curva.iloc[-1]['fecha_humana']
ultima_mag = mejor_curva.iloc[-1]['magpsf']
ax1.scatter(ultima_fecha, ultima_mag, color='yellow', edgecolor='white', marker='*', s=400, zorder=5, label='¡Detección del Flare!')

linea_base = mejor_curva.iloc[:-1]['magpsf'].median()
ax1.axhline(y=linea_base, color='gray', linestyle='--', alpha=0.8, label='Línea Base en Reposo')

# Formato del Eje X para fechas
ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
fig.autofmt_xdate(rotation=45) # Gira las fechas para que no choquen
ax1.invert_yaxis()

ax1.set_title(f"Curva de Luz: {mejor_candidato}", color='white', pad=15)
ax1.set_xlabel("Fecha de Observación (UTC)", color='lightgray')
ax1.set_ylabel("Magnitud Aparente (Brillo)", color='lightgray')
ax1.legend(facecolor='#0f0f0f', edgecolor='gray')
ax1.grid(True, linestyle='-', color='#333333', alpha=0.7)

# Panel Derecho: Mapa
ax2.scatter(coordenadas.ra.deg, coordenadas.dec.deg, color='yellow', marker='*', s=400, label=f'Posición: {mejor_candidato}')
ax2.set_xlim(coordenadas.ra.deg + 1, coordenadas.ra.deg - 1) 
ax2.set_ylim(coordenadas.dec.deg - 1, coordenadas.dec.deg + 1)
ax2.set_title(f"Coordenadas en {constelacion}", color='white', pad=15)
ax2.set_xlabel("Ascensión Recta (RA)", color='lightgray')
ax2.set_ylabel("Declinación (Dec)", color='lightgray')
ax2.legend(facecolor='#0f0f0f', edgecolor='gray', loc='upper right')
ax2.grid(True, linestyle=':', color='#444444')

# --- NUEVO: FICHA TÉCNICA ESTELAR ---
info_text = (
    "ESTADÍSTICAS DEL EVENTO\n"
    "------------------------\n"
    "Tipo: Posible Enana Roja (M-Dwarf)\n"
    "Distancia: ~120 Años Luz (Est.)\n"
    f"Brillo Aumentado: {salto_maximo:.2f} mag\n"
    f"Fecha Pico: {ultima_fecha.strftime('%Y-%m-%d %H:%M')}\n"
    "Estado: Pendiente de revisión"
)
caja_propiedades = dict(boxstyle='round,pad=0.6', facecolor='#2a2a2a', alpha=0.9, edgecolor='#555555')
ax2.text(0.05, 0.95, info_text, transform=ax2.transAxes, fontsize=10,
         verticalalignment='top', color='white', bbox=caja_propiedades)

# Ajuste automático de márgenes para que nada se solape
plt.tight_layout(rect=[0, 0.05, 1, 0.92])

plt.suptitle(f"Reporte Astronómico: Evento Estelar Anómalo", fontsize=20, color='white', fontweight='bold', y=0.98)
fig.text(0.5, 0.01, f"Estación Magallanes | Analizado el {datetime.now().strftime('%Y-%m-%d')} | Red de Alerta ZTF", ha='center', color='gray', fontsize=11)

os.makedirs('data', exist_ok=True)
archivo_plot = f"data/flare_PRO_{mejor_candidato}.png"
plt.savefig(archivo_plot, dpi=150, bbox_inches='tight') 
plt.close()

print(f"\nSimulación completada. Revisa la imagen en la carpeta 'data/'.")
