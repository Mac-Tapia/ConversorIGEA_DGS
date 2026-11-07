"""Spec 091: de la calibración al estudio, en su orden y sin avisos que engañen.

Cada prueba reproduce lo que se vio en la web el 2026-11-05 con TM102. Lo que depende del navegador
se comprueba en la fuente del front, como el resto de la suite, y de verdad en la tarea T7.
"""
from __future__ import annotations

from pathlib import Path

from convertersmartgrid import pf_arnes
from convertersmartgrid.web import services

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / 'frontend' / 'src'
APP = (SRC / 'App.tsx').read_text(encoding='utf-8')
PANEL = (SRC / 'components' / 'FeedersPanel.tsx').read_text(encoding='utf-8')
SERVICES = (RAIZ / 'src' / 'convertersmartgrid' / 'web' / 'services.py').read_text(encoding='utf-8')


# ------------------------------------------------------------------ DIgSILENT abierto o sin conexión


def test_digsilent_abierto_a_mano_pide_cerrarlo():
    """091:RF-1 — dice que hay que cerrarlo y con qué proceso."""
    texto = pf_arnes.causa_sin_conexion(abierto=lambda: [46392], cola=Path('no-existe'))
    assert 'ciérrelo' in texto and '46392' in texto
    assert 'Ábralo' not in texto


def test_digsilent_otra_causa_dice_la_del_arnes(tmp_path):
    """091:RF-2 — sin nada abierto, la última causa que registró el arnés."""
    (tmp_path / 'servidor.log').write_text(
        '2026-11-05 11:00:00 Proceso 1: conectando con DIgSILENT.\nERROR: la vieja\n'
        '2026-11-05 11:16:03 Proceso 2: conectando con DIgSILENT.\n'
        '2026-11-05 11:16:04 ERROR: no se pudo conectar a DIgSILENT: sin licencia\n', encoding='utf-8')
    texto = pf_arnes.causa_sin_conexion(abierto=lambda: [], cola=tmp_path)
    assert 'sin licencia' in texto and 'la vieja' not in texto


def test_digsilent_sin_causa_registrada_no_pide_abrirlo(tmp_path):
    """091:RF-2 / 091:RF-3 — sin causa en el registro de este intento tampoco se pide abrirlo."""
    (tmp_path / 'servidor.log').write_text(
        '2026-11-05 11:00:00 Proceso 1: conectando con DIgSILENT.\nERROR: la vieja\n'
        '2026-11-05 11:20:00 Proceso 2: conectando con DIgSILENT.\nConectado a DIgSILENT.\n', encoding='utf-8')
    texto = pf_arnes.causa_sin_conexion(abierto=lambda: [], cola=tmp_path)
    assert 'la vieja' not in texto and 'Ábralo' not in texto and 'Registro' in texto


def test_digsilent_ningun_mensaje_pide_abrirlo():
    """091:RF-3 / 091:RF-5 — ni el servidor ni la web piden abrir DIgSILENT para una acción."""
    assert 'Ábralo y reintente' not in SERVICES
    assert 'no está abierto' not in SERVICES
    assert services.sin_conexion_digsilent.__doc__
    assert SERVICES.count('raise sin_conexion_digsilent()') == 6
    assert 'Ábralo' not in APP and 'no está abierto' not in APP
    assert 'preferiblemente' not in PANEL and 'cerrado' in PANEL
    manual = (RAIZ / 'docs' / 'MANUAL_COMANDOS.md').read_text(encoding='utf-8')
    assert 'Abra PowerFactory' not in manual


def test_digsilent_el_error_lleva_la_causa(monkeypatch):
    """091:RF-1 / 091:RF-2 — el error de la web es la causa del arnés, no un texto fijo."""
    monkeypatch.setattr(pf_arnes, 'causa_sin_conexion', lambda: 'DIgSILENT está abierto a mano (proceso 9)')
    assert 'proceso 9' in str(services.sin_conexion_digsilent())


def test_causa_en_el_registro_del_cliente(tmp_path, monkeypatch, capsys):
    """091:RF-4 — el Registro dice la causa, no «código ?»."""
    import sys

    sys.path.insert(0, str(RAIZ / 'tools'))
    import pf_cliente

    (tmp_path / 'servidor.log').write_text(
        'X Proceso 2: conectando con DIgSILENT.\nX ERROR: DIgSILENT está abierto a mano (proceso 7): ciérrelo\n',
        encoding='utf-8')

    class Muerto:
        pid, returncode = 1, '?'

        def poll(self):
            return '?'

    monkeypatch.setattr(pf_arnes, 'servidor_vivo', lambda *a, **k: None)
    monkeypatch.setattr(pf_arnes, 'leer_turno', lambda *a, **k: None)
    assert pf_cliente.asegurar_servidor(tmp_path, 5, lanzar=lambda c: Muerto(), dormir=lambda s: None) is False
    salida = capsys.readouterr().out
    assert 'abierto a mano (proceso 7)' in salida and 'código ?' not in salida


def test_marcas_de_procesos_muertos_se_retiran(tmp_path):
    """091:RF-6 — quedaban ficheros de conexión de hace días; las de procesos vivos siguen."""
    turno = tmp_path / 'powerfactory.turno'
    muerta, viva, otro = (tmp_path / f'powerfactory.conexion_{n}' for n in (111, 222, 'x'))
    for m in (muerta, viva, otro):
        m.write_text('fin', encoding='utf-8')
    pf_arnes.barrer_marcas(turno, vivo=lambda pid: pid == 222)
    assert not muerta.exists() and viva.exists() and otro.exists()


def test_marcas_se_barren_al_tomar_el_turno():
    """091:RF-6 — el barrido va antes de dejar la marca propia."""
    fuente = Path(pf_arnes.__file__).read_text(encoding='utf-8')
    assert fuente.index('barrer_marcas(ruta)') < fuente.index("marca = ruta.with_name(f'{ruta.stem}.conexion_")
