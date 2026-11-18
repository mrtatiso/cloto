#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cloto de escritorio
===================
Un servidor local diminuto sirve cloto.html y le da acceso directo a la carpeta de proyectos
(sin los permisos del navegador). Una ventana propia lo muestra como app.

    Cloto                     abre Cloto
    Cloto --instalar          pone el icono en el escritorio y en el menú de aplicaciones
    Cloto --desinstalar       quita esos iconos (no toca tus proyectos)
    Cloto --carpeta RUTA      usa otra carpeta de proyectos (se recuerda)
    Cloto --servidor          solo el servidor; abre la dirección en tu navegador

Seguridad
    · el servidor solo escucha dentro de tu computadora (127.0.0.1) y solo atiende a quien lo llama por ese nombre
    · la ventana entra con una llave de un solo uso; luego una cookie privada (otros programas no obtienen el token)
    · cada operación con archivos exige un token secreto en una cabecera propia (otras páginas web no pueden enviarla)
    · ninguna ruta puede salir de la carpeta de proyectos

Desde el código fuente:  python3 cloto.py  (con «pip install pywebview» para la ventana propia;
sin pywebview usa Chrome, Edge o Chromium en modo app, y si no hay, tu navegador).

La carpeta queda así:
    Cloto/                      (donde pongas la app)
      Cloto(.exe)
      proyectos/
        <proyecto>.cloto        el proyecto completo: el mapa y sus imágenes, vídeos, PDF… (con contraseña, cifrado)
        exportados/             PNG, SVG y Markdown que exportes
"""
import argparse
import atexit
import json
import mimetypes
import os
import platform
import queue
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

APP = 'Cloto'
VERSION = '1.0.0'
PORT = 47821                      # fijo: así el navegador interno recuerda el último mapa entre sesiones
MAX_WRITE = 5 * 1024 ** 3          # un .cloto no pasa de 4 GB (límite del formato)
SYSTEM = platform.system()        # 'Windows' · 'Darwin' · 'Linux'
FROZEN = getattr(sys, 'frozen', False)
RES = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))      # cloto.html e icono/

for ext, typ in {'.cloto': 'application/json', '.laquesis': 'application/json', '.atropos': 'application/json',
                 '.webm': 'video/webm', '.mkv': 'video/x-matroska', '.mp4': 'video/mp4', '.m4v': 'video/mp4', '.mov': 'video/quicktime',
                 '.m4a': 'audio/mp4', '.opus': 'audio/ogg', '.flac': 'audio/flac', '.webp': 'image/webp', '.avif': 'image/avif',
                 '.heic': 'image/heic', '.svg': 'image/svg+xml', '.md': 'text/markdown', '.pdf': 'application/pdf'}.items():
    mimetypes.add_type(typ, ext)


# ---------------------------------------------------------------- rutas
def app_dir() -> Path:
    """La carpeta donde vive la app (portátil: todo junto)."""
    if FROZEN:
        exe = Path(sys.executable).resolve()
        if SYSTEM == 'Darwin' and exe.parent.name == 'MacOS' and len(exe.parents) > 2 and exe.parents[1].parent.suffix == '.app':
            return exe.parents[2].parent          # …/Cloto/Cloto.app/Contents/MacOS/Cloto  →  …/Cloto
        return exe.parent
    return Path(__file__).resolve().parent


def writable(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
        t = d / ('.cloto-%s' % secrets.token_hex(4))
        t.write_text('x'); t.unlink()
        return True
    except Exception:
        return False


def user_dir() -> Path:
    if SYSTEM == 'Windows':
        return Path(os.environ.get('APPDATA') or Path.home()) / APP
    if SYSTEM == 'Darwin':
        return Path.home() / 'Library' / 'Application Support' / APP
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'cloto'


def documents() -> Path:
    for n in ('Documents', 'Documentos'):
        if (Path.home() / n).is_dir():
            return Path.home() / n
    return Path.home()


HERE = app_dir()
PORTABLE = writable(HERE) and not str(HERE).startswith('/private/var/folders')     # macOS mueve apps sin firmar a una carpeta temporal
DATA = HERE if PORTABLE else user_dir()                                           # config, perfil del navegador, registro
CONFIG = DATA / 'cloto.json'
LOG = DATA / 'cloto.log'


def log(*a):
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > 1024 * 1024:
            LOG.replace(LOG.with_suffix('.log.1'))
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + ' '.join(str(x) for x in a) + '\n')
    except Exception:
        pass


def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text('utf-8'))
    except Exception:
        return {}


def save_config(c: dict):
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(c, indent=2, ensure_ascii=False), 'utf-8')
    except Exception as e:
        log('config', e)


OS_DIR = {'Windows': 'windows', 'Darwin': 'macos'}.get(SYSTEM, 'linux')


def usb_root():
    """Si la app está en el paquete USB (CLOTO/windows, CLOTO/macos o CLOTO/linux junto a CLOTO/proyectos), la raíz de la memoria."""
    p = HERE.parent
    return p if HERE.name == OS_DIR and (p / 'proyectos').is_dir() else None


def base_dir() -> Path:
    """Lo que viaja junto: la memoria USB entera, o la carpeta de la app."""
    return usb_root() or HERE


def default_root() -> Path:
    if usb_root():
        return usb_root() / 'proyectos'
    return HERE / 'proyectos' if PORTABLE else documents() / 'Cloto'


def configured_root(c):
    """La carpeta de proyectos elegida. Si está dentro de la app/memoria se guarda relativa: cambiar la letra de la unidad no la rompe."""
    try:
        if c.get('proyectos_rel') is not None:
            p = (base_dir() / c['proyectos_rel']).resolve()
            return p if str(p).startswith(str(base_dir().resolve())) else None
        if c.get('proyectos'):
            return Path(c['proyectos']).expanduser()
    except Exception:
        pass
    return None


class State:
    root: Path = default_root()
    token = secrets.token_urlsafe(32)          # para la API (lo recibe solo la página de Cloto)
    session = secrets.token_urlsafe(32)        # cookie privada de la ventana
    launch_key = secrets.token_urlsafe(24)     # llave de un solo uso con la que entra la ventana
    base_url = ''
    chrome = None                 # Chrome/Edge en modo app, si se usa
    window = None                 # ventana de pywebview, si la hay
    tmp = None                    # carpeta temporal privada para abrir archivos con el sistema
    picked: dict = {}             # archivos elegidos en el selector, a la espera de que la página los recoja (una vez)
    tasks: 'queue.Queue' = queue.Queue()      # trabajos que deben correr en el hilo principal (diálogos con tk)


S = State()


def launch_url():
    """Dirección con una llave nueva de un solo uso."""
    S.launch_key = secrets.token_urlsafe(24)
    return S.base_url + '?k=' + S.launch_key


def temp_dir() -> Path:
    if S.tmp is None:
        S.tmp = Path(tempfile.mkdtemp(prefix='cloto-'))      # solo tu usuario puede leerla
        atexit.register(shutil.rmtree, S.tmp, True)
    return S.tmp


def safe_file_name(n: str) -> str:
    n = ''.join('_' if (c in '\\/:*?"<>|' or ord(c) < 32) else c for c in str(n)).strip(' .')[:120]
    return n or 'archivo'


def set_root(p: Path):
    p = Path(p).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    S.root = p
    c = load_config(); c.pop('proyectos', None); c.pop('proyectos_rel', None)
    try:
        c['proyectos_rel'] = p.relative_to(base_dir().resolve()).as_posix()
    except ValueError:
        c['proyectos'] = str(p)
    save_config(c)


# ---------------------------------------------------------------- abrir cosas con el sistema
def open_with_system(p: Path, reveal=False):
    try:
        if SYSTEM == 'Windows':
            if reveal and p.is_file():
                subprocess.Popen(['explorer', '/select,', str(p)])
            else:
                os.startfile(str(p))  # type: ignore[attr-defined]
        elif SYSTEM == 'Darwin':
            subprocess.Popen(['open', '-R', str(p)] if reveal and p.is_file() else ['open', str(p)])
        else:
            subprocess.Popen(['xdg-open', str(p.parent if reveal and p.is_file() else p)])
    except Exception as e:
        log('abrir', p, e)


# ---------------------------------------------------------------- diálogos del sistema
CLOTO_TYPES = ('Cloto (*.cloto;*.laquesis;*.atropos;*.json)', 'Todos los archivos (*.*)')


def _tk_dialog(kind):
    import tkinter as tk
    from tkinter import filedialog
    r = tk.Tk(); r.withdraw()
    try:
        r.attributes('-topmost', True)
    except Exception:
        pass
    try:
        if kind == 'pick':
            return list(filedialog.askopenfilenames(parent=r, title='Insertar archivos', initialdir=str(assets_dir()))) or None
        if kind == 'open':
            return filedialog.askopenfilename(parent=r, title='Abrir proyecto', initialdir=str(S.root),
                                              filetypes=[('Cloto', '*.cloto *.laquesis *.atropos *.json'), ('Todos', '*.*')]) or None
        return filedialog.askdirectory(parent=r, title='Carpeta de proyectos', initialdir=str(S.root), mustexist=False) or None
    finally:
        r.destroy()


def assets_dir():
    """La carpeta «assets» junto a los proyectos: donde conviene guardar imágenes y archivos para insertarlos."""
    p = S.root / 'assets'
    try:
        p.mkdir(exist_ok=True)
    except Exception:
        return S.root
    return p


PNG_SIG = b'\x89PNG\r\n\x1a\n'


def clip_image():
    """Una imagen del portapapeles como PNG (bytes), o None. Respaldo para cuando la ventana no deja leerla con Ctrl+V."""
    out = temp_dir() / ('portapapeles-' + secrets.token_hex(4) + '.png')
    try:
        if SYSTEM == 'Windows':
            ps = ("Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; "
                  "$i=[System.Windows.Forms.Clipboard]::GetImage(); if($i){$i.Save('%s',[System.Drawing.Imaging.ImageFormat]::Png)}" % str(out).replace("'", "''"))
            subprocess.run(['powershell', '-NoProfile', '-STA', '-NonInteractive', '-Command', ps], timeout=8, capture_output=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        elif SYSTEM == 'Darwin':
            subprocess.run(['osascript', '-e', 'set d to the clipboard as «class PNGf»',
                            '-e', 'set f to open for access POSIX file "%s" with write permission' % out,
                            '-e', 'write d to f', '-e', 'close access f'], timeout=8, capture_output=True)
        else:
            for cmd in (['wl-paste', '--type', 'image/png'], ['xclip', '-selection', 'clipboard', '-t', 'image/png', '-o']):
                if shutil.which(cmd[0]):
                    r = subprocess.run(cmd, timeout=8, capture_output=True)
                    if r.returncode == 0 and r.stdout.startswith(PNG_SIG):
                        return r.stdout
        data = out.read_bytes() if out.exists() else b''
        return data if data.startswith(PNG_SIG) else None
    except Exception as e:
        log('portapapeles', e)
        return None
    finally:
        try:
            out.unlink(missing_ok=True)
        except Exception:
            pass


def dialog(kind):
    """kind: 'open' (un .cloto), 'folder' o 'pick' (varios archivos, empieza en assets). Devuelve una ruta, una lista (pick) o None."""
    if S.window is not None:
        import webview
        fd = getattr(webview, 'FileDialog', None)
        if kind == 'pick':
            t = fd.OPEN if fd else webview.OPEN_DIALOG
            r = S.window.create_file_dialog(t, directory=str(assets_dir()), allow_multiple=True)
            return list(r) if r else None
        if kind == 'open':
            t = fd.OPEN if fd else webview.OPEN_DIALOG
            r = S.window.create_file_dialog(t, directory=str(S.root), allow_multiple=False, file_types=CLOTO_TYPES)
        else:
            t = fd.FOLDER if fd else webview.FOLDER_DIALOG
            r = S.window.create_file_dialog(t, directory=str(S.root))
        if not r:
            return None
        return r if isinstance(r, str) else r[0]
    # sin ventana propia: tk, en el hilo principal
    done: 'queue.Queue' = queue.Queue()
    S.tasks.put((lambda: _tk_dialog(kind), done))
    try:
        return done.get(timeout=600)
    except queue.Empty:
        return None


# ---------------------------------------------------------------- servidor
class Handler(BaseHTTPRequestHandler):
    server_version = 'Cloto/' + VERSION
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def send(self, code, body=b'', ctype='application/json; charset=utf-8', extra=None):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def json(self, obj, code=200):
        self.send(code, json.dumps(obj, ensure_ascii=False).encode('utf-8'))

    def authed(self):            # otras páginas web no pueden enviar esta cabecera: solo Cloto toca tus archivos
        return secrets.compare_digest(self.headers.get('X-Cloto', ''), S.token)

    def has_session(self):
        try:
            c = SimpleCookie(self.headers.get('Cookie', ''))
            return 'cloto' in c and secrets.compare_digest(c['cloto'].value, S.session)
        except Exception:
            return False

    def local_host(self):
        """Solo se atiende a quien llama a este servidor por su nombre local. Bloquea el «DNS rebinding»:
        una página como malo.com que se hace pasar por 127.0.0.1 para leer la página (y el token) desde su propio dominio."""
        port = self.server.server_address[1]
        if self.headers.get('Host', '') not in ('127.0.0.1:%d' % port, 'localhost:%d' % port):
            return False
        origin = self.headers.get('Origin')
        return origin is None or origin in ('http://127.0.0.1:%d' % port, 'http://localhost:%d' % port)

    def parse_request(self):
        ok = super().parse_request()
        if ok and not self.local_host():
            self.send_error(403); return False
        return ok

    def target(self, rel: str) -> Path:
        rel = (rel or '').replace('\\', '/').strip('/')
        root = S.root.resolve()
        p = (root / rel).resolve()
        if p != root and root not in p.parents:
            raise PermissionError(rel)
        return p

    def body(self) -> bytes:
        n = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(n) if n else b''

    # --- GET
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        try:
            if u.path in ('/', '/index.html'):
                k = q.get('k', [''])[0]
                fresh = bool(S.launch_key and k and secrets.compare_digest(k, S.launch_key))
                if not fresh and not self.has_session():          # otro programa pidiendo la página: no recibe el token
                    self.send(403, '<meta charset="utf-8"><p style="font:14px sans-serif;color:#888">Abre Cloto desde su icono.</p>'.encode('utf-8'), 'text/html; charset=utf-8')
                    return
                if fresh:
                    S.launch_key = None                            # la llave sirve una sola vez
                html = (RES / 'cloto.html').read_text('utf-8')
                info = {'token': S.token, 'root': str(S.root), 'name': S.root.name, 'version': VERSION, 'os': SYSTEM}
                js = json.dumps(info, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
                tag = '<script id="cloto-desk">window.CLOTO_DESKTOP=%s;</script>' % js
                extra = {'Content-Security-Policy': "frame-ancestors 'none'", 'Referrer-Policy': 'strict-origin-when-cross-origin'}
                if fresh:
                    extra['Set-Cookie'] = 'cloto=%s; HttpOnly; SameSite=Strict; Path=/' % S.session
                self.send(200, html.replace('<script>', tag + '<script>', 1).encode('utf-8'), 'text/html; charset=utf-8', extra)
                return
            if u.path in ('/icono.png', '/favicon.ico'):
                self.send(200, (RES / 'icono' / 'cloto-256.png').read_bytes(), 'image/png')
                return
            if u.path == '/api/ping':
                self.json({'app': 'cloto', 'version': VERSION})
                return
            if not u.path.startswith('/api/'):
                self.send(404, b'{}'); return
            if not self.authed():
                self.send(403, b'{}'); return
            if u.path == '/api/picked':                           # un archivo que elegiste en el selector: se entrega una sola vez
                f = S.picked.pop(q.get('id', [''])[0], None)
                if not f or not f.is_file():
                    self.send(404, b'{}'); return
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', str(f.stat().st_size))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                with open(f, 'rb') as fh:
                    shutil.copyfileobj(fh, self.wfile, 1 << 20)
                return
            p = self.target(q.get('path', [''])[0])
            if u.path == '/api/fs/stat':
                if not p.exists():
                    self.json({'kind': None}); return            # no existe (sin 404: es una pregunta normal)
                self.json({'kind': 'directory' if p.is_dir() else 'file', 'size': p.stat().st_size})
            elif u.path == '/api/fs/read':
                if not p.is_file():
                    self.send(404, b'{}'); return
                size = p.stat().st_size
                self.send_response(200)
                self.send_header('Content-Type', mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
                self.send_header('Content-Length', str(size))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                with open(p, 'rb') as f:
                    shutil.copyfileobj(f, self.wfile, 1 << 20)
            else:
                self.send(404, b'{}')
        except PermissionError:
            self.send(403, b'{}')
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            log('GET', self.path, e, traceback.format_exc()); self.send(500, b'{}')

    def do_HEAD(self):
        self.do_GET()

    # --- PUT: escribir un archivo (por partes, y se reemplaza de golpe: nunca queda a medias)
    def do_PUT(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        try:
            if u.path not in ('/api/fs/write', '/api/open-temp') or not self.authed():
                self.send(403, b'{}'); return
            left = int(self.headers.get('Content-Length') or 0)
            if left < 0 or left > MAX_WRITE:
                self.send(413, b'{}'); return
            if u.path == '/api/open-temp':                        # abrir un archivo del proyecto con el programa del sistema
                p = temp_dir() / secrets.token_hex(4) / safe_file_name(q.get('name', ['archivo'])[0])
            else:
                p = self.target(q.get('path', [''])[0])
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(p.name + '.parcial')
            with open(tmp, 'wb') as f:
                while left > 0:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        break
                    f.write(chunk); left -= len(chunk)
            if left > 0:
                tmp.unlink(missing_ok=True); self.send(400, b'{}'); return
            os.replace(tmp, p)
            if u.path == '/api/open-temp':
                open_with_system(p)
            self.json({'ok': True})
        except PermissionError:
            self.send(403, b'{}')
        except Exception as e:
            log('PUT', self.path, e, traceback.format_exc()); self.send(500, b'{}')

    # --- POST: carpetas, diálogos y abrir cosas
    def do_POST(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        try:
            if u.path == '/api/focus':                            # otra copia de Cloto pide traer la ventana al frente
                bring_to_front(); self.json({'ok': True}); return
            if not u.path.startswith('/api/') or not self.authed():
                self.send(403, b'{}'); return
            if u.path == '/api/fs/mkdir':
                p = self.target(q.get('path', [''])[0])
                if p.exists() and not p.is_dir():
                    self.send(409, b'{}'); return
                p.mkdir(parents=True, exist_ok=True)
                self.json({'kind': 'directory'}); return
            data = {}
            raw = self.body()
            if raw:
                try:
                    data = json.loads(raw.decode('utf-8'))
                except Exception:
                    data = {}
            op = u.path[5:]
            if op == 'dialog/open':
                path = dialog('open')
                if not path or not Path(path).is_file():
                    self.send(204); return
                f = Path(path)
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', str(f.stat().st_size))
                self.send_header('X-Cloto-Name', quote(f.name))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                with open(f, 'rb') as fh:
                    shutil.copyfileobj(fh, self.wfile, 1 << 20)
            elif op == 'dialog/pick':
                paths = dialog('pick') or []
                out = []
                for pth in paths[:200]:
                    f = Path(pth)
                    if f.is_file():
                        i = secrets.token_hex(6)
                        S.picked[i] = f
                        out.append({'id': i, 'name': f.name, 'size': f.stat().st_size, 'mime': mimetypes.guess_type(f.name)[0] or ''})
                if not out:
                    self.send(204); return
                self.json(out)
            elif op == 'clipboard':
                png = clip_image()
                if not png:
                    self.send(204); return
                self.send(200, png, 'image/png')
            elif op == 'dialog/folder':
                path = dialog('folder')
                if not path:
                    self.json({}); return
                set_root(Path(path))
                self.json({'root': str(S.root), 'name': S.root.name})
            elif op == 'open-url':
                url = str(data.get('url', ''))
                if url.startswith(('http://', 'https://')):
                    webbrowser.open(url)
                self.json({'ok': True})
            elif op == 'reveal':
                if str(data.get('path', '')) == 'assets':
                    assets_dir()
                p = self.target(str(data.get('path', '')))
                if not p.exists():
                    p = S.root
                open_with_system(p, reveal=not data.get('open'))
                self.json({'ok': True})
            else:
                self.send(404, b'{}')
        except PermissionError:
            self.send(403, b'{}')
        except Exception as e:
            log('POST', self.path, e, traceback.format_exc()); self.send(500, b'{}')


def bring_to_front():
    try:
        if S.window is not None:
            S.window.restore(); S.window.show()
        elif S.chrome:
            subprocess.Popen([S.chrome, '--app=' + launch_url(), '--user-data-dir=' + str(DATA / 'navegador-chromium')])
        else:
            webbrowser.open(launch_url())
    except Exception as e:
        log('frente', e)


def ping(port) -> bool:
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d/api/ping' % port, timeout=0.6) as r:
            return json.loads(r.read().decode()).get('app') == 'cloto'
    except Exception:
        return False


def start_server():
    """Devuelve (url, servidor). Si Cloto ya corre, (url, None): se abre otra ventana del mismo."""
    for port in (PORT, 0):
        try:
            srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
            srv.daemon_threads = True
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            S.base_url = 'http://127.0.0.1:%d/' % srv.server_address[1]
            return S.base_url, srv
        except OSError:
            if port == PORT and ping(PORT):
                return 'http://127.0.0.1:%d/' % PORT, None
    raise SystemExit('No se pudo abrir el servidor local')


# ---------------------------------------------------------------- ventana
def find_chromium():
    cands = []
    if SYSTEM == 'Windows':
        for base in (os.environ.get('PROGRAMFILES(X86)'), os.environ.get('PROGRAMFILES'), os.environ.get('LOCALAPPDATA')):
            if base:
                cands += [Path(base) / 'Microsoft/Edge/Application/msedge.exe', Path(base) / 'Google/Chrome/Application/chrome.exe',
                          Path(base) / 'BraveSoftware/Brave-Browser/Application/brave.exe']
    elif SYSTEM == 'Darwin':
        cands = [Path('/Applications') / a for a in ('Google Chrome.app/Contents/MacOS/Google Chrome', 'Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
                                                     'Chromium.app/Contents/MacOS/Chromium', 'Brave Browser.app/Contents/MacOS/Brave Browser')]
    else:
        cands = [shutil.which(n) for n in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'microsoft-edge', 'brave-browser')]
    for c in cands:
        if c and Path(c).exists():
            return str(c)
    return None


def main_loop(until=lambda: False):
    """Hilo principal: atiende diálogos (tk) hasta que se cierre la ventana."""
    try:
        while not until():
            try:
                fn, done = S.tasks.get(timeout=0.3)
            except queue.Empty:
                continue
            try:
                done.put(fn())
            except Exception as e:
                log('diálogo', e); done.put(None)
    except KeyboardInterrupt:
        pass


def open_window(url, server_only=False):
    if not server_only and not os.environ.get('CLOTO_SIN_WEBVIEW'):
        try:
            import webview                                        # pywebview: ventana nativa (WebView2 · WebKit)
            try:
                webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True
            except Exception:
                pass
            S.window = webview.create_window(APP, url, width=1280, height=820, min_size=(640, 420),
                                             background_color='#f4f4f6', text_select=True)
            kw = {'private_mode': False, 'storage_path': str(DATA / 'navegador')}
            try:
                webview.start(icon=str(RES / 'icono' / 'cloto-256.png'), **kw)
            except TypeError:
                webview.start(**kw)
            return
        except ImportError:
            pass
        except Exception as e:
            log('pywebview', e, traceback.format_exc()); S.window = None
    exe = None if server_only else find_chromium()
    if exe:                                                       # Chrome / Edge en modo app: ventana sin pestañas ni barra
        S.chrome = exe
        p = subprocess.Popen([exe, '--app=' + url, '--user-data-dir=' + str(DATA / 'navegador-chromium'), '--no-first-run',
                              '--no-default-browser-check', '--window-size=1280,820', '--class=Cloto'])
        main_loop(until=lambda: p.poll() is not None)
        return
    print('Cloto está en ' + url + '  (ábrela una vez; Ctrl+C para cerrar)', flush=True)
    if not server_only:
        webbrowser.open(url)
    main_loop()


# ---------------------------------------------------------------- instalar: icono en escritorio y menú
def launcher():
    """(programa, argumentos) que abre Cloto, desde el binario o desde el código."""
    if FROZEN:
        return sys.executable, []
    py = Path(sys.executable)
    if SYSTEM == 'Windows' and (py.parent / 'pythonw.exe').exists():
        py = py.parent / 'pythonw.exe'
    return str(py), [str(Path(__file__).resolve())]


def desktop_dir() -> Path:
    if SYSTEM == 'Linux' and shutil.which('xdg-user-dir'):
        try:
            d = subprocess.run(['xdg-user-dir', 'DESKTOP'], capture_output=True, text=True).stdout.strip()
            if d:
                return Path(d)
        except Exception:
            pass
    for n in ('Desktop', 'Escritorio'):
        if (Path.home() / n).is_dir():
            return Path.home() / n
    return Path.home() / 'Desktop'


def aviso(msg):
    print(msg)
    try:
        if SYSTEM == 'Windows':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, APP, 0x40)
        elif SYSTEM == 'Darwin':
            subprocess.run(['osascript', '-e', 'display dialog %s with title "Cloto" buttons {"OK"} default button 1' % json.dumps(msg)], capture_output=True)
        elif not sys.stdout.isatty() and shutil.which('zenity'):
            subprocess.run(['zenity', '--info', '--title=Cloto', '--text=' + msg], capture_output=True)
    except Exception:
        pass


def ps_quote(s):
    return "'" + str(s).replace("'", "''") + "'"


def mount_root(p: Path) -> Path:
    p = Path(p).resolve()
    if SYSTEM == 'Windows':
        return Path(p.anchor)
    while not os.path.ismount(p) and p.parent != p:
        p = p.parent
    return p


def local_dir() -> Path:
    """Lo único que se queda en ESTA computadora: el lanzador y el icono."""
    if SYSTEM == 'Windows':
        return Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local') / 'Cloto' / 'lanzador'
    if SYSTEM == 'Darwin':
        return Path.home() / 'Library' / 'Application Support' / 'Cloto' / 'lanzador'
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share') / 'cloto' / 'lanzador'


def sh_quote(s):
    import shlex
    return shlex.quote(str(s))


NO_MEMORIA = 'Conecta la memoria CLOTO y vuelve a abrir Cloto.'


def usb_id():
    """Identificador aleatorio que vive en la carpeta de la app (o en la raíz de la memoria). El lanzador solo abre una memoria que lo tenga:
    otra memoria que también se llame CLOTO no sirve para que corra un programa ajeno."""
    f = base_dir() / '.cloto-id'
    try:
        v = f.read_text('utf-8').strip() if f.exists() else ''
        if not (len(v) >= 32 and all(ch in '0123456789abcdef' for ch in v)):
            v = secrets.token_hex(24)
            f.write_text(v + '\n', 'utf-8')
        return v
    except Exception as e:
        log('id', e)
        return None


def write_launcher():
    """Escribe el lanzador de esta computadora. Abre Cloto donde se instaló; si esa ruta ya no existe
    (la memoria apareció con otra letra o carpeta), busca el volumen llamado CLOTO. En los dos casos solo abre
    si la carpeta tiene el identificador de esta instalación. Devuelve la ruta del lanzador."""
    exe = Path(sys.executable).resolve()
    mnt = mount_root(exe)
    rel = exe.relative_to(mnt)
    ident = usb_id()
    relbase = base_dir().resolve().relative_to(mnt) if ident else Path('.')
    L = local_dir(); L.mkdir(parents=True, exist_ok=True)
    if SYSTEM == 'Windows':
        f = L / 'abrir.ps1'
        f.write_text(
            "$p = %s; $rel = %s; $rb = %s; $id = %s\r\n"
            "function Valida($root) { if (-not $id) { return $true }; try { return ((Get-Content -LiteralPath (Join-Path (Join-Path $root $rb) '.cloto-id') -Raw).Trim() -eq $id) } catch { return $false } }\r\n"
            "$ok = $false\r\n"
            "if ((Test-Path -LiteralPath $p) -and (Valida ((Split-Path -Qualifier $p) + '\\'))) { $ok = $true }\r\n"
            "if (-not $ok -and $id) {\r\n"
            "  foreach ($d in [System.IO.DriveInfo]::GetDrives()) {\r\n"
            "    if ($d.IsReady -and $d.VolumeLabel -eq 'CLOTO') {\r\n"
            "      $r = $d.RootDirectory.FullName; $c = Join-Path $r $rel\r\n"
            "      if ((Test-Path -LiteralPath $c) -and (Valida $r)) { $p = $c; $ok = $true; break }\r\n"
            "    }\r\n"
            "  }\r\n"
            "}\r\n"
            "if ($ok) { Start-Process -FilePath $p } else { Add-Type -AssemblyName System.Windows.Forms; [void][System.Windows.Forms.MessageBox]::Show(%s, 'Cloto') }\r\n"
            % (ps_quote(exe), ps_quote(rel), ps_quote(relbase), ps_quote(ident or ''), ps_quote(NO_MEMORIA)), encoding='utf-8-sig')
        shutil.copy(RES / 'icono' / 'cloto.ico', L / 'cloto.ico')
    else:
        f = L / 'abrir.sh'
        vols = ('/Volumes/CLOTO "/Volumes/CLOTO 1" "/Volumes/CLOTO 2"' if SYSTEM == 'Darwin'
                else '"/media/$u/CLOTO" "/run/media/$u/CLOTO" /media/CLOTO /mnt/CLOTO')
        warn = ("osascript -e 'display dialog \"%s\" with title \"Cloto\" buttons {\"OK\"} default button 1 with icon caution'\n" % NO_MEMORIA
                if SYSTEM == 'Darwin' else
                "msg=%s\n"
                "if command -v zenity >/dev/null 2>&1; then zenity --warning --title=Cloto --text=\"$msg\"\n"
                "elif command -v kdialog >/dev/null 2>&1; then kdialog --sorry \"$msg\"\n"
                "elif command -v notify-send >/dev/null 2>&1; then notify-send Cloto \"$msg\"\n"
                "else echo \"$msg\" >&2; fi\n" % sh_quote(NO_MEMORIA))
        f.write_text(
            "#!/bin/sh\n"
            "# Abre Cloto donde se instaló; si no está, en la memoria llamada CLOTO. Solo si lleva el identificador de esta instalación.\n"
            "p=%s; rel=%s; rb=%s; id=%s; u=\"${USER:-$(id -un)}\"\n"
            "ok() { [ -z \"$id\" ] || [ \"$(cat \"$1/$rb/.cloto-id\" 2>/dev/null)\" = \"$id\" ]; }\n"
            "root=\"${p%%/$rel}\"\n"
            "if [ -x \"$p\" ] && [ \"$root\" != \"$p\" ] && ok \"$root\"; then exec \"$p\" \"$@\"; fi\n"
            "if [ -n \"$id\" ]; then for m in %s; do [ -x \"$m/$rel\" ] && ok \"$m\" && exec \"$m/$rel\" \"$@\"; done; fi\n"
            "%sexit 1\n" % (sh_quote(exe), sh_quote(rel.as_posix()), sh_quote(relbase.as_posix()), sh_quote(ident or ''), vols, warn))
        f.chmod(0o755)
    return f


def install_vinculado():
    """Accesos que apuntan al lanzador (no a la app): funcionan aunque la memoria USB cambie de letra o de equipo."""
    f = write_launcher()
    if SYSTEM == 'Windows':
        ps_exe = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
        args = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%s"' % f
        ps = ("$w = New-Object -ComObject WScript.Shell;"
              "foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {"
              " $s = $w.CreateShortcut((Join-Path $d 'Cloto.lnk'));"
              " $s.TargetPath = %s; $s.Arguments = %s; $s.WorkingDirectory = %s; $s.IconLocation = %s; $s.WindowStyle = 7; $s.Description = 'Cloto'; $s.Save() }"
              % (ps_quote(ps_exe), ps_quote(args), ps_quote(f.parent), ps_quote(f.parent / 'cloto.ico')))
        subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps], check=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        where = 'el escritorio y el menú Inicio'
    elif SYSTEM == 'Darwin':
        apps = Path.home() / 'Applications'; apps.mkdir(exist_ok=True)
        dest = apps / 'Cloto.app'
        if dest.is_symlink() or dest.exists():
            shutil.rmtree(dest) if dest.is_dir() and not dest.is_symlink() else dest.unlink()
        (dest / 'Contents' / 'MacOS').mkdir(parents=True); (dest / 'Contents' / 'Resources').mkdir()
        sh = dest / 'Contents' / 'MacOS' / 'Cloto'
        sh.write_text('#!/bin/sh\nexec %s "$@"\n' % sh_quote(f)); sh.chmod(0o755)
        shutil.copy(RES / 'icono' / 'cloto.icns', dest / 'Contents' / 'Resources' / 'cloto.icns')
        (dest / 'Contents' / 'Info.plist').write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict>'
            '<key>CFBundleName</key><string>Cloto</string><key>CFBundleExecutable</key><string>Cloto</string>'
            '<key>CFBundleIdentifier</key><string>io.cloto.lanzador</string><key>CFBundleIconFile</key><string>cloto</string>'
            '<key>CFBundlePackageType</key><string>APPL</string><key>CFBundleShortVersionString</key><string>%s</string>'
            '</dict></plist>\n' % VERSION)
        subprocess.run(['osascript', '-e', 'tell application "Finder" to make alias file to POSIX file %s at desktop' % json.dumps(str(dest))], capture_output=True)
        where = 'Aplicaciones (de tu usuario) y el escritorio'
    else:
        share = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share')
        icons = share / 'icons' / 'hicolor'
        for size, src in (('256x256', 'cloto-256.png'), ('1024x1024', 'cloto.png')):
            (icons / size / 'apps').mkdir(parents=True, exist_ok=True)
            shutil.copy(RES / 'icono' / src, icons / size / 'apps' / 'cloto.png')
        (icons / 'scalable' / 'apps').mkdir(parents=True, exist_ok=True)
        shutil.copy(RES / 'icono' / 'cloto.svg', icons / 'scalable' / 'apps' / 'cloto.svg')
        entry = ('[Desktop Entry]\nType=Application\nName=Cloto\nComment=Ideas unidas por hilos\nExec="%s"\nIcon=cloto\n'
                 'Terminal=false\nCategories=Office;Graphics;\nStartupWMClass=Cloto\n' % f)
        apps = share / 'applications'; apps.mkdir(parents=True, exist_ok=True)
        (apps / 'cloto.desktop').write_text(entry); (apps / 'cloto.desktop').chmod(0o755)
        desk = desktop_dir()
        if desk.is_dir():
            d = desk / 'cloto.desktop'; d.write_text(entry); d.chmod(0o755)
            if shutil.which('gio'):
                subprocess.run(['gio', 'set', str(d), 'metadata::trusted', 'true'], capture_output=True)
        if shutil.which('update-desktop-database'):
            subprocess.run(['update-desktop-database', str(apps)], capture_output=True)
        where = 'el menú de aplicaciones y el escritorio'
    S.root.mkdir(parents=True, exist_ok=True)
    aviso('Listo: Cloto está en %s de esta computadora.\nLa app y tus proyectos viven en:\n%s\n\n'
          'Si la app está en una memoria USB, llámala CLOTO: así la encuentra aunque cambie de letra.' % (where, base_dir()))


def install():
    if FROZEN:
        return install_vinculado()
    prog, args = launcher()
    if SYSTEM == 'Windows':
        icon = sys.executable if FROZEN else str(RES / 'icono' / 'cloto.ico')
        ps = ("$w = New-Object -ComObject WScript.Shell;"
              "foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {"
              " $s = $w.CreateShortcut((Join-Path $d 'Cloto.lnk'));"
              " $s.TargetPath = %s; $s.Arguments = %s; $s.WorkingDirectory = %s; $s.IconLocation = %s; $s.Description = 'Cloto'; $s.Save() }"
              % (ps_quote(prog), ps_quote(' '.join('"%s"' % a for a in args)), ps_quote(HERE), ps_quote(icon + ',0')))
        subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps], check=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        where = 'el escritorio y el menú Inicio'
    elif SYSTEM == 'Darwin':
        apps = Path.home() / 'Applications'; apps.mkdir(exist_ok=True)
        dest = apps / 'Cloto.app'
        if dest.is_symlink() or dest.exists():
            shutil.rmtree(dest) if dest.is_dir() and not dest.is_symlink() else dest.unlink()
        bundle = Path(sys.executable).resolve().parents[2] if FROZEN else None
        if bundle and bundle.suffix == '.app':
            dest.symlink_to(bundle)                                # la app sigue en tu carpeta; aquí solo un acceso
        else:                                                      # desde el código: una .app mínima que lanza cloto.py
            (dest / 'Contents' / 'MacOS').mkdir(parents=True)
            (dest / 'Contents' / 'Resources').mkdir()
            sh = dest / 'Contents' / 'MacOS' / 'Cloto'
            sh.write_text('#!/bin/sh\nexec %s %s\n' % (json.dumps(prog), ' '.join(json.dumps(a) for a in args)))
            sh.chmod(0o755)
            shutil.copy(RES / 'icono' / 'cloto.icns', dest / 'Contents' / 'Resources' / 'cloto.icns')
            (dest / 'Contents' / 'Info.plist').write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict>'
                '<key>CFBundleName</key><string>Cloto</string><key>CFBundleExecutable</key><string>Cloto</string>'
                '<key>CFBundleIdentifier</key><string>io.cloto.app</string><key>CFBundleIconFile</key><string>cloto</string>'
                '<key>CFBundlePackageType</key><string>APPL</string><key>CFBundleShortVersionString</key><string>%s</string>'
                '</dict></plist>\n' % VERSION)
        subprocess.run(['osascript', '-e', 'tell application "Finder" to make alias file to POSIX file %s at desktop' % json.dumps(str(dest))], capture_output=True)
        where = 'Aplicaciones (de tu usuario) y el escritorio'
    else:
        share = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share')
        icons = share / 'icons' / 'hicolor'
        for size, src in (('256x256', 'cloto-256.png'), ('1024x1024', 'cloto.png')):
            (icons / size / 'apps').mkdir(parents=True, exist_ok=True)
            shutil.copy(RES / 'icono' / src, icons / size / 'apps' / 'cloto.png')
        (icons / 'scalable' / 'apps').mkdir(parents=True, exist_ok=True)
        shutil.copy(RES / 'icono' / 'cloto.svg', icons / 'scalable' / 'apps' / 'cloto.svg')
        execl = ' '.join('"%s"' % x for x in [prog] + args)
        entry = ('[Desktop Entry]\nType=Application\nName=Cloto\nComment=Ideas unidas por hilos\nExec=%s\nIcon=cloto\n'
                 'Terminal=false\nCategories=Office;Graphics;\nStartupWMClass=Cloto\nPath=%s\n' % (execl, HERE))
        apps = share / 'applications'; apps.mkdir(parents=True, exist_ok=True)
        (apps / 'cloto.desktop').write_text(entry); (apps / 'cloto.desktop').chmod(0o755)
        desk = desktop_dir()
        if desk.is_dir():
            d = desk / 'cloto.desktop'; d.write_text(entry); d.chmod(0o755)
            if shutil.which('gio'):
                subprocess.run(['gio', 'set', str(d), 'metadata::trusted', 'true'], capture_output=True)
        if shutil.which('update-desktop-database'):
            subprocess.run(['update-desktop-database', str(apps)], capture_output=True)
        where = 'el menú de aplicaciones y el escritorio'
    S.root.mkdir(parents=True, exist_ok=True)
    aviso('Listo: Cloto está en %s.\nTus proyectos se guardan en:\n%s' % (where, S.root))


def uninstall():
    gone = []
    if SYSTEM == 'Windows':
        ps = ("foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {"
              " $f = Join-Path $d 'Cloto.lnk'; if (Test-Path $f) { Remove-Item $f } }")
        subprocess.run(['powershell', '-NoProfile', '-Command', ps], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        gone.append('accesos')
    elif SYSTEM == 'Darwin':
        for f in (Path.home() / 'Applications' / 'Cloto.app', desktop_dir() / 'Cloto.app', desktop_dir() / 'Cloto'):
            if f.is_symlink() or f.is_file():
                f.unlink(); gone.append(str(f))
            elif f.is_dir():
                shutil.rmtree(f); gone.append(str(f))
    else:
        share = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share')
        for f in (share / 'applications' / 'cloto.desktop', desktop_dir() / 'cloto.desktop',
                  share / 'icons/hicolor/256x256/apps/cloto.png', share / 'icons/hicolor/1024x1024/apps/cloto.png',
                  share / 'icons/hicolor/scalable/apps/cloto.svg'):
            if f.exists():
                f.unlink(); gone.append(str(f))
    try:
        shutil.rmtree(local_dir(), ignore_errors=True)
    except Exception:
        pass
    aviso('Se quitaron los iconos de Cloto. Tus proyectos siguen en:\n%s' % S.root)


# ---------------------------------------------------------------- inicio
def main():
    ap = argparse.ArgumentParser(prog='Cloto', description='Cloto de escritorio')
    ap.add_argument('--instalar', action='store_true', help='icono en el escritorio y en el menú')
    ap.add_argument('--desinstalar', action='store_true', help='quita los iconos (no toca tus proyectos)')
    ap.add_argument('--carpeta', help='carpeta de proyectos (se recuerda)')
    ap.add_argument('--servidor', action='store_true', help='solo el servidor; abre la dirección en tu navegador')
    ap.add_argument('--version', action='version', version='Cloto ' + VERSION)
    a, _ = ap.parse_known_args()                    # macOS a veces añade -psn_…

    c = load_config()
    if a.carpeta:
        set_root(Path(a.carpeta))
    else:
        r = configured_root(c)
        if r is not None and (r.is_dir() or r.parent.is_dir()):        # una unidad que ya no está (otra letra, otro equipo): se usa la de siempre
            S.root = r
    try:
        S.root.mkdir(parents=True, exist_ok=True)
    except Exception:
        S.root = default_root(); S.root.mkdir(parents=True, exist_ok=True)

    if a.instalar:
        return install()
    if a.desinstalar:
        return uninstall()
    url, srv = start_server()
    if srv is None:                                        # Cloto ya está abierto: se trae su ventana al frente
        try:
            urllib.request.urlopen(urllib.request.Request(url + 'api/focus', data=b'{}', method='POST'), timeout=2)
        except Exception:
            pass
        return
    log('inicio', VERSION, url, S.root)
    open_window(launch_url(), server_only=a.servidor)


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        log('error', e, traceback.format_exc())
        raise
