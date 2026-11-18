#!/bin/sh
# Pone Cloto en el menú de aplicaciones y en el escritorio de ESTA computadora. La app y tus proyectos se quedan en la memoria CLOTO.
cd "$(dirname "$0")" || exit 1
if [ ! -f ./linux/Cloto ]; then
  echo "No encuentro linux/Cloto junto a este instalador."
  echo "Descarga el artefacto 'cloto-usb' (o Cloto-USB.zip de Releases) y copia el contenido"
  echo "de la carpeta CLOTO/ a la raiz de la memoria, ahi esta linux/Cloto."
  exit 1
fi
command -v python3 >/dev/null 2>&1 || { echo "Cloto en Linux necesita Python 3 (paquete python3 de tu distribucion)."; exit 1; }
sh ./linux/Cloto --instalar
