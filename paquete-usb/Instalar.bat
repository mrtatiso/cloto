@echo off
rem Pone Cloto en el escritorio y en el menu Inicio de ESTA computadora.
rem La app y tus proyectos se quedan en la memoria CLOTO.
if not exist "%~dp0windows\Cloto.exe" (
  echo No encuentro windows\Cloto.exe junto a este instalador.
  echo Esta carpeta es el codigo fuente: el programa lo compila GitHub Actions.
  echo Descarga el artefacto cloto-usb o Cloto-USB.zip de Releases y copia el contenido
  echo de la carpeta CLOTO a la raiz de la memoria.
  pause
  exit /b 1
)
"%~dp0windows\Cloto.exe" --instalar
