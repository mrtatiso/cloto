#!/bin/sh
# Pone Cloto en Aplicaciones y en el escritorio de ESTA computadora. La app y tus proyectos se quedan en la memoria CLOTO.
cd "$(dirname "$0")" || exit 1
if [ ! -f ./macos/Cloto.app/Contents/MacOS/Cloto ]; then
  echo "No encuentro macos/Cloto.app junto a este instalador."
  echo "Esta carpeta es el codigo fuente: el programa lo compila GitHub Actions."
  echo "Descarga el artefacto 'cloto-usb' (o Cloto-USB.zip de Releases) y copia el contenido"
  echo "de la carpeta CLOTO/ a la raiz de la memoria."
  exit 1
fi
# la app no está firmada por Apple: se le quita la marca de «descargado de internet»
xattr -dr com.apple.quarantine macos 2>/dev/null
./macos/Cloto.app/Contents/MacOS/Cloto --instalar
