"""Spec 026, RF-46 (T20), y 107:RF-22 (T40): el asistente comprueba las fuentes oficiales de la biblioteca normativa
(solo lee: huella y vigencia), agrega una norma a la capa del usuario y regenera un registro desde su fuente oficial ya
descargada, diciendo antes qué reglas entran, salen o cambian (usuario, 2026-11-18: «el asistente debe controlar el
SmartConverter de punta a punta»).

La biblioteca es la real del programa; la carpeta de fuentes y el generador son los de la prueba (en ``tmp_path``),
para no depender de lo descargado en la máquina: el generador de la prueba escribe la copia de un registro real con una
regla cambiada, y el que falla imita el mensaje de ``tools/normativa/fuentes.py`` ante una fuente alterada.
"""
from __future__ import annotations

import inspect
import json
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from convertersmartgrid.aplicacion import biblioteca_normativa as bn
from convertersmartgrid.aplicacion.asistente import ejecutor, tareas
from convertersmartgrid.aplicacion.asistente.interprete import _por_frase_literal

RAIZ = Path(__file__).resolve().parents[1]
COES = RAIZ / 'config' / 'normativa' / 'coes_maxima_demanda_sein.json'
ORDENES = ('normativa_comprobar', 'normativa_agregar', 'normativa_regenerar')


def test_026_rf46_las_tres_ordenes_de_la_biblioteca_estan_con_su_efecto_y_su_frase():
    """026:RF-46 — comprobar solo lee; agregar y regenerar escriben (esperan la confirmación del operador)."""
    faltan = [t for t in ORDENES if t not in tareas.TAREAS]
    assert faltan == [], f'órdenes de la biblioteca que el asistente aún no tiene: {faltan}'
    assert tareas.EFECTOS['normativa_comprobar'] == (tareas.LEE,) and not tareas.TAREAS['normativa_comprobar'].escribe
    for t in ('normativa_agregar', 'normativa_regenerar'):
        assert tareas.EFECTOS[t] == (tareas.ESCRIBE,) and tareas.TAREAS[t].escribe, t
    assert _por_frase_literal('comprueba las fuentes de la biblioteca normativa', None) == 'normativa_comprobar'
    assert _por_frase_literal('agrega la norma D:/normas/rcd_9_2026.json', None) == 'normativa_agregar'
    assert _por_frase_literal('regenera el registro de la guia vnr', None) == 'normativa_regenerar'


def test_026_rf46_sus_pasos_van_a_las_rutas_de_la_biblioteca(tmp_path):
    """026:RF-46 — agregar sube el .json a POST /api/normativa; regenerar pide la vista previa y aplica con su ficha."""
    assert hasattr(ejecutor, '_pasos_026_rf46'), 'el ejecutor no sabe los pasos de la biblioteca normativa'
    norma = tmp_path / 'rcd_9_2026.json'
    norma.write_text('{}', encoding='utf-8')
    (paso,) = ejecutor.pasos('normativa_agregar', {'ruta': str(norma)}, {})
    assert (paso.metodo, paso.ruta) == ('POST', '/api/normativa') and paso.archivos is not None, paso
    assert paso.archivos([])['file'][0] == 'rcd_9_2026.json'
    previa, aplicar = ejecutor.pasos('normativa_regenerar', {}, {'normativa': {'generador': 'coes'}})
    assert (previa.metodo, previa.ruta, previa.cuerpo) == ('POST', '/api/normativa/regenerar', {'generador': 'coes'})
    assert aplicar.ruta([{'token': 'abc123'}]) == '/api/normativa/regenerar/abc123/aplicar'


def _norma_con_fuente():
    registro = bn.cargar_biblioteca()
    return next(n for a, n in sorted(registro.normas.items()) if n.fichero_local and n.sha256)


def test_107_rf22_comprobar_dice_cuadra_alterada_falta_y_sin_carpeta_sin_escribir(tmp_path):
    """107:RF-22 — la huella de cada fuente contra la registrada; nada se escribe ni se descarga."""
    assert hasattr(bn, 'comprobar_fuentes'), 'la biblioteca no sabe comprobar sus fuentes oficiales'
    n = _norma_con_fuente()
    hoy = '2026-11-18'
    sin = {f['acto']: f for f in bn.comprobar_fuentes(None, hoy)['normas']}
    assert sin[n.acto]['fuente'] == 'sin_carpeta'
    falta = {f['acto']: f for f in bn.comprobar_fuentes(tmp_path, hoy)['normas']}
    assert falta[n.acto]['fuente'] == 'falta' and n.fichero_local in falta[n.acto]['motivo']
    ruta = tmp_path / n.fichero_local
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b'otra cosa')
    alterada = {f['acto']: f for f in bn.comprobar_fuentes(tmp_path, hoy)['normas']}
    assert alterada[n.acto]['fuente'] == 'alterada'
    antes = sorted(p.as_posix() for p in tmp_path.rglob('*'))
    assert bn.comprobar_fuentes(tmp_path, hoy)['cuenta'].get('alterada', 0) >= 1
    assert sorted(p.as_posix() for p in tmp_path.rglob('*')) == antes, 'comprobar escribió algo'


@pytest.fixture
def web_normativa(tmp_path, monkeypatch):
    """La API de la biblioteca con la capa del usuario, las fuentes y el «programa» (su tools/normativa) en tmp. Se
    arma dentro de cada prueba (``armar()``): sin la regeneración, la prueba falla por su aserción y no el fixture."""
    def armar():
        from convertersmartgrid.presentacion.web import normativa_api

        assert 'carpeta_fuentes' in inspect.signature(normativa_api.registrar_rutas_normativa).parameters, \
            'la API de la biblioteca no sabe regenerar un registro desde su fuente oficial'
        return _armar(normativa_api.registrar_rutas_normativa, tmp_path, monkeypatch)
    return armar


def _armar(registrar_rutas_normativa, tmp_path, monkeypatch):
    capa = tmp_path / 'local' / 'normativa_usuario'
    monkeypatch.setenv(bn.VARIABLE_CAPA, str(capa))
    fuentes = tmp_path / 'fuentes'
    fuentes.mkdir()
    programa = tmp_path / 'programa'
    (programa / 'tools' / 'normativa').mkdir(parents=True)

    def guardar(destino: Path, f) -> None:
        destino.write_bytes(f.file.read())

    app = FastAPI()
    registrar_rutas_normativa(app, guardar_subida=guardar, hoy=lambda: '2026-11-18',
                              carpeta_fuentes=lambda: fuentes, programa=lambda: programa)
    return TestClient(app), capa, fuentes, programa


def _generador(programa: Path, guion: str, cuerpo: str) -> None:
    (programa / 'tools' / 'normativa' / guion).write_text(
        'import argparse, shutil, sys\nfrom pathlib import Path\n'
        "ap = argparse.ArgumentParser(); ap.add_argument('--fuentes'); ap.add_argument('--destino')\n"
        'a = ap.parse_args()\n' + cuerpo, encoding='utf-8')


def test_107_rf22_regenerar_dice_que_cambia_y_solo_escribe_al_aplicar(web_normativa):
    """107:RF-22 — la vista previa no toca la biblioteca y dice la regla que cambia; aplicar la escribe en la capa del
    usuario, que sustituye a la del programa."""
    cliente, capa, fuentes, programa = web_normativa()
    datos = json.loads(COES.read_text(encoding='utf-8'))
    norma = next(n for n in datos['normas'] if n.get('reglas'))
    regla = norma['reglas'][0]
    regla['cita_literal'] = (regla.get('cita_literal') or '') + ' (texto regenerado)'
    (fuentes / 'registro.json').write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    _generador(programa, 'generar_coes.py',
               "shutil.copy(Path(a.fuentes) / 'registro.json', "
               "Path(a.destino) / 'config/normativa/coes_maxima_demanda_sein.json')\n")
    huella = bn.huella_biblioteca()
    r = cliente.post('/api/normativa/regenerar', json={'generador': 'coes'})
    assert r.status_code == 200, r.text
    previa = r.json()
    assert not previa['sin_cambios'] and previa['token']
    cambio = next(c for c in previa['cambios'] if c['acto'] == norma['acto'])
    assert cambio['cambian'] == [regla['clave']] and cambio['entran'] == [] and cambio['salen'] == [], cambio
    assert bn.huella_biblioteca() == huella and not capa.exists(), 'la vista previa escribió en la biblioteca'
    r = cliente.post(f"/api/normativa/regenerar/{previa['token']}/aplicar")
    assert r.status_code == 200, r.text
    assert norma['acto'] in r.json()['actos'] and r.json()['cambios'], r.json()
    assert (capa / COES.name).is_file() and bn.huella_biblioteca() != huella
    vigente = bn.cargar_biblioteca().normas[norma['acto']]
    assert any(x.clave == regla['clave'] and x.cita_literal.endswith('(texto regenerado)') for x in vigente.reglas)


def test_107_rf22_fuente_alterada_o_sin_carpeta_no_regenera_y_dice_por_que(web_normativa, tmp_path):
    """107:RF-22 — si la huella no cuadra, el generador se para y la web lo dice sin rutas de la máquina; sin la
    carpeta de fuentes, dice dónde ponerla; un generador desconocido no corre."""
    cliente, capa, fuentes, programa = web_normativa()
    _generador(programa, 'generar_coes.py',
               "sys.exit('FUENTE ALTERADA: ' + str(Path(a.fuentes) / 'x.xlsx') + ' tiene sha256 1 y el registrado es 2.')\n")
    r = cliente.post('/api/normativa/regenerar', json={'generador': 'coes'})
    assert r.status_code == 422 and 'FUENTE ALTERADA' in r.json()['detail'], r.text
    assert str(fuentes) not in r.json()['detail'] and fuentes.as_posix() not in r.json()['detail'], r.json()
    assert not capa.exists()
    assert cliente.post('/api/normativa/regenerar', json={'generador': 'otro'}).status_code == 422
    shutil.rmtree(fuentes)
    r = cliente.post('/api/normativa/regenerar', json={'generador': 'coes'})
    assert r.status_code == 409 and 'CSG_FUENTES_NORMATIVAS' in r.json()['detail'], r.text
    r = cliente.get('/api/normativa/fuentes')
    assert r.status_code == 200 and r.json()['carpeta'] is False, r.text
