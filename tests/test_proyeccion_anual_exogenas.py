"""Spec 031 (T8): PBI y población como exógenas anuales de la proyección, con su fecha de publicación (as-of).

Las series son sintéticas: una región inventada («Región Sintética»), cifras generadas con una elasticidad conocida y
fechas de publicación elegidas para cada prueba. No son cifras del INEI ni del BCRP, ni de ninguna empresa.
"""
from __future__ import annotations

import csv
from datetime import date
import json
import math
from pathlib import Path
import sys

import numpy as np
import pytest

from convertersmartgrid.adaptadores import proyeccion_anual as pa
from convertersmartgrid.adaptadores.digital_twin.pronostico import Objetivo
from convertersmartgrid.adaptadores.pronostico_demanda import CurvaCompacta, Dataset
from convertersmartgrid.aplicacion.proyeccion_mercado import SerieMercado

sys.path.insert(0, str(Path(__file__).parent))
from pronostico_sintetico import SEMILLA  # noqa: E402

REGION = 'Región Sintética'
ELASTICIDAD_VERDADERA = 1.3
CRECE_POBLACION = .012
COLUMNAS = ('variable', 'region', 'anio', 'valor', 'unidad', 'fuente', 'publicado')
#: El PBI de ``_filas`` se publica en «millones de soles»; el registro lo guarda a escala 1 (soles), como la población en habitantes.
MILLONES = 1e6


def _crece_pbi(anio: int) -> float:
    """Un PBI que sube y baja: con él, repetir la tasa del último año se equivoca y la elasticidad no."""
    return .07 if anio % 2 == 0 else -.01


def _niveles(desde: int, hasta: int) -> tuple[dict[int, float], dict[int, float]]:
    pbi, pob = {desde: 50_000.0}, {desde: 1_000_000.0}
    for a in range(desde + 1, hasta + 1):
        pbi[a] = pbi[a - 1] * (1 + _crece_pbi(a))
        pob[a] = pob[a - 1] * (1 + CRECE_POBLACION)
    return pbi, pob


def _demanda_anual(pbi, pob, anio: int, desde: int) -> float:
    """La demanda que la elasticidad explica: por habitante, la potencia ``e`` del PBI por habitante."""
    return (pob[anio] / pob[desde]) * ((pbi[anio] / pob[anio]) / (pbi[desde] / pob[desde])) ** ELASTICIDAD_VERDADERA


def _filas(desde: int, hasta: int, publicado=lambda a: '2000-01-31', region: str = REGION) -> list[dict]:
    pbi, pob = _niveles(desde, hasta)
    filas = []
    for a in range(desde, hasta + 1):
        filas.append({'variable': 'PBI', 'region': region, 'anio': a, 'valor': pbi[a], 'unidad': 'millones de soles de 2007',
                      'fuente': 'BCRP (sintético)', 'publicado': publicado(a)})
        filas.append({'variable': 'Población', 'region': region, 'anio': a, 'valor': pob[a], 'unidad': 'habitantes',
                      'fuente': 'INEI (sintético)', 'publicado': publicado(a)})
    return filas


def _csv(ruta: Path, filas: list[dict], delimitador: str = ',') -> Path:
    with ruta.open('w', newline='', encoding='utf-8') as f:
        escritor = csv.DictWriter(f, fieldnames=list(filas[0]) if filas else list(COLUMNAS), delimiter=delimitador)
        escritor.writeheader()
        escritor.writerows(filas)
    return ruta


def _registro(tmp_path: Path, filas: list[dict], nombre: str = 'exogenas.csv'):
    return pa.leer_exogenas_anuales(_csv(tmp_path / nombre, filas))


def _dataset_que_sigue_al_pbi(desde: int = 2019, hasta: int = 2025, alimentadores: int = 1) -> Dataset:
    """Cabecera, escaladas y clientes cuyo nivel de cada año sale de la elasticidad: la forma diaria no depende de él."""
    pbi, pob = _niveles(desde, hasta)
    t = np.arange(np.datetime64(f'{desde}-01-01', 'ns'), np.datetime64(f'{hasta}-01-01', 'ns'), np.timedelta64(15, 'm'))
    anio = t.astype('datetime64[Y]').astype(int) + 1970
    nivel = np.array([_demanda_anual(pbi, pob, int(a), desde) for a in anio])
    bloque = ((t - np.datetime64('2000-01-01', 'ns')) / np.timedelta64(15, 'm')).astype(int) % 96
    forma = 1 + .3 * np.sin(2 * np.pi * bloque / 96 - 1.2)
    objetivos = []
    for i in range(alimentadores):
        for j, (clase, ident, base) in enumerate((('cabecera', f'F{i}', 3000.0), ('escaladas', f'F{i}', 2000.0), ('cliente', f'C{i}', 900.0))):
            for k, magnitud in enumerate(('kW', 'kVAR')):
                rng = np.random.default_rng(SEMILLA + 100 * i + 10 * j + k)
                v = base * nivel * forma * (1 + .01 * rng.standard_normal(len(t))) * (.3 if magnitud == 'kVAR' else 1)
                objetivos.append(Objetivo(clase, ident, magnitud, magnitud, CurvaCompacta(t, v), {'alimentador': f'F{i}'} if clase == 'cliente' else {}))
    return Dataset(objetivos, [], [], {})


ANUALES = ['tasa_de_un_anio', 'sin_crecimiento', 'tasa_media', 'tendencia_logaritmica']


@pytest.fixture(scope='module')
def sigue_al_pbi(tmp_path_factory):
    """Competición con el registro publicado de antemano (un escenario conocido desde el principio)."""
    carpeta = tmp_path_factory.mktemp('exo')
    registro = _registro(carpeta, _filas(2019, 2030))
    d = _dataset_que_sigue_al_pbi()
    c = pa.competir(d, candidatos=[*ANUALES, pa.ELASTICIDAD, pa.SOLO_POBLACION], paso_meses=3, exogenas_anuales=registro, region=REGION)
    return d, registro, c


# ------------------------------------------------------------------ RF-19: lectura con su fuente, periodo y huella
def test_exogenas_registro_con_fuente_periodo_y_huella(tmp_path):
    """031:RF-19 — cada cifra con su variable, región, año, valor, unidad, fuente y publicación; el registro, por su huella."""
    filas = _filas(2015, 2020)
    r = _registro(tmp_path, filas)
    assert len(r.cifras) == len(filas)
    resumen = r.resumen()
    assert resumen['sha256'] == r.huella and len(r.huella) == 64
    assert resumen['periodo'] == [2015, 2020] and resumen['variables'] == ['pbi', 'poblacion']
    assert resumen['fuentes'] == ['BCRP (sintético)', 'INEI (sintético)'] and resumen['regiones'] == [REGION]
    cifra = next(c for c in r.cifras if c.variable == 'pbi' and c.anio == 2016)
    assert cifra.publicado == date(2000, 1, 31) and cifra.fuente == 'BCRP (sintético)' and cifra.tipo == 'nivel'


def test_exogenas_la_huella_es_del_contenido_no_del_nombre(tmp_path):
    """031:RF-19 — el mismo contenido con otro nombre es el mismo registro; otra cifra, otro registro (ficheros reemplazables)."""
    filas = _filas(2015, 2020)
    a = _registro(tmp_path, filas, 'a.csv')
    b = _registro(tmp_path, filas, 'otro_nombre.csv')
    filas[3] = {**filas[3], 'valor': filas[3]['valor'] * 1.01}
    c = _registro(tmp_path, filas, 'a_v2.csv')
    assert a.huella == b.huella and a.huella != c.huella


def test_exogenas_lee_csv_con_punto_y_coma_y_todas_las_hojas_de_un_libro(tmp_path):
    """031:RF-19 — CSV con «;» y libros con varias hojas: la hoja se reconoce por su cabecera y la que no lo es se avisa."""
    from openpyxl import Workbook

    filas = _filas(2015, 2018)
    r_csv = pa.leer_exogenas_anuales(_csv(tmp_path / 'x.csv', filas, ';'))
    libro = Workbook()
    notas = libro.active
    notas.title = 'Notas'
    notas.append(['Series anuales cargadas por el operador'])
    hoja = libro.create_sheet('Series')
    hoja.append(['Registro de exógenas'])
    hoja.append([])
    hoja.append(['Año', 'Región', 'Variable', 'Valor', 'Unidad', 'Fuente', 'Fecha de publicación'])
    for f in filas:
        hoja.append([f['anio'], f['region'], f['variable'], f['valor'], f['unidad'], f['fuente'], date.fromisoformat(f['publicado'])])
    libro.save(tmp_path / 'x.xlsx')
    r_xlsx = pa.leer_exogenas_anuales(tmp_path / 'x.xlsx')
    def clave(r):
        return sorted((c.variable, c.anio, round(c.valor, 6), c.publicado) for c in r.cifras)

    assert clave(r_csv) == clave(r_xlsx)
    assert any('Notas' in a for a in r_xlsx.avisos), 'la hoja sin cabecera se dice'


def test_exogenas_json_y_escalas_de_unidad(tmp_path):
    """031:RF-19, 031:RF-22 — «miles de habitantes» y «habitantes» son la misma unidad a otra escala; el JSON también vale."""
    filas = [{'variable': 'poblacion', 'region': REGION, 'anio': 2020, 'valor': 1000, 'unidad': 'miles de habitantes', 'fuente': 'INEI', 'publicado': '2021-01-15'},
             {'variable': 'poblacion', 'region': REGION, 'anio': 2021, 'valor': 1_012_000, 'unidad': 'habitantes', 'fuente': 'INEI', 'publicado': '2022-01-15'}]
    ruta = tmp_path / 'r.json'
    ruta.write_text(json.dumps({'cifras': filas}), encoding='utf-8')
    r = pa.leer_exogenas_anuales(ruta)
    niveles = pa.exogenas_al_corte(r, REGION, date(2023, 1, 1))['niveles']['poblacion']
    assert niveles == {2020: pytest.approx(1_000_000.0), 2021: pytest.approx(1_012_000.0)}


# ------------------------------------------------------------------ RF-22: errores y casos límite, con su mensaje
@pytest.mark.parametrize('cambio,mensaje', [
    ({'unidad': 'millones de soles corrientes'}, 'nominal'),
    ({'unidad': 'millones de soles'}, 'año base'),
    ({'unidad': 'toneladas'}, 'unidad'),
    ({'variable': 'exportaciones'}, 'variable'),
    ({'anio': '2016-T1'}, 'anual'),
    ({'anio': '2016-03'}, 'anual'),
    ({'publicado': ''}, 'publicación'),
    ({'publicado': 'ayer'}, 'publicación'),
    ({'fuente': ''}, 'fuente'),
    ({'valor': 'n.d.'}, 'valor'),
    ({'valor': -5}, 'positivo'),
])
def test_exogenas_cifra_invalida_se_rechaza_con_su_motivo(tmp_path, cambio, mensaje):
    """031:RF-22 — nominal, sin año base, unidad o variable desconocida, periodo no anual, sin fecha o sin fuente: se dice y no se lee."""
    filas = _filas(2015, 2017)
    filas[2] = {**filas[2], **cambio}
    with pytest.raises(pa.ProyeccionError, match=mensaje):
        _registro(tmp_path, filas)


def test_exogenas_vacio_columna_que_falta_y_fichero_que_falta(tmp_path):
    """031:RF-22 — un registro vacío, sin una columna o que no existe no da una serie vacía en silencio."""
    with pytest.raises(pa.ProyeccionError, match='no trae cifras'):
        _registro(tmp_path, [])
    sin_fuente = [{k: v for k, v in f.items() if k != 'fuente'} for f in _filas(2015, 2016)]
    with pytest.raises(pa.ProyeccionError, match='fuente'):
        _registro(tmp_path, sin_fuente, 'sin_fuente.csv')
    with pytest.raises(pa.ProyeccionError, match='no se encuentra'):
        pa.leer_exogenas_anuales(tmp_path / 'no_existe.csv')
    (tmp_path / 'r.txt').write_text('x', encoding='utf-8')
    with pytest.raises(pa.ProyeccionError, match='extensión'):
        pa.leer_exogenas_anuales(tmp_path / 'r.txt')


def test_exogenas_bases_mezcladas_y_cifras_contradictorias(tmp_path):
    """031:RF-22 — dos años base de precios no se empalman a ciegas, y dos cifras distintas del mismo día no se eligen al azar."""
    filas = _filas(2015, 2017)
    filas[2] = {**filas[2], 'unidad': 'millones de soles de 1994'}
    with pytest.raises(pa.ProyeccionError, match='1994'):
        _registro(tmp_path, filas)
    filas = _filas(2015, 2017)
    filas.append({**filas[0], 'valor': filas[0]['valor'] * 1.05})
    with pytest.raises(pa.ProyeccionError, match='mismo día'):
        _registro(tmp_path, filas, 'dup.csv')


def test_exogenas_region_desconocida_dice_cuales_hay(tmp_path):
    """031:RF-22 — una región que no está en el registro no se sustituye por otra: se nombra y se listan las que hay."""
    r = _registro(tmp_path, _filas(2015, 2017))
    with pytest.raises(pa.ProyeccionError, match=REGION):
        pa.exogenas_al_corte(r, 'Otra Región', date(2020, 1, 1))
    d = _dataset_que_sigue_al_pbi(2019, 2022)
    with pytest.raises(pa.ProyeccionError, match='Otra Región'):
        pa.competir(d, candidatos=['sin_crecimiento', pa.ELASTICIDAD], exogenas_anuales=r, region='Otra Región')
    with pytest.raises(pa.ProyeccionError, match='región'):
        pa.competir(d, candidatos=['sin_crecimiento', pa.ELASTICIDAD], exogenas_anuales=r)
    with pytest.raises(pa.ProyeccionError, match='registro'):
        pa.competir(d, candidatos=['sin_crecimiento', pa.ELASTICIDAD])


def test_exogenas_anio_que_falta_no_se_inventa(tmp_path):
    """031:RF-22 — sin la cifra de un año, el método no interpola: dice el año y la variable que faltan."""
    filas = [f for f in _filas(2015, 2022) if not (f['variable'] == 'PBI' and f['anio'] == 2020)]
    r = _registro(tmp_path, filas)
    niveles = pa.exogenas_al_corte(r, REGION, date(2030, 1, 1))['niveles']
    assert 2020 not in niveles['pbi'] and 2020 in niveles['poblacion']
    metodo = pa.metodo_exogeno(pa.ELASTICIDAD, niveles)
    hist = {a: 100.0 * 1.03 ** (a - 2015) for a in range(2015, 2019)}
    with pytest.raises(pa.MercadoError, match='2020'):
        metodo(hist, 2018, [2019, 2020, 2021])
    assert set(pa.metodo_exogeno(pa.SOLO_POBLACION, niveles)(hist, 2018, [2019, 2020, 2021])) == {2019, 2020, 2021}, 'la ablación solo pide población'


def test_exogenas_variaciones_se_encadenan_y_sin_ancla_no(tmp_path):
    """031:RF-22 — una proyección publicada como variación real se encadena al nivel anterior; sin nivel anterior, falta y se dice."""
    filas = _filas(2015, 2018)
    filas += [{'variable': 'PBI', 'region': REGION, 'anio': 2019, 'valor': 3.0, 'unidad': 'variación % real', 'fuente': 'BCRP', 'publicado': '2018-12-20'},
              {'variable': 'PBI', 'region': REGION, 'anio': 2021, 'valor': 2.0, 'unidad': 'variación % real', 'fuente': 'BCRP', 'publicado': '2018-12-20'}]
    al = pa.exogenas_al_corte(_registro(tmp_path, filas), REGION, date(2019, 1, 1))
    pbi, _pob = _niveles(2015, 2018)
    assert al['niveles']['pbi'][2019] == pytest.approx(pbi[2018] * MILLONES * 1.03)
    assert 2021 not in al['niveles']['pbi'] and any(x['anio'] == 2021 for x in al['sin_ancla'])


# ------------------------------------------------------------------ RF-20: solo lo publicado hasta el corte
def test_exogenas_cifra_publicada_despues_del_origen_se_rechaza(tmp_path):
    """031:RF-20 — de cada año, la última cifra publicada hasta el corte; la publicada después se rechaza y se anota."""
    filas = _filas(2015, 2023)
    estimada = next(f for f in filas if f['variable'] == 'PBI' and f['anio'] == 2023)
    filas.append({**estimada, 'valor': estimada['valor'] * 1.10, 'publicado': '2024-05-15'})
    r = _registro(tmp_path, filas)
    antes = pa.exogenas_al_corte(r, REGION, date(2023, 12, 31))
    assert antes['niveles']['pbi'][2023] == pytest.approx(estimada['valor'] * MILLONES)
    assert [(x['variable'], x['anio'], x['publicado']) for x in antes['rechazadas']] == [('pbi', 2023, '2024-05-15')]
    despues = pa.exogenas_al_corte(r, REGION, date(2024, 5, 15))
    assert despues['niveles']['pbi'][2023] == pytest.approx(estimada['valor'] * MILLONES * 1.10) and not despues['rechazadas']


def test_exogenas_en_la_competicion_nada_publicado_despues_de_cada_origen(tmp_path):
    """031:RF-20 — si el PBI de cada año solo se publica al año siguiente, ningún origen lo ve antes: la elasticidad no compite."""
    r = _registro(tmp_path, _filas(2019, 2030, publicado=lambda a: f'{a + 1}-05-15'))
    d = _dataset_que_sigue_al_pbi(2019, 2023)
    c = pa.competir(d, candidatos=['tasa_de_un_anio', 'sin_crecimiento', pa.ELASTICIDAD], paso_meses=3, exogenas_anuales=r, region=REGION)
    grupo = c['grupos']['escaladas|kW']
    assert grupo['candidatos'][pa.ELASTICIDAD]['status'] == 'NO_APLICA' and grupo['ganador'] != pa.ELASTICIDAD
    exo = c['exogenas_anuales']
    assert exo['usado'] and all(n > 0 for n in exo['rechazadas_por_origen'].values()), 'cada origen rechaza lo que aún no se había publicado'


# ------------------------------------------------------------------ RF-21: compiten con la regla de RF-4, con su ablación
def test_exogenas_la_elasticidad_gana_cuando_la_demanda_sigue_al_pbi(sigue_al_pbi):
    """031:RF-21, 031:RF-4 — con la demanda que sigue al PBI, la elasticidad gana por las métricas; la ablación se mide igual."""
    _d, _r, c = sigue_al_pbi
    for g in ('escaladas|kW', 'cliente|kW'):
        grupo = c['grupos'][g]
        assert grupo['ganador'] == pa.ELASTICIDAD, grupo['motivo']
        sola, con = grupo['candidatos'][pa.SOLO_POBLACION], grupo['candidatos'][pa.ELASTICIDAD]
        assert 'eleccion' in sola and con['eleccion']['wape'] < sola['eleccion']['wape'], 'la ablación sin PBI pierde'
        assert con['eleccion']['n'] == grupo['candidatos']['tasa_de_un_anio']['eleccion']['n'], 'los mismos datos y orígenes'
        assert grupo['elasticidad_pbi_emision']['elasticidad'] == pytest.approx(ELASTICIDAD_VERDADERA, abs=.15)


def test_exogenas_sin_ellas_no_hay_candidatos_exogenos_y_nada_cambia(tmp_path):
    """031:RF-21 — sin registro no se añaden; con él, los perfiles de 15 minutos dan lo mismo: el PBI anual no entra en la malla."""
    d = _dataset_que_sigue_al_pbi(2021, 2024)
    r = _registro(tmp_path, _filas(2019, 2030))
    sin = pa.competir(d, candidatos=['perfil_anclado', 'sin_crecimiento'], paso_meses=6)
    con = pa.competir(d, candidatos=['perfil_anclado', 'sin_crecimiento'], paso_meses=6, exogenas_anuales=r, region=REGION)
    for g in sin['grupos']:
        assert sin['grupos'][g]['candidatos']['perfil_anclado'] == con['grupos'][g]['candidatos']['perfil_anclado']
    assert not sin['exogenas_anuales']['usado'] and pa.ELASTICIDAD not in sin['candidatos']
    assert 'anual' in con['exogenas_anuales']['resolucion'] and '15 minutos' in con['exogenas_anuales']['resolucion']


def test_exogenas_formato_01_la_elasticidad_compite_y_valida_anios(tmp_path):
    """031:RF-21, 031:RF-8 — en el Formato 01 propio, la elasticidad se mide cortando la historia con lo publicado hasta cada corte."""
    pbi, pob = _niveles(2008, 2030)
    hist = {a: 100.0 * _demanda_anual(pbi, pob, a, 2008) for a in range(2008, 2024)}
    serie = SerieMercado('S1', 'Uno', 'ST2', hist, empresa='E')
    r = _registro(tmp_path, _filas(2008, 2030))
    d = _dataset_que_sigue_al_pbi(2021, 2024)
    c = pa.competir(d, candidatos=['tasa_de_un_anio', 'sin_crecimiento'], paso_meses=6, formato_01=[serie], exogenas_anuales=r, region=REGION)
    f = c['formato_01']
    assert f['usado'] and f['ganador'] == pa.ELASTICIDAD and f['anios_validados'] >= 5
    assert f['por_anio'][pa.ELASTICIDAD]['1']['wape'] < f['por_anio']['tasa_de_un_anio']['1']['wape']
    assert f['exogenas'][pa.SOLO_POBLACION]['mediana_error_pct'] > f['exogenas'][pa.ELASTICIDAD]['mediana_error_pct']


# ------------------------------------------------------------------ emisión: as-of, años que faltan y huella
def test_exogenas_emision_sigue_al_pbi_proyectado_y_lo_anota(sigue_al_pbi):
    """031:RF-21, 031:RF-23 — los años emitidos con el ganador siguen al PBI y la población proyectados; la evaluación lo dice."""
    d, r, c = sigue_al_pbi
    pro, ev = pa.proyectar(d, c, proyecto='P', anio_base=2024, anio_corto=1, anio_fin=4, exogenas_anuales=r, tasa_cola=.02)
    e = c['grupos']['escaladas|kW']['elasticidad_pbi_emision']['elasticidad']
    pbi, pob = _niveles(2019, 2030)
    por = {(f['carga'], f['anio']): f for f in (*pro['filas'], *pro['filas_corto_plazo'])}
    uno, dos = por[('escaladas:F0', 1)], por[('escaladas:F0', 2)]
    assert uno['modelo_p'] == pa.ELASTICIDAD
    if dos['origen_anio'] == 'modelo':
        esperado = (pob[2026] / pob[2025]) * ((pbi[2026] / pob[2026]) / (pbi[2025] / pob[2025])) ** e
        assert dos['p_kw'] / uno['p_kw'] == pytest.approx(esperado, rel=1e-3)
    exo = ev['exogenas_anuales']
    assert exo['sha256'] == r.huella and exo['region'] == REGION and exo['corte_emision'] == '2024-12-31'
    assert exo['fuentes'] and exo['periodo'] == [2019, 2030] and 'rechazadas_emision' in exo


def test_exogenas_emision_con_otro_registro_o_sin_el_se_niega(sigue_al_pbi, tmp_path):
    """031:RF-23 — el ganador exógeno solo se emite con el registro con que compitió: otra huella no se mezcla."""
    d, _r, c = sigue_al_pbi
    otro = _registro(tmp_path, _filas(2019, 2031))
    with pytest.raises(pa.ProyeccionError, match='huella'):
        pa.proyectar(d, c, proyecto='P', anio_base=2024, anio_corto=1, anio_fin=3, exogenas_anuales=otro)
    with pytest.raises(pa.ProyeccionError, match='registro'):
        pa.proyectar(d, c, proyecto='P', anio_base=2024, anio_corto=1, anio_fin=3)


def test_exogenas_emision_hasta_donde_hay_cifras_y_despues_la_tasa(tmp_path):
    """031:RF-22, 031:RF-16 — si lo publicado llega a un año, después sigue la tasa de largo plazo y no se dice validado."""
    d = _dataset_que_sigue_al_pbi()
    r = _registro(tmp_path, _filas(2019, 2025))
    c = pa.competir(d, candidatos=[*ANUALES, pa.ELASTICIDAD], paso_meses=3, exogenas_anuales=r, region=REGION)
    assert c['grupos']['escaladas|kW']['ganador'] == pa.ELASTICIDAD
    pro, ev = pa.proyectar(d, c, proyecto='P', anio_base=2024, anio_corto=1, anio_fin=4, exogenas_anuales=r, tasa_cola=.02)
    por = {(f['carga'], f['anio']): f for f in (*pro['filas'], *pro['filas_corto_plazo'])}
    assert por[('escaladas:F0', 2)]['origen_anio'] == 'tasa_de_largo_plazo' and not por[('escaladas:F0', 2)]['validado']
    assert por[('escaladas:F0', 3)]['p_kw'] / por[('escaladas:F0', 2)]['p_kw'] == pytest.approx(1.02, rel=1e-3)
    assert '2025' in por[('escaladas:F0', 1)]['nota']
    assert ev['horizonte_validado_anios'] <= 1


def test_exogenas_emision_sin_el_primer_anio_publicado_se_dice(tmp_path):
    """031:RF-20, 031:RF-22 — el año siguiente al último dato publicado después del corte de emisión no se usa: se dice cuál falta."""
    d = _dataset_que_sigue_al_pbi()
    filas = _filas(2019, 2030, publicado=lambda a: '2000-01-31' if a <= 2024 else '2025-03-01')
    r = _registro(tmp_path, filas)
    c = pa.competir(d, candidatos=['tasa_de_un_anio', 'sin_crecimiento', pa.ELASTICIDAD], paso_meses=3, exogenas_anuales=r, region=REGION)
    c['grupos']['escaladas|kW']['ganador'] = pa.ELASTICIDAD           # el caso: ganó, pero lo del año que sigue se publicó después
    with pytest.raises(pa.ProyeccionError, match='2025'):
        pa.proyectar(d, c, proyecto='P', anio_base=2024, anio_corto=1, anio_fin=3, exogenas_anuales=r)


def test_exogenas_lo_pronosticado_se_rehace_si_cambia_el_registro(sigue_al_pbi, tmp_path, monkeypatch):
    """031:RF-19, 031:RF-14 — el mismo registro reutiliza lo emitido; otro registro (otra huella) obliga a pronosticar de nuevo."""
    d, _r, _c = sigue_al_pbi
    ds = Dataset(d.objetivos, [], [], {}, huella='c' * 64)
    real = pa.competir
    vistos = []

    def competir(dataset, **kw):
        vistos.append((kw.get('exogenas_anuales'), kw.get('region')))
        return real(dataset, candidatos=[*ANUALES, pa.ELASTICIDAD], **kw)

    monkeypatch.setattr(pa, 'competir', competir)
    uno_ruta = _csv(tmp_path / 'uno.csv', _filas(2019, 2030))
    dos_ruta = _csv(tmp_path / 'dos.csv', _filas(2019, 2031))
    pedir = {'carpeta': tmp_path / 'p', 'proyecto': 'P', 'anio_base': 2024, 'anio_corto': 1, 'anio_fin': 3, 'dataset': ds, 'paso_meses': 3, 'region': REGION}
    uno = pa.pronosticar_estudio(None, exogenas_anuales=uno_ruta, **pedir)
    assert not uno['reutilizada'] and vistos[-1][0].huella == pa.leer_exogenas_anuales(uno_ruta).huella and vistos[-1][1] == REGION
    assert uno['evaluacion']['exogenas_anuales']['sha256'] == vistos[-1][0].huella
    assert pa.pronosticar_estudio(None, exogenas_anuales=uno_ruta, **pedir)['reutilizada']
    assert not pa.pronosticar_estudio(None, exogenas_anuales=dos_ruta, **pedir)['reutilizada']


def test_exogenas_determinista(tmp_path):
    """031:RF-14 — mismos datos, mismo registro y misma semilla: el mismo resultado."""
    d = _dataset_que_sigue_al_pbi(2019, 2023)
    r = _registro(tmp_path, _filas(2019, 2030))
    uno = pa.competir(d, candidatos=['sin_crecimiento', pa.ELASTICIDAD, pa.SOLO_POBLACION], paso_meses=6, exogenas_anuales=r, region=REGION)
    dos = pa.competir(d, candidatos=['sin_crecimiento', pa.ELASTICIDAD, pa.SOLO_POBLACION], paso_meses=6, exogenas_anuales=r, region=REGION)
    assert json.dumps(uno, sort_keys=True, default=str) == json.dumps(dos, sort_keys=True, default=str)
    assert all(math.isfinite(x) for x in (uno['grupos']['escaladas|kW']['candidatos'][pa.SOLO_POBLACION]['eleccion']['wape'],))
