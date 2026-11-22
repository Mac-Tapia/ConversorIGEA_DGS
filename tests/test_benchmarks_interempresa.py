"""Spec 112: dejar una empresa fuera cada vez en la conversión VNR y en el pronóstico (112:RF-15 a RF-19).

La cohorte por empresa (RF-6) repartía los registros, pero nada medía con ella si lo aprendido de unas empresas vale para
otra. Aquí, con empresas sintéticas («Empresa A», «Empresa B», «Empresa C» y una cuarta que no se parece), se comprueba
que el ajuste nunca ve la retenida, que con menos de tres empresas el veredicto es «NO DEMOSTRADA» y lo dice, que el
catálogo de fichas mide lo que la conversión haría con un conductor sin ficha y que el pronóstico compara la forma de las
demás con la base propia de la retenida. Las semillas son fijas y van en cada mensaje. Sin red, sin DIgSILENT y sin GPU.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import random
import re
from pathlib import Path

import numpy as np
import pytest

from apoyo import cargar_herramienta

RAIZ = Path(__file__).resolve().parents[1]
SEMILLA = 20261120
EMPRESAS = ('Empresa A', 'Empresa B', 'Empresa C')
#: Margen de la prueba del pronóstico con datos sorteados (ver la prueba de RF-18).
MARGEN = 0.25


def _dominio():
    nombre = 'convertersmartgrid.dominio.benchmarks.interempresa'
    assert importlib.util.find_spec(nombre), f'falta {nombre}'
    from convertersmartgrid.dominio.benchmarks import interempresa
    return interempresa


def _adaptador():
    nombre = 'convertersmartgrid.adaptadores.benchmarks.interempresa'
    assert importlib.util.find_spec(nombre), f'falta {nombre}'
    from convertersmartgrid.adaptadores.benchmarks import interempresa
    return interempresa


# ------------------------------------------------------------------ el bucle


def test_112_rf15_el_ajuste_no_ve_la_retenida_y_hay_un_pliegue_por_empresa():
    """112:RF-15 — ``ajustar`` recibe solo las demás y ``medir`` solo la retenida, una vez por empresa."""
    d = _dominio()
    datos = {f'E{i}': {'empresa': f'E{i}'} for i in range(1, 5)}
    vistos = []

    def ajustar(entrenamiento):
        vistos.append(sorted(entrenamiento))
        return set(entrenamiento)

    def medir(modelo, retenida):
        assert retenida['empresa'] not in modelo, 'el modelo se ajustó con la retenida'
        return {'n': 1}

    r = d.dejar_una_fuera(datos, ajustar, medir, lambda m: (True, 'pasa'))
    assert [p.retenida for p in r.pliegues] == ['E1', 'E2', 'E3', 'E4']
    assert vistos == [[e for e in sorted(datos) if e != p.retenida] for p in r.pliegues]
    assert all(p.retenida not in p.entrenamiento for p in r.pliegues)
    assert r.veredicto == d.DEMOSTRADA


@pytest.mark.parametrize('n', [0, 1, 2])
def test_112_rf16_con_menos_de_tres_empresas_no_esta_demostrada_y_lo_dice(n):
    """112:RF-16 — con 0, 1 o 2 empresas, «NO DEMOSTRADA», cuántas hay y cuántas hacen falta, aunque todo pase."""
    d = _dominio()
    datos = {f'E{i}': i for i in range(1, n + 1)}
    r = d.dejar_una_fuera(datos, lambda e: e, lambda m, x: {'x': x}, lambda m: (True, ''))
    assert r.veredicto == d.NO_DEMOSTRADA
    assert f'{n} empresa' in r.motivo and str(d.MINIMO_EMPRESAS) in r.motivo, r.motivo
    assert len(r.pliegues) == (n if n >= 2 else 0)
    assert r.como_dict()['minimo_empresas'] == 3


def test_112_rf16_con_tres_o_mas_basta_una_retenida_que_no_pasa_para_no_demostrarla():
    """112:RF-16 — con cuatro empresas y una que no pasa, «NO DEMOSTRADA» con esa empresa y su motivo."""
    d = _dominio()
    datos = {'E1': 1, 'E2': 1, 'E3': 1, 'E4': 0}
    r = d.dejar_una_fuera(datos, lambda e: None, lambda m, x: {'x': x},
                          lambda m: (bool(m['x']), '' if m['x'] else 'no se parece'))
    assert r.veredicto == d.NO_DEMOSTRADA
    assert 'E4: no se parece' in r.motivo and 'E1' not in r.motivo, r.motivo


# ------------------------------------------------------------------ conversión VNR: catálogo de fichas


def _red(semilla: int, fichas: dict, *, codigos_tramo=None, n: int = 40):
    d = _dominio()
    rnd = random.Random(semilla)
    codigos = codigos_tramo or list(fichas)
    tramos = [(rnd.choice(codigos), round(rnd.uniform(0.01, 0.6), 3)) for _ in range(n)]
    return d.RedEmpresa(tramos, {c: d.Ficha(*v) for c, v in fichas.items()})


FICHAS_COMUNES = {'AL050A': (0.64, 0.42, 190.0), 'AL070A': (0.46, 0.41, 235.0), 'CU035S': (0.52, 0.12, 170.0)}


def test_112_rf17_el_catalogo_de_las_demas_resuelve_por_parecido_como_el_modelo():
    """112:RF-17 — un código que no está en el catálogo se resuelve por el más parecido; su acierto, por longitud."""
    d = _dominio()
    catalogo = d.ajustar_catalogo({'E1': _red(SEMILLA, FICHAS_COMUNES)})
    # La retenida llama «AL050B» a un AL050 con la misma impedancia: el modelo tomaría AL050A, y acierta.
    propia = {'AL050B': (0.64, 0.42, 190.0), 'XZ999Q': (1.2, 0.5, 80.0)}
    red = d.RedEmpresa([('AL050B', 2.0), ('XZ999Q', 1.0), ('SINFICHA', 5.0)], {c: d.Ficha(*v) for c, v in propia.items()})
    m = d.medir_catalogo(catalogo, red)
    assert m['tramos'] == 2 and m['tramos_sin_ficha_propia'] == 1, m
    assert m['cobertura'] == pytest.approx(2 / 3) and m['acierto'] == pytest.approx(2 / 3), m
    pasa, motivo = d.criterio_catalogo()(m)
    assert not pasa and '90%' in motivo, motivo


def test_112_rf17_una_ficha_fuera_de_tolerancia_cubre_pero_no_acierta():
    """112:RF-17 — el mismo código con otra R1 (un 30 % más) está en el catálogo, pero no acierta."""
    d = _dominio()
    catalogo = d.ajustar_catalogo({'E1': _red(SEMILLA, FICHAS_COMUNES)})
    red = d.RedEmpresa([('AL070A', 1.0)], {'AL070A': d.Ficha(0.46 * 1.3, 0.41, 235.0)})
    m = d.medir_catalogo(catalogo, red)
    assert m['cobertura'] == 1.0 and m['acierto'] == 0.0, m
    assert d.medir_catalogo(catalogo, red, tolerancia=0.5)['acierto'] == 1.0


def _escribir_trio(carpeta: Path, semilla: int, fichas: dict, codigos_tramo=None) -> None:
    rnd = random.Random(semilla)
    codigos = codigos_tramo or list(fichas)
    carpeta.mkdir(parents=True)
    filas = [f'S{k},{rnd.choice(codigos)},{rnd.uniform(10, 600):.1f},1' for k in range(30)]
    (carpeta / 'RED.txt').write_text('[LINE CONFIGURATION]\nFORMAT_LINECONFIGURATION=SectionID,LineCableID,Length,Overhead\n'
                                     + '\n'.join(filas) + '\n', encoding='utf-8')
    (carpeta / 'BD_Equipo.txt').write_text('[LINE]\nFORMAT_LINE=ID,R1,X1,Amps\n'
                                           + '\n'.join(f'{c},{r},{x},{a}' for c, (r, x, a) in fichas.items()) + '\n',
                                           encoding='utf-8')


def test_112_rf17_rf19_tres_empresas_con_los_mismos_conductores_lo_demuestran_y_una_distinta_no(tmp_path):
    """112:RF-17, 112:RF-19 — con el trío en disco: A, B y C demuestran; con una cuarta de otros conductores, no."""
    a = _adaptador()
    raiz = tmp_path / 'empresas'
    for i, nombre in enumerate(EMPRESAS):
        _escribir_trio(raiz / nombre, SEMILLA + i, FICHAS_COMUNES)
    informe = a.evaluar_vnr(raiz)
    assert informe['veredicto'] == 'DEMOSTRADA', (SEMILLA, informe['motivo'])
    assert informe['empresas'] == 3 and informe['tarea'] == 'conversion_vnr'
    assert all(p['metricas']['acierto'] == 1.0 for p in informe['pliegues'])

    _escribir_trio(raiz / 'Empresa D', SEMILLA + 9, {'QQ10': (2.0, 0.3, 60.0), 'QQ20': (1.5, 0.3, 75.0)})
    informe = a.evaluar_vnr(raiz)
    assert informe['veredicto'] == 'NO DEMOSTRADA', (SEMILLA, informe['motivo'])
    caidas = [p['retenida'] for p in informe['pliegues'] if not p['pasa']]
    assert len(caidas) == 1 and caidas[0] in informe['motivo']
    assert informe['criterio'] == {'metrica': 'acierto', 'umbral': 0.9, 'tolerancia_ficha': 0.1}
    texto = json.dumps(informe, ensure_ascii=False)
    assert not re.search(r'Empresa [A-D]', texto), 'el informe nombra una carpeta de empresa'
    assert sorted(p['retenida'] for p in informe['pliegues']) == ['E1', 'E2', 'E3', 'E4']


def test_112_rf19_los_seudonimos_no_dependen_del_orden_de_las_carpetas(tmp_path):
    """112:RF-19 — ``E1…En`` sale de la huella del nombre: la misma carpeta, el mismo seudónimo."""
    a = _adaptador()
    for nombre in EMPRESAS:
        (tmp_path / nombre).mkdir()
    (tmp_path / '_auxiliar').mkdir()
    primera = a.empresas_de(tmp_path)
    assert sorted(primera) == ['E1', 'E2', 'E3']
    assert {p.name for p in primera.values()} == set(EMPRESAS)
    assert a.empresas_de(tmp_path) == primera
    with pytest.raises(a.SinEmpresas):
        a.empresas_de(tmp_path / 'Empresa A')


# ------------------------------------------------------------------ pronóstico: forma semanal


def _escribir_series(carpeta: Path, semilla: int, *, invertida: bool = False, semanas: int = 8, series: int = 2) -> None:
    rnd = np.random.default_rng(semilla)
    t = np.arange(np.datetime64('2031-03-03T00:15'), np.datetime64('2031-03-03T00:15') + np.timedelta64(semanas * 7, 'D'),
                  np.timedelta64(15, 'm'))
    hora = (t.astype('datetime64[m]').astype(np.int64) % 1440) / 60
    dia = ((t.astype('datetime64[D]').astype(np.int64) + 3) % 7)
    forma = 1 + 0.5 * np.sin((hora - 6) / 24 * 2 * np.pi) * (-1 if invertida else 1) - 0.25 * (dia >= 5)
    carpeta.mkdir(parents=True)
    with (carpeta / 'series_objetivos.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(('objetivo', 'clase', 'ident', 'magnitud', 'unidad', 'banda', 'inicio_base'))
        for k in range(series):
            w.writerow((f'S{k}', 'cabecera', f'S{k}', 'kW', 'kW', '1-5 MW', ''))
        w.writerow(('Q0', 'cabecera', 'Q0', 'kVAR', 'kVAR', '1-5 MW', ''))
    with (carpeta / 'series.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(('objetivo', 't', 'v', 'no_laborable', 'temperatura_c', 'mes'))
        for k in range(series):
            nivel = rnd.uniform(500, 3000)
            y = nivel * forma * (1 + rnd.normal(0, 0.05, len(t)))
            for ti, yi in zip(t, y):
                w.writerow((f'S{k}', str(ti), f'{yi:.3f}', '0', '', ''))
        for ti in t[:200]:
            w.writerow(('Q0', str(ti), f'{rnd.normal(0, 50):.3f}', '0', '', ''))


def test_112_rf18_la_forma_de_las_demas_frente_a_la_base_propia(tmp_path):
    """112:RF-18 — A, B y C con la misma forma semanal: demostrada; una con el día y la noche al revés no pasa."""
    a = _adaptador()
    raiz = tmp_path / 'empresas'
    for i, nombre in enumerate(EMPRESAS):
        _escribir_series(raiz / nombre, SEMILLA + i)
    # Con la misma forma, la de las demás queda a un 5–10 % del WAPE de la base propia (la base ve el ruido de su serie;
    # la forma, además, el nivel): con el margen por defecto (10 %) un pliegue caería por el sorteo del ruido, no por la
    # forma (en la primera corrida, 0,0494 frente a 0,0448). Por eso la prueba fija un margen del 25 %, lejos de los dos
    # lados: la forma invertida da un WAPE unas quince veces el de la base.
    informe = a.evaluar_pronostico(raiz, margen=MARGEN)
    assert informe['veredicto'] == 'DEMOSTRADA', (SEMILLA, informe['motivo'])
    for p in informe['pliegues']:
        m = p['metricas']
        assert m['series'] == 2, (SEMILLA, m)      # la de kVAR no entra
        assert m['wape_forma_de_las_demas'] <= m['wape_base_propia'] * (1 + MARGEN), (SEMILLA, m)
    assert informe['criterio']['base'] == 'semanal' and informe['criterio']['margen_sobre_la_base'] == MARGEN

    _escribir_series(raiz / 'Empresa D', SEMILLA + 9, invertida=True)
    informe = a.evaluar_pronostico(raiz, margen=MARGEN)
    assert informe['veredicto'] == 'NO DEMOSTRADA', (SEMILLA, informe['motivo'])
    caidas = [p for p in informe['pliegues'] if not p['pasa']]
    assert len(caidas) == 1 and 'peor que su base propia' in caidas[0]['motivo'], (SEMILLA, caidas)


def test_112_rf18_el_margen_por_defecto_es_un_10_por_ciento_sobre_la_base():
    """112:RF-18 — por defecto, un WAPE un 20 % peor que la base no pasa y uno un 5 % peor sí; el margen se cambia."""
    a = _adaptador()
    assert a.MARGEN_PRONOSTICO == 0.10
    peor = {'wape_forma_de_las_demas': 0.12, 'wape_base_propia': 0.10}
    assert a.criterio_forma()(peor)[0] is False
    assert a.criterio_forma()({**peor, 'wape_forma_de_las_demas': 0.105})[0] is True
    assert a.criterio_forma(0.25)(peor)[0] is True


def test_112_rf18_sin_una_semana_de_historia_el_pliegue_no_pasa(tmp_path):
    """112:RF-18 — una retenida sin historia que medir no pasa por defecto: lo dice."""
    a = _adaptador()
    forma = np.ones(a.CELDAS)
    t = np.arange(np.datetime64('2031-03-03T00:15'), np.datetime64('2031-03-10T00:15'), np.timedelta64(15, 'm'))
    m = a.medir_forma(forma, [(t, np.ones(len(t)))])
    assert m['series'] == 0 and m['wape_base_propia'] is None
    pasa, motivo = a.criterio_forma()(m)
    assert not pasa and 'sin series' in motivo


# ------------------------------------------------------------------ informe y herramienta


def test_112_rf19_el_informe_se_escribe_de_forma_atomica(tmp_path, monkeypatch):
    """112:RF-19 — el informe pasa por ``write_json_atomic`` (001:RF-5) y lleva su esquema."""
    a = _adaptador()
    llamadas = []
    original = a.write_json_atomic
    monkeypatch.setattr(a, 'write_json_atomic', lambda ruta, dato: (llamadas.append(ruta), original(ruta, dato)))
    ruta = a.escribir_informe({'esquema': a.ESQUEMA, 'veredicto': 'NO DEMOSTRADA'}, tmp_path / 'sub' / 'informe.json')
    assert llamadas == [ruta]
    assert json.loads(ruta.read_text(encoding='utf-8'))['esquema'] == 'csg-interempresa-v1'


def test_112_rf16_rf19_la_herramienta_sale_con_3_y_escribe_el_informe_con_dos_empresas(tmp_path, capsys):
    """112:RF-16, 112:RF-19 — con dos empresas, «NO DEMOSTRADA», código 3 y el informe escrito igual."""
    raiz = tmp_path / 'empresas'
    for i, nombre in enumerate(EMPRESAS[:2]):
        _escribir_trio(raiz / nombre, SEMILLA + i, FICHAS_COMUNES)
    assert (RAIZ / 'tools' / 'interempresa_loco.py').is_file(), 'falta tools/interempresa_loco.py'
    herramienta = cargar_herramienta('interempresa_loco.py')
    salida = tmp_path / 'informe.json'
    assert herramienta.main(['vnr', '--empresas', str(raiz), '--salida', str(salida)]) == 3
    informe = json.loads(salida.read_text(encoding='utf-8'))
    assert informe['veredicto'] == 'NO DEMOSTRADA' and informe['empresas'] == 2
    assert len(informe['pliegues']) == 2
    assert 'NO DEMOSTRADA' in capsys.readouterr().out
    assert herramienta.main(['vnr', '--empresas', str(tmp_path / 'no_existe'), '--salida', str(salida)]) == 1


def test_069_rf41_la_particion_de_las_humanas_no_inventa_sus_etiquetas():
    """069:RF-41 — la T13 se cerró con el código que parte las humanas etiquetadas, sin inventar la empresa ni el grupo
    de paráfrasis de las que no los traen: su cierre dice que las guardadas aún esperan esas etiquetas y quién las da."""
    from convertersmartgrid.aplicacion.asistente import validacion_cruzada as vc
    assert getattr(vc, 'CAMPOS_PARTICION', None) == ('empresa', 'fecha', 'grupo'), 'falta la partición de las humanas'
    tareas = next((RAIZ / 'specs').glob('069-*/tasks.md')).read_text(encoding='utf-8')
    bloque = re.search(r'^- \[( |x)\] T13 .*?(?=^- \[|\Z)', tareas, re.S | re.M)
    assert bloque, 'falta la T13 de la 069'
    assert 'RF-41' in bloque.group(0) and 'Siguiente acción' in bloque.group(0)
    if bloque.group(1) == 'x':
        assert 'particionar_humanas' in bloque.group(0) and 'etiqu' in bloque.group(0)
