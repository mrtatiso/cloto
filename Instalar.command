#!/bin/sh
# Pone Cloto en Aplicaciones y en el escritorio de ESTA computadora. La app y tus proyectos se quedan en la memoria CLOTO.
cd "$(dirname "$0")"
# la app no está firmada por Apple: se le quita la marca de «descargado de internet»
xattr -dr com.apple.quarantine macos 2>/dev/null
./macos/Cloto.app/Contents/MacOS/Cloto --instalar
