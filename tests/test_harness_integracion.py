"""043:RF-1 043:RF-5 043:RF-7 043:RF-13 — conexión en temporales, sin modelos/GPU."""
import hashlib
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from test_harness_ejecucion import evaluadores, preparar, proveedor

from convertersmartgrid.evaluacion_harness.contratos import huella, sellar
from convertersmartgrid.evaluacion_harness.ejecucion import ejecutar
from convertersmartgrid.evaluacion_harness.integracion import (
    crear_etapa,
    registrar_resultado,
)
from convertersmartgrid.model_registry import RegistroModelo
from convertersmartgrid.training_coordinator import TrainingCoordinator


def declaracion(cfg, artefacto):
    sha = hashlib.sha256(artefacto.read_bytes()).hexdigest()
    return {'modelo': 'llm', 'model_manifest': {
        'digest': cfg['modelos']['candidato']['digest'],
        'config_hash': cfg['modelos']['candidato']['config_hash'],
        'artifacts': {artefacto.name: sha}},
        'dataset_manifest': {'dataset_hash': cfg['dataset_hash']},
        'decision_dominio': {'status': 'PROMOVIDO', 'gates': {'approved': True}, 'politica_hash': 'f'*64,
                          'modelo_digest': cfg['modelos']['candidato']['digest'],
                          'config_hash': cfg['modelos']['candidato']['config_hash'],
                          'dataset_hash': cfg['dataset_hash'],
                          'artifacts_hash': huella(cfg['modelos']['candidato']['artifacts'])},
        'smoke_reload': {'ok': True, 'modelo_digest': cfg['modelos']['candidato']['digest'],
                      'config_hash': cfg['modelos']['candidato']['config_hash'],
                      'artifacts_hash': huella(cfg['modelos']['candidato']['artifacts'])},
        'artifacts': [artefacto]}


def vincular(cfg, peso):
    cfg = deepcopy(cfg)
    cfg['integracion'] = {'modelo': 'llm', 'etapa': 'qlora', 'uses_gpu': False,
                          'registro_raiz': str(peso.parent/'registro'), 'activo_esperado': None}
    cfg['modelos']['candidato']['artifacts'] = {
        peso.name: hashlib.sha256(peso.read_bytes()).hexdigest()}
    return sellar(cfg)


def identidades(cfg):
    return {rol: {'digest': modelo['digest'], 'config_hash': modelo['config_hash'],
                  **({'artifacts_hash': huella(modelo['artifacts'])} if 'artifacts' in modelo else {})}
            for rol, modelo in cfg['modelos'].items()}


def runtime_doble(peso):
    """Simula evidencia real solo para probar la frontera de publicación en temporales."""
    cfg = preparar()
    for s in cfg['suites']:
        for caso in list(s['casos']):
            otro = deepcopy(caso)
            otro['record_id'] += ':2'
            otro['group_id'] += ':2'
            otro['entrada']['texto'] += ' 2'
            otro['texto'] += ' 2'
            s['casos'].append(otro)
    cfg['politica'].update(dominio_hash='f'*64, comparaciones=[{
        'suite_id': 'clasificacion', 'metrica': 'acierto', 'estimando': 'media_grupos',
        'margen': .1, 'semilla': 11, 'remuestras': 200, 'confianza': .95, 'min_grupos': 2}])
    cfg = vincular(cfg, peso)

    def predict(modelo, suite, entrada):
        r = proveedor(modelo, suite, entrada)
        r['clase_evidencia'] = 'real'  # Doble, sin llamadas a inferencia ni entrenamiento.
        if modelo['id'] == 'vigente' and suite['tipo'] == 'clasificacion':
            r['prediccion']['tarea'] = 'b'
        return r

    ev = {tipo: (lambda _gold, _pred, _params, _tipo=tipo: {
        'metricas': {'acierto': 1.}, 'aprobado': True, 'clase_evidencia': 'real',
        **({'decision_original': declaracion(cfg, peso)['decision_dominio']} if _tipo == 'dominio' else {})})
        for tipo in evaluadores(cfg)}
    return cfg, ejecutar(cfg, predict, modo='runtime', evaluadores=ev)


class IntegracionTest(unittest.TestCase):
    def test_decision_dominio_de_otra_evaluacion_no_promueve(self):
        with tempfile.TemporaryDirectory() as folder:
            peso = Path(folder)/'peso.bin'
            peso.write_bytes(b'fixture')
            cfg, r = runtime_doble(peso)
            d = declaracion(cfg, peso)
            d['decision_dominio']['modelo_digest'] = '0'*64
            reg = RegistroModelo(peso.parent/'registro')
            resultado = registrar_resultado(r, cfg, registro=reg, activar=True,
                revalidar=lambda: identidades(cfg), **d)
            self.assertEqual(resultado['status'], 'RECHAZADO')
            self.assertIsNone(reg.activo('llm'))

    def test_registro_relativo_se_rechaza_antes_de_evaluar(self):
        with tempfile.TemporaryDirectory() as folder:
            peso = Path(folder)/'peso.bin'
            peso.write_bytes(b'fixture')
            cfg = vincular(preparar(), peso)
            cfg['integracion']['registro_raiz'] = 'registro'
            with self.assertRaisesRegex(ValueError, 'absoluto'):
                sellar(cfg)

    def test_activacion_temporal_exige_dominio_recarga_e_identidad_y_se_relee(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            peso = base/'peso.bin'
            peso.write_bytes(b'fixture publicado solo en registro temporal')
            cfg, r = runtime_doble(peso)
            reg = RegistroModelo(base/'registro')
            m = declaracion(cfg, peso)
            identidad = lambda: identidades(cfg)
            aceptado = registrar_resultado(r, cfg, registro=reg, activar=True,
                                            revalidar=identidad, **m)
            self.assertTrue(aceptado['activado'])
            activo = reg.activo('llm')
            self.assertEqual(activo['candidate_id'], aceptado['candidate_id'])
            # Rechazo del segundo candidato conserva el activo previo.
            m['decision_dominio']['gates']['approved'] = False
            with self.assertRaisesRegex(ValueError, 'activo cambió'):
                registrar_resultado(r, cfg, registro=reg, activar=True, revalidar=identidad, **m)
            self.assertEqual(reg.activo('llm'), activo)

    def test_identidad_cambiada_no_activa_candidato(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            peso = base/'peso.bin'
            peso.write_bytes(b'fixture')
            cfg, r = runtime_doble(peso)
            reg = RegistroModelo(base/'registro')
            with self.assertRaisesRegex(ValueError, 'cambió'):
                registrar_resultado(r, cfg, registro=reg, activar=True,
                    revalidar=lambda: {'digest': '0'*64}, **declaracion(cfg, peso))
            self.assertIsNone(reg.activo('llm'))

    def test_contract_se_registra_rechazado_y_no_altera_activo(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            peso = base/'peso.bin'
            peso.write_bytes(b'fixture no es un modelo entrenado')
            cfg = vincular(preparar(), peso)
            r = ejecutar(cfg, proveedor, modo='contract', evaluadores=evaluadores(cfg))
            registro = RegistroModelo(base/'registro')
            resultado = registrar_resultado(r, cfg, registro=registro, activar=True,
                                            **declaracion(cfg, peso))
            self.assertEqual(resultado['status'], 'RECHAZADO')
            self.assertIsNone(registro.activo('llm'))
            detalle = registro.detalle('llm', resultado['candidate_id'])
            self.assertEqual(detalle['metrics']['harness']['modo'], 'contract')
            self.assertTrue(detalle['decision']['harness_bloqueos'])

    def test_etapa_se_ejecuta_en_coordinador_real_y_publica_evidencia(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            peso = base/'peso.bin'
            peso.write_bytes(b'fixture contrato')
            cfg = vincular(preparar(), peso)
            etapa = crear_etapa(nombre='qlora', config=cfg, proveedor=proveedor,
                evaluadores=evaluadores(cfg), registro=RegistroModelo(base/'registro'),
                declaracion=declaracion(cfg, peso), informe_path=base/'harness.json',
                uses_gpu=False, modo='contract')
            coordinador = TrainingCoordinator([etapa], base/'run', config_hash=cfg['sello'])
            reporte = coordinador.run()
            self.assertTrue(reporte['complete'])
            self.assertEqual(reporte['stages'][0]['status'], 'RECHAZADO')
            self.assertTrue((base/'harness.json').is_file())
            self.assertEqual(coordinador.run(), reporte)

    def test_artefacto_distinto_no_se_registra_ni_promueve(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            peso = base/'peso.bin'
            peso.write_bytes(b'original')
            cfg = vincular(preparar(), peso)
            r = ejecutar(cfg, proveedor, modo='contract', evaluadores=evaluadores(cfg))
            manifest = declaracion(cfg, peso)
            peso.write_bytes(b'cambio')
            registro = RegistroModelo(base/'registro')
            with self.assertRaisesRegex(ValueError, 'artefacto'):
                registrar_resultado(r, cfg, registro=registro, **manifest)
            self.assertFalse((base/'registro').exists())

    def test_manifiesto_de_otro_modelo_o_dataset_no_se_registra(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            peso = base/'peso.bin'
            peso.write_bytes(b'fixture')
            cfg = vincular(preparar(), peso)
            r = ejecutar(cfg, proveedor, modo='contract', evaluadores=evaluadores(cfg))
            for tipo in ('modelo', 'datos'):
                m = declaracion(cfg, peso)
                if tipo == 'modelo':
                    m['model_manifest']['digest'] = '0'*64
                else:
                    m['dataset_manifest']['dataset_hash'] = '0'*64
                with self.subTest(tipo=tipo), self.assertRaises(ValueError):
                    registrar_resultado(r, cfg, registro=RegistroModelo(base/'registro'), **m)

    def test_llm_no_puede_publicarse_en_slot_pinn_ni_en_otro_registro(self):
        with tempfile.TemporaryDirectory() as folder:
            peso = Path(folder)/'peso.bin'
            peso.write_bytes(b'fixture')
            cfg, r = runtime_doble(peso)
            manifest = declaracion(cfg, peso)
            manifest['modelo'] = 'pinn'
            reg = RegistroModelo(peso.parent/'registro')
            with self.assertRaisesRegex(ValueError, 'destino'):
                registrar_resultado(r, cfg, registro=reg, activar=True,
                                     revalidar=lambda: identidades(cfg), **manifest)
            self.assertIsNone(reg.activo('pinn'))
            manifest['modelo'] = 'llm'
            with self.assertRaisesRegex(ValueError, 'destino'):
                registrar_resultado(r, cfg, registro=RegistroModelo(peso.parent/'otro'), **manifest)

    def test_no_se_admite_artefacto_distinto_aunque_manifest_y_bytes_coincidan(self):
        with tempfile.TemporaryDirectory() as folder:
            peso = Path(folder)/'peso.bin'
            peso.write_bytes(b'evaluado')
            cfg, r = runtime_doble(peso)
            peso.write_bytes(b'otro con hash valido despues de evaluar')
            manifest = declaracion(cfg, peso)
            with self.assertRaisesRegex(ValueError, 'artefactos'):
                registrar_resultado(r, cfg, registro=RegistroModelo(peso.parent/'registro'),
                                     activar=True, revalidar=lambda: identidades(cfg), **manifest)

    def test_referencia_cambiada_no_se_publica_con_comparacion_antigua(self):
        with tempfile.TemporaryDirectory() as folder:
            peso = Path(folder)/'peso.bin'
            peso.write_bytes(b'fixture')
            cfg, r = runtime_doble(peso)
            estado = identidades(cfg)
            estado['referencia']['digest'] = '0'*64
            with self.assertRaisesRegex(ValueError, 'referencia'):
                registrar_resultado(r, cfg, registro=RegistroModelo(peso.parent/'registro'),
                                     activar=True, revalidar=lambda: estado, **declaracion(cfg, peso))


if __name__ == '__main__':
    unittest.main()
