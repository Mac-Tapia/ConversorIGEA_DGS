"""Conecta el harness al coordinador y al registro existentes sin modificar sus políticas."""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from copy import deepcopy
from pathlib import Path

from .contratos import huella, validar
from .ejecucion import ejecutar, validar_integridad, validar_promocion
from .publicacion import publicar


def _sha(ruta: Path) -> str:
    with ruta.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


DESTINOS = {
    'asistente': {'llm': 'qlora', 'transformer': 'transformer', 'clasificador': 'clasificador'},
    'cadena': {'llm': 'qlora', 'transformer': 'transformer'},
    'recuperador': {'embeddings': 'embeddings'},
    'pronostico': {'gru': 'gru', 'pronostico_cabecera': 'gru',
                   'pronostico_cliente': 'gru', 'pronostico_escaladas': 'gru'},
    'gemelo': {'pinn': 'pinn'},
    'optimizador': {'evolutivos': 'evolutivos'},
}


def _destino(config, registro, modelo, *, nombre=None, uses_gpu=None):
    vinculo = config.get('integracion')
    if not isinstance(vinculo, dict) or 'activo_esperado' not in vinculo:
        raise ValueError('falta destino de registro sellado y activo esperado')
    etapa = DESTINOS[config['familia']].get(modelo)
    if (not etapa or vinculo.get('modelo') != modelo or vinculo.get('etapa') != etapa
            or type(vinculo.get('uses_gpu')) is not bool
            or not isinstance(vinculo.get('registro_raiz'), str)
            or not Path(vinculo['registro_raiz']).is_absolute()
            or Path(vinculo['registro_raiz']).resolve() != Path(registro.raiz).resolve()
            or (nombre is not None and nombre != etapa)
            or (uses_gpu is not None and uses_gpu != vinculo['uses_gpu'])):
        raise ValueError('destino/familia/etapa/recursos distinto del vínculo sellado')
    if registro.activo(modelo) != vinculo['activo_esperado']:
        raise ValueError('el activo cambió respecto de la referencia sellada')
    if vinculo['activo_esperado'] is not None:
        # El puntero estable no demuestra que se evaluó ese modelo. Releer el
        # candidato íntegro también verifica los bytes de sus artefactos.
        detalle = registro.detalle(modelo, vinculo['activo_esperado']['candidate_id'])
        referencia, manifest = config['modelos']['referencia'], detalle['model_manifest']
        if (detalle['decision'].get('status') != 'PROMOVIDO'
                or detalle['decision'].get('gates', {}).get('approved') is not True
                or detalle['smoke_reload'].get('ok') is not True
                or referencia['digest'] != manifest.get('digest')
                or referencia['config_hash'] != manifest.get('config_hash')
                or referencia.get('artifacts') != detalle['artifacts']):
            raise ValueError('la referencia evaluada no corresponde al activo íntegro sellado')
    return vinculo


def registrar_resultado(informe: dict, config: dict, *, registro, modelo: str,
                        model_manifest: dict, dataset_manifest: dict,
                        decision_dominio: dict, smoke_reload: dict, artifacts,
                        activar: bool = False, revalidar=None) -> dict:
    """Registra evidencia rechazada o aprobada; activar exige runtime y política heredada.

    El registro real verifica sus propios artefactos y conserva el activo anterior.
    No se promueve desde diagnósticos ni se modifica una decisión inmutable existente.
    Sin activo acreditado solo registra rechazo/diagnóstico: el bootstrap requiere
    un protocolo distinto de la comparación contra el activo.
    """
    validar(config)
    validar_integridad(informe)
    if type(activar) is not bool:
        raise ValueError('activar debe ser una decisión booleana explícita')
    vinculo = _destino(config, registro, modelo)
    if informe['configuracion'] != config:
        raise ValueError('configuración distinta del informe')
    candidato = config['modelos']['candidato']
    if (model_manifest.get('digest') != candidato['digest']
            or model_manifest.get('config_hash') != candidato['config_hash']
            or dataset_manifest.get('dataset_hash') != config['dataset_hash']):
        raise ValueError('manifiesto de otro modelo/configuración/dataset')
    rutas = [Path(p) for p in artifacts]
    esperados = model_manifest.get('artifacts')
    if (not rutas or not isinstance(esperados, dict) or len({p.name for p in rutas}) != len(rutas)
            or set(esperados) != {p.name for p in rutas}
            or esperados != candidato.get('artifacts')):
        raise ValueError('manifiesto de artefactos incompleto o nombres duplicados')
    for p in rutas:
        if not p.is_file() or _sha(p) != esperados[p.name]:
            raise ValueError('artefacto modificado/ausente: '+str(p))
    bloqueos = []
    if vinculo['activo_esperado'] is None:
        # Un arranque sin activo necesita un protocolo de bootstrap distinto.
        # Conservar diagnóstico/rechazo no autoriza a inventar equivalencia.
        bloqueos.append('sin referencia activa acreditada: bootstrap no habilita promoción')
    try:
        validar_promocion(informe, config)
    except ValueError as exc:
        bloqueos.append(str(exc))
    dominio_hash = config['politica'].get('dominio_hash')
    if (not isinstance(dominio_hash, str) or len(dominio_hash) != 64
            or decision_dominio.get('politica_hash') != dominio_hash
            or decision_dominio.get('status') != 'PROMOVIDO'
            or decision_dominio.get('gates', {}).get('approved') is not True):
        bloqueos.append('política/puertas heredadas no aprobadas o no vinculadas')
    if (decision_dominio.get('modelo_digest') != candidato['digest']
            or decision_dominio.get('config_hash') != candidato['config_hash']
            or decision_dominio.get('dataset_hash') != config['dataset_hash']
            or decision_dominio.get('artifacts_hash') != huella(esperados)):
        bloqueos.append('decisión de dominio de otro modelo/configuración/dataset/artefactos')
    recibos = [informe['suites'][s['id']].get('medidas', {}).get('candidato', {}).get('decision_original')
               for s in config['suites'] if s['obligatoria'] and s['tipo'] == 'dominio']
    if len(recibos) != 1 or recibos[0] != decision_dominio:
        bloqueos.append('decisión heredada no corresponde al recibo de dominio de esta campaña')
    if (smoke_reload.get('ok') is not True
            or smoke_reload.get('modelo_digest') != candidato['digest']
            or smoke_reload.get('config_hash') != candidato['config_hash']
            or smoke_reload.get('artifacts_hash') != huella(esperados)):
        bloqueos.append('recarga independiente ausente o de otro modelo/configuración')
    if not bloqueos and not callable(revalidar):
        bloqueos.append('falta revalidación de identidad efectiva antes de registrar')

    def identidad_actual():
        identidad = revalidar()
        if not isinstance(identidad, dict):
            raise TypeError('revalidación debe devolver identidades como objeto')
        for rol, esperado in config['modelos'].items():
            actual = identidad.get(rol)
            if (not isinstance(actual, dict) or actual.get('digest') != esperado['digest']
                    or actual.get('config_hash') != esperado['config_hash']
                    or (esperado.get('artifacts') is not None
                        and actual.get('artifacts_hash') != huella(esperado['artifacts']))):
                raise ValueError('modelo/configuración/artefactos de '+rol+' cambió después de evaluar')

    if not bloqueos:
        identidad_actual()
    decision = deepcopy(decision_dominio)
    decision['status'] = 'RECHAZADO' if bloqueos else 'PROMOVIDO'
    decision['gates'] = {**decision.get('gates', {}), 'approved': not bloqueos}
    decision['harness_bloqueos'] = bloqueos
    decision['harness_hash'] = informe['sello_informe']
    # Snapshot privado comprobado: nunca se leen pesos cambiantes al copiar al registro.
    # TemporaryDirectory administra únicamente su carpeta nueva bajo el Temp del sistema.
    with tempfile.TemporaryDirectory(prefix='csg-harness-candidato-') as carpeta:
        raiz_temporal = Path(carpeta).resolve()
        if raiz_temporal.parent != Path(tempfile.gettempdir()).resolve():
            raise ValueError('directorio temporal fuera del alcance propio')
        copias = []
        for original in rutas:
            copia = raiz_temporal / original.name
            shutil.copyfile(original, copia)
            if _sha(copia) != esperados[original.name]:
                raise ValueError('artefacto cambió al crear el snapshot')
            copias.append(copia)
        resultado = registro.registrar_candidato(modelo, model_manifest=deepcopy(model_manifest),
            dataset_manifest=deepcopy(dataset_manifest), metrics={'harness': deepcopy(informe)},
            decision=decision, smoke_reload=deepcopy(smoke_reload), artifacts=copias)
        detalle = registro.detalle(modelo, resultado['candidate_id'])
        if detalle['artifacts'] != esperados or detalle['metrics']['harness'] != informe:
            raise ValueError('relectura del registro no corresponde al candidato evaluado')
    activado = False
    if not bloqueos and activar:
        identidad_actual()
        _destino(config, registro, modelo)
        registro.promover(modelo, resultado['candidate_id'])
        activo = registro.activo(modelo)
        if not activo or activo.get('candidate_id') != resultado['candidate_id']:
            raise ValueError('relectura del activo no confirma la promoción')
        activado = True
    return {**resultado, 'activado': activado, 'harness_hash': informe['sello_informe'],
            'harness_bloqueos': bloqueos, 'aceptacion_electrica': informe['aceptacion_electrica']}


def crear_etapa(*, nombre: str, config: dict, proveedor, evaluadores: dict,
                 registro, declaracion: dict, informe_path: Path, uses_gpu: bool,
                 modo: str = 'runtime', cancelar=None, activar: bool = False,
                 revalidar=None):
    """Etapa insertable en TrainingCoordinator, con su orden y exclusión habituales.

    La aplicación conserva control de admisión de trabajos y turno nativo de PF.
    No se seleccionan proveedores mediante imports arbitrarios desde JSON.
    """
    from ..training_coordinator import ORDEN_MODELOS, TrainingStage
    validar(config)
    if nombre not in ORDEN_MODELOS or type(uses_gpu) is not bool:
        raise ValueError('etapa/dispositivo no declarado en el coordinador')
    _destino(config, registro, declaracion['modelo'], nombre=nombre, uses_gpu=uses_gpu)
    cfg, manifest = deepcopy(config), deepcopy(declaracion)

    def run():
        _destino(cfg, registro, manifest['modelo'], nombre=nombre, uses_gpu=uses_gpu)
        informe = ejecutar(cfg, proveedor, modo=modo, evaluadores=evaluadores, cancelar=cancelar)
        publicar(Path(informe_path), informe)
        if informe['estado'] == 'CANCELADA':
            return {'status': 'BLOQUEADO_POR_DATOS', 'model': nombre,
                    'reason': 'evaluación cancelada; informe conservado', 'informe': str(informe_path)}
        r = registrar_resultado(informe, cfg, registro=registro, activar=activar,
                                revalidar=revalidar, **manifest)
        return {**r, 'model': nombre, 'informe': str(informe_path)}

    return TrainingStage(nombre, run, uses_gpu=uses_gpu)
