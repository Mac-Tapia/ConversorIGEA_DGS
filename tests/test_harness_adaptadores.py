"""043:RF-9 044:RF-5 044:RF-8 — procedencia y evaluadores existentes."""
import unittest

from convertersmartgrid.evaluacion_harness.adaptadores import (
    desde_ordenes,
    evaluar_electrico,
    importar_upstream,
)


class AdaptadoresTest(unittest.TestCase):
    def test_ordenes_recalcula_y_conserva_convencion_historica(self):
        informe = {'ejemplos': 1, 'acierto_tarea': 1., 'f1_datos': 1.,
                   'casos': [{'record_id': 'x', 'esperado': 'a', 'obtenido': 'a',
                              'correcto': True, 'esperados': [], 'vistos': [],
                              'vp': 0, 'fp': 0, 'fn': 0}]}
        m = desde_ordenes(informe)
        self.assertIsNone(m['entidades']['precision'])
        self.assertEqual(m['historico']['f1_datos'], 1.)
        informe['casos'][0]['vp'] = 1
        with self.assertRaises(ValueError):
            desde_ordenes(informe)

    def test_electrico_aplica_politica_existente_sin_aceptacion_nativa(self):
        from convertersmartgrid.evaluacion_modelos import PoliticaDeError
        politica = PoliticaDeError(modo='agente', topes=(('mae_v', .02),))
        valores = {'ejemplos': 3, 'mae_v': .01, 'mae_fisica': .01}
        m = evaluar_electrico({'global': valores, 'familias': {'red': valores}}, politica=politica)
        self.assertTrue(m['aprobado'])
        self.assertFalse(m['aceptacion_nativa'])
        valores['mae_v'] = .2
        self.assertFalse(evaluar_electrico(
            {'global': valores, 'familias': {'red': valores}}, politica=politica)['aprobado'])

    def test_importacion_upstream_exige_commit_formato_y_sin_nan(self):
        lock = {'repositories': [{'id': 'promptfoo', 'commit': 'a'*40}]}
        raw = {'version': 3, 'results': [{'success': True}, {'success': False}]}
        r = importar_upstream(raw, herramienta='promptfoo', commit='a'*40, lock=lock)
        self.assertEqual(r['resumen']['casos'], 2)
        self.assertFalse(r['promocion_permitida'])
        self.assertEqual(r['original'], raw)
        for payload, commit in ((raw, 'b'*40), ({'version': 2, 'results': []}, 'a'*40),
                                ({'version': 3, 'results': [{'success': 1}]}, 'a'*40)):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                importar_upstream(payload, herramienta='promptfoo', commit=commit, lock=lock)

    def test_lm_eval_y_ragas_son_importaciones_auxiliares(self):
        lock = {'repositories': [{'id': 'lm_evaluation_harness', 'commit': 'a'*40},
                                 {'id': 'ragas', 'commit': 'b'*40}]}
        lm = importar_upstream({'results': {'tarea': {'acc,none': .5}}},
            herramienta='lm_evaluation_harness', commit='a'*40, lock=lock)
        self.assertEqual(lm['resumen']['tareas'], 1)
        rag = importar_upstream({'scores': [{'faithfulness': .8}]},
            herramienta='ragas', commit='b'*40, lock=lock)
        self.assertFalse(rag['verdad_experta'])


if __name__ == '__main__':
    unittest.main()
