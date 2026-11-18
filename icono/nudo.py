# Icono de Cloto: un círculo negro con el nudo blanco, una cinta en ∞ que se cruza consigo misma.
# Cada hebra es una barra recta que entra tangente a un anillo (arcos exactos, sin tramos rectos fuera de la barra);
# la segunda hebra es la primera girada 180°. Cada anillo termina cortado por el borde de su propia barra.
# Uso:  python3 icono/nudo.py   →  cloto.svg y nudo.svg (siempre) y, con Pillow, cloto.png, cloto-256.png, cloto.ico, cloto.icns
import math, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent

# medidas del dibujo (unidades arbitrarias; el centro del nudo es M)
CL, CR = (300.0, 345.0), (795.0, 345.0)     # centros de los dos anillos
M = ((CL[0]+CR[0])/2, CL[1])
R, W, G = 138.0, 94.0, 12.0                 # radio del trazo central, grosor, hueco blanco entre piezas
PHI = math.radians(57)                      # inclinación de la barra
END = (598.0, 495.0)                        # hacia dónde apunta el extremo redondeado de la barra
ARC_END = math.radians(-350)                # el arco da casi la vuelta; el borde de la barra lo recorta
CUT_AT = 55.0                               # el borde blanco empieza a esta distancia del punto de tangencia (antes todo está fundido)

def _rot(q):  return (2*M[0]-q[0], 2*M[1]-q[1])
def _strand(flip):
    d = (math.cos(PHI), math.sin(PHI))
    P = (CL[0]+R*math.sin(PHI), CL[1]-R*math.cos(PHI))                       # donde la barra toca al anillo
    t = (END[0]-P[0])*d[0]+(END[1]-P[1])*d[1]; E = (P[0]+t*d[0], P[1]+t*d[1])  # extremo de la barra
    th0 = PHI-math.pi/2
    at = lambda th: (CL[0]+R*math.cos(th), CL[1]+R*math.sin(th))
    mid = at((th0+ARC_END)/2)                                                 # el arco son dos mitades (<180° cada una)
    S = (P[0]+d[0]*CUT_AT, P[1]+d[1]*CUT_AT)                                  # inicio del borde blanco
    pts = dict(E=E, P=P, mid=mid, end=at(ARC_END), S=S)
    return {k: (_rot(v) if flip else v) for k, v in pts.items()}
STR = [_strand(False), _strand(True)]

def _bar(s):     return f'M{s["E"][0]:.2f} {s["E"][1]:.2f} L{s["P"][0]:.2f} {s["P"][1]:.2f}'
def _arc(s):     return (f'M{s["P"][0]:.2f} {s["P"][1]:.2f} A{R} {R} 0 0 0 {s["mid"][0]:.2f} {s["mid"][1]:.2f} '
                         f'A{R} {R} 0 0 0 {s["end"][0]:.2f} {s["end"][1]:.2f}')
def _outline(s): return f'M{s["S"][0]:.2f} {s["S"][1]:.2f} L{s["E"][0]:.2f} {s["E"][1]:.2f}'

def svg(bare):
    """bare=False: círculo negro con el nudo blanco. bare=True: solo el nudo, en negro y sobre transparente."""
    Rc = 62.0; s = (0.90*2*Rc if bare else 0.72*2*Rc)/(CR[0]-CL[0]+2*R+W)    # ancho del nudo ≈ 72 % del círculo
    ink = '#111' if bare else '#fff'
    cut = lambda i: f'<path d="{_outline(STR[i])}" stroke="#000" stroke-width="{W+2*G:.2f}" stroke-linecap="round" fill="none"/>'
    mask = lambda name, cuts: (f'<mask id="{name}" maskUnits="userSpaceOnUse" x="-100" y="-100" width="1300" height="900">'
                               f'<rect x="-100" y="-100" width="1300" height="900" fill="#fff"/>{"".join(cut(i) for i in cuts)}</mask>')
    defs = mask('a1', (0, 1)) + mask('b1', (1,)) + mask('a2', (1,))            # a: arco, b: barra; cada hebra la recortan las de después
    body = (f'<path mask="url(#a1)" d="{_arc(STR[0])}"/><path mask="url(#b1)" d="{_bar(STR[0])}"/>'
            f'<path mask="url(#a2)" d="{_arc(STR[1])}"/><path d="{_bar(STR[1])}"/>')
    g = (f'<g transform="translate(64 64) scale({s:.5f}) translate({-M[0]} {-M[1]})" fill="none" stroke="{ink}" '
         f'stroke-width="{W}" stroke-linecap="round">{body}</g>')
    disc = '' if bare else f'<circle cx="64" cy="64" r="{Rc}" fill="#000"/>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128"><defs>{defs}</defs>{disc}{g}</svg>'

def _pts(p0, p1, n=60): return [(p0[0]+(p1[0]-p0[0])*i/n, p0[1]+(p1[1]-p0[1])*i/n) for i in range(n+1)]
def _arcpts(flip, n=900):
    d = PHI-math.pi/2; pts = [(CL[0]+R*math.cos(d+(ARC_END-d)*i/n), CL[1]+R*math.sin(d+(ARC_END-d)*i/n)) for i in range(n+1)]
    return [_rot(q) for q in pts] if flip else pts

def raster(size, ss=3):
    """El mismo dibujo en píxeles (sin depender de ninguna librería de SVG)."""
    from PIL import Image, ImageDraw
    N = size*ss; Rc = N/2*(62/64); s = 0.72*2*Rc/(CR[0]-CL[0]+2*R+W)
    X = lambda q: (N/2+(q[0]-M[0])*s, N/2+(q[1]-M[1])*s)
    ink = Image.new('L', (N, N), 0); d = ImageDraw.Draw(ink)
    def stamp(path, wd, col):
        r = wd*s/2
        for q in path:
            x, y = X(q); d.ellipse((x-r, y-r, x+r, y+r), fill=col)
    for flip in (False, True):
        st = STR[int(flip)]
        arc = _arcpts(flip); bar = _pts(st['E'], st['P'], 200); out = _pts(st['S'], st['E'], 200)
        stamp(arc, W, 255); stamp(bar, W, 255)
        stamp(out, W+2*G, 0)                  # el borde recorta a lo que ya hay…
        stamp(bar, W, 255)                    # …y la barra queda entera encima
    disc = Image.new('L', (N, N), 0); ImageDraw.Draw(disc).ellipse((N/2-Rc, N/2-Rc, N/2+Rc, N/2+Rc), fill=255)
    rgb = Image.new('RGB', (N, N), (0, 0, 0)); rgb.paste((255, 255, 255), mask=ink)
    out = rgb.convert('RGBA'); out.putalpha(disc)
    return out.resize((size, size), Image.LANCZOS)

if __name__ == '__main__':
    (HERE/'cloto.svg').write_text(svg(False)); (HERE/'nudo.svg').write_text(svg(True))
    print('icono/cloto.svg y icono/nudo.svg listos')
    try:
        import PIL
    except ImportError:
        print('Sin Pillow: instala «pip install pillow» para generar también PNG, ICO e ICNS'); sys.exit(0)
    big = raster(1024, 2); big.save(HERE/'cloto.png'); raster(256).save(HERE/'cloto-256.png')
    big.save(HERE/'cloto.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    big.save(HERE/'cloto.icns')
    print('icono/cloto.png, cloto-256.png, cloto.ico y cloto.icns listos')
