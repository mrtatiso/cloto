#!/bin/sh
# Pone Cloto en Aplicaciones y en el escritorio. La app se queda en esta carpeta.
cd "$(dirname "$0")"
# la app no está firmada por Apple: se le quita la marca de «descargado de internet»
xattr -dr com.apple.quarantine . 2>/dev/null
./Cloto.app/Contents/MacOS/Cloto --instalar
