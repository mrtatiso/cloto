#!/bin/sh
# Abre Cloto en Linux con el Python de este equipo (el equipo hace de intérprete). Es la misma ventana de «python3 cloto.py».
d=$(cd "$(dirname "$0")" && pwd) || exit 1
py=
for c in /usr/bin/python3 python3; do                       # primero el Python del sistema: ahí viven GTK y WebKit
  command -v "$c" >/dev/null 2>&1 || continue
  if "$c" -c 'import webview' >/dev/null 2>&1; then py=$c; break; fi
  [ -n "$py" ] || fallback=$c
done
if [ -z "$py" ]; then
  py=$fallback
  if [ -z "$py" ]; then echo "Cloto necesita Python 3 (paquete python3 de tu distribución)." >&2; exit 1; fi
  echo "Aviso: sin «pywebview» no hay ventana propia; Cloto se abrirá en Chrome/Chromium (modo app) o en tu navegador." >&2
  echo "Para la ventana propia instala pywebview y WebKitGTK (python3-gi y WebKit2GTK de tu distribución)." >&2
fi
exec "$py" "$d/cloto.py" "$@"
