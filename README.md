<img width="1200" height="400" alt="CLOTO" src="https://github.com/user-attachments/assets/5922c609-2673-4b01-9a12-f577922b01b0" />

Ideas, cajas de texto, imágenes, vídeos, PDF, enlaces y cuerdas.
Cada proyecto es un solo archivo `.cloto` con todo dentro. Se puede proteger con contraseña.

## La app de escritorio

Se descarga como una carpeta portátil:

```
Cloto/
  Cloto.exe · Cloto.app · Cloto      la app
  Instalar.bat · Instalar.command · instalar.sh
  proyectos/
    <proyecto>.cloto                 el proyecto completo (con contraseña: cifrado)
    exportados/                      PNG, SVG y Markdown que exportes
```

### Insertar imágenes y archivos

Tres caminos, por si uno falla en tu sistema:

- **Pegar** (`Ctrl/⌘ + V`): imágenes copiadas de cualquier parte (captura de pantalla, página web, otro programa), enlaces y texto.
- **Clic derecho en el lienzo → Insertar imagen o archivo**: *Pegar del portapapeles* (lee el portapapeles directamente, sin depender de `Ctrl+V`), *Elegir archivos* (en la app el selector empieza en la carpeta `assets/` junto a tus proyectos, que se crea sola) y *Abrir la carpeta assets*.
- **Arrastrar** el archivo al lienzo.

En la app, si el visor no deja leer el portapapeles, Cloto lo pide al sistema: PowerShell en Windows, `osascript` en macOS, `wl-paste` o `xclip` en Linux (instálalo si no lo tienes).

### Tags y cajas en el hilo

Un hilo conecta bloques de texto. **Doble clic en el tercio central** de un hilo crea un **tag**: un peso que parte el hilo en dos, y cada mitad conserva el largo que tenía hasta el tag. Puedes poner otro tag en medio de cualquiera de esas mitades, y en medio de esas otras, y así sucesivamente.

**Doble clic en los tercios de las orillas** crea, en ese punto, una **caja de texto** que parte el hilo: según dónde cortes, cada tramo queda con su largo y puedes seguir extendiendo desde la caja. Si dejas el tag o la caja vacíos, el hilo se vuelve a unir.

### Borrar sin deshacer el hilo

Cada hilo une los elementos que toca, sean cajas o pesos (las etiquetas de los hilos). Al borrar uno, el hilo se rehace uniendo a los demás:

- en una cadena A — B — C, si borras B, A y C quedan unidos;
- si borras una caja de un hilo con etiqueta, el hilo sigue entre la etiqueta y la otra caja: la etiqueta se vuelve un **peso** suelto, una caja de texto pequeña que puedes mover y editar;
- los pesos **cuelgan como en un resorte**: tienen masa, caen, estiran el hilo y rebotan hasta asentarse. El hilo conserva el largo que tenía hasta el peso y vuelve a él en cuanto lo sueltas. Un peso sin ningún hilo se queda donde está hasta que lo borres;
- si vacías el texto de un peso o lo borras, sus vecinos se unen entre sí.

En el archivo, el peso suelto es un nodo con `"w": true`.

## En una memoria USB

La forma pensada para llevar Cloto a cualquier computadora: la app y los proyectos viven en una memoria llamada **CLOTO**, y cada computadora solo guarda un acceso directo.

1. Descarga `Cloto-USB.zip` de *Releases* (trae las versiones de Windows, macOS y Linux).
2. Llama **CLOTO** a la memoria (exFAT) y copia el contenido del zip en su raíz: `windows/`, `macos/`, `linux/`, `proyectos/` y los instaladores.
3. En cada computadora ejecuta el instalador de ese sistema (`Instalar.bat`, `Instalar.command` o `instalar.sh`). Desde entonces basta el acceso directo.

Cómo funciona:

- La instalación no pide administrador: solo escribe en carpetas del usuario (acceso directo, icono y un lanzador pequeño).
- El acceso directo no apunta a la app sino al lanzador, que abre Cloto donde se instaló y, si esa ruta ya no existe (la memoria apareció con otra letra o puerto), busca el volumen llamado `CLOTO`.
- **Seguridad del lanzador:** al instalar se guarda en la memoria un identificador aleatorio (`.cloto-id`) y en la computadora su copia. El lanzador solo abre una memoria que lo tenga, así que otra memoria que también se llame `CLOTO` no puede hacerle correr un programa ajeno.
- Los proyectos van en `CLOTO/proyectos/`. La carpeta elegida se guarda relativa a la memoria, así que sigue valiendo en otra computadora.
- Windows y macOS crean el acceso directo con las herramientas del propio sistema (PowerShell y Finder); Linux crea un `.desktop`. Quitar: `Desinstalar.bat` / `.command` / `desinstalar.sh`.

## El archivo .cloto

Un `.cloto` es un ZIP con:

```
cloto.json        el mapa: cajas, hilos, islas, posiciones
assets/…          imágenes, vídeos, audio, PDF y capturas de enlaces
```

Con contraseña, ese ZIP va cifrado:

```
«CLOTOENC» · versión (1) · vueltas (uint32) · salt (16 bytes) · iv (12 bytes) · AES-256-GCM(zip)
```

- La llave se obtiene de la contraseña con **PBKDF2-SHA256** (600 000 vueltas) y un **salt** aleatorio por proyecto. Así la misma contraseña da llaves distintas en cada proyecto, y probar contraseñas a ciegas toma muchísimo tiempo.
- **AES-256-GCM** cifra el contenido y además detecta cualquier alteración del archivo. La cabecera también va autenticada.
- Cada guardado usa un iv nuevo. La contraseña nunca se guarda: en memoria solo queda la llave, que no se puede exportar.
- Todo lo hace el propio navegador (WebCrypto). No hay librerías externas.
- **Contraseña olvidada = proyecto perdido.** No existe forma de recuperarlo.

Los `.cloto` de versiones anteriores (JSON, o carpeta con `assets/`) se abren igual y se convierten al guardar.

«Instalar» solo pone el icono del nudo en el escritorio y en el menú de aplicaciones. La app no se mueve de su carpeta, y para llevártela a otra computadora basta con copiar la carpeta entera.

### Cómo funciona

```
Cloto (cloto.py, compilado con PyInstaller)
 ├─ servidor local en 127.0.0.1:47821, que sirve cloto.html y una API mínima de archivos
 │    /api/fs/stat · read · write · mkdir        solo dentro de la carpeta de proyectos
 │    /api/dialog/open · dialog/folder           diálogos del sistema
 │    /api/open-url · reveal                     abrir enlaces y archivos con el sistema
 └─ ventana: pywebview (WebView2 en Windows, WebKit en macOS)
             sin pywebview: Chrome, Edge o Chromium en modo app; si no hay ninguno, el navegador
```

`cloto.html` detecta el modo en que corre:

| Modo | Cómo se detecta | Proyectos |
|---|---|---|
| App de escritorio | el lanzador inyecta `window.CLOTO_DESKTOP` | carpeta `proyectos/` sin pedir permisos |
| Prueba en línea | se sirve por https | se guarda y se abre `.cloto` (con los archivos dentro) |
| Archivo local | se abre `cloto.html` con doble clic | carpeta con la API del navegador (Chrome y Edge) |

## Seguridad

**La app (servidor local)**
- Solo escucha en `127.0.0.1` y solo atiende a quien la llama por ese nombre (`Host` y `Origin`). Eso bloquea el *DNS rebinding*, en el que una página web se hace pasar por tu computadora.
- La ventana entra con una llave de un solo uso y luego usa una cookie privada (`HttpOnly`, `SameSite=Strict`). Otros programas de tu computadora no obtienen el token pidiendo la página.
- Cada operación con archivos exige un token secreto en una cabecera propia (`X-Cloto`), que otras páginas web no pueden enviar.
- Ninguna ruta puede salir de la carpeta de proyectos (`..` y enlaces simbólicos se resuelven y se rechazan). Las escrituras tienen tope de tamaño y se reemplazan de golpe: nunca queda un archivo a medias.
- Los archivos que se abren con un programa del sistema se copian a una carpeta temporal privada, que se borra al cerrar.

**La página (cloto.html)**
- Política de seguridad de contenido (CSP): no se carga código de ningún otro lado, ni objetos incrustados ni formularios.
- Los proyectos ajenos se limpian al abrirse: ids, nombres de archivo (sin rutas ni nombres reservados), colores y enlaces (solo `http`/`https`).
- El lector de `.cloto` solo extrae `cloto.json` y `assets/<nombre>`, y tiene límites contra archivos inflados («bombas ZIP»).
- El tipo de cada archivo lo decide Cloto por su extensión, nunca el archivo. Un `.html` o `.svg` nunca se abre como página (podría traer código): se descarga o lo abre el sistema.
- Las páginas web del visor corren aisladas (`sandbox`).
- Con contraseña, en el navegador no queda nada legible: ni el mapa ni copias de los archivos. Las vistas previas de enlaces solo se piden si tú lo haces.

**Publicación (GitHub Actions)**
- Permisos mínimos: compilar solo lee y solo el paso de publicar escribe.
- La versión de la etiqueta se valida (`1.2.3` o `1.2.3-beta.1`), así que una etiqueta no puede colar código.

**Lo que no cubre**
- Un programa malicioso ya instalado en tu computadora puede ver lo que tengas abierto, igual que con cualquier otra app. El cifrado protege el archivo guardado (si pierdes la laptop, una USB o algo en la nube), no lo que está abierto en pantalla.
- Las vistas previas de enlaces envían la dirección a microlink.io.

## Desarrollo

```sh
pip install pywebview          # opcional: ventana nativa
python3 cloto.py               # abre la app
python3 cloto.py --servidor    # solo el servidor
python3 cloto.py --instalar    # icono apuntando al código fuente
```

Compilar en tu sistema:

```sh
pip install pyinstaller pywebview
pyinstaller cloto.spec         # dist/Cloto(.exe) · dist/Cloto.app
```

El icono se genera con `python3 icono/nudo.py`, que produce el SVG. Los PNG, ICO e ICNS se exportan a partir de él.

## Publicar

1. Sube el repositorio a GitHub.
2. **Versión en línea:** en *Settings → Pages → Source* elige «GitHub Actions». Cada cambio en `main` publica `cloto.html`.
3. **App:** crea una etiqueta de versión y GitHub compila los tres sistemas y los sube a *Releases*:
   ```sh
   git tag v1.0.0
   git push origin v1.0.0
   ```

El enlace «descargar la app» de la versión en línea se completa solo con el nombre del repositorio (`__CLOTO_REPO__`).

### Notas

- **macOS:** la app no está firmada por Apple. La primera vez hay que abrirla con clic derecho → Abrir, o usar `Instalar.command`, que le quita la marca de «descargado de internet». Para firmarla y notarizarla hace falta una cuenta de desarrollador de Apple.
- **Windows:** sin firma de código, SmartScreen puede avisar la primera vez («Más información → Ejecutar de todas formas»).
- **Linux:** el binario (`Cloto-linux.tar.gz`) usa Chrome o Chromium en modo app, o tu navegador. En la memoria USB, Linux va como código más un script (`linux/Cloto`): tu computadora hace de intérprete y abre la misma ventana de `python3 cloto.py`. Necesita `python3`; para la ventana propia, `pywebview` y WebKitGTK (`python3-gi`).
