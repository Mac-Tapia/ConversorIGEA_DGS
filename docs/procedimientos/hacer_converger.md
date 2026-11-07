# Hacer converger

Un flujo que no converge no se acepta: se busca la causa y se corrige.

## Antes de importar en DIgSILENT

1. Si el flujo del oráculo no converge, el sistema busca la causa antes de importar (057:RF-1) con
   `corregir_para_converger` (`src/convertersmartgrid/oraculo.py:717` («def corregir_para_converger»)).
2. Solo corrige las SED cuya demanda es de relleno o mayor que su potencia (057:RF-2); la corrección queda en el informe de
   reglas del alimentador (`src/convertersmartgrid/reglas.py:262` («def _corregir_con_oraculo»)).
3. A DIgSILENT solo llega la red que converge en el oráculo (057:RF-5). Si ni así converge, ese alimentador no se importa, se
   dice qué elementos lo impiden y el lote sigue con los demás (057:RF-6).

## En DIgSILENT

1. Si un flujo no converge, leer primero lo que informa DIgSILENT en el `historial` del informe, antes de tocar nada
   (`CLAUDE.md:195` («que no converge dice lo que informa DIgSILENT»)). La cadena de un sistema lo muestra al terminar
   (`tools/sistema_web.py:153` («inf.get('historial')»)).
2. Con ese mensaje se aísla la isla o la barra que lo causa y se corrige la causa, en su variación. No se aceptan atajos como
   bajar la demanda de todo el alimentador.
3. **Lo hace el operador:** si el arreglo exige cambiar algo a mano en DIgSILENT, el asistente le dice qué elemento y por qué, y
   espera. Los cambios manuales del operador son intencionales: se avisa de ellos, nunca se borran.
