"""Spec 112: control de reidentificación con fugas plantadas (112:RF-4, RF-10).

Antes de emitir un benchmark se busca en cada byte lo que delataría a la empresa: un identificador o un cliente
original, un término de su perfil, una coordenada real, una fecha sin desplazar, una secuencia de valores original, un
fragmento de un texto suyo o un fichero que no está en la lista cerrada. Para que el control valga algo hay que verlo
fallar: se genera un benchmark limpio, se planta una fuga de cada clase en una copia y cada copia se rechaza con su
clase, sin repetir el valor original en el mensaje. La copia limpia pasa.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import shutil
from pathlib import Path

import numpy as np
import pytest

from synthetic_export import ExportSpec, write_export
from test_benchmarks_series import _dataset

TERMINO = 'Distribuidora Ejemplo del Sur'
INFORME = 'El informe de planificacion de la gerencia tecnica recomienda reforzar el tramo troncal'


def _perfil(tmp_path: Path) -> Path:
    ruta = tmp_path / 'perfil.json'
    ruta.write_text(json.dumps({'empresa': TERMINO, 'patron_sed_medicion': '^SE1'}), encoding='utf-8')
    return ruta


def _limpio(tmp_path: Path):
    """Un benchmark de redes y series sin fugas, y lo que el control sabe del origen."""
    from convertersmartgrid.dominio.benchmarks import redes as R
    from convertersmartgrid.adaptadores.benchmarks import series as S
    from convertersmartgrid.adaptadores.benchmarks.reidentificacion import Origen
    from convertersmartgrid.dominio.benchmarks.seudonimos import Mapa

    # Lejos del origen neutro: si la red ya estuviera allí, cualquier coordenada parecería una fuga.
    spec = ExportSpec(feeders=3, sections_per_feeder=5, loads_per_feeder=3, seed=61, layout='completo',
                      origin_x=300000.0, origin_y=8200000.0)
    trio = write_export(spec, tmp_path / 'origen')
    ficheros = [R.leer_fichero(r, n) for r, n in zip(trio, R.NOMBRES)]
    serie = _dataset()
    mapa = Mapa(17)
    R.registrar(ficheros, mapa)
    S.registrar(serie, mapa)
    mapa.congelar()
    bench = tmp_path / 'bench'
    R.escribir(ficheros, bench, mapa, semilla=17)
    S.escribir(serie, bench, mapa, semilla=17)
    origen = Origen.desde(red=ficheros, series=serie, perfil=_perfil(tmp_path), textos=[INFORME])
    return bench, origen, ficheros, serie


def _revisar(carpeta, origen):
    from convertersmartgrid.adaptadores.benchmarks.reidentificacion import revisar
    return revisar(carpeta, origen)


def test_el_benchmark_limpio_pasa(tmp_path):
    """112:RF-4 — sin fugas, ningún hallazgo: el control no rechaza lo que está bien anonimizado."""
    bench, origen, _, _ = _limpio(tmp_path)
    assert _revisar(bench, origen) == []


def _filas(ruta: Path):
    with ruta.open(encoding='utf-8', newline='') as f:
        return list(csv.reader(f))


def _escribir_filas(ruta: Path, filas):
    with ruta.open('w', encoding='utf-8', newline='') as f:
        csv.writer(f, lineterminator='\n').writerows(filas)


def _reemplazar_en(ruta: Path, viejo: str, nuevo: str):
    texto = ruta.read_text(encoding='utf-8')
    assert viejo in texto
    ruta.write_text(texto.replace(viejo, nuevo, 1), encoding='utf-8')


def _plantar(clase: str, bench: Path, ficheros, serie) -> str:
    """Planta una fuga de ``clase`` en el benchmark y devuelve el valor original plantado."""
    red = next(f for f in ficheros if f.nombre == 'RED.txt')
    carga = next(f for f in ficheros if f.nombre == 'CARGA.txt')
    if clase == 'identificador':
        original = next(e[2]['NetworkID'] for e in red.entradas if e[0] == 'fila' and e[1] == 'HEADNODES')
        lineas = (bench / 'RED.txt').read_text(encoding='utf-8').splitlines()
        i = lineas.index('[HEADNODES]') + 2
        lineas[i] = lineas[i].split(',')[0] + ',' + original
        (bench / 'RED.txt').write_text('\n'.join(lineas) + '\n', encoding='utf-8')
        return original
    if clase == 'cliente':
        original = next(e[2]['CustomerNumber'] for e in carga.entradas if e[0] == 'fila' and e[1] == 'CUSTOMER LOADS')
        with (bench / 'CARGA.txt').open('a', encoding='utf-8') as f:
            f.write(f'BT-1,BE-1,SPOT,{original},1\n')
        return original
    if clase == 'coordenada':
        fila = next(e[2] for e in red.entradas if e[0] == 'fila' and e[1] == 'NODE')
        lineas = (bench / 'RED.txt').read_text(encoding='utf-8').splitlines()
        i = lineas.index('[NODE]') + 2
        lineas[i] = f"{lineas[i].split(',')[0]},{float(fila['CoordX']) + 120:.3f},{float(fila['CoordY']) - 80:.3f}"
        (bench / 'RED.txt').write_text('\n'.join(lineas) + '\n', encoding='utf-8')
        return fila['CoordX']
    if clase == 'termino':
        with (bench / 'BD_Equipo.txt').open('a', encoding='utf-8') as f:
            f.write(f'DEFAULT,0.1,0.2,0.3,0.4,0.5,0.6,100,,{TERMINO.upper()}\n')
        return TERMINO
    if clase == 'fecha':
        filas = _filas(bench / 'series.csv')
        j = filas[0].index('t')
        original = str(serie.objetivos[0].curva.t[100].astype('datetime64[s]')).replace(' ', 'T')
        filas[5][j] = original
        _escribir_filas(bench / 'series.csv', filas)
        return original
    if clase == 'secuencia':
        filas = _filas(bench / 'series.csv')
        j = filas[0].index('v')
        valores = np.asarray(serie.objetivos[1].curva.columnas[0][500:512])
        for k, v in enumerate(valores):
            filas[200 + k][j] = f'{v:.6f}'
        _escribir_filas(bench / 'series.csv', filas)
        return f'{valores[0]:.6f}'
    if clase == 'texto':
        with (bench / 'CARGA.txt').open('a', encoding='utf-8') as f:
            f.write('nota: el informe de planificacion de la gerencia tecnica recomienda reforzar todo\n')
        return 'planificacion de la gerencia'
    if clase == 'fichero':
        (bench / 'notas_del_operador.txt').write_text('nada\n', encoding='utf-8')
        return 'notas_del_operador.txt'
    raise AssertionError(clase)


CLASES = ('identificador', 'cliente', 'coordenada', 'termino', 'fecha', 'secuencia', 'texto', 'fichero')


@pytest.mark.parametrize('clase', CLASES)
def test_cada_fuga_plantada_se_rechaza_con_su_clase(tmp_path, clase):
    """112:RF-4, RF-10 — una fuga de cada clase en una copia: se rechaza, dice su clase y no repite el original."""
    from convertersmartgrid.adaptadores.benchmarks.reidentificacion import FugaDetectada, exigir_limpio
    bench, origen, ficheros, serie = _limpio(tmp_path)
    copia = tmp_path / f'copia_{clase}'
    shutil.copytree(bench, copia)
    original = _plantar(clase, copia, ficheros, serie)

    hallazgos = _revisar(copia, origen)
    assert hallazgos, f'la fuga de clase {clase} pasó el control'
    assert clase in {h.tipo for h in hallazgos}, [h.tipo for h in hallazgos]
    if clase != 'fichero':        # el nombre de un fichero de más no es un dato de la empresa: se dice cuál es
        for h in hallazgos:
            assert original not in h.motivo and original not in h.texto()
    with pytest.raises(FugaDetectada, match=clase) as exc:
        exigir_limpio(hallazgos)
    if clase != 'fichero':
        assert original not in str(exc.value)
    # La copia limpia sigue pasando: la fuga estaba solo en la copia.
    assert _revisar(bench, origen) == []


def test_un_perfil_ilegible_no_deja_emitir(tmp_path):
    """112:RF-4 — si el perfil de la empresa no se puede leer, el control no sabe qué términos buscar: no se arma el
    control (y por tanto no se emite) en vez de buscar «ningún término» en silencio."""
    from convertersmartgrid.adaptadores.benchmarks.reidentificacion import Origen
    from convertersmartgrid.dominio.privacidad import PerfilIlegible
    roto = tmp_path / 'perfil.json'
    roto.write_text('{"empresa": "' + TERMINO + '",', encoding='utf-8')
    with pytest.raises(PerfilIlegible, match='perfil.json'):
        Origen.desde(perfil=roto)
    with pytest.raises(PerfilIlegible, match='no existe'):
        Origen.desde(perfil=tmp_path / 'falta.json')
    assert Origen.desde(perfil=None).terminos == frozenset()


# --------------------------------------------------------------------------- T12: semilla secreta (112:RF-5, RF-12)

SECRETA = 8_811_234_567_890_123_457      # con la forma de las que se sortean: 63 bits


def _hay_semilla() -> bool:
    import importlib.util
    return importlib.util.find_spec('convertersmartgrid.dominio.benchmarks.semilla') is not None


def test_semilla_publica_de_un_solo_sentido():
    """112:RF-12 — lo publicado es sha256("publica:" + semilla): no contiene la secreta y siempre es la misma."""
    import hashlib
    assert _hay_semilla(), 'falta convertersmartgrid.dominio.benchmarks.semilla'
    from convertersmartgrid.dominio.benchmarks.semilla import semilla_publica
    publica = semilla_publica(SECRETA)
    assert publica == hashlib.sha256(f'publica:{SECRETA}'.encode()).hexdigest()
    assert str(SECRETA) not in publica and publica == semilla_publica(SECRETA)
    assert publica != semilla_publica(SECRETA + 1)


def test_la_semilla_secreta_se_guarda_solo_en_el_equipo(tmp_path):
    """112:RF-12 — la secreta queda en la carpeta local, por la huella del origen, nunca en el destino del benchmark;
    una segunda semilla distinta para el mismo origen no pisa la primera."""
    assert _hay_semilla(), 'falta convertersmartgrid.dominio.benchmarks.semilla'
    from convertersmartgrid.dominio.benchmarks.semilla import guardar_secreta, leer_secreta, nueva_semilla
    destino = tmp_path / 'bench'
    destino.mkdir()
    ruta = guardar_secreta('ab' * 32, SECRETA, raiz=tmp_path / 'local')
    assert ruta == tmp_path / 'local' / 'benchmarks' / ('ab' * 32) / 'semilla'
    assert destino not in ruta.parents and not list(destino.iterdir())
    assert leer_secreta('ab' * 32, raiz=tmp_path / 'local') == SECRETA
    assert leer_secreta('cd' * 32, raiz=tmp_path / 'local') is None
    assert guardar_secreta('ab' * 32, SECRETA, raiz=tmp_path / 'local') == ruta     # la misma: nada cambia
    with pytest.raises(FileExistsError):
        guardar_secreta('ab' * 32, SECRETA + 1, raiz=tmp_path / 'local')
    assert leer_secreta('ab' * 32, raiz=tmp_path / 'local') == SECRETA
    with pytest.raises(ValueError, match='huella'):
        guardar_secreta('../fuera', SECRETA, raiz=tmp_path / 'local')
    s = nueva_semilla()
    assert isinstance(s, int) and len(str(s)) >= 12 and s != nueva_semilla()


def test_semilla_corta_no_se_admite():
    """112:RF-12 — una semilla corta no se distingue de cualquier número del benchmark: el control no la vería."""
    assert _hay_semilla(), 'falta convertersmartgrid.dominio.benchmarks.semilla'
    from convertersmartgrid.dominio.benchmarks.semilla import validar_secreta
    for corta in (17, -SECRETA, True, '881123456789012'):
        with pytest.raises(ValueError, match='semilla'):
            validar_secreta(corta)
    assert validar_secreta(SECRETA) == SECRETA


@pytest.mark.parametrize('fuga', ['semilla', 'derivada', 'publica'])
def test_un_manifiesto_con_la_semilla_secreta_se_rechaza(tmp_path, fuga):
    """112:RF-5, RF-12 — la semilla de los seudónimos, o una cadena con la que se rehace el mapa, no se publica; la
    pública sí."""
    import inspect

    from convertersmartgrid.adaptadores.benchmarks.reidentificacion import Origen
    assert _hay_semilla(), 'falta convertersmartgrid.dominio.benchmarks.semilla'
    assert 'semilla' in inspect.signature(Origen.desde).parameters, 'el control no sabe de la semilla secreta'
    from convertersmartgrid.dominio.benchmarks.semilla import semilla_publica
    bench, origen, ficheros, serie = _limpio(tmp_path)
    origen = Origen.desde(red=ficheros, series=serie, perfil=_perfil(tmp_path), textos=[INFORME], semilla=SECRETA)
    assert str(SECRETA) not in repr(origen)
    contenido = {'semilla': {'semilla': SECRETA, 'derivada': f'{SECRETA}:cliente',
                             'publica': semilla_publica(SECRETA)}[fuga]}
    (bench / 'manifiesto.json').write_text(json.dumps(contenido), encoding='utf-8')
    hallazgos = _revisar(bench, origen)
    if fuga == 'publica':
        assert hallazgos == []
    else:
        assert {h.tipo for h in hallazgos} == {'semilla'}
        assert all(str(SECRETA) not in h.texto() for h in hallazgos)




# --------------------------------------------------------------------------- T13: geometría y publicación (112:RF-3, RF-13, RF-14)
# (Se añade al final de tests/test_benchmarks_reidentificacion.py al empezar la T13.)

def _red_grande(tmp_path: Path, semilla: int, *, feeders: int = 6, layout: str = 'reducido', secciones: int = 110):
    from convertersmartgrid.dominio.benchmarks.sintetico import ExportSpec as ES
    from convertersmartgrid.dominio.benchmarks.sintetico import write_export as we
    # Longitudes y cargas variadas, como una red real: sin ellas todos los tramos medirían lo mismo.
    spec = ES(feeders=feeders, sections_per_feeder=secciones, loads_per_feeder=20, seed=semilla, layout=layout,
              origin_x=300000.0, origin_y=8200000.0,
              longitudes_m=(1.0, 8.0, 25.0, 60.0, 120.0, 250.0, 500.0, 900.0, 1500.0, 2400.0, 4000.0),
              cargas_kw=(1.0, 3.0, 6.0, 10.0, 15.0, 25.0, 40.0, 70.0, 120.0, 200.0, 400.0))
    return we(spec, tmp_path / f'origen_{semilla}')


def test_geometria_el_atacante_que_conoce_el_margen_empareja_la_red_perturbada():
    """112:RF-14 — con ±5 % las longitudes ordenadas se emparejan dentro del margen: la red perturbada está identificada."""
    assert importlib.util.find_spec('convertersmartgrid.dominio.benchmarks.geometria'), 'falta convertersmartgrid.dominio.benchmarks.geometria'
    import random

    from convertersmartgrid.dominio.benchmarks.geometria import UMBRAL_IDENTIFICADO, fraccion_emparejada
    r = random.Random(3)
    original = [math.exp(r.uniform(0, math.log(4000))) for _ in range(400)]
    perturbada = [x * (1 + r.uniform(-0.05, 0.05)) for x in original]
    otra = [math.exp(r.uniform(0, math.log(4000))) * 7.3 for _ in range(400)]
    assert fraccion_emparejada(original, perturbada, 0.05) >= UMBRAL_IDENTIFICADO == 0.5
    assert fraccion_emparejada(original, otra, 0.05) < UMBRAL_IDENTIFICADO
    assert fraccion_emparejada([], [], 0.05) == 0.0


@pytest.mark.parametrize('semilla,layout', [(3101, 'reducido'), (3202, 'completo')])
def test_geometria_de_uso_local_reproduce_y_se_marca(tmp_path, semilla, layout):
    """112:RF-13, RF-3, RF-14 — trazado sintético y longitudes perturbadas: reproduce el estudio y queda «uso local»."""
    assert importlib.util.find_spec('convertersmartgrid.dominio.benchmarks.geometria'), 'falta convertersmartgrid.dominio.benchmarks.geometria'
    pytest.importorskip('pandapower')
    from convertersmartgrid.adaptadores.benchmarks import generar_benchmark
    from convertersmartgrid.adaptadores.dataset import DatasetRed
    trio = _red_grande(tmp_path, semilla, feeders=3, layout=layout)
    m = generar_benchmark(*trio, tmp_path / 'bench', semilla=SECRETA, raiz=tmp_path / 'local')
    assert m['uso_local'] is True
    assert m['geometria']['trazado'] == 'sintetico' and 0 < m['geometria']['amplitud'] <= 0.05
    assert m['geometria']['identificados'] >= 1        # lo esperado con una red real perturbada (aclaración RF-14)
    original = DatasetRed.from_files(*trio)
    bench = DatasetRed.from_files(*(tmp_path / 'bench' / n for n in ('RED.txt', 'CARGA.txt', 'BD_Equipo.txt')))
    xo = sorted(float(n['CoordX']) for n in original.nodes.values() if n.get('CoordX'))
    xb = sorted(float(n['CoordX']) for n in bench.nodes.values() if n.get('CoordX'))
    assert len(xo) == len(xb) and xo != xb
    lo = sorted(float(c['Length']) for c in original.line_configurations.values())
    lb = sorted(float(c['Length']) for c in bench.line_configurations.values())
    assert lo != lb and len(lo) == len(lb)


def test_geometria_publicar_rechaza_lo_de_uso_local(tmp_path):
    """112:RF-14 — un benchmark derivado de una red real no sale por la vía de publicación."""
    assert importlib.util.find_spec('convertersmartgrid.dominio.benchmarks.geometria'), 'falta convertersmartgrid.dominio.benchmarks.geometria'
    pytest.importorskip('pandapower')
    from convertersmartgrid.adaptadores.benchmarks import NoPublicable, generar_benchmark, publicar
    trio = _red_grande(tmp_path, 3303, feeders=2)
    generar_benchmark(*trio, tmp_path / 'bench', semilla=SECRETA, raiz=tmp_path / 'local')
    with pytest.raises(NoPublicable, match='uso local.*la identifica; publique el sintético'):
        publicar(tmp_path / 'bench', tmp_path / 'publico')
    assert not (tmp_path / 'publico').exists()


def test_geometria_el_publicable_sale_de_las_estadisticas_y_no_se_identifica(tmp_path):
    """112:RF-13, RF-14 — el publicable es sintético con los agregados del origen: ningún alimentador se identifica."""
    assert importlib.util.find_spec('convertersmartgrid.dominio.benchmarks.geometria'), 'falta convertersmartgrid.dominio.benchmarks.geometria'
    from convertersmartgrid.adaptadores.benchmarks import publicar
    from convertersmartgrid.adaptadores.benchmarks.publicable import generar_publicable
    trio = _red_grande(tmp_path, 3404, feeders=6, secciones=200)    # tamaños sorteados: ≥ 500 tramos en total
    m = generar_publicable([trio], tmp_path / 'pub', semilla=SECRETA, raiz=tmp_path / 'local')
    assert m['uso_local'] is False
    assert m['geometria']['identificados'] == 0
    assert m['minimos'] == {'alimentadores': 5, 'tramos': 500}
    assert m['estadisticas']['alimentadores'] == 6 and m['estadisticas']['tramos'] >= 500
    # Ningún tramo del origen (su código con su longitud) está en el publicable: el generador comparte la forma de los
    # códigos, no los tramos.
    from convertersmartgrid.adaptadores.dataset import DatasetRed
    original = DatasetRed.from_files(*trio)
    pub = DatasetRed.from_files(*(tmp_path / 'pub' / n for n in ('RED.txt', 'CARGA.txt', 'BD_Equipo.txt')))
    tramos_o = {(s, c['Length']) for s, c in original.line_configurations.items()}
    tramos_p = {(s, c['Length']) for s, c in pub.line_configurations.items()}
    assert len(tramos_p) >= 500 and not tramos_o & tramos_p
    publicar(tmp_path / 'pub', tmp_path / 'publico')
    assert (tmp_path / 'publico' / 'manifiesto.json').is_file()


def test_geometria_un_origen_pequeno_se_agrupa_o_no_se_emite(tmp_path):
    """112:RF-14 — con menos de 5 alimentadores o de 500 tramos se agrupa con la entrega; si no llega, no se emite."""
    assert importlib.util.find_spec('convertersmartgrid.dominio.benchmarks.geometria'), 'falta convertersmartgrid.dominio.benchmarks.geometria'
    from convertersmartgrid.adaptadores.benchmarks.publicable import AgregadoInsuficiente, generar_publicable
    pequenas = [_red_grande(tmp_path, s, feeders=2, secciones=200) for s in (3501, 3502, 3503)]
    m = generar_publicable(pequenas, tmp_path / 'pub', semilla=SECRETA, raiz=tmp_path / 'local')
    assert m['estadisticas']['alimentadores'] == 6 and m['estadisticas']['redes_agrupadas'] == 3
    with pytest.raises(AgregadoInsuficiente, match='5 alimentadores'):
        generar_publicable(pequenas[:1], tmp_path / 'otro', semilla=SECRETA, raiz=tmp_path / 'local')
    assert not (tmp_path / 'otro').exists()


def test_geometria_los_minimos_se_suben_pero_no_se_bajan(tmp_path):
    """112:RF-14 — un mínimo por encima del de la spec se respeta; uno por debajo se rechaza."""
    assert importlib.util.find_spec('convertersmartgrid.dominio.benchmarks.geometria'), 'falta convertersmartgrid.dominio.benchmarks.geometria'
    from convertersmartgrid.adaptadores.benchmarks.publicable import minimos_para
    assert minimos_para(None) == {'alimentadores': 5, 'tramos': 500}
    assert minimos_para({'alimentadores': 8}) == {'alimentadores': 8, 'tramos': 500}
    with pytest.raises(ValueError, match='no se puede bajar de 5: se pidió 4'):
        minimos_para({'alimentadores': 4})
    with pytest.raises(ValueError, match='mínimo'):
        minimos_para({'tramos': 100})


# --------------------------------------------------------------------------- T14: cuadre contra la geometría pública (112:RF-14)

def _hay_publica() -> bool:
    return importlib.util.find_spec('convertersmartgrid.adaptadores.benchmarks.geometria_publica') is not None


def _red_ramificada(semilla: int, nudos: int = 80):
    """Una red radial con ramas y giros sorteados, como el trazado de una calle real: (cabecera, tramos, coordenadas)."""
    import random
    r = random.Random(semilla)
    coords = {'N0': (300000.0, 8200000.0)}
    rumbo = {'N0': r.uniform(0, 2 * math.pi)}
    tramos = []
    for k in range(1, nudos):
        padre = f'N{r.randrange(max(0, k - 6), k)}' if r.random() < 0.8 else f'N{r.randrange(k)}'
        theta = rumbo[padre] + r.uniform(-1.2, 1.2)
        largo = r.uniform(40.0, 400.0)
        x, y = coords[padre]
        coords[f'N{k}'] = (x + largo * math.cos(theta), y + largo * math.sin(theta))
        rumbo[f'N{k}'] = theta
        tramos.append((f'T{k}', padre, f'N{k}'))
    return 'N0', tramos, coords


def test_publica_la_red_girada_cuadra_y_el_trazado_no(tmp_path):
    """112:RF-14 — una red girada (T2, uso local) cuadra por ICP con la «pública»; el trazado sintético, con la misma
    topología y las longitudes perturbadas, no. Y con menos de 3 vértices no se compara."""
    assert _hay_publica(), 'falta convertersmartgrid.adaptadores.benchmarks.geometria_publica'
    from convertersmartgrid.dominio.benchmarks import geometria as G
    from convertersmartgrid.dominio.benchmarks.seudonimos import transformar_coordenadas
    publica = {}
    for k, semilla in enumerate((3601, 3602, 3603)):
        _cab, _tramos, coords = _red_ramificada(semilla)
        publica[f'A{k}'] = np.array(list(coords.values()))
    cabecera, tramos, coords = _red_ramificada(3601)
    girada = np.array(transformar_coordenadas(list(coords.values()), semilla=99))
    assert G.cuadre_publico({'g': girada}, publica) == ['g']
    largos = {t: (math.dist(coords[a], coords[b]), 'CABLE') for t, a, b in tramos}
    nuevos = G.perturbar(largos, semilla=SECRETA, amplitud=0.05)
    trazado, _inter = G.trazar([('A0', cabecera, tramos)], {t: float(nuevos[t]) for t in largos},
                               (299000.0, 8199000.0, 301000.0, 8201000.0))
    sintetica = np.array([trazado[n] for n in coords])
    assert G.cuadre_publico({'s': sintetica}, publica) == []
    assert G.residuo_icp(girada[:2], publica['A0']) == float('inf')


def _publicaciones():
    from convertersmartgrid.adaptadores.entrada.vnr.discovery.catalog import Publication
    base = 'https://www2.osinergmin.gob.pe/GRT/Procesos-Regulatorios/VNR/'
    return [
        Publication('p1', title='Distribuidora Uno', company='Distribuidora Uno', period_label='2025',
                    regulatory_reference='RCD 154-2026-OS/CD', download_url=base + '2025/VNRGIS/Distribuidora%20Uno.zip',
                    file_name='Distribuidora Uno.zip', file_type='zip', publication_type='REGULATORY_VNRGIS_PACKAGE'),
        Publication('p2', title='Distribuidora Uno', company='Distribuidora Uno', period_label='2025',
                    regulatory_reference='RCD 184-2026-OS/CD',
                    download_url=base + '2026/01%20VNRGIS/Distribuidora%20Uno.zip', file_name='Distribuidora Uno.zip',
                    file_type='zip', publication_type='REGULATORY_VNRGIS_PACKAGE'),
        Publication('p3', title='Otra Empresa', company='Otra Empresa', period_label='2025',
                    regulatory_reference='RCD 184-2026-OS/CD', download_url=base + '2026/01%20VNRGIS/Otra%20Empresa.zip',
                    file_name='Otra Empresa.zip', file_type='zip', publication_type='REGULATORY_VNRGIS_PACKAGE'),
    ]


def test_publica_la_descarga_es_bajo_demanda_por_empresa_y_fuera_del_programa(tmp_path, monkeypatch):
    """112:RF-14 — el plan elige el paquete vigente (por resolución) de UNA empresa, de una URL oficial, sin abrir la
    red; un destino dentro del programa o de sus datos se rechaza (no puede acabar en el corpus); la descarga pasa por
    el gestor del VNR con esa URL."""
    import socket
    assert _hay_publica(), 'falta convertersmartgrid.adaptadores.benchmarks.geometria_publica'
    from convertersmartgrid.adaptadores.benchmarks import geometria_publica as GP
    from convertersmartgrid.dominio.runtime_paths import raiz_local, raiz_programa

    def sin_red(*a, **k):
        raise AssertionError('el plan abrió la red')
    monkeypatch.setattr(socket, 'create_connection', sin_red)
    plan = GP.plan_descarga('distribuidora uno', tmp_path / 'vnr', _publicaciones())
    assert plan['url'].startswith('https://www2.osinergmin.gob.pe/') and '2026/01%20VNRGIS' in plan['url']
    assert plan['resolucion'] == 'RCD 184-2026-OS/CD' and plan['destino'].endswith('Distribuidora Uno.zip')
    with pytest.raises(LookupError, match='Sin Paquete'):
        GP.plan_descarga('Sin Paquete', tmp_path / 'vnr', _publicaciones())
    for dentro in (raiz_programa() / 'output' / 'vnr', raiz_local() / 'vnr'):
        with pytest.raises(GP.DestinoNoPermitido):
            GP.plan_descarga('Distribuidora Uno', dentro, _publicaciones())
    with pytest.raises(GP.DestinoNoPermitido):
        GP.comprobar_destino('relativa/vnr')

    llamadas = []

    class Gestor:
        def download(self, url, destino, **k):
            llamadas.append((url, Path(destino), k))
            return {'sha256': '0' * 64, 'url': url}
    m = GP.descargar(plan, gestor=Gestor())
    assert llamadas == [(plan['url'], Path(plan['destino']), {'publication_id': 'p2', 'company': 'Distribuidora Uno',
                                                              'period': '2025', 'cancelled': None})]
    assert m['url'] == plan['url']


def test_publica_el_manifiesto_declara_los_identificados_contra_la_publica(tmp_path):
    """112:RF-14 — con la geometría pública (un trío, p. ej. el del ETL del VNR), el manifiesto dice cuántos
    alimentadores del benchmark cuadran con ella: con el trazado sintético, ninguno."""
    pytest.importorskip('pandapower')
    assert _hay_publica(), 'falta convertersmartgrid.adaptadores.benchmarks.geometria_publica'
    import inspect

    from convertersmartgrid.adaptadores.benchmarks import generar_benchmark
    assert 'geometria_publica' in inspect.signature(generar_benchmark).parameters
    trio = _red_grande(tmp_path, 3702, feeders=2)
    m = generar_benchmark(*trio, tmp_path / 'bench', semilla=SECRETA, raiz=tmp_path / 'local', geometria_publica=trio)
    assert m['geometria']['identificados_publica'] == 0 and m['geometria']['alimentadores'] == 2
