"""Spec 100 T1 a T3 — la aceptación automática de una versión: la matriz, el recorrido y el veredicto (100:RF-1 a RF-7).

Con una web falsa (el ejecutor de la herramienta se sustituye): ningún DIgSILENT, ninguna web real ni dato de una
empresa. Las variables ``${CSG_...}`` de la matriz se dan con valores sintéticos sorteados.
"""
from __future__ import annotations

import importlib.util
import json
import random
import string
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
MATRIZ = RAIZ / 'config' / 'aceptacion' / 'matriz.json'
SEMILLA = 100_3


def _herramienta():
    """La herramienta de la 100: su ausencia es la falla de la aserción, no un error de importación."""
    ruta = RAIZ / 'tools' / 'aceptacion_version.py'
    assert ruta.is_file(), 'falta tools/aceptacion_version.py (100 T2)'
    spec = importlib.util.spec_from_file_location('aceptacion_version', ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _variables(rng):
    nombre = lambda: ''.join(rng.choice(string.ascii_uppercase) for _ in range(2)) + str(rng.randint(100, 999))
    v = {'CSG_DEMANDA_DIR': 'demanda', 'CSG_ACEPTACION_PERIODO': '2041'}
    for f in ('TXT', 'MDB', 'VNR'):
        v.update({f'CSG_ACEPTACION_{f}_ESPACIO': f'esp{f.lower()}', f'CSG_ACEPTACION_{f}_ALIMENTADOR': nombre(),
                  f'CSG_ACEPTACION_{f}_VARIOS': f'{nombre()} {nombre()}', f'CSG_ACEPTACION_{f}_SISTEMA': 'Zonal X'})
    return v


class WebFalsa:
    """Responde por el espacio de cada caso: ``rc`` (espacio → lista de rc por intento); deja el registro y el
    resumen como la herramienta real."""

    def __init__(self, rc=None):
        self.rc, self.llamadas = dict(rc or {}), []

    def __call__(self, argv, registro, cwd):
        self.llamadas.append(list(argv))
        espacio = argv[argv.index('--espacio') + 1]
        cola = self.rc.get(espacio, [0])
        rc = cola.pop(0) if len(cola) > 1 else cola[0]
        registro.write_text(f'corrida falsa {espacio} rc={rc}\n', encoding='utf-8')
        if '--resumen-json' in argv:
            Path(argv[argv.index('--resumen-json') + 1]).write_text(json.dumps({'no_calibrados': [] if rc == 0 else
                                                                                 ['A1']}), encoding='utf-8')
        return rc


# --- T1: la matriz (RF-1, RF-4) -------------------------------------------------------------------------------------
def test_100_rf1_matriz_real_cubre_cada_fuente_con_cada_alcance_sin_datos_de_una_empresa():
    """100:RF-1 — la matriz del repositorio declara TXT, MDB y VNR-GIS por separado, cada una con un alimentador,
    varios unidos y un sistema entero, y sus datos de empresa van como ``${CSG_...}``."""
    mod = _herramienta()
    m = mod.cargar_matriz(MATRIZ)
    assert {(c['fuente'], c['alcance']) for c in m['casos']} == {(f, a) for f in mod.FUENTES for a in mod.ALCANCES}
    for c in m['casos']:
        espacio = c['argumentos'][c['argumentos'].index('--espacio') + 1]
        assert espacio == f'${{CSG_ACEPTACION_{c["fuente"].upper()}_ESPACIO}}', 'cada fuente en su espacio: no se mezclan'


@pytest.mark.parametrize('cambio, mensaje', (
    (lambda m: m['casos'].pop(), 'faltan en la matriz'),
    (lambda m: m['casos'][0]['argumentos'].__setitem__(1, 'espacio-de-una-empresa'), 'dato de la empresa'),
    (lambda m: m['casos'][1].update(id=m['casos'][0]['id']), 'repetido'),
    (lambda m: m['casos'][0].update(fuente='mixta'), 'desconocidos'),
    (lambda m: m.update(intentos=0), 'intentos'),
    (lambda m: m['herramientas']['sistema_web']['codigos'].update({'9': 'quizas'}), 'codigos'),
), ids=('falta_un_alcance', 'dato_literal', 'id_repetido', 'fuente_mezclada', 'sin_intentos', 'codigo_raro'))
def test_100_rf1_matriz_invalida_se_rechaza_diciendo_por_que(tmp_path, cambio, mensaje):
    """100:RF-1, 100:RF-5 — una matriz sin un alcance, con un dato literal de empresa, con ids repetidos, con una
    fuente que no es una de las tres, sin intentos o con un código de salida sin sentido no se usa."""
    mod = _herramienta()
    m = json.loads(MATRIZ.read_text(encoding='utf-8'))
    cambio(m)
    ruta = tmp_path / 'matriz.json'
    ruta.write_text(json.dumps(m), encoding='utf-8')
    with pytest.raises(mod.MatrizError, match=mensaje):
        mod.cargar_matriz(ruta)


def test_100_rf4_matriz_y_recorrido_no_crean_tareas_ni_casillas(tmp_path):
    """100:RF-4 — correr la aceptación no escribe nada en specs/ ni crea casillas de pendiente: todo va al informe."""
    mod = _herramienta()
    repo = tmp_path / 'repo'
    (repo / 'specs').mkdir(parents=True)
    antes = sorted(p.name for p in (repo / 'specs').iterdir())
    mod.aceptar_version(mod.cargar_matriz(MATRIZ), 'v' * 40, tmp_path / 'salida', variables=_variables(random.Random(1)),
                        ejecutar=WebFalsa(), repo=repo, regresiones=tmp_path / 'reg')
    assert sorted(p.name for p in (repo / 'specs').iterdir()) == antes
    assert not list((tmp_path / 'salida').rglob('tasks.md'))


# --- T2: el recorrido (RF-2, RF-3, RF-5) ----------------------------------------------------------------------------
def test_100_rf2_rf3_recorrido_en_serie_con_informe_por_caso(tmp_path):
    """100:RF-2, 100:RF-3 — los casos se corren en el orden de la matriz, uno tras otro, y cada uno deja su informe con
    la revisión, el rc, el estado, las cifras de la herramienta y las huellas de lo comprobado."""
    mod = _herramienta()
    matriz, web = mod.cargar_matriz(MATRIZ), WebFalsa()
    variables = _variables(random.Random(SEMILLA))
    informe = mod.aceptar_version(matriz, 'a' * 40, tmp_path / 's', variables=variables, ejecutar=web,
                                  regresiones=tmp_path / 'reg')
    assert [ll[ll.index('--espacio') + 1] for ll in web.llamadas] == [
        variables[f'CSG_ACEPTACION_{c["fuente"].upper()}_ESPACIO'] for c in matriz['casos']]
    redes = [ll[ll.index('--red') + 1:ll.index('--demanda-dir')] for ll in web.llamadas
             if '--red' in ll and ll[ll.index('--espacio') + 1] == 'esptxt']
    assert variables['CSG_ACEPTACION_TXT_VARIOS'].split() in redes, 'la variable con varios da varios argumentos'
    caso = json.loads((tmp_path / 's' / 'casos' / 'txt-alimentador.json').read_text(encoding='utf-8'))
    assert caso['revision'] == 'a' * 40 and caso['rc'] == 0 and caso['estado'] == 'aceptado'
    assert caso['cifras'] == {'no_calibrados': []} and all(len(h) == 64 for h in caso['huellas'].values())
    assert set(informe['casos']) == {c['id'] for c in matriz['casos']} and informe['inicio'] and informe['fin']
    assert 'arbol' in informe and informe['version'] == 'a' * 40


def test_100_rf5_recorrido_relanza_lo_recuperable_hasta_los_intentos_y_retoma_sin_repetir_lo_aceptado(tmp_path):
    """100:RF-5 — un caso cortado por una causa recuperable se relanza hasta los intentos de la matriz; al relanzar la
    aceptación, lo ya aceptado sobre la misma versión no se repite y se sigue desde donde quedó."""
    mod = _herramienta()
    matriz = mod.cargar_matriz(MATRIZ)
    variables = _variables(random.Random(SEMILLA))
    web = WebFalsa({'espmdb': [2, 0]})
    informe = mod.aceptar_version(matriz, 'b' * 40, tmp_path / 's', variables=variables, ejecutar=web,
                                  regresiones=tmp_path / 'reg')
    assert informe['casos']['mdb-alimentador']['intentos'] == 2 and informe['casos']['mdb-alimentador']['estado'] == 'aceptado'
    siempre = WebFalsa({'espvnr': [2]})
    otra = mod.aceptar_version(matriz, 'c' * 40, tmp_path / 's2', variables=variables, ejecutar=siempre,
                               regresiones=tmp_path / 'reg')
    assert otra['casos']['vnr-sistema']['intentos'] == matriz['intentos'] and otra['casos']['vnr-sistema']['estado'] == 'fallo'
    retomada = WebFalsa()
    mod.aceptar_version(matriz, 'c' * 40, tmp_path / 's2', variables=variables, ejecutar=retomada,
                        regresiones=tmp_path / 'reg')
    assert {ll[ll.index('--espacio') + 1] for ll in retomada.llamadas} == {'espvnr'}, 'solo se repite lo no aceptado'
    desde = WebFalsa()
    mod.aceptar_version(matriz, 'd' * 40, tmp_path / 's3', variables=variables, ejecutar=desde, desde='vnr-varios',
                        regresiones=tmp_path / 'reg')
    assert len(desde.llamadas) == 2


def test_100_rf3_recorrido_sin_una_variable_deja_el_caso_sin_datos_y_no_lo_corre(tmp_path):
    """100:RF-3 — sin una variable de la matriz, el caso no se corre: queda «sin_datos» con la variable que falta."""
    mod = _herramienta()
    variables = _variables(random.Random(SEMILLA))
    del variables['CSG_ACEPTACION_MDB_VARIOS']
    web = WebFalsa()
    informe = mod.aceptar_version(mod.cargar_matriz(MATRIZ), 'e' * 40, tmp_path / 's', variables=variables,
                                  ejecutar=web, regresiones=tmp_path / 'reg')
    caso = informe['casos']['mdb-varios']
    assert caso['estado'] == 'sin_datos' and 'CSG_ACEPTACION_MDB_VARIOS' in caso['causa'] and caso['intentos'] == 0
    assert len(web.llamadas) == 8


# --- T3: el veredicto (RF-6, RF-7) ----------------------------------------------------------------------------------
def test_100_rf7_veredicto_aceptada_solo_con_todos_los_casos_sobre_la_misma_revision(tmp_path):
    """100:RF-7 — la versión queda aceptada solo si todos los casos de la matriz pasan sobre esa misma revisión: un
    caso aceptado sobre otra revisión no cuenta."""
    mod = _herramienta()
    matriz = mod.cargar_matriz(MATRIZ)
    variables = _variables(random.Random(SEMILLA))
    bien = mod.aceptar_version(matriz, 'f' * 40, tmp_path / 's', variables=variables, ejecutar=WebFalsa(),
                               regresiones=tmp_path / 'reg')
    assert bien['veredicto'] == {'aceptada': True, 'version': 'f' * 40, 'motivos': []}
    casos = dict(bien['casos'])
    casos['txt-sistema'] = {**casos['txt-sistema'], 'revision': '0' * 40}
    otro = mod.veredicto(casos, matriz, 'f' * 40)
    assert not otro['aceptada'] and otro['motivos'][0].startswith('txt-sistema: aceptado sobre otra revisión')
    sin_uno = mod.veredicto({k: v for k, v in bien['casos'].items() if k != 'vnr-varios'}, matriz, 'f' * 40)
    assert sin_uno['motivos'] == ['vnr-varios: sin correr']


def test_100_rf6_veredicto_con_un_fallo_del_conversor_dice_su_causa_y_deja_la_comprobacion_permanente(tmp_path):
    """100:RF-6 — un caso que falla por un defecto del conversor va con su causa al informe y deja el borrador de su
    comprobación permanente (081) con sus cuatro apartados; la versión no se acepta y la salida lo dice con rc=1."""
    mod = _herramienta()
    matriz = mod.cargar_matriz(MATRIZ)
    informe = mod.aceptar_version(matriz, '1' * 40, tmp_path / 's', variables=_variables(random.Random(SEMILLA)),
                                  ejecutar=WebFalsa({'esptxt': [1]}), regresiones=tmp_path / 'reg')
    caso = informe['casos']['txt-alimentador']
    assert caso['estado'] == 'fallo' and 'defecto del conversor' in caso['causa'] and caso['cifras'] == {'no_calibrados': ['A1']}
    borrador = Path(caso['regresion']).read_text(encoding='utf-8')
    for apartado in ('## Síntoma', '## Causa', '## Comprobación permanente', '## Prueba'):
        assert apartado in borrador
    assert not informe['veredicto']['aceptada'] and any(m.startswith('txt-alimentador: fallo') for m in
                                                        informe['veredicto']['motivos'])


def test_100_rf7_veredicto_la_salida_da_1_si_no_se_acepta_y_2_con_una_matriz_invalida(tmp_path, capsys):
    """100:RF-7 — la orden sale con 2 si la matriz no vale; sin las variables de la matriz, ningún caso se acepta y
    sale con 1, diciendo cuáles faltan."""
    mod = _herramienta()
    mala = tmp_path / 'm.json'
    mala.write_text('{"esquema": "otro"}', encoding='utf-8')
    assert mod.main(['--matriz', str(mala), '--version', 'x', '--salida', str(tmp_path / 's')]) == 2
    vacio = tmp_path / 'vars.json'
    vacio.write_text(json.dumps({k: '' for k in _variables(random.Random(1))}), encoding='utf-8')
    assert mod.main(['--matriz', str(MATRIZ), '--version', 'x' * 40, '--salida', str(tmp_path / 's'),
                     '--variables', str(vacio)]) == 1
    assert 'NO ACEPTADA' in capsys.readouterr().out


# --- T7: una aceptación por carpeta de salida (RF-14) ---------------------------------------------------------------
def test_100_rf14_otra_aceptacion_viva_en_la_misma_salida_no_deja_correr_ningun_caso(tmp_path):
    """100:RF-14 — 25-11: dos lanzadores de la noche arrancaron dos aceptaciones a la vez sobre la misma carpeta y el
    mismo espacio; cada importación de una borró el proyecto de la otra (005:RF-22) y la calibración falló con un
    error interno. Con el candado vivo de otra, ningún caso se corre y el error nombra su proceso; con el candado de un
    proceso muerto, se toma, se corre y se suelta al terminar."""
    mod = _herramienta()
    assert hasattr(mod, 'CANDADO'), 'la aceptación no toma un candado de su carpeta de salida (100 T7)'
    matriz, salida = mod.cargar_matriz(MATRIZ), tmp_path / 's'
    salida.mkdir()
    candado = salida / mod.CANDADO
    candado.write_text(json.dumps({'pid': 4242, 'inicio': '2041-01-01T23:25:55'}), encoding='utf-8')
    web = WebFalsa()
    with pytest.raises(mod.AceptacionOcupada, match='4242'):
        mod.aceptar_version(matriz, 'a' * 40, salida, variables=_variables(random.Random(SEMILLA)), ejecutar=web,
                            regresiones=tmp_path / 'reg', vivo=lambda pid: pid == 4242)
    assert web.llamadas == [] and json.loads(candado.read_text(encoding='utf-8'))['pid'] == 4242
    informe = mod.aceptar_version(matriz, 'a' * 40, salida, variables=_variables(random.Random(SEMILLA)), ejecutar=web,
                                  regresiones=tmp_path / 'reg', vivo=lambda pid: False)
    assert web.llamadas and informe['veredicto']['aceptada'] and not candado.exists()


def test_100_rf14_la_orden_sale_con_3_si_otra_aceptacion_tiene_la_salida(tmp_path, capsys):
    """100:RF-14 — por la línea de órdenes: con la carpeta tomada por un proceso vivo (aquí, el que lanzó pytest),
    sale con 3 y dice qué proceso la tiene, sin tocar el informe."""
    import os

    mod = _herramienta()
    assert hasattr(mod, 'CANDADO'), 'la aceptación no toma un candado de su carpeta de salida (100 T7)'
    salida = tmp_path / 's'
    salida.mkdir()
    (salida / mod.CANDADO).write_text(json.dumps({'pid': os.getppid(), 'inicio': 'antes'}), encoding='utf-8')
    assert mod.main(['--matriz', str(MATRIZ), '--version', 'x' * 40, '--salida', str(salida)]) == 3
    err = capsys.readouterr().err
    assert str(os.getppid()) in err and 'otra aceptación' in err
    assert not (salida / 'informe.json').exists()