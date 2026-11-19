"""086:RF-120 — la identidad 043 de los episodios del gemelo: la captura la graba y lo grabado sin ella se rellena aparte.

Búfer sintético: proyectos, alimentadores y huellas inventados. Orden del integrador del 19-11 por la ablación de 045 T3.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

from convertersmartgrid.adaptadores.digital_twin import buffer as bf
from convertersmartgrid.adaptadores.digital_twin.buffer import BuferEpisodios
from convertersmartgrid.aplicacion.evaluacion_modelos import huella
from convertersmartgrid.dominio.digital_twin.episode import Caso, leer_episodio

from test_digital_twin_episode import _payload
from test_gemelo_contratos_v2 import _grafo

REPO = Path(__file__).resolve().parents[1]
PERIODO = {'clientes': '2026-07', 'maxima': '2026-07', 'status': 'CLIENT_PERIOD_MATCH'}


def _modulo(nombre: str):
    ruta = REPO / 'tools' / f'{nombre}.py'
    assert ruta.is_file(), f'falta tools/{nombre}.py (086:RF-120)'
    spec = importlib.util.spec_from_file_location(f'{nombre}_rf120', ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _funcion(nombre: str):
    funcion = getattr(bf, nombre, None)
    assert funcion is not None, f'el búfer no tiene {nombre} (086:RF-120)'
    return funcion


def _fisico(**campos):
    return {'case_role': 'sin_proyecto', 'case_id': 'IntCase:Estudios\\sin_proyecto', 'topology_hash': 'a' * 64,
            'controls_hash': 'a' * 64, 'scenario_hash': 'a' * 64, **campos}


def _calibracion(proyecto='P', creado='2026-10-21T09:00:00+00:00', feeders=('A1', 'A2'), **campos):
    """Episodio de una calibración: trae mes y criterio de fijas, pero no la huella del perfil (anterior a 050:RF-23)."""
    nativo = {'project': proyecto, 'folder': 'F', 'feeders': list(feeders), 'pf_version': '2024', 'reopen_verified': True}
    return _payload(creado=creado, nativo=nativo, accion={'tipo': 'ajuste', 'aplicada': True},
                    contexto_fisico=_fisico(period=PERIODO, criterio_fijas='coincidente', **campos))


def _escenario(proyecto='P', creado='2026-10-21T10:00:00+00:00'):
    """Contrafactual que enseña, grabado sin periodo, criterio ni huella del perfil."""
    nativo = {'project': proyecto, 'folder': 'F', 'feeders': ['A1', 'A2'], 'pf_version': '2024', 'reopen_verified': True}
    return _payload(creado=creado, nativo=nativo, topologia={'grafo': _grafo()},
                    accion={'tipo': 'gemelo_escenarios', 'aplicada': False})


def _bufer(tmp_path, *payloads):
    raiz = tmp_path / 'twin'
    b = BuferEpisodios(raiz)
    episodios = [leer_episodio(p) for p in payloads]
    for e in episodios:
        b.guardar(e)
    return raiz, episodios


def _huellas(raiz: Path) -> dict[str, str]:
    """Lo que no se puede tocar: cada objeto y el índice."""
    rutas = [*sorted((raiz / 'objetos').rglob('*.json')), raiz / 'episodios.sqlite3']
    return {r.relative_to(raiz).as_posix(): hashlib.sha256(r.read_bytes()).hexdigest() for r in rutas}


def _perfil(tmp_path):
    ruta = tmp_path / 'config' / 'perfil_empresa.json'
    ruta.parent.mkdir(parents=True)
    ruta.write_text('{"empresa": "Distribuidora de prueba"}', encoding='utf-8')
    return ruta


def _correr(herramienta, *args) -> tuple[int, dict]:
    salida = io.StringIO()
    with redirect_stdout(salida):
        rc = herramienta.main([str(a) for a in args])
    return rc, (json.loads(salida.getvalue()) if salida.getvalue().strip() else {})


def _args_ciclo(pc, salida, twin):
    return SimpleNamespace(salida=salida, dataset=None, observaciones=[], vocabulario=None, twin=twin, cabeceras=None,
                           llm_dataset=None, casos_evolutivos=None, referencia_pinn=None, complemento=None, espacios=[],
                           perfil=None, declarado_por='', proyecto_series=None, proyecto_casos=[], zona_horaria=None,
                           cadencia_min=None, horizontes=None, semillas=pc.SEMILLAS, embedding_model=pc.MODELO_EMBEDDINGS)


def test_086_rf120_la_captura_salta_la_calibracion_que_fallo_y_el_episodio_lleva_su_identidad(tmp_path):
    """086:RF-120 — una calibración que falló entera no deja al episodio nuevo sin periodo ni criterio de fijas."""
    from convertersmartgrid.presentacion.web import services as sv
    from test_digital_twin_capture import _construir, _plan
    raiz = tmp_path / 'esp'
    buena = raiz / 'runs' / 'r1' / 'salida' / 'ajuste_cabecera_aplicacion_aaa111.json'
    fallida = raiz / 'runs' / 'r2' / 'salida' / 'ajuste_cabecera_aplicacion_bbb222.json'
    for ruta, informe, t in ((buena, {'project': 'P', 'feeder': 'A1', 'criterio_fijas': 'coincidente',
                                      'objetivo': {'fecha': '2026-07-13 10:45:00'}}, 1000),
                             (fallida, {'project': 'P', 'feeder': 'A1',
                                        'error': "no existe el proyecto 'P' en la carpeta 'X' de DIgSILENT"}, 2000)):
        ruta.parent.mkdir(parents=True)
        ruta.write_text(json.dumps(informe), encoding='utf-8')
        os.utime(ruta, (t, t))
    ws = SimpleNamespace(root=raiz, out_dir=fallida.parent, criterio_cabecera={})
    perfil = {'empresa': 'Distribuidora de prueba'}
    identidad = sv.identidad_de_captura(ws, 'P', perfil)
    assert identidad == {'periodo': '2026-07', 'criterio_fijas': 'coincidente', 'profile_hash': huella(perfil)}
    e = _construir(plan={**_plan(), **identidad}, caso=Caso.SIN_PROYECTO, referencia=None)
    assert (e.contexto_fisico['period'], e.contexto_fisico['criterio_fijas'], e.contexto_fisico['profile_hash']) == (
        '2026-07', 'coincidente', huella(perfil))
    # Una calibración posterior que sí se aplicó es la que vale, aunque sea de otro mes.
    nueva = raiz / 'runs' / 'r3' / 'salida' / 'ajuste_cabecera_aplicacion_ccc333.json'
    nueva.parent.mkdir(parents=True)
    nueva.write_text(json.dumps({'project': 'P', 'feeder': 'A1', 'criterio_fijas': 'maximo_mes',
                                 'objetivo': {'fecha': '2026-08-02 19:00:00'}}), encoding='utf-8')
    os.utime(nueva, (3000, 3000))
    ws.out_dir = nueva.parent
    assert sv.identidad_de_captura(ws, 'P', perfil)['periodo'] == '2026-08'


def test_086_rf120_en_seco_dice_que_rellenaria_y_de_donde_sin_escribir_nada(tmp_path):
    """086:RF-120 — por defecto, en seco: el mes y el criterio de la calibración anterior, la huella del perfil vigente."""
    herramienta = _modulo('rellenar_identidad_043')
    twin, (cal, esc) = _bufer(tmp_path, _calibracion(), _escenario())
    antes = _huellas(twin)
    perfil = _perfil(tmp_path)
    rc, r = _correr(herramienta, '--twin', twin, '--perfil', perfil)
    assert rc == 0 and r['aplicado'] is False and r['escritas'] == 0
    filas = {f['episode_id']: f for f in r['rellenaria']}
    assert set(filas) == {cal.episode_id, esc.episode_id} and filas[esc.episode_id]['ensena'] is True
    assert filas[esc.episode_id]['campos'] == {'period': '2026-07', 'criterio_fijas': 'coincidente',
                                               'profile_hash': huella({'empresa': 'Distribuidora de prueba'})}
    assert cal.episode_id in filas[esc.episode_id]['origen']['period']
    assert str(perfil) in filas[esc.episode_id]['origen']['profile_hash']
    assert filas[cal.episode_id]['campos'] == {'profile_hash': huella({'empresa': 'Distribuidora de prueba'})}
    assert _huellas(twin) == antes and not (twin / bf.ARCHIVO_IDENTIDAD_043).exists()


def test_086_rf120_aplicar_escribe_solo_el_registro_y_el_ciclo_lo_combina_con_el_objeto(tmp_path):
    """086:RF-120 — con --aplicar, solo el registro aparte; preparar_ciclo saca el episodio de cuarentena con él."""
    herramienta = _modulo('rellenar_identidad_043')
    pc = _modulo('preparar_ciclo_aprendizaje')
    twin, (cal, esc) = _bufer(tmp_path, _calibracion(), _escenario())
    sin_relleno = pc.preparar(_args_ciclo(pc, tmp_path / 'antes', twin))
    assert sin_relleno['proyectos_043'] == 0 and sin_relleno['contexto_hash'] is None
    antes = _huellas(twin)
    assert _correr(herramienta, '--twin', twin, '--perfil', _perfil(tmp_path), '--aplicar')[0] == 1   # sin responsable
    rc, r = _correr(herramienta, '--twin', twin, '--perfil', tmp_path / 'config' / 'perfil_empresa.json',
                    '--aplicar', '--declarado-por', 'integrador')
    assert rc == 0 and r['escritas'] == 2
    assert _huellas(twin) == antes, 'objetos/ y el índice no se tocan'
    registro = _funcion('leer_identidades_043')(twin)
    assert registro[esc.episode_id]['declarado_por'] == 'integrador'
    assert _correr(herramienta, '--twin', twin, '--aplicar', '--declarado-por', 'integrador')[1]['escritas'] == 0
    resumen = pc.preparar(_args_ciclo(pc, tmp_path / 'despues', twin))
    assert resumen['proyectos_043'] == 1 and resumen['contexto_hash']
    cuarentena = json.loads((tmp_path / 'despues' / 'cuarentena.json').read_text(encoding='utf-8'))
    assert all(f['registro'] != esc.episode_id for f in cuarentena)
    assert resumen['informe']['twin']['identidad_043'] == {'registradas': 2, 'completan': 2, 'con_referencia': 1}
    congelado = json.loads(Path(resumen['fuentes']['identidad_043']).read_text(encoding='utf-8'))
    assert list(congelado) == [esc.episode_id] and congelado[esc.episode_id]['origen']['period'].startswith('deducido')
    assert [p.stem for p in Path(resumen['fuentes']['twin']).rglob('*.json')] == [esc.episode_id]


def test_086_rf120_lo_que_no_se_deduce_sigue_en_cuarentena_con_su_motivo(tmp_path):
    """086:RF-120 — sin calibración anterior del proyecto no se rellena nada y el episodio sigue apartado."""
    herramienta = _modulo('rellenar_identidad_043')
    pc = _modulo('preparar_ciclo_aprendizaje')
    # La única calibración es de otro proyecto, y la del mismo es posterior al episodio.
    twin, (_, _, esc) = _bufer(tmp_path, _calibracion(proyecto='OTRO'),
                               _calibracion(creado='2026-10-22T09:00:00+00:00'), _escenario())
    rc, r = _correr(herramienta, '--twin', twin, '--perfil', _perfil(tmp_path), '--aplicar', '--declarado-por', 'x')
    assert rc == 0 and esc.episode_id in r['sin_deducir']
    assert r['sin_deducir'][esc.episode_id]['motivo'] == ('ninguna calibración del proyecto anterior al episodio trae '
                                                          'mes y criterio de fijas')
    assert esc.episode_id not in _funcion('leer_identidades_043')(twin)
    pc.preparar(_args_ciclo(pc, tmp_path / 's', twin))
    cuarentena = json.loads((tmp_path / 's' / 'cuarentena.json').read_text(encoding='utf-8'))
    assert {'fuente': 'twin', 'registro': esc.episode_id,
            'motivo': 'identidad 043 incompleta: faltan period, criterio_fijas, profile_hash'} in cuarentena


def test_086_rf120_registro_que_contradice_al_episodio_no_lo_sustituye(tmp_path):
    """086:RF-120 — lo registrado completa lo que falta; si contradice lo leído en el episodio, va a cuarentena."""
    pc = _modulo('preparar_ciclo_aprendizaje')
    escenario = _escenario()
    escenario['contexto_fisico'] = _fisico(period='2026-07')
    twin, (esc,) = _bufer(tmp_path, escenario)
    _funcion('registrar_identidades_043')(twin, [{
        'schema': bf.ESQUEMA_IDENTIDAD_043, 'episode_id': esc.episode_id, 'fecha': '2026-11-19T10:00:00+00:00',
        'declarado_por': 'prueba', 'campos': {'period': '2025-01', 'criterio_fijas': 'coincidente', 'profile_hash': 'b' * 64},
        'origen': {'period': 'a mano', 'criterio_fijas': 'a mano', 'profile_hash': 'a mano'}}])
    resumen = pc.preparar(_args_ciclo(pc, tmp_path / 's', twin))
    cuarentena = json.loads((tmp_path / 's' / 'cuarentena.json').read_text(encoding='utf-8'))
    assert resumen['proyectos_043'] == 0
    assert cuarentena[0]['motivo'] == ("el registro de identidad 043 contradice al episodio en period: "
                                       "episodio '2026-07', registrado '2025-01'")


def test_086_rf120_registro_atomico_que_sobrevive_al_indice_y_bufer_viejo_legible(tmp_path, monkeypatch):
    """086:RF-120 — un búfer sin registro se lee; el registro no se parte, no admite ajenos y no lo borra el índice."""
    leer, registrar = _funcion('leer_identidades_043'), _funcion('registrar_identidades_043')
    twin, (esc, cal) = _bufer(tmp_path, _escenario(), _calibracion())
    assert leer(twin) == {}
    fila = {'schema': bf.ESQUEMA_IDENTIDAD_043, 'episode_id': esc.episode_id, 'fecha': '2026-11-19T10:00:00+00:00',
            'declarado_por': 'prueba', 'campos': {'profile_hash': 'b' * 64}, 'origen': {'profile_hash': 'perfil'}}
    with pytest.raises(ValueError, match='lleva su origen'):
        registrar(twin, [{**fila, 'origen': {}}])
    with pytest.raises(ValueError, match='no está en'):
        registrar(twin, [{**fila, 'episode_id': 'c' * 64}])
    assert registrar(twin, [fila]) == 1 and registrar(twin, [fila]) == 0
    texto = (twin / bf.ARCHIVO_IDENTIDAD_043).read_text(encoding='utf-8')
    reemplazar = os.replace

    def falla_al_publicar(origen, destino):
        if Path(destino).name == bf.ARCHIVO_IDENTIDAD_043:
            raise OSError('disco lleno')
        return reemplazar(origen, destino)
    monkeypatch.setattr(bf.os, 'replace', falla_al_publicar)
    with pytest.raises(OSError, match='disco lleno'):
        registrar(twin, [{**fila, 'episode_id': cal.episode_id}])
    monkeypatch.undo()
    assert (twin / bf.ARCHIVO_IDENTIDAD_043).read_text(encoding='utf-8') == texto
    (twin / 'episodios.sqlite3').unlink()
    BuferEpisodios(twin)                      # rehace el índice desde los objetos
    assert leer(twin) == {esc.episode_id: fila}
