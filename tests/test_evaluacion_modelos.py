"""044:RF-1 a RF-3 y RF-8 — cuatro particiones con custodia y política previa."""
import pytest


def filas():
    return [{'record_id': str(i), 'group_id': f'g{i}', 'texto': f'orden {i}',
             'particion': p, 'sistema': 'S1'} for i, p in enumerate(
                 ('entrenamiento', 'seleccion', 'calibracion', 'prueba'))]


def test_cuatro_particiones_sin_solape():
    """044:RF-1 / 044:RF-8 — se preserva la asignación y el hash predeclarado."""
    from convertersmartgrid.evaluacion_modelos import PoliticaEvaluacion, particionar_registros
    politica = PoliticaEvaluacion(modo='agente', semillas=(11, 23))
    p = particionar_registros(filas(), politica)
    assert p.entrenamiento == ('0',) and p.prueba == ('3',)
    assert p.politica_hash == politica.hash
    partes = [set(getattr(p, n)) for n in ('entrenamiento', 'seleccion', 'calibracion', 'prueba')]
    assert all(not a & b for i, a in enumerate(partes) for b in partes[i + 1:])
    grupos = {f['record_id']: f['group_id'] for f in filas()}
    por_grupo = [{grupos[i] for i in parte} for parte in partes]
    assert all(not a & b for i, a in enumerate(por_grupo) for b in por_grupo[i + 1:])
    assert politica.hash != PoliticaEvaluacion(modo='agente', semillas=(11,)).hash


@pytest.mark.parametrize('campo,valor', [('group_id', 'g0'), ('texto', 'ORDEN 0')])
def test_grupo_o_texto_hermano_no_cruza(campo, valor):
    """044:RF-1 — no basta con que los IDs de las filas sean distintos."""
    from convertersmartgrid.evaluacion_modelos import PoliticaEvaluacion, particionar_registros
    registros = filas(); registros[-1][campo] = valor
    with pytest.raises(ValueError, match='solapamiento'):
        particionar_registros(registros, PoliticaEvaluacion(modo='agente'))


def test_sin_calibracion_bloquea():
    """044:RF-2 / 044:RF-3 — no se reemplaza calibración por entrenamiento."""
    from convertersmartgrid.evaluacion_modelos import PoliticaEvaluacion, particionar_registros
    with pytest.raises(ValueError, match='BLOQUEADO_POR_DATOS'):
        particionar_registros([f for f in filas() if f['particion'] != 'calibracion'],
                             PoliticaEvaluacion(modo='agente'))


def test_generalizacion_no_admite_mismo_sistema():
    """044:RF-1 — declarar generalización no habilita usar el mismo sistema."""
    from convertersmartgrid.evaluacion_modelos import PoliticaEvaluacion, particionar_registros
    with pytest.raises(ValueError, match='sistema'):
        particionar_registros(filas(), PoliticaEvaluacion(modo='generalizacion'))


def _filas_de_sistema(sistema='S1', **cuotas):
    filas_ = []
    for parte, n in cuotas.items():
        filas_ += [{'record_id': f'{sistema}-{parte}-{i}', 'group_id': f'{sistema}-{parte}-{i}', 'texto': '',
                    'particion': parte, 'sistema': sistema} for i in range(n)]
    return filas_


def test_modo_por_sistema_no_finge_generalizacion():
    """044:RF-1 / 027:RF-68 — un solo sistema basta, y lo que se publica no dice nada de otra red."""
    from convertersmartgrid.evaluacion_modelos import PoliticaEvaluacion, alcance_de, particionar_registros
    politica = PoliticaEvaluacion(modo='por_sistema')
    p = particionar_registros(_filas_de_sistema(entrenamiento=30, seleccion=10, calibracion=1, prueba=10), politica)
    assert len(p.entrenamiento) == 30 and alcance_de(politica)['generaliza_a_otros_sistemas'] is False
    assert alcance_de(PoliticaEvaluacion(modo='generalizacion'))['generaliza_a_otros_sistemas'] is True
    assert alcance_de(PoliticaEvaluacion(modo='agente'))['generaliza_a_otros_sistemas'] is False


@pytest.mark.parametrize('parte,cuota', [('entrenamiento', 29), ('seleccion', 9), ('prueba', 9)])
def test_cuotas_por_sistema_bloquean(parte, cuota):
    """044:RF-2 — 30/10/10 por sistema: un grupo menos es BLOQUEADO_POR_DATOS, no menos exigencia."""
    from convertersmartgrid.evaluacion_modelos import PoliticaEvaluacion, particionar_registros
    cuotas = {'entrenamiento': 30, 'seleccion': 10, 'calibracion': 1, 'prueba': 10, parte: cuota}
    with pytest.raises(ValueError, match='BLOQUEADO_POR_DATOS'):
        particionar_registros(_filas_de_sistema(**cuotas), PoliticaEvaluacion(modo='por_sistema'))


@pytest.mark.parametrize('minimo', [0, -1, None, 1.0])
def test_minimo_de_calibracion_no_declarado_bloquea(minimo):
    """044:RF-2 — sin un mínimo positivo declarado no hay política con que evaluar."""
    from convertersmartgrid.evaluacion_modelos import PoliticaEvaluacion
    with pytest.raises(ValueError, match='BLOQUEADO_POR_DATOS'):
        PoliticaEvaluacion(modo='agente', min_calibracion_grupos=minimo)


def test_minimo_de_calibracion_exigido_por_grupos_no_por_filas():
    """044:RF-2 — muchas filas de un solo grupo no hacen una calibración de varios."""
    from convertersmartgrid.evaluacion_modelos import PoliticaEvaluacion, particionar_registros
    registros = filas() + [{'record_id': 'c2', 'group_id': 'g2', 'texto': '', 'particion': 'calibracion', 'sistema': 'S1'}]
    with pytest.raises(ValueError, match='BLOQUEADO_POR_DATOS'):
        particionar_registros(registros, PoliticaEvaluacion(modo='agente', min_calibracion_grupos=2))


def test_series_se_cortan_por_dias_enteros():
    """044:RF-1 — en una serie el grupo es el día local: sin solape, y en orden de tiempo."""
    from datetime import datetime, timedelta, timezone

    from convertersmartgrid.digital_twin.series_causales import particionar_dias
    from convertersmartgrid.evaluacion_modelos import PoliticaEvaluacion
    inicio = datetime(2026, 1, 1, tzinfo=timezone.utc)
    instantes = [inicio + timedelta(hours=6 * i) for i in range(4 * 100)]
    r = particionar_dias(instantes, 'UTC', PoliticaEvaluacion(modo='agente'))
    dias = r['dias']
    assert not set(dias['entrenamiento']) & set(dias['prueba'])
    assert max(dias['entrenamiento']) < min(dias['seleccion']) <= max(dias['seleccion']) < min(dias['calibracion'])
    assert max(dias['calibracion']) < min(dias['prueba'])


def _muestra(red, familia):
    from types import SimpleNamespace
    return SimpleNamespace(ids=[red], familia=familia)


def _grupos_pinn():
    return {'entrenamiento': [_muestra('a', 'f0')], 'validacion': [_muestra('a', 'f1')],
            'calibracion': [_muestra('a', 'f2')], 'prueba': [_muestra('b', 'f3')]}


def _identidades(grupos):
    return {id(m): f'e{i}' for i, m in enumerate(m for ms in grupos.values() for m in ms)}


def _politica_pinn(sistema=None):
    from convertersmartgrid.digital_twin import oraculo as orc
    return orc.politica_pinn(orc.Puertas(), orc.Entrenamiento(), sistema)


def test_custodia_de_la_pinn_pasa_por_el_particionador_comun():
    """044:RF-1 — un sistema fuera y familias por partición es una generalización válida."""
    from convertersmartgrid.digital_twin import oraculo as orc
    grupos = _grupos_pinn()
    assert orc.fallos_de_custodia(grupos, _identidades(grupos), _politica_pinn()) == []


def test_custodia_rechaza_la_red_de_prueba_vista_al_ajustar():
    """044:RF-1 — si la red de prueba también ajusta, no hay generalización que publicar."""
    from convertersmartgrid.digital_twin import oraculo as orc
    grupos = _grupos_pinn()
    grupos['prueba'] = [_muestra('a', 'f3')]
    fallos = orc.fallos_de_custodia(grupos, _identidades(grupos), _politica_pinn())
    assert fallos and 'sistema' in fallos[0] and '044:RF-1' in fallos[0]


def test_custodia_rechaza_familia_hermana_entre_particiones():
    """044:RF-1 — otro episodio de la misma familia a cada lado es ver la prueba."""
    from convertersmartgrid.digital_twin import oraculo as orc
    grupos = _grupos_pinn()
    grupos['calibracion'] = [_muestra('a', 'f1')]
    fallos = orc.fallos_de_custodia(grupos, _identidades(grupos), _politica_pinn())
    assert fallos and 'solapamiento' in fallos[0]


def test_custodia_sin_calibracion_bloquea():
    """044:RF-2 — la PINN tampoco sustituye la calibración por otra partición."""
    from convertersmartgrid.digital_twin import oraculo as orc
    grupos = _grupos_pinn()
    grupos['calibracion'] = []
    fallos = orc.fallos_de_custodia(grupos, _identidades(grupos), _politica_pinn())
    assert fallos and 'BLOQUEADO_POR_DATOS' in fallos[0]


def test_con_sistema_los_cupos_30_10_10_se_exigen():
    """044:RF-2 — con ``sistema``, modo por sistema: sus cuotas en familias, no en filas sueltas."""
    from convertersmartgrid.digital_twin import oraculo as orc
    grupos = _grupos_pinn()
    grupos['prueba'] = [_muestra('a', 'f3')]
    politica = _politica_pinn('abc')
    assert politica.modo == 'por_sistema'
    fallos = orc.fallos_de_custodia(grupos, _identidades(grupos), politica)
    assert fallos and 'BLOQUEADO_POR_DATOS' in fallos[0] and 'cuotas' in fallos[0]


def test_reparto_del_sistema_no_separa_hermanos():
    """044:RF-1 — las variantes de demanda de una familia caen juntas, sea cual sea su huella."""
    import hashlib

    from convertersmartgrid.digital_twin.curva import reparto_del_sistema
    ids = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(200)]
    familias = [f'f{i % 7}' for i in range(200)]
    reparto = reparto_del_sistema(ids, familias)
    donde = [{familias[i] for i in indices} for indices in reparto.values()]
    assert sum(len(d) for d in donde) == 7, reparto
    # Sin familia cuenta el propio episodio, como en los recuentos de 027:RF-53.
    assert reparto_del_sistema(ids) == reparto_del_sistema(ids, [''] * 200)


def test_entrenar_con_familias_a_ambos_lados_no_se_inicia(tmp_path, monkeypatch):
    """044:RF-1, 044:RF-2 — la custodia se comprueba antes de abrir modelos o pedir la GPU."""
    import numpy as np

    from convertersmartgrid.digital_twin import oraculo as orc
    from convertersmartgrid.digital_twin.buffer import BuferEpisodios
    from types import SimpleNamespace

    def muestra(red, familia):
        return SimpleNamespace(ids=[red], familia=familia, x=np.zeros((1, 5)), z=np.array([]), v=np.ones(1),
                               mascara=np.ones(1, dtype=bool))
    grupos = {'entrenamiento': [muestra('a', 'f0'), muestra('a', 'f1')], 'validacion': [muestra('a', 'f2'), muestra('a', 'f3')],
              'prueba': [muestra('a', f'p{i}') for i in range(10)]}
    ms = [m for v in grupos.values() for m in v]
    monkeypatch.setattr(orc, '_muestras', lambda *_a: (ms, [str(i) for i in range(len(ms))]))
    monkeypatch.setattr(orc, '_grupos', lambda *_a: grupos)
    monkeypatch.setattr(orc, 'cargar', lambda *_a: pytest.fail('abrió el modelo sin custodia válida'))
    monkeypatch.setattr(orc, 'dispositivo', lambda: pytest.fail('pidió la GPU sin custodia válida'))
    r = orc.entrenar(BuferEpisodios(tmp_path))
    assert not r['entrenado'] and r['status'] == 'BLOQUEADO_POR_DATOS' and any('044:RF-1' in f for f in r['fallos'])
