"""044:RF-8 047:RF-4 — métricas con soporte y recuperación, sin ejecutar modelos."""
import unittest

from convertersmartgrid.evaluacion_harness.metricas import (
    clasificacion,
    comparar_pareado,
    conteos,
    entidades,
    recuperacion,
)


class MetricasTest(unittest.TestCase):
    def test_conteos_y_denominadores_vacios(self):
        m = conteos(2, 1, 2)
        self.assertAlmostEqual(m['precision'], 2/3)
        self.assertEqual(m['recall'], .5)
        self.assertAlmostEqual(m['f1'], 4/7)
        self.assertIsNone(conteos(0, 0, 0)['precision'])
        self.assertIsNone(conteos(0, 0, 0)['recall'])
        self.assertIsNone(conteos(0, 0, 0)['f1'])
        for v in (-1, True, float('nan')):
            with self.subTest(v=v), self.assertRaises(ValueError):
                conteos(v, 0, 0)

    def test_abstencion_no_se_pierde_en_clasificacion(self):
        casos = [{'esperado': 'a', 'obtenido': 'a'},
                 {'esperado': 'a', 'obtenido': None},
                 {'esperado': 'b', 'obtenido': 'a'}]
        m = clasificacion(casos, ['a', 'b', 'c'])
        self.assertEqual(m['ejemplos'], 3)
        self.assertEqual(m['matriz']['a']['__abstencion__'], 1)
        self.assertEqual(m['clases']['a']['precision'], .5)
        self.assertEqual(m['clases']['b']['recall'], 0)
        self.assertIsNone(m['clases']['c']['recall'])
        self.assertAlmostEqual(m['micro']['recall'], 1/3)

    def test_entidades_recalcula_y_rechaza_conteos_contradictorios(self):
        m = entidades([{'esperados': [['sed', 'A'], ['sed', 'B']],
                        'vistos': [['sed', 'A'], ['sed', 'C']]}])
        self.assertEqual((m['vp'], m['fp'], m['fn']), (1, 1, 1))
        with self.assertRaises(ValueError):
            entidades([{'esperados': [['sed', 'A']], 'vistos': [], 'vp': 1}])

    def test_recuperacion_gold_completo_parcial_y_sin_respuesta(self):
        m = recuperacion([{'relevantes': ['a', 'b'], 'recuperados': ['z', 'a', 'x'],
                           'gold_completo': True}], k=3)
        self.assertAlmostEqual(m['precision@k'], 1/3)
        self.assertEqual(m['recall@k'], .5)
        self.assertEqual(m['mrr@k'], .5)
        parcial = recuperacion([{'relevantes': ['a'], 'recuperados': ['a'],
                                 'gold_completo': False}], k=3)
        self.assertIsNone(parcial['recall@k'])
        self.assertIsNone(parcial['precision@k'])
        self.assertIsNone(parcial['mrr@k'])
        self.assertAlmostEqual(parcial['precision_positivos_conocidos@k'], 1/3)
        sin = recuperacion([{'relevantes': [], 'recuperados': [],
                             'gold_completo': True}], k=3)
        self.assertIsNone(sin['recall@k'])
        self.assertEqual(sin['abstencion_correcta'], 1)
        with self.assertRaises(ValueError):
            recuperacion([{'relevantes': ['a'], 'recuperados': ['a', 'a'],
                           'gold_completo': True}], k=3)

    def test_intervalo_pareado_por_grupo_no_por_fila(self):
        filas = [{'group_id': str(i), 'referencia': .4, 'candidato': .8} for i in range(5)]
        kw = {'metrica': 'precision', 'margen': .1, 'semilla': 11, 'remuestras': 200,
                  'confianza': .95, 'min_grupos': 5}
        m = comparar_pareado(filas, **kw)
        self.assertTrue(m['mejora_demostrada'])
        self.assertEqual(m, comparar_pareado(filas, **kw))
        for f in filas:
            f['group_id'] = 'mismo'
        self.assertFalse(comparar_pareado(filas, **kw)['mejora_demostrada'])
        with self.assertRaises(ValueError):
            comparar_pareado([{'group_id': 'a', 'referencia': 1, 'candidato': float('nan')}], **kw)

    def test_error_electrico_menor_es_mejor(self):
        casos = [{'group_id': str(i), 'referencia': 2., 'candidato': 1.} for i in range(4)]
        r = comparar_pareado(casos, metrica='mae', direccion='menor_mejor', margen=.1,
            semilla=11, remuestras=200, confianza=.95, min_grupos=4)
        self.assertTrue(r['mejora_demostrada'])
        self.assertEqual(r['diferencia'], 1.)


if __name__ == '__main__':
    unittest.main()
