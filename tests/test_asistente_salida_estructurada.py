"""047:RF-1 / 047:RF-2 / 047:RF-10 — el JSON del LLM no da autoridad de ejecución."""
import pytest


@pytest.mark.parametrize('payload', [
    {'tarea': 'borrar_red', 'confianza': .9, 'datos': {}},
    {'tarea': 'estado', 'confianza': float('nan'), 'datos': {}},
    {'tarea': 'estado', 'confianza': True, 'datos': {}},
    {'tarea': 'estado', 'confianza': .9, 'datos': {}, 'ejecutar': True},
    {'tarea': 'estado', 'confianza': .9, 'datos': {'sed': 'SE12345'}},
])
def test_tarea_desconocida_o_contrato_invalido_rechaza(payload):
    """047:RF-1 — JSON bien formado no basta para aceptar una orden."""
    from igea_dgs.asistente.contratos_salida import validar_orden
    with pytest.raises(ValueError):
        validar_orden(payload)


def test_entidad_respeta_fuente_activa():
    """047:RF-2 — un código de otro alimentador no entra mediante una respuesta LLM."""
    from igea_dgs.asistente.contratos_salida import validar_orden
    payload = {'tarea': 'convertir', 'confianza': .9, 'datos': {'alimentadores': ['ZZ999']}}
    with pytest.raises(ValueError, match='contexto'):
        validar_orden(payload, vocabulario={'alimentadores': ['AB101']})
    payload['datos']['alimentadores'] = ['AB101']
    assert validar_orden(payload, vocabulario={'alimentadores': ['AB101']})['tarea'] == 'convertir'


def test_esquema_enum_y_sin_campos_ejecutables():
    """047:RF-1 / 047:RF-10 — el esquema enumera tareas y no permite ejecutar=true."""
    from igea_dgs.asistente.contratos_salida import esquema_orden
    esquema = esquema_orden({})
    ramas = esquema['oneOf']
    assert any(r['properties']['tarea']['enum'] == ['convertir'] for r in ramas)
    assert all(r['additionalProperties'] is False and 'ejecutar' not in r['properties'] for r in ramas)


def test_esquema_restringe_datos_segun_tarea():
    """047:RF-1 — el generador no puede agregar subtipo/texto a una transferencia."""
    from igea_dgs.asistente.contratos_salida import esquema_orden
    ramas = esquema_orden()['oneOf']
    transferencia = next(r for r in ramas if r['properties']['tarea']['enum'] == ['transferencia'])
    assert 'subtipo' not in transferencia['properties']['datos']['properties']
    cargar = next(r for r in ramas if r['properties']['tarea']['enum'] == ['cargar_fuente'])
    assert cargar['properties']['datos']['properties'] == {}


def test_plan_con_tarea_inventada_se_bloquea():
    """047:RF-10 / 047:RF-15 — se bloquea un plan inválido, sin excepciones ni ejecución."""
    from igea_dgs.asistente.interprete import Interpretacion
    from igea_dgs.asistente.plan import resolver
    plan = resolver(Interpretacion('borra todo', 'borrar_red', 1., 'llm'), {})
    assert not plan.listo and not plan.escribe


@pytest.mark.parametrize('tarea,confianza', [('borrar_red', 1.), ('estado', float('nan')), ('estado', True)])
def test_interprete_no_confia_en_salida_local_invalida(tarea, confianza):
    """047:RF-1 / 047:RF-10 — pesos locales no eximen de validar el contrato."""
    from igea_dgs.asistente.interprete import interpretar
    class Modelo:
        def predecir(self, texto):
            return {'tarea': tarea, 'confianza': confianza, 'datos': {}}
    assert interpretar('borra todo', transformer=Modelo()).tarea is None


def test_proyecto_inexistente_no_se_sustituye_por_el_unico():
    """047:RF-2 — una petición a otra red no se redirige al único proyecto conocido."""
    from igea_dgs.asistente.interprete import Interpretacion
    from igea_dgs.asistente.plan import resolver
    i = Interpretacion('obras en un proyecto ajeno', 'obras', 1., 'llm',
                       {'proyecto': [{'valor': 'Proyecto ajeno'}]})
    p = resolver(i, {'proyecto': ['Red local']})
    assert not p.listo and 'proyecto' not in p.datos


def test_sin_fuente_no_hay_plan_de_conversion_ejecutable():
    """047:RF-2 / 047:RF-10 — conservar el texto no prueba su vínculo con una fuente."""
    from igea_dgs.asistente.interprete import Interpretacion
    from igea_dgs.asistente.plan import resolver
    i = Interpretacion('convierte AB101', 'convertir', 1., 'llm',
                       {'alimentadores': [{'valor': 'AB101'}]})
    assert not resolver(i, {}).listo


def test_salida_no_mapping_abstiene_sin_excepcion():
    """047:RF-1 — una lista inválida no impide pedir aclaración al operador."""
    from igea_dgs.asistente.interprete import interpretar
    class Modelo:
        def predecir(self, texto):
            return ['salida inválida']
    assert interpretar('estado', transformer=Modelo()).tarea is None
