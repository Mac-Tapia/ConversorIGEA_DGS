"""Spec 081, 057: un «Caso base» que no converge por una causa reconstruible llega convergido, con su anotación.

Con un doble de DIgSILENT: la confirmación real es la T10.
"""
from __future__ import annotations

import pytest

from apoyo import cargar_herramienta
from convertersmartgrid.powerfactory_metadata import estado_flujo
from convertersmartgrid.resolver_convergencia import (
    DEMANDA, DESCONOCIDA, FASES, ISLA, QUE_HACER, clasificar_causas, resolver, texto_de_resolucion,
)


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('powerfactory_acceptance.py', 'powerfactory_acceptance_081', tools_en_path=True)


class Obj:
    def __init__(self, clase, nombre, **attrs):
        self.clase, self.loc_name = clase, nombre
        self.__dict__.update(attrs)
        self.escritos = []

    def GetClassName(self):
        return self.clase

    def GetParent(self):
        return None

    def GetAttribute(self, nombre):
        return self.__dict__.get(nombre)

    def SetAttribute(self, nombre, valor):
        self.escritos.append((nombre, valor))
        self.__dict__[nombre] = valor


def _cub(terminal):
    return Obj('StaCubic', f'Cub_{terminal.loc_name}', cterm=terminal)


class Ventana:
    def __init__(self, app):
        self.app = app

    def GetContent(self):
        return [self.app.mensaje]


class Comando(Obj):
    def __init__(self, app):
        super().__init__('ComLdf', 'ComLdf')
        self.app = app

    def Execute(self):
        self.app.flujos += 1
        return 0 if self.app.cuadra() else 1


class App:
    """DIgSILENT en lo que aquí importa: no calcula mientras un elemento tenga más fases que su barra."""

    def __init__(self, objetos, *, mensaje=''):
        self.objetos, self.mensaje, self.flujos = objetos, mensaje, 0
        self.comando = Comando(self)

    def cuadra(self):
        fases = {0: 3, 4: 2, 6: 1}
        for o in self.objetos:
            if o.clase == 'ElmCoup' and o.nphase > min(fases[c.cterm.phtech] for c in (o.bus1, o.bus2)):
                return False
            if o.clase == 'ElmShnt' and {1: 3, 3: 2, 6: 1}[o.ctech] > fases[o.bus1.cterm.phtech]:
                return False
        return True

    def GetCalcRelevantObjects(self, patron):
        return [o for o in self.objetos if patron == f'*.{o.clase}']

    def GetFromStudyCase(self, _nombre):
        return self.comando

    def IsLdfValid(self):
        return self.cuadra()

    def GetOutputWindow(self):
        return Ventana(self)

    def GetActiveScenario(self):
        return None


def _app_con_acoplador():
    tri, mono = Obj('ElmTerm', 'T3', phtech=0, uknom=10.0), Obj('ElmTerm', 'T1', phtech=6, uknom=10.0)
    acoplador = Obj('ElmCoup', 'CP1', nphase=3, bus1=_cub(tri), bus2=_cub(mono), outserv=0)
    return App([tri, mono, acoplador], mensaje='The no. of phases (3) of the element must be less than or equal to the no. of phases (1)'), acoplador


def _ldf_malo():
    return {'pass': False, 'return_code': 1, 'return_meaning': 'Error in load flow data', 'ldf_valid': False, 'errors': []}


def test_caso_base_con_causa_reconstruible_llega_convergido(guion):
    """081:RF-26, 081:RF-27, 081:RF-28, 081:RF-32 — el acoplador de tres fases en una barra monofásica (fallo real): se corrige, se vuelve a medir, y queda dicho."""
    app, acoplador = _app_con_acoplador()
    load_flow = {'requested': True, 'pass': False, 'return_code': 1, 'ldf_valid': False, 'errors': ['Error in load flow data']}
    assert guion.dar_solucion(app, _ldf_malo(), load_flow, corregir=True) is True
    assert acoplador.nphase == 1 and app.flujos == 1
    res = load_flow['resolucion']
    assert res['estado'] == 'converge' and res['queda'] == [] and res['vueltas'] == 1
    a = res['anotaciones'][0]
    assert a['elemento'] == 'acoplador CP1' and a['antes'] == '3 fases' and a['despues'] == '1 fases'
    assert '081:RF-26' in a['regla'] and 'T1' in a['evidencia']
    assert load_flow['pass'] is True and load_flow['return_code'] == 0 and 'ajuste_de_cargas' not in load_flow
    flujo = estado_flujo({'load_flow': load_flow})
    assert flujo['estado'] == 'converge' and flujo['correcciones'] == res['anotaciones']


def test_banco_trifasico_en_barra_de_dos_fases(guion):
    """081:RF-26 — el otro fallo real, en el proyecto ya importado: el banco toma la tecnología de su barra."""
    barra = Obj('ElmTerm', 'B2', phtech=4, uknom=10.0)
    banco = Obj('ElmShnt', 'BC', ctech=1, ilcph=0, bus1=_cub(barra), outserv=0)
    app = App([barra, banco], mensaje='Error in load flow data')
    lf = {'requested': True}
    assert guion.dar_solucion(app, _ldf_malo(), lf, corregir=True) is True
    assert banco.ctech == 3 and lf['resolucion']['anotaciones'][0]['despues'] == '2 fases'


def test_lectura_de_fases_sin_escribir(guion):
    """081:RF-10 — la misma comprobación sobre un proyecto, y sin una sola escritura."""
    from convertersmartgrid.comprobacion_fases import comprobar

    app, acoplador = _app_con_acoplador()
    fuera = Obj('ElmCoup', 'CP2', nphase=3, bus1=acoplador.bus1, bus2=acoplador.bus2, outserv=1)
    tipo = Obj('TypLne', 'T', nlnph=3)
    tramo = Obj('ElmLne', 'L1', typ_id=tipo, bus1=acoplador.bus1, bus2=acoplador.bus2, outserv=0)
    reg = Obj('ElmVoltreg', 'R1', nphase=3, bus1=acoplador.bus2, outserv=0)
    trafo = Obj('ElmTr2', 'TR', typ_id=Obj('TypTr2', 'TT', nt2ph=1), bushv=acoplador.bus2, outserv=0)
    app.objetos += [fuera, tramo, reg, trafo]
    elementos, barras, _ = guion.elementos_de_pf(app)
    informe = comprobar(elementos, barras)
    assert informe.conteo == {'acoplador': 1, 'regulador': 1, 'tramo': 1}
    assert all(o.escritos == [] for o in app.objetos)


def test_tramo_con_tipo_no_se_toca_y_queda_dicho(guion, monkeypatch):
    """081:RF-29, 081:RF-30 — un tipo compartido no se cambia aquí: se dice, con su elemento y qué hacer; y baja la demanda como siempre, sin parar."""
    tri, mono = Obj('ElmTerm', 'T3', phtech=0, uknom=10.0), Obj('ElmTerm', 'T1', phtech=6, uknom=10.0)
    tramo = Obj('ElmLne', 'L1', typ_id=Obj('TypLne', 'T', nlnph=3), bus1=_cub(tri), bus2=_cub(mono), outserv=0)
    app = App([tri, mono, tramo], mensaje='')
    monkeypatch.setattr(guion, 'converger_caso_base', lambda _app: {'pass': False, 'factor': None, 'intentos': []})
    lf = {'requested': True}
    assert guion.dar_solucion(app, _ldf_malo(), lf, corregir=True) is False
    assert tramo.typ_id.nlnph == 3 and lf['ajuste_de_cargas']['pass'] is False
    queda = lf['resolucion']['queda']
    assert queda[0]['causa'] == FASES and 'tramo L1' in queda[0]['elementos'][0] and queda[0]['que_hacer'] == QUE_HACER[FASES]
    flujo = estado_flujo({'load_flow': lf})
    assert flujo['queda'] == queda
    assert any('Queda fases' in x and 'Qué hacer' in x for x in texto_de_resolucion(flujo))


def test_demanda_sigue_si_la_causa_no_es_reconstruible(guion, monkeypatch):
    """081:RF-26, 015:RF-38 — primero la causa, después la demanda; si esta resuelve, no queda nada por decir."""
    app = App([Obj('ElmTerm', 'T', phtech=0, uknom=10.0)], mensaje='')
    orden = []
    monkeypatch.setattr(guion, 'converger_caso_base', lambda _app: orden.append('demanda') or {'pass': True, 'factor': .7, 'intentos': []})
    lf = {'requested': True}
    assert guion.dar_solucion(app, _ldf_malo(), lf, corregir=True) is True
    assert orden == ['demanda'] and lf['resolucion']['queda'] == [] and lf['pass'] is True


def test_con_sin_proyecto_no_se_corrige_el_caso_base(guion, monkeypatch):
    """081:RF-31 — «Sin proyecto» ya creado: ni fases ni demanda (015:RF-39)."""
    app, acoplador = _app_con_acoplador()
    monkeypatch.setattr(guion, 'converger_caso_base', lambda _app: pytest.fail('no debe tocar la demanda'))
    lf = {'requested': True}
    assert guion.dar_solucion(app, _ldf_malo(), lf, corregir=False) is False
    assert acoplador.nphase == 3 and acoplador.escritos == [] and lf['ajuste_de_cargas'] == {'omitido': 'sin_proyecto'}


@pytest.mark.parametrize('mensajes,oraculo,tipo', [
    ('The no. of phases (3) of the element must be less than or equal to the no. of phases (2)', [], FASES),
    ('Area not supplied', [], ISLA),
    ('', ['isla sin camino a la fuente'], ISLA),
    ('', ['el flujo no converge: exceso de demanda en la barra X'], DEMANDA),
    ('sin más', [], DESCONOCIDA),
])
def test_causa_de_la_no_convergencia(mensajes, oraculo, tipo):
    """081:RF-25 — con los mensajes de DIgSILENT y lo que halló el oráculo, de la más concreta a la más general."""
    causas = clasificar_causas(mensajes, oraculo=oraculo)
    assert causas[0].tipo == tipo and causas[0].detalle
    assert clasificar_causas('', hallazgos_fases=['banco B: 3 fases'])[0].elementos == ('banco B: 3 fases',)


def test_el_bucle_para_si_no_hay_correccion_nueva():
    """081:RF-28, 081:RF-29 — repetir la misma corrección no ayuda: se para y dice lo que queda."""
    medidas = []

    def medir():
        medidas.append(1)
        return {'estado': 'no_converge', 'mensajes': 'Error in load flow data', 'hallazgos_fases': ['banco B']}

    corrige = [{'elemento': 'banco B', 'antes': 3, 'despues': 2, 'regla': 'r', 'evidencia': 'e'}]
    res = resolver(medir, {FASES: lambda _c: list(corrige)})
    assert len(medidas) == 2 and len(res.anotaciones) == 1 and res.estado == 'no_converge'
    assert {q['causa'] for q in res.queda} == {FASES, 'datos'}
    assert [h['paso'] for h in res.historial] == [0, 1]


def test_lectura_tras_el_flujo_sin_escribir(guion):
    """081:RF-11, 081:RF-12, 081:RF-13 — lee barras y cargas de DIgSILENT, cuenta lo que no se sirve y no escribe nada."""
    mt = Obj('ElmTerm', 'MT', uknom=10.0, **{'m:u': 1.0})
    bt = Obj('ElmTerm', 'BT', uknom=.23)                        # sin resultado: DIgSILENT no la alimentó
    otra = Obj('ElmTerm', 'BT2', uknom=.23, **{'m:u': .97})
    mala = Obj('ElmLod', 'S1', plini=.01, scale0=1.0, outserv=0, bus1=_cub(bt))
    buena = Obj('ElmLod', 'S2', plini=.01, scale0=1.0, outserv=0, bus1=_cub(otra), **{'m:Psum:bus1': .01})
    app = App([mt, bt, otra, mala, buena])
    tras = guion.leer_tras_flujo(app)
    assert tras['barras_bt_a_cero'] == 1 and tras['cargas_sin_consumo'] == 1 and tras['limpio'] is False
    assert tras['lista_barras'] == ['BT'] and tras['lista_cargas'] == ['S1']
    assert all(o.escritos == [] for o in app.objetos)


def test_lectura_sin_ningun_resultado_no_saca_conclusiones(guion):
    """081:RF-13 — si ninguna barra tiene resultado, no hay lectura: no se dice que todo está a cero."""
    app = App([Obj('ElmTerm', 'BT', uknom=.23), Obj('ElmLod', 'S', plini=.01, outserv=0)])
    assert guion.leer_tras_flujo(app) == {'sin_lectura': True, 'limpio': True, 'barras_bt_a_cero': 0, 'cargas_sin_consumo': 0}


def test_causas_por_alimentador_en_la_web():
    """081:RF-25, 081:RF-29 — en la web también: lo que dice el flujo y lo que halló el oráculo de ese alimentador."""
    from convertersmartgrid.web import services

    flujo = {'motivo': 'DIgSILENT devolvió return_code 1.', 'fallos': []}
    preflight = {'feeders': [{'feeder': 'A', 'hallazgos': [{'texto': 'isla sin camino a la fuente'}]},
                             {'feeder': 'B', 'hallazgos': ['demanda fuera de escala']}]}
    queda = services._causas_de_no_convergencia(flujo, preflight, 'A')
    assert queda[0]['causa'] == ISLA and queda[0]['que_hacer']
