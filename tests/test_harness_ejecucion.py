"""044:RF-5 044:RF-6 044:RF-8 — contratos; no evidencia de aceptación real."""
import unittest
from copy import deepcopy
from unittest.mock import patch

from test_harness_contratos import configuracion

from convertersmartgrid.evaluacion_harness.contratos import huella, sellar
from convertersmartgrid.evaluacion_harness.ejecucion import (
    ejecutar,
    validar_integridad,
    validar_promocion,
)


def preparar():
    cfg = configuracion()
    for suite in cfg['suites']:
        if suite['tipo'] == 'entidades':
            suite['puertas'] = {'precision': {'minimo': .9}, 'recall': {'minimo': .9}}
            for c in suite['casos']:
                c['esperado'] = {'entidades': [['sed', 'a']]}
    return sellar(cfg)


def proveedor(modelo, suite, entrada):
    assert 'casos' not in suite and 'esperado' not in entrada
    return {'prediccion': {'tarea': 'a', 'entidades': [['sed', 'a']]},
            **({'artifacts_hash': huella(modelo['artifacts'])} if 'artifacts' in modelo else {}),
            'modelo_digest': modelo['digest'], 'config_hash': modelo['config_hash'], 'backend': 'doble_contrato',
            'dispositivo': 'cpu', 'clase_evidencia': 'contrato'}


def evaluadores(cfg):
    # Estos dobles solo verifican el cableado: el reporte conserva su clase contrato.
    return {s['tipo']: lambda _gold, _pred, _params: {
                'metricas': {'acierto': 1.}, 'aprobado': True,
                'clase_evidencia': 'contrato'}
            for s in cfg['suites'] if s['tipo'] not in ('clasificacion', 'entidades')}


class EjecucionTest(unittest.TestCase):
    def test_guarda_runtime_vivo_no_admite_informe_historico(self):
        # Solo prueba de la guarda con dobles; no se registra ni promueve un modelo.
        cfg = preparar()
        for s in cfg['suites']:
            for c in list(s['casos']):
                copia = deepcopy(c)
                copia['record_id'] += ':2'
                copia['group_id'] += ':2'
                copia['entrada']['texto'] += ' 2'
                copia['texto'] += ' 2'
                s['casos'].append(copia)
        cfg['politica']['comparaciones'] = [{'suite_id': 'clasificacion', 'metrica': 'acierto',
            'estimando': 'media_grupos', 'margen': .1, 'semilla': 11,
            'remuestras': 200, 'confianza': .95, 'min_grupos': 2}]
        cfg = sellar(cfg)

        def doble(modelo, suite, entrada):
            r = proveedor(modelo, suite, entrada)
            r['clase_evidencia'] = 'real'  # Metadata ficticia exclusivamente del test.
            if modelo['id'] == 'vigente' and suite['tipo'] == 'clasificacion':
                r['prediccion']['tarea'] = 'b'
            return r

        ev = {t: lambda *_args: {'metricas': {'acierto': 1.}, 'aprobado': True,
                                 'clase_evidencia': 'real'} for t in evaluadores(cfg)}
        r = ejecutar(cfg, doble, modo='runtime', evaluadores=ev)
        validar_promocion(r, cfg)
        with (patch.dict('convertersmartgrid.evaluacion_harness.ejecucion._RUNTIME_VIVOS', {}, clear=True),
              self.assertRaisesRegex(ValueError, 'vivo')):
            validar_promocion(r, cfg)

    def test_configuracion_efectiva_distinta_no_cuenta_como_caso_valido(self):
        cfg = preparar()
        r = ejecutar(cfg, lambda *args: {**proveedor(*args), 'config_hash': '0'*64}, modo='runtime')
        self.assertEqual(r['completados'], 0)
        self.assertFalse(r['promocion_permitida'])

    def test_puerta_por_clase_no_oculta_regresion(self):
        cfg = preparar()
        cfg['suites'][0]['puertas'] = {'clases.b.recall': {'minimo': .9}}
        cfg = sellar(cfg)
        r = ejecutar(cfg, proveedor, modo='contract', evaluadores=evaluadores(cfg))
        self.assertFalse(r['suites']['clasificacion']['aprobada'])
        self.assertTrue(any('sin denominador' in f for f in r['suites']['clasificacion']['bloqueos']))

    def test_grupo_fallido_en_ambos_modelos_no_desaparece_de_comparacion(self):
        cfg = preparar()
        for s in cfg['suites']:
            c = deepcopy(s['casos'][-1])
            c['record_id'] += ':otro'
            c['group_id'] += ':otro'
            c['entrada']['texto'] += ' otro'
            c['texto'] += ' otro'
            s['casos'].append(c)
        cfg['politica']['comparaciones'] = [{'suite_id': 'clasificacion', 'metrica': 'acierto',
            'estimando': 'media_grupos', 'margen': 0, 'semilla': 11,
            'remuestras': 200, 'confianza': .95, 'min_grupos': 2}]
        cfg = sellar(cfg)

        def parcial(modelo, suite, entrada):
            if 'otro' in entrada['texto']:
                raise TimeoutError('grupo completo ausente')
            return proveedor(modelo, suite, entrada)

        r = ejecutar(cfg, parcial, modo='contract', evaluadores=evaluadores(cfg))
        self.assertFalse(r['mejora_demostrada'])
        self.assertTrue(r['comparaciones'][0]['bloqueos'])
        validar_integridad(r)

    def test_comparacion_electrica_usa_grupos_y_direccion(self):
        cfg = configuracion('pronostico')
        for s in cfg['suites']:
            originals = list(s['casos'])
            for c in originals:
                copia = deepcopy(c)
                copia['record_id'] += ':2'
                copia['group_id'] += ':2'
                copia['entrada']['texto'] += ' 2'
                copia['texto'] += ' 2'
                s['casos'].append(copia)
            s['puertas'] = {'mae': {'maximo': 3.}}
        cfg['politica']['comparaciones'] = [{'suite_id': 'pronostico', 'metrica': 'mae',
            'direccion': 'menor_mejor', 'estimando': 'media_grupos', 'margen': .1,
            'semilla': 11, 'remuestras': 200, 'confianza': .95, 'min_grupos': 2}]
        cfg = sellar(cfg)

        def electrico(modelo, suite, entrada):
            return {**proveedor(modelo, suite, entrada),
                    'prediccion': {'error': 2. if modelo['id'] == 'vigente' else 1.}}

        def medir(_gold, pred, params):
            return {'metricas': {'mae': sum(p['error'] for p in pred)/len(pred)},
                    'por_grupo': {g: {'mae': pred[0]['error']} for g in params['_harness']['grupos']},
                    'aprobado': True, 'clase_evidencia': 'contrato'}

        r = ejecutar(cfg, electrico, modo='contract',
                     evaluadores={s['tipo']: medir for s in cfg['suites']})
        self.assertTrue(r['comparaciones'][0]['mejora_demostrada'])
        validar_integridad(r)

        cfg['politica']['comparaciones'].append({**cfg['politica']['comparaciones'][0], 'metrica': 'rmse'})
        cfg = sellar(cfg)

        def ambiguo(gold, pred, params):
            resultado = medir(gold, pred, params)
            resultado['metricas']['rmse'] = 3-pred[0]['error']
            resultado['por_grupo'] = {g: pred[0]['error'] for g in params['_harness']['grupos']}
            return resultado

        invalido = ejecutar(cfg, electrico, modo='contract',
                            evaluadores={s['tipo']: ambiguo for s in cfg['suites']})
        self.assertFalse(invalido['mejora_demostrada'])
        self.assertTrue(all(c['bloqueos'] for c in invalido['comparaciones']))
        validar_integridad(invalido)

        def mapeado(gold, pred, params):
            resultado = ambiguo(gold, pred, params)
            resultado['por_grupo'] = {g: {'mae': pred[0]['error'], 'rmse': 3-pred[0]['error']}
                                       for g in params['_harness']['grupos']}
            return resultado

        control = ejecutar(cfg, electrico, modo='contract',
                           evaluadores={s['tipo']: mapeado for s in cfg['suites']})
        self.assertTrue(control['comparaciones'][0]['mejora_demostrada'])
        self.assertFalse(control['comparaciones'][1]['mejora_demostrada'])
        self.assertFalse(control['mejora_demostrada'])

    def test_resellar_un_resumen_falso_no_lo_hace_valido(self):
        cfg = preparar()
        for defecto in ('resumen', 'gold', 'caso_extra', 'comparaciones'):
            r = ejecutar(cfg, proveedor, modo='contract', evaluadores=evaluadores(cfg))
            if defecto == 'resumen':
                r['suites']['clasificacion']['medidas']['candidato']['metricas']['acierto'] = .25
            elif defecto == 'gold':
                r['casos'][0]['esperado']['tarea'] = 'b'
            elif defecto == 'caso_extra':
                r['casos'].append(deepcopy(r['casos'][0]))
            else:
                r['comparaciones'] = [{'mejora_demostrada': True}]
            r['sello_informe'] = huella({k: v for k, v in r.items() if k != 'sello_informe'})
            with self.subTest(defecto=defecto), self.assertRaises(ValueError):
                validar_integridad(r)

    def test_casos_pareados_y_gold_no_visible_al_proveedor(self):
        cfg = preparar()
        original = deepcopy(cfg)
        llamadas = []

        def predecir(modelo, suite, entrada):
            llamadas.append((modelo['id'], suite['id'], deepcopy(entrada)))
            resultado = proveedor(modelo, suite, entrada)
            entrada.clear()  # El proveedor no puede alterar el dataset sellado.
            return resultado

        r = ejecutar(cfg, predecir, modo='contract', evaluadores=evaluadores(cfg))
        self.assertEqual(cfg, original)
        self.assertEqual(len(llamadas), 2*len(cfg['suites']))
        self.assertEqual(r['estado'], 'COMPLETA')
        self.assertEqual(r['programados'], r['completados'])
        self.assertFalse(r['promocion_permitida'])
        with self.assertRaisesRegex(ValueError, 'runtime'):
            validar_promocion(r, cfg)

    def test_fallo_y_cancelacion_no_desaparecen_del_denominador(self):
        cfg = preparar()

        def falla(*_args):
            raise TimeoutError('fallo controlado')

        r = ejecutar(cfg, falla, modo='runtime', evaluadores=evaluadores(cfg))
        self.assertEqual(r['estado'], 'INCOMPLETA')
        self.assertEqual(r['fallidos'], r['programados'])
        self.assertFalse(r['promocion_permitida'])
        c = ejecutar(cfg, proveedor, modo='runtime', cancelar=lambda: True)
        self.assertEqual(c['estado'], 'CANCELADA')
        self.assertEqual(len(c['casos']), c['programados'])

    def test_digest_incorrecto_y_evaluador_ausente_bloquean(self):
        cfg = preparar()

        def distinto(*args):
            return {**proveedor(*args), 'modelo_digest': '0'*64}

        r = ejecutar(cfg, distinto, modo='runtime')
        self.assertGreater(r['fallidos'], 0)
        r = ejecutar(cfg, proveedor, modo='runtime')
        self.assertFalse(r['promocion_permitida'])
        self.assertTrue(any('evaluador' in b for b in r['bloqueos']))

    def test_replay_y_resumen_editado_nunca_promueven(self):
        cfg = preparar()
        r = ejecutar(cfg, proveedor, modo='replay', evaluadores=evaluadores(cfg))
        with self.assertRaises(ValueError):
            validar_promocion(r, cfg)
        r['modo'] = 'runtime'
        r['promocion_permitida'] = True
        with self.assertRaises(ValueError):
            validar_promocion(r, cfg)

    def test_auxiliar_fallida_queda_visible_sin_cambiar_suites_obligatorias(self):
        cfg = preparar()
        aux = deepcopy(cfg['suites'][0])
        aux['id'] = 'auxiliar'
        aux['obligatoria'] = False
        for c in aux['casos']:
            c['record_id'] = 'aux:'+c['record_id']
        cfg['suites'].append(aux)
        cfg = sellar(cfg)

        def predict(modelo, suite, entrada):
            if suite['id'] == 'auxiliar':
                raise TimeoutError('solo auxiliar')
            return proveedor(modelo, suite, entrada)

        r = ejecutar(cfg, predict, modo='contract', evaluadores=evaluadores(cfg))
        self.assertEqual(r['estado'], 'COMPLETA')
        self.assertEqual(r['fallidos'], 2)
        self.assertFalse(r['suites']['auxiliar']['completa'])


if __name__ == '__main__':
    unittest.main()
