#!/bin/sh
# Pone Cloto en el menú de aplicaciones y en el escritorio de ESTA computadora. La app y tus proyectos se quedan en la memoria CLOTO.
cd "$(dirname "$0")" || exit 1
if [ ! -f ./linux/Cloto ]; then
  echo "No encuentro linux/Cloto junto a este instalador."
  echo "Esta carpeta es el codigo fuente: el programa lo compila GitHub Actions."
  echo "Descarga el artefacto 'cloto-usb' (o Cloto-USB.zip de Releases) y copia el contenido"
  echo "de la carpeta CLOTO/ a la raiz de la memoria, ahi esta linux/Cloto."
  exit 1
fi
[ -x ./linux/Cloto ] || chmod +x ./linux/Cloto 2>/dev/null
./linux/Cloto --instalar
