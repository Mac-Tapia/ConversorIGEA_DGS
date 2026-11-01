"""044:RF-1 a RF-3 y RF-8 — cuatro particiones con custodia y política previa."""
import pytest


def filas():
    return [{'record_id': str(i), 'group_id': f'g{i}', 'texto': f'orden {i}',
             'particion': p, 'sistema': 'S1'} for i, p in enumerate(
                 ('entrenamiento', 'seleccion', 'calibracion', 'prueba'))]


def test_cuatro_particiones_sin_solape():
    """044:RF-1 / 044:RF-8 — se preserva la asignación y el hash predeclarado."""
    from igea_dgs.evaluacion_modelos import PoliticaEvaluacion, particionar_registros
    politica = PoliticaEvaluacion(modo='agente', semillas=(11, 23))
    p = particionar_registros(filas(), politica)
    assert p.entrenamiento == ('0',) and p.prueba == ('3',)
    assert p.politica_hash == politica.hash
    assert politica.hash != PoliticaEvaluacion(modo='agente', semillas=(11,)).hash


@pytest.mark.parametrize('campo,valor', [('group_id', 'g0'), ('texto', 'ORDEN 0')])
def test_grupo_o_texto_hermano_no_cruza(campo, valor):
    """044:RF-1 — no basta con que los IDs de las filas sean distintos."""
    from igea_dgs.evaluacion_modelos import PoliticaEvaluacion, particionar_registros
    registros = filas(); registros[-1][campo] = valor
    with pytest.raises(ValueError, match='solapamiento'):
        particionar_registros(registros, PoliticaEvaluacion(modo='agente'))


def test_sin_calibracion_bloquea():
    """044:RF-2 / 044:RF-3 — no se reemplaza calibración por entrenamiento."""
    from igea_dgs.evaluacion_modelos import PoliticaEvaluacion, particionar_registros
    with pytest.raises(ValueError, match='BLOQUEADO_POR_DATOS'):
        particionar_registros([f for f in filas() if f['particion'] != 'calibracion'],
                             PoliticaEvaluacion(modo='agente'))


def test_generalizacion_no_admite_mismo_sistema():
    """044:RF-1 — declarar generalización no habilita usar el mismo sistema."""
    from igea_dgs.evaluacion_modelos import PoliticaEvaluacion, particionar_registros
    with pytest.raises(ValueError, match='sistema'):
        particionar_registros(filas(), PoliticaEvaluacion(modo='generalizacion'))
