#!/bin/sh
# Quita de ESTA computadora los accesos de Cloto. No toca la memoria ni tus proyectos.
cd "$(dirname "$0")" && ./linux/Cloto --desinstalar
