"""Arranca la interfaz web: ``python -m igea_dgs.web`` o ``igea-dgs-web``.

Por defecto escucha solo en 127.0.0.1, que es lo que permite indicar rutas del disco
local en lugar de subir los ficheros. Con ``--host 0.0.0.0`` se expone en la red y
esas rutas se desactivan siempre, aunque ``IGEA_WEB_SERVER_PATHS`` valga ``1``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.request
import webbrowser


def puerto_ocupado(host: str, port: int) -> bool:
    """Si ya escucha algo en ``host:port``: el servidor nuevo no podría arrancar."""
    import socket

    destino = '127.0.0.1' if host in ('0.0.0.0', '::') else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((destino, port)) == 0


def _salida(cmd: list[str]) -> str:
    import subprocess

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError):
        return ''
    return r.stdout or ''


def quien_escucha(port: int) -> tuple[int, str] | None:
    """PID y línea de órdenes de quien escucha en ``port``, o None si no se averigua.

    2026-10-14: un servidor arrancado con ``--no-browser`` por una sesión de prueba se
    quedó escuchando sin ventana; el acceso directo decía «cierre la otra ventana» y no
    había ninguna que cerrar. Sin el PID no había forma de encontrarlo desde la consola.
    Es solo para el aviso: si falla cualquier paso, se avisa sin él.
    """
    pid = None
    if os.name == 'nt':
        for linea in _salida(['netstat', '-ano', '-p', 'TCP']).splitlines():
            campos = linea.split()
            if (len(campos) >= 5 and campos[1].endswith(f':{port}')
                    and campos[3].upper() in ('LISTENING', 'ESCUCHANDO') and campos[4].isdigit()):
                pid = int(campos[4])
                break
    else:
        primera = _salida(['lsof', '-nP', f'-iTCP:{port}', '-sTCP:LISTEN', '-t']).split()
        pid = int(primera[0]) if primera and primera[0].isdigit() else None
    if pid is None:
        return None
    if os.name == 'nt':
        orden = _salida(['powershell', '-NoProfile', '-Command',
                         f'(Get-CimInstance Win32_Process -Filter "ProcessId={pid}").CommandLine'])
    else:
        orden = _salida(['ps', '-o', 'args=', '-p', str(pid)])
    return pid, orden.strip()


def conversor_en(url: str, timeout: float = 4.0) -> dict | None:
    """La respuesta de ``/api/health`` si en ``url`` hay un Conversor, o None."""
    try:
        with urllib.request.urlopen(url + 'api/health', timeout=timeout) as r:
            datos = json.loads(r.read().decode('utf-8'))
    except (OSError, ValueError):
        return None
    return datos if isinstance(datos, dict) and 'slots' in datos and 'version' in datos else None


def _json(url: str, timeout: float = 4.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def trabajos_en_curso(url: str, salud: dict) -> int | None:
    """Trabajos sin terminar del Conversor de ``url``, o None si no se puede saber."""
    servidor = salud.get('servidor')
    if isinstance(servidor, dict) and isinstance(servidor.get('trabajos_en_curso'), int):
        return servidor['trabajos_en_curso']
    # Servidor anterior al 2026-10-15, sin el recuento: se mira espacio por espacio.
    try:
        n = 0
        for ws in _json(url + 'api/workspaces'):
            for job in _json(url + f'api/workspaces/{ws["id"]}').get('jobs', []):
                if job.get('status') not in ('done', 'failed', 'cancelled'):
                    n += 1
        return n
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def esperar_respuesta(url: str, segundos: float) -> dict | None:
    """La salud del Conversor de ``url`` en cuanto responda, o None si no lo hace a tiempo."""
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        salud = conversor_en(url, timeout=min(10.0, max(1.0, limite - time.monotonic())))
        if salud is not None:
            return salud
        time.sleep(1.0)
    return None


def carpeta_registro() -> str:
    """Donde los servidores anotan sus trabajos en curso para el lanzador (RF-34)."""
    import tempfile

    return os.path.join(os.environ.get('LOCALAPPDATA') or tempfile.gettempdir(), 'igea_dgs', 'trabajos_web')


def pedir_cierre(url: str) -> bool:
    """Pide al Conversor de ``url`` que se cierre; True si lo acepta."""
    from .app import CABECERA_LANZADOR

    peticion = urllib.request.Request(url + 'api/sistema/cerrar', method='POST', data=b'',
                                      headers={CABECERA_LANZADOR: '1'})
    try:
        with urllib.request.urlopen(peticion, timeout=5) as r:
            return r.status == 202
    except (OSError, ValueError):
        return False


def esperar_puerto_libre(host: str, port: int, segundos: float) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if not puerto_ocupado(host, port):
            return True
        time.sleep(0.3)
    return not puerto_ocupado(host, port)


def es_conversor(orden: str) -> bool:
    """Si una línea de órdenes es un servidor del Conversor (no su comprobación de entorno)."""
    return re.search(r'igea_dgs\.web(?![.\w])|igea-dgs-web', orden or '') is not None


def puerto_libre_siguiente(host: str, port: int, intentos: int = 20) -> int | None:
    for candidato in range(port + 1, port + 1 + intentos):
        if not puerto_ocupado(host, candidato):
            return candidato
    return None


def _terminar(pid: int) -> None:
    from ..powerfactory_env import terminar_arbol

    try:
        terminar_arbol(pid)
    except (OSError, ValueError):
        pass


def abrir_cuando_responda(url: str, segundos: float = 120.0) -> threading.Thread:
    """Abre el navegador en cuanto el servidor responde.

    Con 1,2 s fijos, el navegador llegaba antes de que el servidor terminara de importar
    (geopandas, VNR-GIS) y mostraba «no se puede conectar» (spec 001, RF-32).
    """
    def esperar() -> None:
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            if conversor_en(url, timeout=1.0) is not None:
                webbrowser.open(url)
                return
            time.sleep(0.5)

    hilo = threading.Thread(target=esperar, name='igea-navegador', daemon=True)
    hilo.start()
    return hilo


# Código de salida con el que run_gui.bat deja leer el aviso y cierra la ventana solo.
SALIDA_OTRA_VERSION = 3


def _destino(host: str) -> str:
    return '127.0.0.1' if host in ('0.0.0.0', '::') else host


def resolver_puerto(host: str, port: int, abrir: bool) -> tuple[str, int]:
    """Qué hacer con el puerto ocupado: ``('arrancar', puerto)`` o ``('salir', código)``.

    2026-10-15, fase comercial: el acceso directo se quedaba en «Presione una tecla» cada
    vez que el puerto estaba ocupado (doble clic dos veces, un servidor de prueba con
    ``--no-browser``, uno colgado), y el operador no tiene por qué saber qué cerrar
    (spec 001, RF-28 a RF-31).
    """
    from .app import frontend_dist
    from .runtime import huella_del_codigo

    from .jobs import trabajos_anotados

    url = f'http://{_destino(host)}:{port}/'
    salud = conversor_en(url) or conversor_en(url)
    if salud is None:
        ocupante = quien_escucha(port)
        if (ocupante and ocupante[0] != os.getpid() and es_conversor(ocupante[1])
                and (trabajos_anotados(ocupante[0]) or 0) > 0):
            # RF-34: ocupado con un trabajo largo no es colgado; se le da un minuto.
            print(f'El Conversor del puerto {port} (proceso {ocupante[0]}) tiene trabajos en curso '
                  'y tarda en responder: se espera.')
            salud = esperar_respuesta(url, 60.0)
            if salud is None:
                print(f'El Conversor de {url} sigue sin responder con trabajos en curso: no se cierra '
                      'para no perderlos y se muestra en el navegador.', file=sys.stderr)
                if abrir:
                    webbrowser.open(url)
                return 'salir', SALIDA_OTRA_VERSION
    if salud is not None:
        servidor = salud.get('servidor') if isinstance(salud.get('servidor'), dict) else {}
        if servidor.get('huella') == huella_del_codigo(frontend_dist()):
            print(f'El Conversor ya está abierto en {url}: se muestra en el navegador.')
            if abrir:
                webbrowser.open(url)
            return 'salir', 0
        en_curso = trabajos_en_curso(url, salud)
        if en_curso != 0:
            motivo = (f'tiene {en_curso} trabajo(s) en curso' if en_curso
                      else 'no se pudo saber si tiene trabajos en curso')
            print(f'En {url} hay otra versión del Conversor que {motivo}: no se cierra para no '
                  'perder ese trabajo y se muestra en el navegador. Cuando termine, cierre su '
                  'ventana y vuelva a abrir el acceso directo para usar esta versión.',
                  file=sys.stderr)
            if abrir:
                webbrowser.open(url)
            return 'salir', SALIDA_OTRA_VERSION
        print(f'En {url} hay otra versión del Conversor sin trabajos: se cierra y se abre esta.')
        if not (pedir_cierre(url) and esperar_puerto_libre(host, port, 45)):
            # Servidor anterior a la petición de cierre, o que no la atendió.
            pid = servidor.get('pid') if isinstance(servidor.get('pid'), int) else None
            ocupante = quien_escucha(port)
            if ocupante and es_conversor(ocupante[1]):
                pid = ocupante[0]
            if pid and pid != os.getpid():
                _terminar(pid)
                esperar_puerto_libre(host, port, 15)
    else:
        ocupante = quien_escucha(port)
        if ocupante and ocupante[0] != os.getpid() and es_conversor(ocupante[1]):
            print(f'El Conversor del puerto {port} (proceso {ocupante[0]}) no responde: se cierra '
                  'y se abre uno nuevo.')
            _terminar(ocupante[0])
            esperar_puerto_libre(host, port, 15)
    if not puerto_ocupado(host, port):
        return 'arrancar', port
    nuevo = puerto_libre_siguiente(host, port)
    ocupante = quien_escucha(port)
    quien = f' (proceso {ocupante[0]}: {ocupante[1] or "sin línea de órdenes"})' if ocupante else ''
    if nuevo is None:
        cerrar = ''
        if ocupante:
            cerrar = f'  Ciérrelo con:  {"taskkill /PID" if os.name == "nt" else "kill"} {ocupante[0]}'
        print(f'El puerto {port} y los 20 siguientes están ocupados{quien}.\n{cerrar}',
              file=sys.stderr)
        return 'salir', 2
    print(f'El puerto {port} lo usa otro programa{quien}: el Conversor se abre en el {nuevo}.')
    return 'arrancar', nuevo


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog='igea-dgs-web', description=__doc__)
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--no-browser', action='store_true', help='No abrir el navegador')
    p.add_argument('--reload', action='store_true', help='Recarga en caliente (desarrollo)')
    args = p.parse_args(argv)

    # En Windows, con la salida redirigida (servicio, .bat > log), la consola es cp1252
    # y cualquier carácter fuera de ella tumbaba el arranque antes de servir nada.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError):
            pass

    try:
        import uvicorn
    except ImportError:
        print('Falta la parte web. Instale:  python -m pip install -r requirements.txt',
              file=sys.stderr)
        return 1

    # La API decide las rutas locales por la interfaz de escucha (create_app); con
    # factory=True no recibe argumentos, así que va por el entorno, que hereda también
    # el proceso de recarga.
    os.environ['IGEA_WEB_HOST'] = args.host
    from .jobs import VARIABLE_REGISTRO, registro_de_trabajos

    os.environ.setdefault(VARIABLE_REGISTRO, carpeta_registro())       # RF-34
    # 026:RF-22: la vigilancia del asistente corre en el servidor real, no en las pruebas.
    os.environ.setdefault('IGEA_ASISTENTE_VIGILANCIA', '1')

    from .app import al_pedir_cierre, frontend_dist

    port = args.port
    if puerto_ocupado(args.host, port):
        # 2026-10-14: con un servidor de la mañana aún abierto, el acceso directo abría el
        # navegador en él —sin los cambios del día— y el nuevo moría sin bind. Ahora se
        # reutiliza si es el mismo código y se reemplaza si no.
        accion, valor = resolver_puerto(args.host, port, abrir=not args.no_browser)
        if accion == 'salir':
            return valor
        port = valor
    url = f'http://{_destino(args.host)}:{port}/'
    if not (frontend_dist() / 'index.html').is_file():
        print('AVISO: no está compilado el front (frontend/dist). Solo responderá la API.\n'
              '       Compílelo con:  cd frontend && npm install && npm run build',
              file=sys.stderr)
    elif not args.no_browser:
        abrir_cuando_responda(url)

    print(f'Conversor IGEA -> DGS en {url}  (Ctrl+C o cerrar esta ventana para salir)')
    try:
        if args.reload:
            uvicorn.run('igea_dgs.web.app:create_app', factory=True, host=args.host, port=port,
                        reload=True, log_level='info')
        else:
            servidor = uvicorn.Server(uvicorn.Config(
                'igea_dgs.web.app:create_app', factory=True, host=args.host, port=port,
                log_level='info'))
            # Con el servidor a mano, el cierre que pide el lanzador es el mismo que Ctrl+C:
            # termina las peticiones y cancela los trabajos limpio (RF-29).
            al_pedir_cierre(lambda: setattr(servidor, 'should_exit', True))
            servidor.run()
    except KeyboardInterrupt:
        # uvicorn vuelve a lanzar el Ctrl+C tras cerrar limpio; sin esto salía con traza
        # y código 1, y run_gui.bat decía «si faltan librerías» y pedía una tecla (RF-32).
        pass
    finally:
        registro = registro_de_trabajos(os.getpid())
        if registro is not None:
            registro.unlink(missing_ok=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
