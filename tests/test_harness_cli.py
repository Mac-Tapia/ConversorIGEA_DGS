"""043:RF-13 044:RF-8 — publicación y CLI real en subproceso aislado."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_harness_contratos import configuracion
from test_harness_ejecucion import evaluadores, preparar, proveedor

from convertersmartgrid.evaluacion_harness.ejecucion import ejecutar
from convertersmartgrid.evaluacion_harness.publicacion import (
    leer_informe,
    leer_json,
    publicar,
)


class CliTest(unittest.TestCase):
    def test_fallo_readback_despues_de_replace_restaura_informe_anterior(self):
        with tempfile.TemporaryDirectory() as folder:
            ruta = Path(folder)/'informe.json'
            publicar(ruta, {'valor': 1})
            anterior = ruta.read_bytes()
            with (patch('convertersmartgrid.evaluacion_harness.publicacion.leer_informe',
                        side_effect=[{'valor': 2}, OSError('readback controlado')]),
                  self.assertRaises(OSError)):
                publicar(ruta, {'valor': 2})
            self.assertEqual(ruta.read_bytes(), anterior)

    def test_cli_rechaza_configuracion_escalar_sin_traceback(self):
        tool = Path(__file__).resolve().parents[1]/'tools/evaluar_harness.py'
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base/'entrada.json').write_text('null', encoding='utf-8')
            r = subprocess.run([sys.executable, '-I', '-B', str(tool), 'sellar',
                '--config', str(base/'entrada.json'), '--salida', str(base/'salida.json')],
                capture_output=True, text=True, timeout=15, check=False)
            self.assertEqual(r.returncode, 2)
            self.assertNotIn('Traceback', r.stderr)
            self.assertFalse((base/'salida.json').exists())

    def test_atomicidad_y_relectura(self):
        with tempfile.TemporaryDirectory() as folder:
            ruta = Path(folder)/'informe.json'
            publicar(ruta, {'valor': 1})
            anterior = ruta.read_bytes()
            with (patch('convertersmartgrid.evaluacion_harness.publicacion.os.replace',
                        side_effect=OSError('disco de ensayo')),
                  self.assertRaises(OSError)):
                publicar(ruta, {'valor': 2})
            self.assertEqual(ruta.read_bytes(), anterior)
            self.assertEqual(leer_informe(ruta), {'valor': 1})
            self.assertEqual(list(Path(folder).glob('*.tmp')), [])
            with self.assertRaises(ValueError):
                publicar(ruta, {'valor': float('nan')})
            self.assertEqual(ruta.read_bytes(), anterior)

    def test_json_duplicado_nan_y_sello_modificado_rechazados(self):
        with tempfile.TemporaryDirectory() as folder:
            ruta = Path(folder)/'informe.json'
            for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{'):
                ruta.write_text(raw, encoding='utf-8')
                with self.assertRaises(ValueError):
                    leer_json(ruta)
            publicar(ruta, {'valor': 1})
            data = json.loads(ruta.read_text(encoding='utf-8'))
            data['contenido']['valor'] = 2
            ruta.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaises(ValueError):
                leer_informe(ruta)

    def test_cli_sellar_y_verificar_en_hijo(self):
        tool = Path(__file__).resolve().parents[1]/'tools/evaluar_harness.py'
        with tempfile.TemporaryDirectory() as folder:
            ruta, salida = Path(folder)/'config.json', Path(folder)/'sellada.json'
            ruta.write_text(json.dumps(configuracion()), encoding='utf-8')
            r = subprocess.run([sys.executable, '-I', '-B', str(tool), 'sellar',
                                '--config', str(ruta), '--salida', str(salida)],
                               capture_output=True, text=True, timeout=15, check=False)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(leer_informe(salida)['sello'])
            r = subprocess.run([sys.executable, '-I', '-B', str(tool), 'verificar',
                                '--informe', str(salida)], capture_output=True, text=True, timeout=15, check=False)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_cli_replay_conserva_incompleto_y_no_sobrescribe_entrada(self):
        tool = Path(__file__).resolve().parents[1]/'tools/evaluar_harness.py'
        cfg = preparar()
        r = ejecutar(cfg, proveedor, modo='contract', evaluadores=evaluadores(cfg))
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base/'config.json').write_text(json.dumps(cfg), encoding='utf-8')
            (base/'pred.json').write_text(json.dumps(r['casos']), encoding='utf-8')
            cmd = [sys.executable, '-I', '-B', str(tool), 'replay', '--config', str(base/'config.json'),
                   '--predicciones', str(base/'pred.json'), '--salida', str(base/'salida.json')]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
            # Faltan evaluadores independientes de dominio: se conserva el diagnóstico, sin aprobarlo.
            self.assertEqual(result.returncode, 2, result.stderr)
            salida = leer_informe(base/'salida.json')
            self.assertEqual(salida['modo'], 'replay')
            self.assertFalse(salida['promocion_permitida'])
            original = (base/'pred.json').read_bytes()
            cmd[-1] = str(base/'pred.json')
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((base/'pred.json').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
