"""Spec 060: regresiones de independencia, custodia y trazabilidad de alumnos."""
import json
from datetime import date, datetime
from types import SimpleNamespace

import pytest


def test_pinn_no_inicia_sin_particiones_independientes(tmp_path, monkeypatch):
    """060:RF-1: una validación no se convierte silenciosamente en entrenamiento."""
    from convertersmartgrid.digital_twin import oraculo as m
    from convertersmartgrid.digital_twin.buffer import BuferEpisodios
    import numpy as np
    muestra=SimpleNamespace(ids=['a'],familia='f',x=np.zeros((1,5)),z=np.array([]),v=np.ones(1),mascara=np.ones(1,dtype=bool))
    monkeypatch.setattr(m,'_muestras',lambda *a:([muestra],['id']))
    monkeypatch.setattr(m,'_grupos',lambda *a:{'entrenamiento':[], 'validacion':[muestra], 'prueba':[]})
    # La comprobación debe ocurrir antes de abrir el modelo/GPU.
    monkeypatch.setattr(m,'cargar',lambda *a:pytest.fail('cargó pesos sin particiones válidas'))
    r=m.entrenar(BuferEpisodios(tmp_path))
    assert not r['entrenado'] and not r['promovido'] and r['fallos']


def test_calibracion_pinn_separa_familias_y_es_estable():
    """060:RF-2: las variantes de una familia no cruzan selección/calibración."""
    from convertersmartgrid.digital_twin import oraculo as m
    familias=[SimpleNamespace(ids=['red'],familia=f'familia{i}') for i in range(6) for _ in range(2)]
    grupos={'entrenamiento':[], 'validacion':familias, 'prueba':[]}
    a=m.separar_calibracion(grupos);b=m.separar_calibracion({**grupos,'validacion':list(reversed(familias))})
    assert a['calibracion'] and a['validacion']
    assert {x.familia for x in a['calibracion']}=={x.familia for x in b['calibracion']}
    assert not {x.familia for x in a['calibracion']}&{x.familia for x in a['validacion']}
    assert len(grupos['validacion'])==12


def test_pinn_rechaza_familia_compartida_aunque_cambie_episodio(tmp_path,monkeypatch):
    """060:RF-2: otra demanda de la misma familia no constituye calibración independiente."""
    import numpy as np
    from convertersmartgrid.digital_twin import oraculo as m
    from convertersmartgrid.digital_twin.buffer import BuferEpisodios
    def muestra(red,familia):
        return SimpleNamespace(ids=[red],familia=familia,x=np.zeros((1,5)),z=np.array([]),
                               v=np.ones(1),mascara=np.ones(1,dtype=bool))
    train=[muestra('a','f0')];valid=[muestra('a','f0'),muestra('a','f1')]
    prueba=[muestra('b',f'test{i}') for i in range(10)]
    ms=train+valid+prueba
    monkeypatch.setattr(m,'_muestras',lambda *a:(ms,[str(i) for i in range(len(ms))]))
    monkeypatch.setattr(m,'_grupos',lambda *a:{'entrenamiento':train,'validacion':valid,'prueba':prueba})
    monkeypatch.setattr(m,'cargar',lambda *a:pytest.fail('heredó una familia de calibración vista'))
    r=m.entrenar(BuferEpisodios(tmp_path))
    assert not r['entrenado'] and any('familia' in f for f in r['fallos'])


@pytest.mark.parametrize('previo,esperado',[(None,False),({},False),
    ({'entrenamiento':['a'],'validacion':['b']},True),
    ({'entrenamiento':['test'],'validacion':['b']},False),
    ({'entrenamiento':['a'],'validacion':['cal']},False)])
def test_genealogia_no_hereda_ajuste_contaminado(previo,esperado):
    """060:RF-3: el warm-start exige trazabilidad de ajuste y selección anteriores."""
    from convertersmartgrid.digital_twin import oraculo as m
    assert m.herencia_independiente(previo,{'calibracion':['cal'],'prueba':['test']}) is esperado


def test_custodia_politica_copia_inmutable_y_detecta_cambio(tmp_path):
    """060:RF-4: una edición del original no invalida la versión ya custodiada."""
    from convertersmartgrid.asistente import llm_destilacion as m
    original=tmp_path/'politica.md';original.write_text('política vigente',encoding='utf-8')
    evidencia=m.custodiar_politica(original,tmp_path/'corpus')
    original.write_text('política posterior',encoding='utf-8')
    assert m.verificar_fuente(evidencia['copia'])
    copia=tmp_path/'corpus/fuentes/politica.md';copia.write_text('alterada',encoding='utf-8')
    with pytest.raises(ValueError,match='huella'):m.verificar_fuente(evidencia['copia'])


@pytest.mark.parametrize('fechas,esperada',[
    ([date(2025,1,2),datetime(2025,1,2,5)],datetime(2025,1,2)),
    ([date(2025,1,2),datetime(2025,1,2,5,15)],datetime(2025,1,2,5,15))])
def test_fecha_local_medianoche_no_salta_a_timestamp(fechas,esperada):
    """060:RF-5: prioridad por columna temporal, incluidas celdas date a medianoche."""
    from convertersmartgrid.demanda_medida import registros_de_hoja,ALIAS
    anterior=datetime(2025,1,1,23,45) if esperada.hour==0 else date(2025,1,1)
    filas=[['Local Time','Timestamp','kW tot'],[anterior,datetime(2025,1,2,4,45),1], [*fechas,2]]
    registros,_=registros_de_hoja(filas,ALIAS)
    assert registros[-1].fecha==esperada


@pytest.mark.parametrize('rechazado',[False,True])
def test_estado_heredado_se_distingue_del_registro(tmp_path,monkeypatch,rechazado):
    """060:RF-7: un puntero heredado no se convierte en aceptación del registro común."""
    from convertersmartgrid.asistente import almacen
    from convertersmartgrid.web.services import asistente_estado_modelos
    monkeypatch.setattr(almacen,'raiz',lambda:tmp_path)
    base=tmp_path/'modelos/ordenes';(base/'v1').mkdir(parents=True)
    (base/'promovido.json').write_text(json.dumps({'version':'v1'}))
    (base/'v1/modelo.json').write_text(json.dumps({'cfg':{'epocas':24},'metricas':{'f1_datos':.86}}))
    if rechazado:
        from convertersmartgrid.model_registry import RegistroModelo
        from test_model_registry import _payload
        payload=_payload(tmp_path)
        payload['decision']={'status':'RECHAZADO','gates':{'approved':False},'fallos':['F1 insuficiente']}
        RegistroModelo(tmp_path/'model_registry').registrar_candidato('transformer',**payload)
    antes=sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob('*') if p.is_file())
    fila=next(f for f in asistente_estado_modelos()['familias'] if f['familia']=='transformer')
    assert fila['heredado']['version']=='v1' and fila['heredado']['aceptado_registro'] is False
    assert fila['estado']==('RECHAZADO' if rechazado else None)
    assert any('heredado' in b for b in fila['bloqueos'])
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob('*') if p.is_file())==antes


def test_temporal_localiza_celda_sin_potencia(tmp_path):
    """060:RF-5: una potencia ausente se localiza sin imputarla."""
    from openpyxl import Workbook
    from convertersmartgrid.digital_twin.temporal_entrenamiento import cargar_cabeceras
    w=Workbook();h=w.active;h.title='Medidor'
    h.append(['Local Time','kW tot']);h.append([datetime(2025,1,1),1]);h.append([datetime(2025,1,1,0,15),None])
    p=tmp_path/'datos.xlsx';w.save(p)
    with pytest.raises(ValueError,match='Medidor.*fila 3.*potencia'):
        cargar_cabeceras(p,zona_horaria='UTC',hojas=('Medidor',))
    # Sin hojas pedidas y sin otra serie útil, también falla y dice cuál y dónde.
    with pytest.raises(ValueError,match='Medidor.*fila 3.*potencia'):
        cargar_cabeceras(p,zona_horaria='UTC')


def test_temporal_aparta_la_serie_sin_potencia_y_sigue(tmp_path):
    """060:RF-5: sin hojas pedidas, una serie con la potencia vacía se aparta con su motivo y no tumba el libro."""
    from openpyxl import Workbook
    from convertersmartgrid.digital_twin.temporal_entrenamiento import cargar_cabeceras
    w=Workbook();h=w.active;h.title='Buena';b=w.create_sheet('Mala')
    for hoja,segundo in ((h,2),(b,None)):
        hoja.append(['Local Time','kW tot']);hoja.append([datetime(2025,1,1),1]);hoja.append([datetime(2025,1,1,0,15),segundo])
    p=tmp_path/'datos.xlsx';w.save(p)
    series,meta=cargar_cabeceras(p,zona_horaria='UTC')
    assert series=={'Buena':[1,2]} and meta['hojas_omitidas']==['Mala'] and not meta['targets_imputed']
    assert 'Mala: fila 3' in meta['motivos_omitidas']['Mala']


def test_temporal_recorta_al_tramo_comun_sin_hojas_pedidas(tmp_path):
    """060:RF-5: sin hojas pedidas, las series con otro rango de fechas se recortan a su tramo común."""
    from openpyxl import Workbook
    from convertersmartgrid.digital_twin.temporal_entrenamiento import cargar_cabeceras
    w=Workbook();a=w.active;a.title='A';b=w.create_sheet('B')
    a.append(['Local Time','kW tot']);b.append(['Local Time','kW tot'])
    for k in range(3):a.append([datetime(2025,1,1,0,15*k),k+1])
    for k in range(1,4):b.append([datetime(2025,1,1,0,15*k),k+10])
    p=tmp_path/'datos.xlsx';w.save(p)
    series,meta=cargar_cabeceras(p,zona_horaria='UTC')
    assert series=={'A':[2,3],'B':[11,12]} and len(meta['instantes'])==2
    with pytest.raises(ValueError,match='cronologia'):
        cargar_cabeceras(p,zona_horaria='UTC',hojas=('A','B'))


def test_temporal_fecha_textual_y_medianoche(tmp_path):
    """060:RF-5: los formatos soportados por el lector compartido mantienen la hora."""
    from openpyxl import Workbook
    from convertersmartgrid.digital_twin.temporal_entrenamiento import cargar_cabeceras
    w=Workbook();h=w.active;h.title='Medidor';h.append(['Local Time','kW tot'])
    h.append(['2025-01-01 00:00',1]);h.append(['2025-01-01 00:15',2])
    p=tmp_path/'datos.xlsx';w.save(p)
    series,meta=cargar_cabeceras(p,zona_horaria='UTC')
    assert series['Medidor']==[1,2] and not meta['targets_imputed']


def test_gru_declara_configuracion_completa_sin_cargar_red():
    """060:RF-6: el manifiesto preserva todos los parámetros de construcción."""
    from convertersmartgrid.digital_twin.temporal import GemeloGRU
    m=object.__new__(GemeloGRU)
    m.ventana=96;m.ocultas=32;m.epocas=40;m.semilla=11;m.paciencia=8;m.recorte=1.;m.fraccion_validacion=.2
    assert m.configuracion()=={'ventana':96,'ocultas':32,'epocas':40,'semilla':11,
        'paciencia':8,'recorte':1.,'fraccion_validacion':.2}


def test_alcance_temporal_se_fija_por_fecha_no_por_calidad(tmp_path):
    """060:RF-8: seleccionar enero no autoriza omitir un dato ausente de enero."""
    from openpyxl import Workbook
    from convertersmartgrid.digital_twin.temporal_entrenamiento import cargar_cabeceras
    w=Workbook();h=w.active;h.title='Medidor';h.append(['Local Time','kW tot'])
    h.append([datetime(2025,1,1),1]);h.append([datetime(2025,1,1,0,15),2])
    h.append([datetime(2025,2,1),None]);p=tmp_path/'datos.xlsx';w.save(p)
    s,meta=cargar_cabeceras(p,zona_horaria='UTC',hojas=('Medidor',),desde='2025-01-01',hasta='2025-02-01')
    assert s['Medidor']==[1,2] and meta['alcance']['filas_fuera_intervalo']=={'Medidor':1}
    h.cell(3,2).value=None;w.save(p)
    with pytest.raises(ValueError,match='fila 3'):
        cargar_cabeceras(p,zona_horaria='UTC',hojas=('Medidor',),desde='2025-01-01',hasta='2025-02-01')


def test_alcance_temporal_no_acepta_hoja_ausente(tmp_path):
    """060:RF-8: una hoja mal escrita no se omite ni se sustituye por otra."""
    from openpyxl import Workbook
    from convertersmartgrid.digital_twin.temporal_entrenamiento import cargar_cabeceras
    w=Workbook();p=tmp_path/'datos.xlsx';w.save(p)
    with pytest.raises(ValueError,match='hojas'):
        cargar_cabeceras(p,zona_horaria='UTC',hojas=('ausente',))


def test_coordinador_conserva_alcance_temporal_explicito(tmp_path,monkeypatch):
    """060:RF-8: el coordinador entrega las mismas hojas y límites al trabajador existente."""
    from tools import reentrenar_modelos as m
    args=SimpleNamespace(vocabulario=None,dataset=tmp_path,semillas='11',cabeceras=tmp_path/'libro.xlsx',
        twin=tmp_path,zona_horaria='UTC',codigos_temporales=None,hojas_temporales=['Medidor'],
        temporal_desde='2025-01-01',temporal_hasta='2025-02-01')
    llamadas=[]
    monkeypatch.setattr(m,'_subproceso',lambda cmd,*a:llamadas.append(cmd) or {})
    next(e for e in m._etapas(args,tmp_path) if e.name=='gru').run()
    cmd=llamadas[0]
    assert cmd[cmd.index('--hoja')+1]=='Medidor'
    assert cmd[cmd.index('--desde')+1]=='2025-01-01'
    assert cmd[cmd.index('--hasta')+1]=='2025-02-01'


@pytest.mark.parametrize('fecha,error',[(datetime(2025,1,1),'duplicado'),('2025-19-40 00:15','fecha')])
def test_temporal_localiza_fecha_invalida_o_duplicada(tmp_path,fecha,error):
    """060:RF-5: fechas corruptas o repetidas tienen un localizador de origen."""
    from openpyxl import Workbook
    from convertersmartgrid.digital_twin.temporal_entrenamiento import cargar_cabeceras
    w=Workbook();h=w.active;h.title='Medidor';h.append(['Local Time','kW tot'])
    h.append([datetime(2025,1,1),1]);h.append([fecha,2]);p=tmp_path/'datos.xlsx';w.save(p)
    with pytest.raises(ValueError,match='Medidor.*fila 3.*'+error):cargar_cabeceras(p,zona_horaria='UTC')


def test_temporal_rechaza_libro_cambiado_durante_lectura(tmp_path,monkeypatch):
    """060:RF-8: el hash posterior no debe atribuirse a observaciones de otra versión."""
    from openpyxl import Workbook
    from convertersmartgrid.digital_twin.temporal_entrenamiento import cargar_cabeceras
    from convertersmartgrid import trabajadores_ml
    w=Workbook();h=w.active;h.append(['Local Time','kW tot'])
    h.append([datetime(2025,1,1),1]);h.append([datetime(2025,1,1,0,15),2])
    p=tmp_path/'datos.xlsx';w.save(p)
    hashes=iter(['a'*64,'b'*64]);monkeypatch.setattr(trabajadores_ml,'sha_archivo',lambda p:next(hashes))
    with pytest.raises(ValueError,match='cambi.*lectura'):cargar_cabeceras(p,zona_horaria='UTC')


def test_busqueda_reserva_calibracion_antes_del_ajuste(monkeypatch):
    """060:RF-2: la selección de hiperparámetros no usa familias de calibración."""
    import numpy as np
    from convertersmartgrid.digital_twin import hiperparametros as hp,oraculo as m
    train=SimpleNamespace(ids=['a'],x=np.zeros((1,5)),familia='train')
    valid=[SimpleNamespace(ids=['a'],x=np.zeros((1,5)),familia=f'f{i}') for i in range(6)]
    grupos={'entrenamiento':[train],'validacion':valid,'prueba':[]}
    esperada=m.separar_calibracion(grupos)['validacion'];llamadas=[]
    monkeypatch.setattr(hp,'particionar',lambda ms:grupos)
    def detener(*args,validacion,**kw):
        llamadas.append(validacion)
        raise ValueError('fin del contrato antes de CUDA')
    monkeypatch.setattr(hp,'entrenar_miembro',detener)
    with pytest.raises(ValueError,match='fin del contrato'):hp.buscar([train,*valid],ensayos=1)
    assert llamadas==[esperada]
