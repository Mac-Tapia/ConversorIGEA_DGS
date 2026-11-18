# ADR-005 · Un fallo de dato se avisa con su causa; nunca se calla con una excepción amplia

- Estado: vigente
- Fecha: 2026-11-14
- Specs: 034:RF-5, 034:RF-10, 034:RF-40
- Elementos C4: engine, oracle, nativeRunner, security
- Evidencia: `docs/architecture/adr/deuda_excepciones_mudas.json~"ficheros"`, `src/convertersmartgrid/dominio/model.py::palabras_de`, `docs/architecture/workspace.dsl~Devuelve avisos; la importacion continua`

## Contexto

El 2026-11-14 aparecieron tres fallos con la misma forma: un `except Exception: return True` en el filtro de
secretos de la web, que fallaba abierto; una lectura de capas que ignoraba en silencio los filtros pedidos; y un
`ValueError` en las fases que apagaba el oráculo sin decirlo. En los tres, el resultado parecía bueno y no lo era.
La skill de backend ya prohibía «capturar Exception y callarla en el motor», pero nada lo comprobaba en el código
existente. El checklist de skills v2/v3 lo comprueba en las líneas añadidas; faltaba que la deuda que ya existía
no pudiera crecer.

## Decisión

- En el motor y en los guiones, un fallo de dato se convierte en un aviso con su código, el elemento y la causa
  (por ejemplo `PERFIL_ILEGIBLE` o `ramas_sin_fases`), que llega al manifiesto o al informe; si el fallo es de un
  alimentador, falla solo él (034:RF-5, RF-10).
- Un `except` amplio (`except:`, `Exception`, `BaseException`) cuyo único cuerpo calla o da paso (`pass`, `...`,
  `continue`, `return`, `return True` o `return None`) solo se admite con la marca `# justificado: <motivo>`; un
  `# noqa` no basta.
- Los que ya existían quedan contados por fichero en `deuda_excepciones_mudas.json`, y ningún fichero de `src/` o de
  `tools/` puede pasar de su cuenta (034:RF-40). La cuenta se baja a mano al retirar uno.
- El oráculo de pandapower informa y no bloquea la importación nativa: el aviso es su salida, como dice el AS-IS.

## Alternativa descartada

Prohibir de golpe todo `except` amplio. En los guiones de DIgSILENT muchos protegen la limpieza de una sesión
nativa que ya está fallando, y retirarlos todos a la vez, sin DIgSILENT en la máquina para probarlo, cambiaría el
comportamiento sin evidencia. También se descarta un ratchet que falle cuando la cuenta baja: con varias tarjetas
retirando excepciones a la vez, rompería la integración de cada una.

## Consecuencias

- Una excepción muda nueva no entra: el checklist la para en el diff y la prueba de arquitectura en el árbol.
- La deuda inicial, en 00d30651, es de 88 en 27 ficheros, casi toda en los guiones de DIgSILENT de `tools/`; cada retirada se
  anota bajando su cuenta.
- Como la cuenta solo se comprueba hacia arriba, un fichero que retira una y añade otra no se detecta en el árbol;
  sí en el diff, por el checklist.

## Contratos afectados

Los avisos del manifiesto del lote y de los informes (formato sin cambios), y el fichero
`docs/architecture/adr/deuda_excepciones_mudas.json`.

## Vuelta atrás

Quitar la prueba de 034:RF-40 y el fichero de la deuda. No cambia el comportamiento del producto: solo deja de
impedir que la deuda crezca.
