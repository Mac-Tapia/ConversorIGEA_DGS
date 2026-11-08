"""Contrato del ciclo común de aprendizaje (spec 050).

Contrato puro con registro, coordinador e instantánea reales sobre carpetas temporales: no acredita
un entrenamiento real (eso son las tareas T1b a T5b de la spec, con GPU y datos locales).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from convertersmartgrid import aprendizaje_continuo as ac
from convertersmartgrid.model_registry import RegistroModelo
from convertersmartgrid.training_coordinator import TrainingStage

RAIZ = Path(__file__).resolve().parents[1]
CTX = hashlib.sha256(b'contexto-043').hexdigest()
VERSIONES = {'codigo': 'abc123', 'catalogo_modelos': 'def456'}


def _fuentes(tmp_path: Path) -> dict[str, Path]:
    twin = tmp_path / 'origen' / 'twin' / 'objetos'
    twin.mkdir(parents=True)
    (twin / 'ep1.json').write_text('{"v": 1}', encoding='utf-8')
    dataset = tmp_path / 'origen' / 'dataset.jsonl'
    dataset.write_text('{"tarea": "convertir"}\n', encoding='utf-8')
    return {'twin': tmp_path / 'origen' / 'twin', 'dataset': dataset}


def _instantanea(tmp_path: Path) -> dict:
    return ac.congelar_instantanea(_fuentes(tmp_path), tmp_path / 'ap', contexto=CTX, versiones=VERSIONES)


# --------------------------------------------------------------------------- T1

def test_instantanea_copia_verificada_e_idempotente(tmp_path):
    """050:RF-1, 050:RF-2: copias con huella, la misma identidad al repetir y rutas a la copia."""
    fuentes = _fuentes(tmp_path)
    a = ac.congelar_instantanea(fuentes, tmp_path / 'ap', contexto=CTX, versiones=VERSIONES)
    b = ac.congelar_instantanea(fuentes, tmp_path / 'ap', contexto=CTX, versiones=VERSIONES)
    assert a['snapshot_id'] == b['snapshot_id'] and a['verificada'] and a['contexto_hash'] == CTX
    copia = ac.ruta_de(a, 'dataset')
    assert copia.is_file() and copia != fuentes['dataset'] and copia.read_text(encoding='utf-8').startswith('{')
    assert (ac.ruta_de(a, 'twin') / 'objetos' / 'ep1.json').is_file()
    # Un episodio nuevo en el origen no toca la instantánea; da otra.
    (fuentes['twin'] / 'objetos' / 'ep2.json').write_text('{}', encoding='utf-8')
    assert ac.verificar_instantanea(a['ruta'])['verificada']
    c = ac.congelar_instantanea(fuentes, tmp_path / 'ap', contexto=CTX, versiones=VERSIONES)
    assert c['snapshot_id'] != a['snapshot_id']


def test_otro_contexto_u_otras_versiones_es_otra_instantanea(tmp_path):
    """050:RF-1: el contexto 043 y las versiones entran en la identidad."""
    fuentes = _fuentes(tmp_path)
    a = ac.congelar_instantanea(fuentes, tmp_path / 'ap', contexto=CTX, versiones=VERSIONES)
    otro = hashlib.sha256(b'otro').hexdigest()
    b = ac.congelar_instantanea(fuentes, tmp_path / 'ap', contexto=otro, versiones=VERSIONES)
    c = ac.congelar_instantanea(fuentes, tmp_path / 'ap', contexto=CTX, versiones={**VERSIONES, 'codigo': 'x'})
    assert len({a['snapshot_id'], b['snapshot_id'], c['snapshot_id']}) == 3


def test_fuente_obligatoria_ausente_bloquea_y_se_anota(tmp_path):
    """050:RF-8: sin una fuente obligatoria no hay instantánea, y el bloqueo queda escrito."""
    fuentes = {**_fuentes(tmp_path), 'cabeceras': tmp_path / 'no_existe.xlsx'}
    with pytest.raises(ac.CicloBloqueado, match='cabeceras'):
        ac.congelar_instantanea(fuentes, tmp_path / 'ap', contexto=CTX, versiones=VERSIONES)
    fila = json.loads((tmp_path / 'ap' / 'bloqueos.jsonl').read_text(encoding='utf-8').splitlines()[-1])
    assert fila['estado'] == 'bloqueado' and 'cabeceras' in fila['motivos'][0]
    assert not (tmp_path / 'ap' / 'instantaneas').exists()


def test_contexto_sin_huella_bloquea(tmp_path):
    """050:RF-1: sin contexto 043 no se congela nada."""
    with pytest.raises(ac.CicloBloqueado, match='contexto'):
        ac.congelar_instantanea(_fuentes(tmp_path), tmp_path / 'ap', contexto='sin-huella', versiones=VERSIONES)


def test_contexto_de_ciclo_conserva_proyectos_y_es_invariante_al_orden(tmp_path):
    """050:RF-1 — varios proyectos conservan sus contextos individuales."""
    otro = hashlib.sha256(b'otro-contexto').hexdigest()
    a = ac.crear_contexto_ciclo({'carpeta/P1': CTX, 'carpeta/P2': otro})
    b = ac.crear_contexto_ciclo({'carpeta/P2': otro, 'carpeta/P1': CTX})
    assert a == b
    inst = ac.congelar_instantanea(_fuentes(tmp_path), tmp_path / 'ap', contexto=a, versiones=VERSIONES)
    assert inst['contexto_hash'] == a['contexto_hash']
    assert inst['contextos'] == a['proyectos']
    ruta = Path(inst['ruta']) / 'manifiesto.json'
    dato = json.loads(ruta.read_text(encoding='utf-8'))
    dato['contextos']['carpeta/P2'] = CTX
    ruta.write_text(json.dumps(dato), encoding='utf-8')
    with pytest.raises(ac.CicloBloqueado, match='contexto'):
        ac.verificar_instantanea(inst['ruta'])


def test_contexto_de_ciclo_no_se_puede_retirar_del_manifiesto(tmp_path):
    """050:RF-1 — quitar el mapa no convierte una captura múltiple en una heredada."""
    inst = ac.congelar_instantanea(_fuentes(tmp_path), tmp_path / 'ap',
        contexto=ac.crear_contexto_ciclo({'P1': CTX}), versiones=VERSIONES)
    ruta = Path(inst['ruta']) / 'manifiesto.json'
    dato = json.loads(ruta.read_text(encoding='utf-8'))
    del dato['contextos']
    ruta.write_text(json.dumps(dato), encoding='utf-8')
    with pytest.raises(ac.CicloBloqueado, match='contexto'):
        ac.verificar_instantanea(inst['ruta'])


@pytest.mark.parametrize('proyectos', [{}, {'': CTX}, {' P1': CTX}, {'P1': 'incompleta'}])
def test_contexto_de_ciclo_rechaza_identidad_incompleta(proyectos):
    """050:RF-1, 050:RF-8 — no se inventan identidades de proyecto ni huellas."""
    with pytest.raises(ac.CicloBloqueado):
        ac.crear_contexto_ciclo(proyectos)


def test_observacion_comun_sin_familia_y_con_fecha_canonica():
    """050:RF-2 — la misma observación tiene identidad común entre familias."""
    fuente = hashlib.sha256(b'fuente-medida').hexdigest()
    a = ac.crear_observacion_id(CTX, fuente, 'fila/17', '2026-07-20T11:15:00-05:00')
    b = ac.crear_observacion_id(CTX, fuente, 'fila/17', '2026-07-20T16:15:00+00:00')
    assert a == b and len(a) == 64
    assert a != ac.crear_observacion_id(CTX, fuente, 'fila/18', '2026-07-20T16:15:00Z')
    assert a != ac.crear_observacion_id(fuente, fuente, 'fila/17', '2026-07-20T16:15:00Z')


@pytest.mark.parametrize('campo,valor', [('contexto_hash', ''), ('fuente_hash', 'x'),
    ('registro_id', ' '), ('instante', '2026-07-20T11:15:00'), ('instante', 'desconocido')])
def test_observacion_sin_procedencia_no_recibe_identidad(campo, valor):
    """050:RF-2, 050:RF-8 — no se presume zona horaria ni procedencia."""
    datos = dict(contexto_hash=CTX, fuente_hash=CTX, registro_id='fila/17', instante='2026-07-20T16:15:00Z')
    datos[campo] = valor
    with pytest.raises(ac.CicloBloqueado):
        ac.crear_observacion_id(**datos)


def test_cambio_de_la_fuente_durante_la_copia_bloquea(tmp_path, monkeypatch):
    """050:RF-1, 050:RF-8: un dato que llega a mitad de la copia no se mezcla con la instantánea."""
    fuentes = _fuentes(tmp_path)
    original = ac.shutil.copy2

    def copiar_y_tocar(origen, destino):
        original(origen, destino)
        Path(fuentes['dataset']).write_text('{"tarea": "otra"}\n', encoding='utf-8')
    monkeypatch.setattr(ac.shutil, 'copy2', copiar_y_tocar)
    with pytest.raises(ac.CicloBloqueado, match='cambiadas'):
        ac.congelar_instantanea(fuentes, tmp_path / 'ap', contexto=CTX, versiones=VERSIONES)
    assert not list((tmp_path / 'ap' / 'instantaneas').glob('*'))


def test_copia_tocada_despues_no_verifica(tmp_path):
    """050:RF-1: una copia modificada tras congelar se detecta al releer."""
    inst = _instantanea(tmp_path)
    ac.ruta_de(inst, 'dataset').write_text('manipulado', encoding='utf-8')
    with pytest.raises(ac.CicloBloqueado, match='cambió'):
        ac.verificar_instantanea(inst['ruta'])


# --------------------------------------------------------------------------- T2

def _m(inst, obs, familia, particion='entrenamiento', origen='observado', etiqueta='medicion'):
    return ac.Muestra(obs, familia, inst['snapshot_id'], origen, etiqueta, particion)


def test_vistas_comparten_particion_por_observacion(tmp_path):
    """050:RF-2: la partición es de la observación; distinta entre familias es una fuga."""
    inst = _instantanea(tmp_path)
    vistas = ac.preparar_vistas(inst, [_m(inst, 'o1', 'pinn'), _m(inst, 'o1', 'transformer', etiqueta='operador'),
                                      _m(inst, 'o2', 'gru', 'prueba')])
    assert vistas['resumen'] == {'gru': {'prueba': 1}, 'pinn': {'entrenamiento': 1},
                                 'transformer': {'entrenamiento': 1}}
    with pytest.raises(ac.CicloBloqueado, match='fuga'):
        ac.preparar_vistas(inst, [_m(inst, 'o1', 'pinn', 'prueba'), _m(inst, 'o1', 'transformer', etiqueta='operador')])


def test_muestra_de_otra_instantanea_no_entra(tmp_path):
    """050:RF-2: una muestra de otra instantánea no se mezcla."""
    inst = _instantanea(tmp_path)
    ajena = ac.Muestra('o1', 'pinn', hashlib.sha256(b'otra').hexdigest(), 'observado', 'medicion', 'entrenamiento')
    with pytest.raises(ac.CicloBloqueado, match='otra instantánea'):
        ac.preparar_vistas(inst, [ajena])


def test_duplicado_identico_no_aumenta_peso_y_colision_bloquea(tmp_path):
    """050:RF-2, 050:RF-9 — un duplicado no es una observación nueva."""
    from dataclasses import replace
    inst = _instantanea(tmp_path)
    m = _m(inst, 'o1', 'transformer', etiqueta='operador')
    vistas = ac.preparar_vistas(inst, [m, m])
    assert vistas['resumen']['transformer']['entrenamiento'] == 1
    assert vistas['duplicadas'] == 1
    with pytest.raises(ac.CicloBloqueado, match='colisión'):
        ac.preparar_vistas(inst, [m, replace(m, etiqueta='maestro')])


def test_replay_se_deduplica_y_completa_otra_familia(tmp_path):
    """050:RF-2, 050:RF-6 — replay válido de otra familia conserva la observación común."""
    inst = _instantanea(tmp_path)
    viejo = hashlib.sha256(b'vieja').hexdigest()
    h = ac.Muestra('o1', 'pinn', viejo, 'observado', 'medicion', 'entrenamiento')
    vistas = ac.preparar_vistas(inst, [_m(inst, 'o1', 'transformer', etiqueta='operador')], historicas=[h, h])
    assert vistas['resumen']['pinn'] == {'entrenamiento': 1}
    assert vistas['replay'] == 1 and vistas['duplicadas'] == 1


def test_replay_no_oculta_colision_de_registro(tmp_path):
    """050:RF-6, 050:RF-9 — una etiqueta contradictoria no se oculta como repetida."""
    from dataclasses import replace
    inst = _instantanea(tmp_path)
    m = _m(inst, 'o1', 'transformer', etiqueta='operador')
    vieja = replace(m, snapshot_id=hashlib.sha256(b'vieja').hexdigest())
    assert ac.preparar_vistas(inst, [m], historicas=[vieja])['replay'] == 0
    with pytest.raises(ac.CicloBloqueado, match='colisión'):
        ac.preparar_vistas(inst, [m], historicas=[replace(vieja, etiqueta='maestro')])


def test_muestra_de_contexto_no_declarado_en_ciclo_bloquea(tmp_path):
    """050:RF-1, 050:RF-2 — cada muestra declara un contexto miembro del ciclo."""
    from dataclasses import replace
    inst = ac.congelar_instantanea(_fuentes(tmp_path), tmp_path / 'ap',
        contexto=ac.crear_contexto_ciclo({'P1': CTX}), versiones=VERSIONES)
    m = replace(_m(inst, 'o1', 'pinn'), contexto=CTX)
    assert ac.preparar_vistas(inst, [m])['resumen']['pinn'] == {'entrenamiento': 1}
    with pytest.raises(ac.CicloBloqueado, match='contexto'):
        ac.preparar_vistas(inst, [replace(m, contexto='')])


@pytest.mark.parametrize('etiqueta, origen', [('llm', 'observado'), ('prediccion', 'simulado_nativo'),
                                              ('maestro', 'observado'), ('medicion', 'redactado')])
def test_etiqueta_electrica_inventada_va_a_cuarentena(tmp_path, etiqueta, origen):
    """050:RF-3: lo que dice un LLM o un modelo no es verdad eléctrica observada."""
    inst = _instantanea(tmp_path)
    vistas = ac.preparar_vistas(inst, [_m(inst, 'o1', 'pinn', etiqueta=etiqueta, origen=origen)])
    assert 'pinn' not in vistas['vistas'] and vistas['cuarentena'][0]['familia'] == 'pinn'


def test_replay_sin_fuga_de_prueba(tmp_path):
    """050:RF-6: el replay añade entrenamiento histórico; nunca una prueba vigente ni histórica."""
    inst = _instantanea(tmp_path)
    viejo = hashlib.sha256(b'vieja').hexdigest()
    historicas = [ac.Muestra('h1', 'pinn', viejo, 'observado', 'medicion', 'entrenamiento'),
                  ac.Muestra('h2', 'pinn', viejo, 'observado', 'medicion', 'prueba')]
    vistas = ac.preparar_vistas(inst, [_m(inst, 'o1', 'pinn', 'prueba')], historicas=historicas)
    assert vistas['replay'] == 1 and vistas['resumen']['pinn'] == {'prueba': 1, 'entrenamiento': 1}
    reciclada = [ac.Muestra('o1', 'pinn', viejo, 'observado', 'medicion', 'entrenamiento')]
    with pytest.raises(ac.CicloBloqueado, match='prueba vigente'):
        ac.preparar_vistas(inst, [_m(inst, 'o1', 'pinn', 'prueba')], historicas=reciclada)


def test_propuestas_propias_necesitan_contraste_y_se_conservan_las_rechazadas():
    """050:RF-9: procedencia, consistencia y contraste independiente; lo rechazado queda con su motivo."""
    buena = {'id': 'p1', 'autor': 'pinn', 'procedencia': 'episodio e1', 'consistente': True,
             'contraste': {'fuente': 'motor_nativo'}}
    autorrecompensa = {**buena, 'id': 'p2', 'recompensa_de': 'pinn'}
    sin_contraste = {**buena, 'id': 'p3', 'contraste': {'fuente': 'pinn'}}
    r = ac.validar_propuestas([buena, autorrecompensa, sin_contraste])
    assert [p['id'] for p in r['aceptadas']] == ['p1']
    assert {p['id'] for p in r['rechazadas']} == {'p2', 'p3'} and all(p['motivos'] for p in r['rechazadas'])


# --------------------------------------------------------------------------- T3

def _candidato(reg: RegistroModelo, familia: str, *, aprobado=True, reabierto=True, n=0) -> str:
    return reg.registrar_candidato(
        familia, model_manifest={'n': n}, dataset_manifest={'familia': familia}, metrics={'m': 1},
        decision={'status': 'PROMOVIDO' if aprobado and reabierto else 'RECHAZADO',
                  'gates': {'approved': aprobado}},
        smoke_reload={'ok': reabierto})['candidate_id']


def _etapa(nombre, cid, llamadas):
    def run():
        llamadas.append(nombre)
        return {'status': 'PROMOVIDO', 'candidate_id': cid, 'training_completed': True}
    return TrainingStage(nombre, run, uses_gpu=False)


PRES = ac.Presupuesto(tiempo_s=3600, memoria_gib=1, usa_gpu=False)


def test_ciclo_unico_idempotente(tmp_path):
    """050:RF-4: la misma instantánea con las mismas familias y política se ejecuta una sola vez."""
    inst, reg, llamadas = _instantanea(tmp_path), RegistroModelo(tmp_path / 'reg'), []
    etapas = [_etapa('pinn', _candidato(reg, 'pinn'), llamadas), _etapa('transformer', _candidato(reg, 'transformer'), llamadas)]
    a = ac.ejecutar_ciclo(tmp_path / 'ap', inst, etapas, politica_hash='p' * 64, presupuesto=PRES, registro=reg)
    b = ac.ejecutar_ciclo(tmp_path / 'ap', inst, etapas, politica_hash='p' * 64, presupuesto=PRES, registro=reg)
    assert a['estado'] == 'terminado' and b['repetido'] and b['clave'] == a['clave']
    assert llamadas == ['transformer', 'pinn'] and set(a['candidatos']) == {'pinn', 'transformer'}


def test_ciclo_cpu_excluye_otro_arranque_durante_su_preflight(tmp_path):
    """050:RF-4 — dos clientes concurrentes no ejecutan dos veces la misma captura CPU."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    inst, reg, llamadas = _instantanea(tmp_path), RegistroModelo(tmp_path / 'reg'), []
    etapas = [_etapa('pinn', _candidato(reg, 'pinn'), llamadas)]
    entered, release = Event(), Event()

    def preflight():
        entered.set()
        assert release.wait(10), 'el segundo cliente no devolvió el control'
        return False

    def iniciar(**kwargs):
        return ac.ejecutar_ciclo(tmp_path / 'ap', inst, etapas, politica_hash=CTX,
                                presupuesto=PRES, registro=reg, **kwargs)

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(iniciar, operador_ocupado=preflight)
        try:
            assert entered.wait(10)
            second = iniciar()
        finally:
            release.set()
        completed = first.result(timeout=15)
    assert second['estado'] == 'en_curso' and second['repetido']
    assert completed['estado'] == 'terminado'
    assert llamadas == ['pinn']


def test_ciclo_guarda_fecha_del_proceso_y_token_en_su_marca(tmp_path):
    """050:RF-4/10 — un PID reutilizado no identifica al dueño del entrenamiento anterior."""
    import os
    import psutil

    inst, reg = _instantanea(tmp_path), RegistroModelo(tmp_path / 'reg')
    cid = _candidato(reg, 'pinn')
    key = ac.clave_ciclo(inst['snapshot_id'], ['pinn'], CTX)
    marker = tmp_path / 'ap/ciclos' / key / 'en_curso'

    def run():
        owner = json.loads(marker.read_text(encoding='utf-8'))
        assert isinstance(owner, dict)
        assert owner['pid'] == os.getpid() and owner['creado'] == psutil.Process().create_time()
        assert len(owner['token']) == 32
        return {'status': 'PROMOVIDO', 'candidate_id': cid, 'training_completed': True}

    result = ac.ejecutar_ciclo(tmp_path / 'ap', inst, [TrainingStage('pinn', run, uses_gpu=False)],
                              politica_hash=CTX, presupuesto=PRES, registro=reg)
    assert result['estado'] == 'terminado', result
    assert not marker.exists()


def test_estado_interrumpido_si_el_pid_corresponde_a_otro_inicio(tmp_path):
    """050:RF-4/10 — la consulta distingue un PID vivo de la identidad que dejó el diario."""
    import os
    import psutil

    folder = tmp_path / 'ciclos' / ('a' * 64); folder.mkdir(parents=True)
    diary = folder / 'ciclo.json'
    diary.write_text(json.dumps({'clave':'a'*64, 'snapshot_id':'b'*64, 'estado':'en_curso',
                                 'inicio':'2026-11-08T05:00:00Z', 'motivos':[]}), encoding='utf-8')
    marker = folder / 'en_curso'
    marker.write_text(json.dumps({'schema':'convertersmartgrid-cycle-owner-v1', 'pid':os.getpid(),
                                  'creado':psutil.Process().create_time()-60, 'token':'f'*32}), encoding='utf-8')
    original = {p:p.read_bytes() for p in (diary,marker)}
    state = ac.estado_aprendizaje(tmp_path)
    assert state['ultimo_ciclo']['estado'] == 'interrumpido'
    assert state['ultimo_ciclo']['estado_registrado'] == 'en_curso'
    assert {p:p.read_bytes() for p in original} == original


def test_marcador_ilegible_bloquea_sin_anunciar_ciclo_en_marcha(tmp_path):
    """050:RF-4/10 — un dueño ilegible se conserva y no se presenta como trabajo ejecutándose."""
    inst, reg, calls = _instantanea(tmp_path), RegistroModelo(tmp_path / 'reg'), []
    stages = [_etapa('pinn', _candidato(reg,'pinn'), calls)]
    key = ac.clave_ciclo(inst['snapshot_id'], ['pinn'], CTX)
    marker = tmp_path/'ap/ciclos'/key/'en_curso';marker.parent.mkdir(parents=True)
    marker.write_bytes(b'{ilegible')
    result = ac.ejecutar_ciclo(tmp_path/'ap',inst,stages,politica_hash=CTX,presupuesto=PRES,registro=reg)
    assert result['estado']=='bloqueado' and result['motivos']
    assert marker.read_bytes()==b'{ilegible' and calls==[]


def test_ciclo_reanuda_despues_de_muerte_real_del_proceso(tmp_path):
    """050:RF-4/10 — morir sin finally libera la guardia OS y conserva el diario para reanudar."""
    import subprocess
    import sys

    inst, reg, calls = _instantanea(tmp_path), RegistroModelo(tmp_path/'reg'), []
    cid = _candidato(reg,'pinn');root=tmp_path/'ap'
    script = '''import sys,os
sys.path.insert(0,sys.argv[1])
from convertersmartgrid import aprendizaje_continuo as ac
from convertersmartgrid.model_registry import RegistroModelo
from convertersmartgrid.training_coordinator import TrainingStage
inst=ac.verificar_instantanea(sys.argv[3])
ac.ejecutar_ciclo(sys.argv[2],inst,[TrainingStage('pinn',lambda:os._exit(73),uses_gpu=False)],
    politica_hash=sys.argv[5],presupuesto=ac.Presupuesto(tiempo_s=3600,memoria_gib=1,usa_gpu=False),
    registro=RegistroModelo(sys.argv[4]))
'''
    child = subprocess.run([sys.executable,'-B','-c',script,str(RAIZ/'src'),str(root),str(inst['ruta']),
                            str(tmp_path/'reg'),CTX],capture_output=True,timeout=20)
    assert child.returncode==73,child.stderr.decode('utf-8','replace')
    key=ac.clave_ciclo(inst['snapshot_id'],['pinn'],CTX);marker=root/'ciclos'/key/'en_curso'
    abandoned=marker.read_bytes()
    assert ac.estado_aprendizaje(root)['ultimo_ciclo']['estado']=='interrumpido'
    assert marker.read_bytes()==abandoned
    result=ac.ejecutar_ciclo(root,inst,[_etapa('pinn',cid,calls)],politica_hash=CTX,presupuesto=PRES,registro=reg)
    assert result['estado']=='terminado' and calls==['pinn']
    assert not marker.exists() and (marker.parent/'en_curso.guard').is_file()


def test_ciclo_no_da_por_inmutable_una_copia_modificada_por_trabajador(tmp_path):
    """050:RF-1, 050:RF-8 — también se verifica la instantánea al terminar las etapas."""
    inst, reg = _instantanea(tmp_path), RegistroModelo(tmp_path / 'reg')
    cid = _candidato(reg, 'pinn')

    def run():
        ac.ruta_de(inst, 'dataset').write_text('alterado', encoding='utf-8')
        return {'status': 'PROMOVIDO', 'candidate_id': cid, 'training_completed': True}

    r = ac.ejecutar_ciclo(tmp_path / 'ap', inst, [TrainingStage('pinn', run, uses_gpu=False)],
        politica_hash=CTX, presupuesto=PRES, registro=reg)
    assert r['estado'] == 'bloqueado' and any('instantánea' in m for m in r['motivos'])


def test_ciclo_reintenta_preflight_si_se_recupera_memoria(tmp_path):
    """050:RF-4, 050:RF-8 — la falta temporal de memoria no sella el ciclo sin entrenar."""
    inst, reg, llamadas = _instantanea(tmp_path), RegistroModelo(tmp_path / 'reg'), []
    etapas = [_etapa('pinn', _candidato(reg, 'pinn'), llamadas)]
    r = ac.ejecutar_ciclo(tmp_path / 'ap', inst, etapas, politica_hash=CTX, presupuesto=PRES,
        registro=reg, memoria_libre_gib=lambda: 0.1)
    assert r['estado'] == 'bloqueado' and llamadas == []
    r = ac.ejecutar_ciclo(tmp_path / 'ap', inst, etapas, politica_hash=CTX, presupuesto=PRES,
        registro=reg, memoria_libre_gib=lambda: 2)
    assert r['estado'] == 'terminado' and llamadas == ['pinn']


def test_operador_tiene_prioridad_y_presupuestos(tmp_path):
    """050:RF-4: con trabajos del operador el ciclo espera; sin memoria o con licencia nativa, se bloquea."""
    inst, reg = _instantanea(tmp_path), RegistroModelo(tmp_path / 'reg')
    etapas = [_etapa('pinn', _candidato(reg, 'pinn'), [])]
    r = ac.ejecutar_ciclo(tmp_path / 'ap', inst, etapas, politica_hash='a' * 64, presupuesto=PRES,
                          registro=reg, operador_ocupado=lambda: True)
    assert r['estado'] == 'pospuesto'
    r = ac.ejecutar_ciclo(tmp_path / 'ap', inst, etapas, politica_hash='b' * 64, presupuesto=PRES,
                          registro=reg, memoria_libre_gib=lambda: 0.1)
    assert r['estado'] == 'bloqueado' and 'memoria' in r['motivos'][0]
    nativa = ac.Presupuesto(3600, 1, False, usa_licencia_nativa=True)
    r = ac.ejecutar_ciclo(tmp_path / 'ap', inst, etapas, politica_hash='c' * 64, presupuesto=nativa, registro=reg)
    assert r['estado'] == 'bloqueado'
    with pytest.raises(ValueError):
        ac.Presupuesto(0, 1, False)


def test_tiempo_agotado_bloquea_sin_ok_falso(tmp_path):
    """050:RF-4, 050:RF-8: pasado el presupuesto de tiempo, las etapas siguientes no corren."""
    inst, reg, llamadas = _instantanea(tmp_path), RegistroModelo(tmp_path / 'reg'), []
    reloj = iter([0.0, 0.0, 10_000.0, 10_000.0])
    etapas = [_etapa('transformer', _candidato(reg, 'transformer'), llamadas), _etapa('pinn', _candidato(reg, 'pinn'), llamadas)]
    r = ac.ejecutar_ciclo(tmp_path / 'ap', inst, etapas, politica_hash='t' * 64, presupuesto=PRES,
                          registro=reg, reloj=lambda: next(reloj))
    assert llamadas == ['transformer'] and r['estado'] == 'bloqueado'
    assert any('tiempo' in m for m in r['motivos'])


@pytest.mark.parametrize('clave_ajena',['absoluta','../../ajeno','invalida'])
def test_cancelar_ciclo_rechaza_identidad_ajena_sin_escribir(tmp_path,clave_ajena):
    """050:RF-4/8 — una clave no puede nombrar un directorio ajeno al ciclo."""
    ajeno=tmp_path/'ajeno';ajeno.mkdir();(ajeno/'en_curso').write_text('testigo',encoding='utf-8')
    clave=str(ajeno) if clave_ajena=='absoluta' else clave_ajena
    with pytest.raises(ac.CicloBloqueado,match='ciclo'):
        ac.cancelar_ciclo(tmp_path/'ap',clave)
    assert not (ajeno/'cancelar').exists()
    assert (ajeno/'en_curso').read_text(encoding='utf-8')=='testigo'


def test_cancelacion_repetida_conserva_primer_pedido(tmp_path,monkeypatch):
    """050:RF-4 — pedir dos veces cancelar no reescribe el primer marcador."""
    clave='a'*64;p=tmp_path/'ciclos'/clave;p.mkdir(parents=True)
    (p/'en_curso').write_text('activo',encoding='utf-8')
    monkeypatch.setattr(ac,'_ahora',lambda:'2026-11-08T05:00:00+00:00')
    assert ac.cancelar_ciclo(tmp_path,clave)
    anterior=(p/'cancelar').read_bytes()
    monkeypatch.setattr(ac,'_ahora',lambda:'2026-11-08T06:00:00+00:00')
    assert ac.cancelar_ciclo(tmp_path,clave)
    assert (p/'cancelar').read_bytes()==anterior


def test_cli_cancelar_no_declara_terminacion_del_ciclo(tmp_path):
    """050:RF-4/10 — la CLI también distingue solicitud aceptada y ciclo terminado."""
    import os
    import subprocess
    import sys
    clave = 'a' * 64
    carpeta = tmp_path / 'ciclos' / clave
    carpeta.mkdir(parents=True)
    (carpeta / 'en_curso').write_text(str(os.getpid()), encoding='utf-8')
    proceso = subprocess.run([sys.executable, '-B', str(RAIZ / 'tools/aprendizaje_continuo.py'),
        '--raiz', str(tmp_path), 'cancelar', '--clave', clave], capture_output=True, text=True)
    assert proceso.returncode == 0, proceso.stderr
    respuesta = json.loads(proceso.stdout)
    assert respuesta.get('solicitada') is True
    assert 'cancelado' not in respuesta
    assert (carpeta / 'en_curso').is_file()


def test_estado_no_muestra_ciclo_de_otro_directorio(tmp_path):
    """050:RF-4/8/10 — un diario con otra clave no dirige un control al ciclo equivocado."""
    p=tmp_path/'ciclos'/('a'*64);p.mkdir(parents=True)
    (p/'ciclo.json').write_text(json.dumps({'clave':'b'*64,'snapshot_id':'c'*64,'estado':'en_curso'}),encoding='utf-8')
    e=ac.estado_aprendizaje(tmp_path)
    assert e['fases']['preparacion']['estado']=='bloqueado'
    assert e['ultimo_ciclo']['estado']=='ilegible'


@pytest.mark.parametrize('ultima_etapa', [False, True])
def test_ciclo_visible_mientras_trabaja_y_cancelable_desde_estado(tmp_path, ultima_etapa):
    """050:RF-4/10 — el ciclo real publica su diario antes de la etapa, también al cancelar la última."""
    inst, reg, llamadas = _instantanea(tmp_path), RegistroModelo(tmp_path / 'reg'), []
    cid = _candidato(reg, 'transformer')

    def primera():
        llamadas.append('transformer')
        estado = ac.estado_aprendizaje(tmp_path / 'ap')
        assert estado['ultimo_ciclo'] is not None, 'el ciclo real no es visible durante su etapa'
        assert estado['ultimo_ciclo']['estado'] == 'en_curso'
        assert estado['fases']['entrenamiento']['estado'] == 'en_curso'
        assert ac.cancelar_ciclo(tmp_path / 'ap', estado['ultimo_ciclo']['clave'])
        assert ac.estado_aprendizaje(tmp_path / 'ap')['ultimo_ciclo']['cancelacion_solicitada']
        return {'status': 'PROMOVIDO', 'candidate_id': cid, 'training_completed': True}

    etapas = [TrainingStage('transformer', primera, uses_gpu=False)]
    if not ultima_etapa:
        etapas.append(_etapa('pinn', _candidato(reg, 'pinn'), llamadas))
    r = ac.ejecutar_ciclo(tmp_path / 'ap', inst, etapas, politica_hash=CTX, presupuesto=PRES, registro=reg)
    assert r['estado'] == 'cancelado', r
    assert llamadas == ['transformer']
    assert ac.estado_aprendizaje(tmp_path / 'ap')['ultimo_ciclo']['estado'] == 'cancelado'
    assert ac.conjunto_activo(tmp_path / 'ap') is None


def test_cancelacion_entre_etapas(tmp_path):
    """050:RF-4: el operador cancela; la etapa siguiente no empieza y el ciclo queda cancelado."""
    inst, reg, llamadas = _instantanea(tmp_path), RegistroModelo(tmp_path / 'reg'), []
    clave = ac.clave_ciclo(inst['snapshot_id'], ['transformer', 'pinn'], 'k' * 64)

    def y_cancela():
        llamadas.append('transformer')
        assert ac.cancelar_ciclo(tmp_path / 'ap', clave)
        return {'status': 'RECHAZADO', 'candidate_id': _candidato(reg, 'transformer'), 'training_completed': True}
    etapas = [TrainingStage('transformer', y_cancela, uses_gpu=False), _etapa('pinn', _candidato(reg, 'pinn'), llamadas)]
    r = ac.ejecutar_ciclo(tmp_path / 'ap', inst, etapas, politica_hash='k' * 64, presupuesto=PRES, registro=reg)
    assert r['estado'] == 'cancelado' and llamadas == ['transformer']


def test_etapa_sin_informe_o_adaptador_ausente_bloquea(tmp_path):
    """050:RF-8: una etapa que termina sin candidato, o falla, deja el ciclo bloqueado con su motivo."""
    inst, reg = _instantanea(tmp_path), RegistroModelo(tmp_path / 'reg')

    def sin_adaptador():
        raise ValueError('adaptador NHITS ausente')
    etapas = [TrainingStage('gru', sin_adaptador, uses_gpu=False),
              TrainingStage('pinn', lambda: {'status': 'RECHAZADO'}, uses_gpu=False)]
    r = ac.ejecutar_ciclo(tmp_path / 'ap', inst, etapas, politica_hash='s' * 64, presupuesto=PRES, registro=reg)
    assert r['estado'] == 'bloqueado'
    assert any('NHITS' in m for m in r['motivos']) and any('sin candidato' in m for m in r['motivos'])


def test_promocion_individual_durante_el_ciclo_bloquea(tmp_path):
    """050:RF-4, 050:RF-7: si una etapa cambia por su cuenta el modelo en uso, el conjunto no se publica."""
    inst, reg = _instantanea(tmp_path), RegistroModelo(tmp_path / 'reg')
    cid = _candidato(reg, 'pinn')

    def promueve_suelta():
        reg.promover('pinn', cid)
        return {'status': 'PROMOVIDO', 'candidate_id': cid, 'training_completed': True}
    r = ac.ejecutar_ciclo(tmp_path / 'ap', inst, [TrainingStage('pinn', promueve_suelta, uses_gpu=False)],
                          politica_hash='i' * 64, presupuesto=PRES, registro=reg)
    assert r['estado'] == 'bloqueado' and 'promoción individual' in r['motivos'][0]
    pub = ac.publicar_conjunto(tmp_path / 'ap', reg, r, retencion={'pinn': {'retiene': True}},
                               conjunta={'aprobado': True}, obligatorias=['pinn'])
    assert pub['publicado'] is False


def test_decidir_ciclo_por_datos_o_deriva():
    """050:RF-4: datos nuevos sobre el mínimo de la 027, o deriva; la misma instantánea no repite."""
    assert ac.decidir_ciclo(datos_nuevos=5, deriva=False, minimo=10, ultimo_snapshot=None, snapshot_actual='a')['toca'] is False
    assert ac.decidir_ciclo(datos_nuevos=12, deriva=False, minimo=10, ultimo_snapshot=None, snapshot_actual='a')['toca']
    assert ac.decidir_ciclo(datos_nuevos=0, deriva=True, minimo=10, ultimo_snapshot=None, snapshot_actual='a')['toca']
    assert ac.decidir_ciclo(datos_nuevos=99, deriva=True, minimo=10, ultimo_snapshot='a', snapshot_actual='a')['toca'] is False


def test_vigilancia_lanza_un_solo_ciclo(monkeypatch, tmp_path):
    """050:RF-4: gemelo y asistente con datos nuevos lanzan un ciclo, no dos entrenamientos sueltos."""
    from convertersmartgrid.asistente import almacen, vigilancia
    monkeypatch.setattr(almacen, 'raiz', lambda: tmp_path)
    ciclos, sueltos = [], []
    v = vigilancia.Vigilante(listar_trabajos=lambda: [], reintentar=lambda _j: None,
                             entrenar_gemelo=lambda: sueltos.append('g'),
                             entrenar_asistente=lambda: sueltos.append('a'),
                             contar_nuevos=lambda: (30, 40), repo=tmp_path, ciclo=ciclos.append)
    monkeypatch.setattr(vigilancia, 'toca_suite', lambda *a, **k: False)
    v.tic(ahora=0.0)
    v.tic(ahora=60.0)
    assert len(ciclos) == 1 and len(ciclos[0]) == 2 and sueltos == []


def test_aportes_de_cada_version_en_una_propuesta():
    """050:RF-5: cada aporte cita su familia y su candidato del conjunto; la validación nativa, su evidencia."""
    conjunto = {'conjunto_id': 'c1', 'miembros': {'transformer': 't1', 'gru': 'g1', 'pinn': 'p1',
                                                  'evolutivos': 'e1', 'embeddings': 'r1'}}
    aportes = {'interpretacion': {'familia': 'transformer', 'candidate_id': 't1'},
               'pronostico': {'familia': 'gru', 'candidate_id': 'g1'},
               'estimacion_fisica': {'familia': 'pinn', 'candidate_id': 'p1'},
               'alternativas': {'familia': 'evolutivos', 'candidate_id': 'e1'},
               'evidencia': {'familia': 'embeddings', 'candidate_id': 'r1'}}
    r = ac.registrar_aportes('prop1', aportes, conjunto)
    assert r['completa'] is False and r['faltan'] == ['validacion_nativa']
    r = ac.registrar_aportes('prop1', {**aportes, 'validacion_nativa': {'evidencia': 'job/abc'}}, conjunto)
    assert r['completa'] and r['aportes']['pronostico'] == {'familia': 'gru', 'candidate_id': 'g1'}
    with pytest.raises(ac.CicloBloqueado):
        ac.registrar_aportes('prop2', {**aportes, 'pronostico': {'familia': 'gru', 'candidate_id': 'otro'}}, conjunto)


# --------------------------------------------------------------------------- T4

@pytest.mark.parametrize('contenido',['{incompleto','[]','{"estado":"en_curso","clave":"a"}'])
def test_estado_no_acredita_preparacion_con_diario_ilegible(tmp_path,contenido):
    """050:RF-8/10 — una escritura incompleta no tumba la vista ni acredita preparación."""
    ruta=tmp_path/'ciclos'/'corte'/'ciclo.json';ruta.parent.mkdir(parents=True)
    ruta.write_text(contenido,encoding='utf-8')
    e=ac.estado_aprendizaje(tmp_path)
    assert e['ultimo_ciclo']['estado']=='ilegible'
    assert e['fases']['preparacion']['estado']=='bloqueado'
    assert e['fases']['aceptacion_nativa']['estado']=='pendiente'


def test_estado_expone_bloqueos_ilegibles_y_conjunto_corrupto(tmp_path):
    """050:RF-8/10 — se conserva el daño y se muestra; no se anuncia un conjunto activo."""
    p=tmp_path/'conjuntos'/'activo.json';p.parent.mkdir()
    p.write_text('{"conjunto_id":"inexistente"}',encoding='utf-8')
    (tmp_path/'bloqueos.jsonl').write_text('{roto\n'+json.dumps({'etapa':'preflight','motivos':['sin memoria']})+'\n',encoding='utf-8')
    e=ac.estado_aprendizaje(tmp_path)
    assert e['conjunto_activo']['error']
    assert e['fases']['activacion']['estado']=='bloqueado'
    assert any('ilegible' in str(b) for b in e['bloqueos'])
    assert e['bloqueos'][-1]['motivos']==['sin memoria']
    assert p.read_text(encoding='utf-8')=='{"conjunto_id":"inexistente"}'


def test_estado_no_oculta_diario_roto_al_haber_ciclo_con_fecha(tmp_path):
    """050:RF-8/10 — una entrada sin fecha por daño no desaparece tras ordenar las legibles."""
    import os
    for nombre,contenido in [('b'*64,json.dumps({'snapshot_id':'a'*64,'clave':'b'*64,
            'inicio':'2026-11-07T12:00:00Z','estado':'en_curso'})),('ilegible','{roto')]:
        p=tmp_path/'ciclos'/nombre/'ciclo.json';p.parent.mkdir(parents=True)
        p.write_text(contenido,encoding='utf-8')
        if nombre == 'b'*64:
            (p.parent/'en_curso').write_text(str(os.getpid()),encoding='utf-8')
    e=ac.estado_aprendizaje(tmp_path)
    assert e['ultimo_ciclo']['clave']=='b'*64 and e['ultimo_ciclo']['estado']=='en_curso'
    assert e['fases']['preparacion']['estado']=='bloqueado'
    assert any('diario' in str(b) and 'ilegible' in str(b) for b in e['bloqueos'])


def test_retencion_por_contexto():
    """050:RF-6: un contexto histórico que retrocede, o que falta, no se da por retenido."""
    metricas = {'acierto': 'alta', 'mae_v': 'baja'}
    vigente = {'sistema_a': {'acierto': .9, 'mae_v': .01}, 'sistema_b': {'acierto': .8, 'mae_v': .02}}
    bien = {'sistema_a': {'acierto': .92, 'mae_v': .01}, 'sistema_b': {'acierto': .8, 'mae_v': .015}}
    assert ac.evaluar_retencion(bien, vigente, metricas=metricas)['retiene']
    olvida = {**bien, 'sistema_b': {'acierto': .7, 'mae_v': .015}}
    r = ac.evaluar_retencion(olvida, vigente, metricas=metricas)
    assert not r['retiene'] and 'sistema_b' in r['fallos'][0]
    assert not ac.evaluar_retencion({'sistema_a': bien['sistema_a']}, vigente, metricas=metricas)['retiene']
    assert not ac.evaluar_retencion({}, {}, metricas=metricas)['retiene']


def test_evaluacion_conjunta_empate_no_es_mejora():
    """050:RF-7: un empate o un deterioro no acreditan mejora."""
    m = {'acierto': 'alta', 'mae_v': 'baja'}
    assert not ac.evaluar_conjunto({'acierto': .9, 'mae_v': .01}, {'acierto': .9, 'mae_v': .01}, metricas=m)['aprobado']
    assert not ac.evaluar_conjunto({'acierto': .95, 'mae_v': .02}, {'acierto': .9, 'mae_v': .01}, metricas=m)['aprobado']
    assert ac.evaluar_conjunto({'acierto': .95, 'mae_v': .01}, {'acierto': .9, 'mae_v': .01}, metricas=m)['aprobado']
    assert not ac.evaluar_conjunto({'acierto': float('nan'), 'mae_v': .01}, None, metricas=m)['aprobado']


def _ciclo_terminado(tmp_path, reg, n=0, politica='q'):
    inst = _instantanea(tmp_path) if n == 0 else ac.congelar_instantanea(
        _fuentes_n(tmp_path, n), tmp_path / 'ap', contexto=CTX, versiones=VERSIONES)
    etapas = [_etapa('pinn', _candidato(reg, 'pinn', n=n), []), _etapa('transformer', _candidato(reg, 'transformer', n=n), [])]
    return ac.ejecutar_ciclo(tmp_path / 'ap', inst, etapas, politica_hash=politica * 64, presupuesto=PRES, registro=reg)


def _fuentes_n(tmp_path, n):
    f = _fuentes(tmp_path / f'v{n}')
    (f['twin'] / 'objetos' / f'ep_n{n}.json').write_text('{}', encoding='utf-8')
    return f


def test_publicacion_conjunta_y_reversion_por_relectura(tmp_path):
    """050:RF-7: se publica el conjunto entero con su anterior; revertir se comprueba al releer."""
    reg = RegistroModelo(tmp_path / 'reg')
    ap = tmp_path / 'ap'
    ok = {'pinn': {'retiene': True}, 'transformer': {'retiene': True}}
    c1 = _ciclo_terminado(tmp_path, reg)
    p1 = ac.publicar_conjunto(ap, reg, c1, retencion=ok, conjunta={'aprobado': True}, obligatorias=['pinn', 'transformer'])
    assert p1['publicado'] and ac.version_del_conjunto(ap, 'pinn') == c1['candidatos']['pinn']
    c2 = _ciclo_terminado(tmp_path, reg, n=1)
    p2 = ac.publicar_conjunto(ap, reg, c2, retencion=ok, conjunta={'aprobado': True}, obligatorias=['pinn', 'transformer'])
    assert p2['publicado'] and p2['anterior'] == p1['conjunto']['conjunto_id']
    assert ac.version_del_conjunto(ap, 'pinn') == c2['candidatos']['pinn']
    vuelto = ac.revertir_conjunto(ap)
    assert vuelto['conjunto_id'] == p1['conjunto']['conjunto_id']
    assert ac.version_del_conjunto(ap, 'pinn') == c1['candidatos']['pinn']
    # El registro individual no se tocó: el conjunto no promueve por su cuenta.
    assert reg.activo('pinn') is None


def test_conjunto_resuelve_alias_de_registro_temporal(tmp_path):
    """050:RF-7 — GRU registra pronóstico por clase, sin fingir un registro llamado gru."""
    reg, ap = RegistroModelo(tmp_path / 'reg'), tmp_path / 'ap'
    inst = _instantanea(tmp_path)
    cid = _candidato(reg, 'pronostico_cabecera')
    c = ac.ejecutar_ciclo(ap, inst, [_etapa('gru', cid, [])], politica_hash=CTX, presupuesto=PRES, registro=reg)
    p = ac.publicar_conjunto(ap, reg, c, retencion={'gru': {'retiene': True}},
        conjunta={'aprobado': True}, obligatorias=['gru'])
    assert p['publicado'], p
    m = ac.miembro_del_conjunto(ap, 'gru', registro=reg)
    assert m['candidate_id'] == cid and m['modelo_registro'] == 'pronostico_cabecera'
    assert m['conjunto_id'] == p['conjunto']['conjunto_id']


def test_conjunto_configurado_sin_familia_no_recurre_a_puntero_individual(tmp_path):
    """050:RF-7, 050:RF-8 — ausente del conjunto no significa versión heredada."""
    reg, ap = RegistroModelo(tmp_path / 'reg'), tmp_path / 'ap'
    c = _ciclo_terminado(tmp_path, reg)
    ac.publicar_conjunto(ap, reg, c, retencion={'pinn': {'retiene': True}},
        conjunta={'aprobado': True}, obligatorias=['pinn'])
    with pytest.raises(ac.CicloBloqueado, match='gru'):
        ac.version_del_conjunto(ap, 'gru')


def test_conjunto_sin_obligatorias_no_se_publica(tmp_path):
    """050:RF-7, 050:RF-8 — un conjunto vacío no acredita familias compatibles."""
    reg = RegistroModelo(tmp_path / 'reg')
    c = _ciclo_terminado(tmp_path, reg)
    r = ac.publicar_conjunto(tmp_path / 'ap', reg, c, retencion={}, conjunta={'aprobado': True}, obligatorias=[])
    assert not r['publicado'] and r['motivos']


def test_obligatorias_iterables_no_se_consumen_dos_veces(tmp_path):
    """050:RF-7 — el contrato Iterable conserva todas las familias al escribir."""
    reg = RegistroModelo(tmp_path / 'reg')
    c = _ciclo_terminado(tmp_path, reg)
    r = ac.publicar_conjunto(tmp_path / 'ap', reg, c, retencion={'pinn': {'retiene': True}},
        conjunta={'aprobado': True}, obligatorias=(f for f in ['pinn']))
    assert r['publicado'] and r['conjunto']['miembros'] == {'pinn': c['candidatos']['pinn']}


def test_miembro_modificado_no_se_carga_desde_registro(tmp_path):
    """050:RF-7 — la resolución del conjunto también comprueba los artefactos."""
    reg, ap = RegistroModelo(tmp_path / 'reg'), tmp_path / 'ap'
    c = _ciclo_terminado(tmp_path, reg)
    ac.publicar_conjunto(ap, reg, c, retencion={'pinn': {'retiene': True}},
        conjunta={'aprobado': True}, obligatorias=['pinn'])
    cid = c['candidatos']['pinn']
    (reg.raiz / 'pinn' / 'candidates' / cid / 'model_manifest.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ac.CicloBloqueado, match='integridad'):
        ac.miembro_del_conjunto(ap, 'pinn', registro=reg)


@pytest.mark.parametrize('campo,valor', [('schema', 'incompatible'), ('conjunto_id', '0' * 64)])
def test_manifiesto_conjunto_no_ignora_identidad_y_esquema(tmp_path, campo, valor):
    """050:RF-7 — la relectura valida el manifiesto completo antes de servirlo."""
    reg, ap = RegistroModelo(tmp_path / 'reg'), tmp_path / 'ap'
    c = _ciclo_terminado(tmp_path, reg)
    p = ac.publicar_conjunto(ap, reg, c, retencion={'pinn': {'retiene': True}},
        conjunta={'aprobado': True}, obligatorias=['pinn'])
    ruta = ap / 'conjuntos' / f"{p['conjunto']['conjunto_id']}.json"
    dato = json.loads(ruta.read_text(encoding='utf-8')); dato[campo] = valor
    ruta.write_text(json.dumps(dato), encoding='utf-8')
    with pytest.raises(ac.CicloBloqueado):
        ac.conjunto_activo(ap)


def test_reversion_a_conjunto_corrupto_conserva_el_actual(tmp_path):
    """050:RF-7 — validar el destino precede al cambio del puntero en una reversión."""
    reg, ap = RegistroModelo(tmp_path / 'reg'), tmp_path / 'ap'
    ret = {'pinn': {'retiene': True}, 'transformer': {'retiene': True}}
    a = ac.publicar_conjunto(ap, reg, _ciclo_terminado(tmp_path, reg), retencion=ret,
        conjunta={'aprobado': True}, obligatorias=['pinn', 'transformer'])
    b = ac.publicar_conjunto(ap, reg, _ciclo_terminado(tmp_path, reg, n=1), retencion=ret,
        conjunta={'aprobado': True}, obligatorias=['pinn', 'transformer'])
    ruta = ap / 'conjuntos' / f"{a['conjunto']['conjunto_id']}.json"
    ruta.write_text('{}', encoding='utf-8')
    with pytest.raises(ac.CicloBloqueado):
        ac.revertir_conjunto(ap)
    assert ac.conjunto_activo(ap)['conjunto_id'] == b['conjunto']['conjunto_id']


def test_evaluacion_conjunta_tocada_no_conserva_identidad(tmp_path):
    """050:RF-6, 050:RF-7 — retención y evaluación también quedan protegidas por la huella."""
    reg, ap = RegistroModelo(tmp_path / 'reg'), tmp_path / 'ap'
    p = ac.publicar_conjunto(ap, reg, _ciclo_terminado(tmp_path, reg), retencion={'pinn': {'retiene': True}},
        conjunta={'aprobado': True}, obligatorias=['pinn'])
    ruta = ap / 'conjuntos' / f"{p['conjunto']['conjunto_id']}.json"
    dato = json.loads(ruta.read_text(encoding='utf-8')); dato['conjunta']['aprobado'] = False
    ruta.write_text(json.dumps(dato), encoding='utf-8')
    with pytest.raises(ac.CicloBloqueado):
        ac.conjunto_activo(ap)


def test_conjunto_v1_sigue_legible_con_su_identidad_original(tmp_path):
    """050:RF-7 — la evolución de la huella no reescribe los conjuntos anteriores."""
    reg, ap = RegistroModelo(tmp_path / 'reg'), tmp_path / 'ap'
    c = _ciclo_terminado(tmp_path, reg)
    cuerpo = {'miembros': c['candidatos'], 'snapshot_id': c['snapshot_id'], 'ciclo': c['clave']}
    cid = ac._huella(cuerpo)
    carpeta = ap / 'conjuntos'; carpeta.mkdir()
    legado = {'schema': ac.ESQUEMA_CONJUNTO_V1, 'conjunto_id': cid, **cuerpo,
        'retencion': {}, 'conjunta': {}, 'publicado': '2026-11-03'}
    ruta = carpeta / f'{cid}.json'
    ruta.write_text(json.dumps(legado), encoding='utf-8')
    antes = ruta.read_bytes()
    (carpeta / 'activo.json').write_text(json.dumps({'conjunto_id': cid}), encoding='utf-8')
    assert ac.conjunto_activo(ap) == legado and ruta.read_bytes() == antes


def test_publicacion_rechazada_mantiene_el_conjunto(tmp_path):
    """050:RF-6, 050:RF-7, 050:RF-8: sin puertas, reapertura, retención o mejora conjunta, sigue el anterior."""
    reg = RegistroModelo(tmp_path / 'reg')
    ap = tmp_path / 'ap'
    ok = {'pinn': {'retiene': True}, 'transformer': {'retiene': True}}
    c1 = _ciclo_terminado(tmp_path, reg)
    activo = ac.publicar_conjunto(ap, reg, c1, retencion=ok, conjunta={'aprobado': True},
                                  obligatorias=['pinn', 'transformer'])['conjunto']['conjunto_id']
    c2 = _ciclo_terminado(tmp_path, reg, n=1)
    casos = [({'pinn': {'retiene': False}, 'transformer': {'retiene': True}}, {'aprobado': True}),
             (ok, {'aprobado': False, 'fallos': ['empate: el conjunto nuevo no mejora al vigente']})]
    for retencion, conjunta in casos:
        r = ac.publicar_conjunto(ap, reg, c2, retencion=retencion, conjunta=conjunta, obligatorias=['pinn', 'transformer'])
        assert r['publicado'] is False and r['activo']['conjunto_id'] == activo
    sin_reabrir = {**c2, 'candidatos': {**c2['candidatos'], 'pinn': _candidato(reg, 'pinn', reabierto=False, n=9)}}
    r = ac.publicar_conjunto(ap, reg, sin_reabrir, retencion=ok, conjunta={'aprobado': True}, obligatorias=['pinn', 'transformer'])
    assert r['publicado'] is False and any('reabrió' in m for m in r['motivos'])
    falta = ac.publicar_conjunto(ap, reg, c2, retencion=ok, conjunta={'aprobado': True},
                                 obligatorias=['pinn', 'transformer', 'gru'])
    assert falta['publicado'] is False and any('gru' in m for m in falta['motivos'])


def test_conjunto_manipulado_no_se_lee(tmp_path):
    """050:RF-7: un manifiesto de conjunto modificado después de publicar no se usa."""
    reg = RegistroModelo(tmp_path / 'reg')
    ap = tmp_path / 'ap'
    c1 = _ciclo_terminado(tmp_path, reg)
    p = ac.publicar_conjunto(ap, reg, c1, retencion={'pinn': {'retiene': True}, 'transformer': {'retiene': True}},
                             conjunta={'aprobado': True}, obligatorias=['pinn', 'transformer'])
    ruta = ap / 'conjuntos' / f"{p['conjunto']['conjunto_id']}.json"
    dato = json.loads(ruta.read_text(encoding='utf-8'))
    dato['miembros']['pinn'] = '0' * 64
    ruta.write_text(json.dumps(dato), encoding='utf-8')
    with pytest.raises(ac.CicloBloqueado):
        ac.conjunto_activo(ap)


# --------------------------------------------------------------------------- T5

def test_estado_distingue_las_fases(tmp_path):
    """050:RF-10: preparación, entrenamiento, selección, evaluación, publicación, activación y aceptación nativa."""
    reg = RegistroModelo(tmp_path / 'reg')
    ap = tmp_path / 'ap'
    vacio = ac.estado_aprendizaje(ap)
    assert set(vacio['fases']) == set(ac.FASES) and all(f['estado'] == 'pendiente' for f in vacio['fases'].values())
    c1 = _ciclo_terminado(tmp_path, reg)
    e = ac.estado_aprendizaje(ap)
    assert e['fases']['entrenamiento']['estado'] == 'hecho' and e['fases']['publicacion']['estado'] == 'pendiente'
    ac.publicar_conjunto(ap, reg, c1, retencion={'pinn': {'retiene': True}, 'transformer': {'retiene': False}},
                         conjunta={'aprobado': True}, obligatorias=['pinn', 'transformer'])
    e = ac.estado_aprendizaje(ap)
    assert e['fases']['evaluacion']['estado'] == 'rechazado' and 'transformer' in e['fases']['evaluacion']['motivo']
    ac.publicar_conjunto(ap, reg, c1, retencion={'pinn': {'retiene': True}, 'transformer': {'retiene': True}},
                         conjunta={'aprobado': True}, obligatorias=['pinn', 'transformer'])
    e = ac.estado_aprendizaje(ap)
    assert e['fases']['activacion']['estado'] == 'hecho'
    assert e['fases']['activacion']['versiones'] == c1['candidatos']
    assert e['fases']['aceptacion_nativa']['estado'] == 'pendiente'


def test_cli_estado_y_congelar(tmp_path, capsys):
    """050:RF-1, 050:RF-10: la orden congela y muestra las fases; un bloqueo sale con código 2."""
    spec = importlib.util.spec_from_file_location('aprendizaje_cli', RAIZ / 'tools' / 'aprendizaje_continuo.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    f = _fuentes(tmp_path)
    rc = cli.main(['--raiz', str(tmp_path / 'ap'), 'congelar', '--fuente', f"dataset={f['dataset']}",
                   '--fuente', f"twin={f['twin']}", '--contexto', CTX])
    salida = json.loads(capsys.readouterr().out)
    assert rc == 0 and salida['ok'] and len(salida['snapshot_id']) == 64
    rc = cli.main(['--raiz', str(tmp_path / 'ap'), 'congelar', '--fuente', f"dataset={tmp_path / 'nada'}",
                   '--contexto', CTX])
    assert rc == 2 and json.loads(capsys.readouterr().out)['estado'] == 'bloqueado'
    assert cli.main(['--raiz', str(tmp_path / 'ap'), 'estado']) == 0
    assert set(json.loads(capsys.readouterr().out)['fases']) == set(ac.FASES)


def test_cli_congela_contexto_de_varios_proyectos(tmp_path, capsys):
    """050:RF-1 — el CLI consume el manifiesto de contexto agregado comprobado."""
    spec = importlib.util.spec_from_file_location('aprendizaje_cli_multi', RAIZ / 'tools' / 'aprendizaje_continuo.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    archivo = tmp_path / 'contexto.json'
    archivo.write_text(json.dumps(ac.crear_contexto_ciclo({'P1': CTX})), encoding='utf-8')
    f = _fuentes(tmp_path)
    assert cli.main(['--raiz', str(tmp_path / 'ap'), 'congelar', '--fuente',
        f"dataset={f['dataset']}", '--contexto', str(archivo)]) == 0
    assert json.loads(capsys.readouterr().out)['ok']


def test_etapas_del_ciclo_aislan_salidas_y_no_publican(tmp_path, monkeypatch):
    """050:RF-1, 050:RF-4, 050:RF-7 — comandos reales, sin arrancar modelos ni GPU."""
    from types import SimpleNamespace
    import subprocess
    fuentes = _fuentes(tmp_path)
    fuentes['cabeceras'] = tmp_path / 'cabecera.txt'
    fuentes['cabeceras'].write_text('medición de contrato', encoding='utf-8')
    inst = ac.congelar_instantanea(fuentes, tmp_path / 'ap', contexto=CTX, versiones=VERSIONES)
    antes = ac.huellas_de(inst['ruta'])
    spec = importlib.util.spec_from_file_location('aprendizaje_cli_etapas', RAIZ / 'tools' / 'aprendizaje_continuo.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    comandos = []

    def ejecutar(cmd, **_kw):
        comandos.append(cmd)
        destino = Path(cmd[cmd.index('--raiz') + 1])
        assert not destino.is_relative_to(Path(inst['ruta']))
        if 'digital_twin_entrenar.py' in cmd[1]:
            assert ac.huellas_de(destino / 'objetos') == ac.huellas_de(ac.ruta_de(inst, 'twin') / 'objetos')
        (destino / 'modelos').mkdir(parents=True, exist_ok=True)
        (destino / 'modelos' / 'candidato.txt').write_text('salida', encoding='utf-8')
        reporte = Path(cmd[cmd.index('--output-json') + 1])
        reporte.write_text(json.dumps({'entrenado': True, 'promovido': False, 'candidato_aprobado': True,
            'publicacion_pendiente': True, 'candidate_id': CTX, 'gates': {'approved': True}}), encoding='utf-8')
        return subprocess.CompletedProcess(cmd, 0, '', '')

    monkeypatch.setattr(subprocess, 'run', ejecutar)
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(tmp_path / 'gpu.lock'))
    args = SimpleNamespace(semillas='11', zona_horaria='America/Lima', embedding_model='modelo-fijado',
        cadencia_min=15, horizontes='1,4,96')
    # Esta prueba aísla comandos/salidas. El preflight real y su rechazo de este
    # fixture incompleto se comprueban en test_aprendizaje_productores.py.
    monkeypatch.setattr(ac, 'preparar_fuentes', lambda *_a, **_kw: {'estado': 'preparado'})
    etapas = cli._etapas(inst, ['gru', 'pinn'], args, tmp_path / 'ejecucion')
    for e in etapas:
        r = e.run()
        assert r['status'] == 'PROMOVIDO' and r['publicacion_pendiente'] is True
    assert ac.huellas_de(inst['ruta']) == antes
    assert len(comandos) == 2 and all('--sin-publicar' in cmd for cmd in comandos)
    gru = next(cmd for cmd in comandos if 'temporal' in cmd[1])
    assert '--comparar' in gru and '--cadencia-min' in gru and '--horizontes' in gru
    algoritmos = gru[gru.index('--comparar') + 1].split(',')
    assert len(algoritmos) == len(set(algoritmos))


def test_cli_recibe_cadencia_horizontes_y_versiona_parametros(tmp_path, capsys, monkeypatch):
    """050:RF-1, 050:RF-4 — cambiar semillas no reutiliza el ciclo de otro ajuste."""
    spec = importlib.util.spec_from_file_location('aprendizaje_cli_parametros', RAIZ / 'tools' / 'aprendizaje_continuo.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, '_etapas', lambda *_: [])  # se detiene antes de ocupar recursos
    monkeypatch.setattr(ac, 'preflight_ciclo', lambda *_a, **_kw: {'estado': 'preparado'})
    fuentes = _fuentes(tmp_path)
    args = ['--raiz', str(tmp_path / 'ap'), 'ciclo', '--fuente', f"dataset={fuentes['dataset']}",
        '--contexto', CTX, '--familias', 'gru', '--politica-hash', CTX, '--tiempo-s', '10',
        '--memoria-gib', '1', '--cadencia-min', '15', '--horizontes', '1,4,96']
    for semillas in ('11', '23'):
        assert cli.main([*args, '--semillas', semillas]) == 2
        assert 'familias sin etapa' in json.loads(capsys.readouterr().out)['motivo']
    assert len(list((tmp_path / 'ap' / 'instantaneas').iterdir())) == 2


@pytest.mark.parametrize(('marca', 'esperado'), [
    (None, 'interrumpido'), ('no-es-un-pid', 'bloqueado'),
    ('0', 'bloqueado'), ('123456', 'interrumpido'),
])
def test_estado_sin_propietario_activo_no_anuncia_entrenamiento(marca, esperado, tmp_path, monkeypatch):
    """050:RF-8, 050:RF-10 — no se acredita actividad sin propietario vivo; diario inmutable."""
    carpeta = tmp_path / 'ciclos' / ('a' * 64)
    carpeta.mkdir(parents=True)
    diario = carpeta / 'ciclo.json'
    diario.write_text(json.dumps({'clave': 'a' * 64, 'snapshot_id': 'b' * 64,
        'estado': 'en_curso', 'inicio': '2026-11-08T05:00:00Z', 'motivos': []}), encoding='utf-8')
    if marca is not None:
        (carpeta / 'en_curso').write_text(marca, encoding='utf-8')
    monkeypatch.setattr(ac, 'pid_vivo', lambda _pid: False)
    antes = diario.read_bytes()
    estado = ac.estado_aprendizaje(tmp_path)
    assert estado['ultimo_ciclo']['estado'] == esperado
    assert estado['ultimo_ciclo']['estado_registrado'] == 'en_curso'
    assert estado['ultimo_ciclo']['motivos']
    assert estado['fases']['entrenamiento']['estado'] == esperado
    assert estado['conjunto_activo'] is None
    assert estado['fases']['aceptacion_nativa']['estado'] == 'pendiente'
    assert diario.read_bytes() == antes


def test_estado_con_propietario_actual_conserva_actividad(tmp_path):
    """050:RF-10 — el proceso real actual sigue activo y no se reescribe su evidencia."""
    import os
    carpeta = tmp_path / 'ciclos' / ('a' * 64)
    carpeta.mkdir(parents=True)
    diario = carpeta / 'ciclo.json'
    diario.write_text(json.dumps({'clave': 'a' * 64, 'snapshot_id': 'b' * 64,
        'estado': 'en_curso', 'inicio': '2026-11-08T05:00:00Z', 'motivos': []}), encoding='utf-8')
    (carpeta / 'en_curso').write_text(str(os.getpid()), encoding='utf-8')
    antes = diario.read_bytes()
    estado = ac.estado_aprendizaje(tmp_path)
    assert estado['ultimo_ciclo']['estado'] == 'en_curso'
    assert estado['fases']['entrenamiento']['estado'] == 'en_curso'
    assert diario.read_bytes() == antes
