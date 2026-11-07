"""Spec 091: de la calibración al estudio, en su orden y sin avisos que engañen.

Cada prueba reproduce lo que se vio en la web el 2026-11-05 con TM102. Lo que depende del navegador
se comprueba en la fuente del front, como el resto de la suite, y de verdad en la tarea T7.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from convertersmartgrid import pf_arnes
from convertersmartgrid.demanda_medida import (
    MOTIVO_SIN_SUMINISTRO, ClienteImportante, cabeceras_de_hojas, completar_desde_hojas,
)
from convertersmartgrid.web import services

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / 'frontend' / 'src'
APP = (SRC / 'App.tsx').read_text(encoding='utf-8')
PANEL = (SRC / 'components' / 'FeedersPanel.tsx').read_text(encoding='utf-8')
DEMANDA = (SRC / 'components' / 'DemandaMedida.tsx').read_text(encoding='utf-8')
AJUSTE = (SRC / 'components' / 'AjusteCabecera.tsx').read_text(encoding='utf-8')
CATALOGO = (SRC / 'clientesCatalogo.ts').read_text(encoding='utf-8')
API = (SRC / 'api.ts').read_text(encoding='utf-8')
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


# ------------------------------------------------------------------ pestañas


def test_pestanas_visitadas_siguen_montadas():
    """091:RF-7 — se ocultan, no se desmontan: el proyecto vivía en la pestaña y se perdía."""
    assert '{actual.el}' not in APP
    assert 'hidden={t.id !== actual.id}' in APP
    assert 'visitadas.current.add(actual.id)' in APP


def test_pestanas_de_otro_espacio_empiezan_de_cero():
    """091:RF-8 — la clave del espacio las vuelve a montar."""
    assert 'key={w.state.id}' in APP


# ------------------------------------------------------------------ clientes por su hoja


def _cliente(codigo: str) -> ClienteImportante:
    c = ClienteImportante(codigo=codigo, fila=2, ea=1.0, eri=1.0, pot=1.0)
    c.motivo = MOTIVO_SIN_SUMINISTRO
    return c


def _libro(ruta: Path, hojas: dict[str, list[list[object]]]) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        ws = wb.create_sheet(nombre)
        for fila in filas:
            ws.append(fila)
    wb.save(ruta)
    return ruta


def test_hoja_da_la_sed_de_la_red(tmp_path):
    """091:RF-9 / 091:RF-10 — sin depender de su posición ni de un patrón de empresa."""
    libro = _libro(tmp_path / 'clientes.xlsx', {
        'resumen': [['Nis', 'EA'], ['381000358', 3.0]],
        'Hayduk2': [['', 'Gen', 381000358.0, 'TM102'], ['', 'Pesquera', 'SE20066'], ['dia', 'hora']],
    })
    cruzados, aparte = completar_desde_hojas([_cliente('381000358')], libro, {'SE20066': {'TM102'}, 'OTRA': {'X'}})
    assert not aparte
    assert cruzados[0].sed == 'SE20066' and cruzados[0].cruzado_por == 'hoja'
    assert cruzados[0].radial == 'TM102'
    assert 'hoja «Hayduk2»' in cruzados[0].nota_asignacion and 'suministros' in cruzados[0].nota_asignacion


def test_hoja_con_dos_sed_queda_aparte(tmp_path):
    """091:RF-11 — no se elige entre dos SED."""
    libro = _libro(tmp_path / 'c.xlsx', {'Dos': [['7001'], ['SED1', 'SED2']]})
    cruzados, aparte = completar_desde_hojas([_cliente('7001')], libro, {'SED1': {'A'}, 'SED2': {'B'}})
    assert not cruzados and 'SED1, SED2' in aparte[0].motivo


def test_hoja_que_falta_o_no_nombra_sed_lo_dice(tmp_path):
    """091:RF-12 — dice cuál de las dos cosas falta."""
    libro = _libro(tmp_path / 'c.xlsx', {'Sin': [['7001'], ['nada de la red']]})
    cruzados, aparte = completar_desde_hojas([_cliente('7001'), _cliente('7002')], libro, {'SED1': {'A'}})
    assert not cruzados
    por = {c.codigo: c.motivo for c in aparte}
    assert 'no nombra ninguna SED' in por['7001'] and 'Sin' in por['7001']
    assert 'no tiene hoja' in por['7002']


def test_hoja_no_toca_a_los_que_estan_aparte_por_otra_causa(tmp_path):
    """091:RF-9 — el que cruza sin SED en el libro de suministros sigue con su motivo."""
    libro = _libro(tmp_path / 'c.xlsx', {'H': [['7001'], ['SED1']]})
    c = _cliente('7001')
    c.motivo = 'cruza por el código actual pero el suministro no tiene SED'
    cruzados, aparte = completar_desde_hojas([c], libro, {'SED1': {'A'}})
    assert not cruzados and aparte[0].motivo.startswith('cruza por')


def test_hoja_sin_red_cargada_no_cambia_nada(tmp_path):
    """091:RF-12 — sin red no hay con qué comparar: siguen aparte, sin abrir el libro."""
    cruzados, aparte = completar_desde_hojas([_cliente('7001')], tmp_path / 'no_existe.xlsx', {})
    assert not cruzados and aparte[0].motivo == MOTIVO_SIN_SUMINISTRO


def test_hoja_se_lee_una_vez_mientras_el_libro_no_cambia(tmp_path, monkeypatch):
    """091:RF-13 — el plan cruza por alimentador; un libro real trae cientos de hojas."""
    from convertersmartgrid import demanda_medida

    libro = _libro(tmp_path / 'c.xlsx', {'H': [['7001'], ['SED1']]})
    aperturas = []
    original = demanda_medida.abrir_libro
    monkeypatch.setattr(demanda_medida, 'abrir_libro', lambda p: (aperturas.append(p), original(p))[1])
    assert cabeceras_de_hojas(libro) == cabeceras_de_hojas(libro)
    assert len(aperturas) == 1
    _libro(libro, {'H': [['7001'], ['SED2'], ['y', 'mas', 'contenido']]})
    os.utime(libro, (2_000_000_000, 2_000_000_000))
    assert 'SED2' in str(cabeceras_de_hojas(libro))
    assert len(aperturas) == 2


def test_hoja_entra_en_el_cruce_real():
    """091:RF-9 / 091:RF-10 — el cruce de la web la usa antes de reconciliar, y la fila dice de dónde sale."""
    assert 'completar_desde_hojas(aparte, libro, nombres)' in SERVICES
    assert SERVICES.count('_cruzar_clientes_en_red(ws, clientes, suministros, libro)') == 2
    assert SERVICES.count("'por_hoja':") == 2
    assert "c.cruzado_por === 'hoja'" in DEMANDA and 'por su hoja' in DEMANDA


# ------------------------------------------------------------------ máxima y cruce


def _maxima_y_plan(tmp_path, monkeypatch, proyecto_maxima, proyecto_plan):
    from fastapi.testclient import TestClient

    from convertersmartgrid.web.app import create_app

    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setattr(services, 'demanda_cabecera', lambda *a, **k: {'resultados': [{'alimentador': 'F1'}]})
    planes = []
    monkeypatch.setattr(services, 'ajuste_plan', lambda *a, **k: planes.append(a[1]) or {'token': 'x'})
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as c:
        wid = c.post('/api/workspaces').json()['id']
        cuerpo = {'medidores': [{'alimentador': 'F1', 'medidor': 'M1'}]}
        if proyecto_maxima is not None:
            cuerpo['project'] = proyecto_maxima
        job = c.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json=cuerpo).json()
        for _ in range(200):
            estado = c.get(f"/api/jobs/{job['id']}").json()
            if estado['status'] in ('done', 'error'):
                break
            time.sleep(0.05)
        r = c.post(f'/api/workspaces/{wid}/demanda/ajuste/plan', json={
            'project': proyecto_plan, 'job_id': job['id'], 'medidor': '', 'medidores': ['M1']})
    return estado, r, planes


def test_maxima_recuerda_su_proyecto(tmp_path, monkeypatch):
    """091:RF-14 / 091:RF-15 — una máxima de otro proyecto no vale para este plan."""
    estado, r, planes = _maxima_y_plan(tmp_path, monkeypatch, 'PROY_A', 'PROY_B')
    assert estado['result']['project'] == 'PROY_A'
    assert r.status_code == 409 and not planes
    assert 'PROY_A' in r.json()['detail'] and 'PROY_B' in r.json()['detail']


def test_maxima_del_mismo_proyecto_o_sin_proyecto_pasa(tmp_path, monkeypatch):
    """091:RF-15 — la del mismo proyecto sigue; una buscada sin decirlo (el asistente, 070) no se rechaza."""
    assert _maxima_y_plan(tmp_path / 'a', monkeypatch, 'PROY_A', 'PROY_A')[1].status_code == 200
    estado, r, _ = _maxima_y_plan(tmp_path / 'b', monkeypatch, None, 'PROY_A')
    assert estado['result']['project'] is None and r.status_code == 200


def test_maxima_solo_la_del_proyecto_y_el_ano():
    """091:RF-16 — ofrecía la última del espacio: «Ajustar» activo en un proyecto recién importado."""
    assert 'const ultimo = faltaAnio ? undefined : Object.values(jobs)' in DEMANDA
    assert 'project === project' in DEMANDA
    assert 'startsWith(anio)' in DEMANDA
    assert 'project, periodo, instante' in DEMANDA
    assert 'project: criterio.project' in API


def test_cruce_a_la_vista_antes_de_ajustar():
    """091:RF-17 — sin la tabla no se simula ni se ajusta, y se dice."""
    assert 'faltaCruce' in AJUSTE
    # Sin máxima por alimentador (nada que cruzar con ella) no se pide: «Ajustar» no se queda apagado para siempre.
    assert 'faltaCruce={Boolean(hayMaximas &&' in DEMANDA
    assert re.search(r"faltaCruce\s*\?\s*'[^']*[Cc]ruce", AJUSTE)


def test_cruce_viejo_no_vale_con_otra_maxima():
    """091:RF-18 — una máxima nueva borra el cruce mostrado."""
    assert re.search(r"useEffect\(\(\) => \{\s*setCruce\(null\);\s*setDesconectados\(new Set\(\)\);\s*\}, \[ultimo\?\.id\]\)",
                     DEMANDA)


def test_cruce_con_el_ano_entero():
    """091:RF-19 — con «Todo 2026» y máxima se puede cruzar (cambia 025:RF-10); un índice viejo sigue sin dejar."""
    assert 'cruzaPorSuMes' in DEMANDA
    assert '!(estadoClientes.listoParaCruzar || cruzaPorSuMes)' in DEMANDA
    assert 'estadoClientes.porAnio' in DEMANDA
    assert 'porAnio: true' in CATALOGO
    # Solo la rama del año entero lo lleva: «Actualice el índice» no se salta con las máximas.
    assert CATALOGO.count('porAnio: true') == 1
    assert CATALOGO.index('porAnio: true') > CATALOGO.index('Actualice el índice')
