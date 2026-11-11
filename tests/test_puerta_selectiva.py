"""Puerta selectiva del intérprete y plan robusto (spec 069, RF-35 y RF-36)."""
from __future__ import annotations

from convertersmartgrid.asistente import destilacion_integral as di
from convertersmartgrid.asistente import plan as pl
from convertersmartgrid.asistente.interprete import Interpretacion


class _Modelo:
    """Predice lo que se le diga por texto: así se mide la puerta sin GPU ni codificador."""

    def __init__(self, respuestas):
        self.respuestas = respuestas

    def predecir(self, texto):
        tarea, confianza, datos = self.respuestas[texto]
        return {'tarea': tarea, 'confianza': confianza, 'datos': datos}


def _fila(texto, tarea, *datos):
    return {'texto': texto, 'tarea': tarea,
            'datos': [(texto.index(v), texto.index(v) + len(v), t) for v, t in datos]}


def _dato(valor):
    return [{'valor': valor, 'inicio': 0, 'fin': len(valor), 'confianza': .99}]


def test_069_rf35_mide_lo_que_ejecuta_solo_como_lo_resuelve_el_plan():
    """069:RF-35 — «CA101 a CHN102» frente a dos códigos es el mismo plan; lo dudoso no cubre."""
    filas = [_fila('transfiere de CA101 a CHN102 en PRUEBA_X', 'transferencia', ('CA101 a CHN102', 'alimentadores'),
                   ('PRUEBA_X', 'proyecto')),
             _fila('flujo de AB101', 'flujo', ('AB101', 'alimentadores')),
             _fila('estado del trabajo', 'estado')]
    modelo = _Modelo({
        filas[0]['texto']: ('transferencia', .99, {'alimentadores': _dato('CA101') + _dato('CHN102'),
                                                  'proyecto': _dato('PRUEBA_X')}),
        filas[1]['texto']: ('flujo', .99, {'alimentadores': _dato('AB101')}),
        filas[2]['texto']: ('cancelar_trabajo', .60, {})})
    m = di.medir_selectiva(modelo, filas, .95)
    assert (m['cubiertos'], m['acierto_tarea'], m['plan_igual']) == (2, 1.0, 1.0)
    assert abs(m['cobertura'] - 2 / 3) < 1e-9


def test_069_rf35_la_decision_selectiva():
    """069:RF-35 — pasa con lo que ejecuta solo en regla; falla con poca cobertura o por debajo del modelo en uso."""
    buena = {'acierto_tarea': .985, 'plan_igual': .96, 'cobertura': .6}
    selectiva = {'sinteticas': buena, 'maestro': buena, 'humanas': None}
    en_uso = {'sinteticas': {'acierto_tarea': .83}}
    rechazo = {'ejemplos': 206, 'rechazada': 1.0, 'se_cuela': 0.0}
    assert di.decidir_selectiva(selectiva, 'maestro', {'acierto_tarea': .87}, en_uso, rechazo)['status'] == 'PROMOVIDO'
    # La puerta de la charla (069:RF-17 a RF-19) sigue: sin medirla no se aprueba.
    assert di.decidir_selectiva(selectiva, 'maestro', {'acierto_tarea': .87}, en_uso)['status'] == 'RECHAZADO'
    # Lo que no reconoce como charla pero queda bajo el umbral no se ejecuta: decide lo que se cuela.
    poca_charla = {'ejemplos': 213, 'rechazada': .887, 'se_cuela': 0.0}
    assert di.decidir_selectiva(selectiva, 'maestro', {'acierto_tarea': .87}, en_uso, poca_charla)['status'] == 'PROMOVIDO'
    se_cuela = {'ejemplos': 213, 'rechazada': .99, 'se_cuela': .05}
    assert di.decidir_selectiva(selectiva, 'maestro', {'acierto_tarea': .87}, en_uso, se_cuela)['status'] == 'RECHAZADO'
    poca = {**selectiva, 'maestro': {**buena, 'cobertura': .4}}
    d = di.decidir_selectiva(poca, 'maestro', {'acierto_tarea': .87}, en_uso, rechazo)
    assert d['status'] == 'RECHAZADO' and any('cobertura' in f for f in d['fallos'])
    peor = di.decidir_selectiva(selectiva, 'maestro', {'acierto_tarea': .80}, en_uso, rechazo)
    assert peor['status'] == 'RECHAZADO' and any('modelo en uso' in f for f in peor['fallos'])
    assert di.decidir_selectiva(selectiva, 'humanas', {'acierto_tarea': .87}, en_uso, rechazo)['status'] == 'RECHAZADO'


def test_069_rf36_el_plan_resuelve_uniones_rutas_y_mensaje_entero(tmp_path):
    """069:RF-36 — sin «A» ni «CON» como alimentadores; la ruta que existe; el mensaje entero donde toca."""
    assert pl.trozos_lista('CA101 a CHN102') == ['CA101', 'CHN102']
    assert pl.trozos_lista('CA101 con PE104') == ['CA101', 'PE104']
    assert pl.trozos_lista('AL105, AL108 y PO101') == ['AL105', 'AL108', 'PO101']
    libro = tmp_path / 'cargas nuevas.xlsx'
    libro.write_bytes(b'x')
    ruta = libro.as_posix()
    assert pl.ruta_existente(f'archivo {ruta} porfa', '') == ruta
    plan = pl.resolver(Interpretacion(f'cargas nuevas: archivo {ruta} porfa', 'cargas_nuevas', .99, 'transformer',
                                      {'ruta': _dato(f'archivo {ruta} porfa')}), {})
    assert plan.datos.get('ruta') == ruta
    texto = 'clasifica este informe solicitud de factibilidad para 800 kW'
    p = pl.resolver(Interpretacion(texto, 'clasificar_informe', .99, 'transformer', {'texto': _dato('factibilidad')}), {})
    assert p.datos.get('texto') == texto
    q = pl.resolver(Interpretacion('busca en internet precio de bancos', 'buscar_internet', .99, 'transformer',
                                   {'texto': _dato('precio de bancos')}), {})
    assert q.datos.get('texto') == 'precio de bancos'
