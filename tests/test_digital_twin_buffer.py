"""Spec 024, T2: búfer inmutable de episodios con índice reconstruible (sin DIgSILENT)."""
from __future__ import annotations

import copy
import random

import pytest
from test_digital_twin_episode import _payload

from igea_dgs.digital_twin import buffer as bf
from igea_dgs.digital_twin import episode as ep


def _episodio(**cambios) -> ep.Episodio:
    return ep.leer_episodio(_payload(**cambios))


@pytest.fixture
def bufer(tmp_path):
    return bf.BuferEpisodios(tmp_path / 'twin')


def test_guardar_escribe_un_objeto_por_huella(bufer):
    """024:RF-6 — el episodio se guarda una vez, en ``objetos/<ab>/<huella>.json``."""
    e = _episodio()
    ruta = bufer.guardar(e)
    assert ruta == bufer.raiz / 'objetos' / e.episode_id[:2] / f'{e.episode_id}.json'
    assert bufer.leer(e.episode_id) == e
    assert not list(ruta.parent.glob('*.tmp'))


def test_guardar_dos_veces_es_idempotente(bufer):
    """024:RF-6 — el mismo episodio registrado dos veces no reescribe nada."""
    e = _episodio()
    ruta = bufer.guardar(e)
    antes = ruta.stat().st_mtime_ns
    assert bufer.guardar(e) == ruta
    assert ruta.stat().st_mtime_ns == antes
    assert len(bufer.consultar(bf.Consulta())) == 1


def test_un_objeto_alterado_es_una_colision(bufer):
    """024:RF-6 / 024:RF-9 — si en la ruta de una huella hay otro contenido, no se pisa."""
    e = _episodio()
    ruta = bufer.guardar(e)
    ruta.write_text('{"otro": 1}', encoding='utf-8')
    with pytest.raises(bf.ColisionEpisodio):
        bufer.guardar(e)
    assert ruta.read_text(encoding='utf-8') == '{"otro": 1}'


def test_leer_un_episodio_que_no_existe(bufer):
    """024:RF-8 — una huella sin objeto es un error claro, no un episodio vacío."""
    with pytest.raises(KeyError):
        bufer.leer('c' * 64)


def test_consultas_por_proyecto_alimentador_caso_clase_accion_y_version(bufer):
    """024:RF-8 — se consulta por proyecto, alimentador, caso, clase, acción, fuente y
    versión de PowerFactory."""
    a = _episodio()
    p = _payload(caso='con_proyecto', clase='converged_with_violations')
    p['nativo'].update(project='Q', feeders=['B9'], pf_version='2025')
    p['accion']['tipo'] = 'obras_ejecutar'
    p['fuente']['source_fingerprint'] = 'b' * 64
    b = ep.leer_episodio(p)
    for e in (a, b):
        bufer.guardar(e)
    assert [e.episode_id for e in bufer.consultar(bf.Consulta(proyecto='Q'))] == [b.episode_id]
    assert [e.episode_id for e in bufer.consultar(bf.Consulta(alimentador='A2'))] == [a.episode_id]
    assert bufer.consultar(bf.Consulta(caso='con_proyecto')) == [b]
    assert bufer.consultar(bf.Consulta(clase='accepted')) == [a]
    assert bufer.consultar(bf.Consulta(accion='obras_ejecutar')) == [b]
    assert bufer.consultar(bf.Consulta(pf_version='2024')) == [a]
    assert bufer.consultar(bf.Consulta(fuente='b' * 64)) == [b]
    assert bufer.consultar(bf.Consulta(proyecto='Q', clase='accepted')) == []


def test_indice_borrado_se_reconstruye_igual(bufer):
    """024:RF-6 / 024:RF-8 — SQLite es solo un índice: sin él, se rehace con los objetos y
    las consultas dan lo mismo."""
    semilla = random.randrange(1 << 30)
    rnd = random.Random(semilla)
    for i in range(rnd.randint(3, 30)):
        p = _payload(caso=rnd.choice([c.value for c in ep.Caso]))
        p['nativo']['feeders'] = [f'F{i}', f'F{i + 1}']
        bufer.guardar(ep.leer_episodio(p))
    antes = [e.episode_id for e in bufer.consultar(bf.Consulta(caso='sin_proyecto'))]
    bufer.indice.unlink()
    assert bufer.reconstruir_indice() == len(list(bufer.raiz.glob('objetos/*/*.json')))
    assert [e.episode_id for e in bufer.consultar(bf.Consulta(caso='sin_proyecto'))] == antes, \
        f'semilla {semilla}'


def test_indice_corrupto_se_sustituye_sin_tocar_los_objetos(bufer):
    """024:RF-9 — un índice dañado se rehace; los objetos siguen intactos."""
    e = _episodio()
    ruta = bufer.guardar(e)
    contenido = ruta.read_bytes()
    bufer.indice.write_bytes(b'esto no es sqlite')
    otro = bf.BuferEpisodios(bufer.raiz)
    assert otro.consultar(bf.Consulta()) == [e]
    assert ruta.read_bytes() == contenido


def test_un_objeto_corrupto_va_a_cuarentena_sin_borrarse(bufer):
    """024:RF-9 / 024:RF-10 — al reconstruir, un manifiesto ilegible pasa a cuarentena con su
    contenido; nunca se borra evidencia."""
    bueno = _episodio()
    bufer.guardar(bueno)
    malo = bufer.raiz / 'objetos' / 'zz' / ('d' * 64 + '.json')
    malo.parent.mkdir(parents=True)
    malo.write_text('{roto', encoding='utf-8')
    assert bufer.reconstruir_indice() == 1
    en_cuarentena = bufer.cuarentena()
    assert [p.name for p in en_cuarentena] == [malo.name]
    assert en_cuarentena[0].read_text(encoding='utf-8') == '{roto'
    assert bufer.consultar(bf.Consulta()) == [bueno]


def test_el_bufer_no_tiene_borrado(bufer):
    """024:RF-10 — la evidencia original no se borra: el búfer no ofrece cómo hacerlo."""
    publicos = {n for n in dir(bufer) if not n.startswith('_')}
    assert not {n for n in publicos if 'borr' in n or 'delet' in n or 'elimin' in n}


def test_esquema_de_otra_version_no_se_mezcla(bufer):
    """024:RF-7 — un manifiesto de otro esquema no entra al índice: va a cuarentena."""
    e = _episodio()
    otro = copy.deepcopy(ep.episodio_a_dict(e))
    otro['schema'] = 'igea-dgs-digital-twin-episode-v9'
    ruta = bufer.raiz / 'objetos' / e.episode_id[:2] / f'{e.episode_id}.json'
    ruta.parent.mkdir(parents=True)
    ruta.write_text(ep.contenido_canonico(otro), encoding='utf-8')
    assert bufer.reconstruir_indice() == 0
    assert len(bufer.cuarentena()) == 1


def test_raiz_por_variable_de_entorno(tmp_path, monkeypatch):
    """024:RF-6 — el búfer es local: ``IGEA_TWIN_DATA`` o junto a los espacios de la web."""
    monkeypatch.setenv('IGEA_TWIN_DATA', str(tmp_path / 'aqui'))
    assert bf.raiz_buffer() == tmp_path / 'aqui'
    monkeypatch.delenv('IGEA_TWIN_DATA')
    monkeypatch.setenv('IGEA_WEB_DATA', str(tmp_path / 'web'))
    assert bf.raiz_buffer() == tmp_path / 'web' / '_digital_twin'
