"""044:RF-1 044:RF-2 044:RF-3 044:RF-8 — sello y particiones antes de medir."""
import unittest
from copy import deepcopy

from convertersmartgrid.evaluacion_harness.contratos import (
    MINIMAS,
    huella,
    sellar,
    validar,
)


def configuracion(familia='asistente'):
    suites = []
    for tipo in MINIMAS[familia]:
        casos = []
        for parte in ('entrenamiento', 'seleccion', 'calibracion', 'prueba'):
            casos.append({'record_id': tipo+':'+parte, 'group_id': parte,
                          'particion': parte, 'origen': 'sintetico_contrato',
                          'entrada': {'texto': 'a '+parte}, 'esperado': {'tarea': 'a'},
                          'texto': tipo+' '+parte})
        suites.append({'id': tipo, 'tipo': tipo, 'obligatoria': True,
                       'parametros': {'clases': ['a', 'b']}, 'casos': casos,
                       'puertas': {'acierto': {'minimo': .9}}})
    cfg = {'schema_version': 1, 'run_id': 'ensayo-contrato', 'familia': familia,
           'revision': 'a'*40, 'minimos': {p: 1 for p in
                 ('entrenamiento', 'seleccion', 'calibracion', 'prueba')},
           'modelos': {'referencia': {'id': 'vigente', 'digest': 'b'*64, 'config_hash': 'c'*64},
                       'candidato': {'id': 'nuevo', 'digest': 'd'*64, 'config_hash': 'e'*64}},
           'custodia': {'localizador': 'contrato_local', 'sha256': 'f'*64},
           'suites': suites, 'politica': {'version': 1, 'comparaciones': []}}
    return sellar(cfg)


class ContratosTest(unittest.TestCase):
    def test_sello_y_datos_inmutables(self):
        cfg = configuracion()
        validar(cfg)
        cfg['modelos']['candidato']['digest'] = 'f'*64
        with self.assertRaisesRegex(ValueError, 'sello'):
            validar(cfg)

    def test_omitir_suite_o_hacerla_auxiliar_no_elude_minimos(self):
        for operacion in ('borrar', 'auxiliar'):
            cfg = configuracion()
            if operacion == 'borrar':
                cfg['suites'].pop()
            else:
                cfg['suites'][0]['obligatoria'] = False
            with self.assertRaisesRegex(ValueError, 'obligatoria'):
                sellar(cfg)

    def test_sin_solape_ni_ids_duplicados_ni_minimos_implicitos(self):
        for defecto in ('grupo', 'id', 'minimo', 'nan', 'familia'):
            cfg = configuracion()
            if defecto == 'grupo':
                cfg['suites'][0]['casos'][1]['group_id'] = 'entrenamiento'
            elif defecto == 'id':
                cfg['suites'][0]['casos'][1]['record_id'] = cfg['suites'][0]['casos'][0]['record_id']
            elif defecto == 'minimo':
                del cfg['minimos']['prueba']
            elif defecto == 'familia':
                cfg['familia'] = 'desconocido'
            else:
                cfg['suites'][0]['puertas']['acierto']['minimo'] = float('nan')
            with self.subTest(defecto=defecto), self.assertRaises(ValueError):
                sellar(cfg)

    def test_sellado_no_muta_original_y_hashes_recalculables(self):
        cfg = configuracion()
        original = deepcopy(cfg)
        self.assertEqual(sellar(cfg), original)
        self.assertEqual(cfg, original)
        self.assertEqual(cfg['dataset_hash'], huella([s['casos'] for s in cfg['suites']]))


if __name__ == '__main__':
    unittest.main()
