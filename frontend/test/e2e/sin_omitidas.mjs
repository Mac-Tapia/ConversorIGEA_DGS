/**
 * Reportero de los recorridos en navegador real: una omisión no es un pase (B25 y B26 del integrador, 17-11-2026).
 *
 * El 17-11 la corrida de los recorridos dio «11 passed, 1 skipped» y salía con 0: el «skipped» era F02, un
 * «test.fixme» vacío que no prueba nada. Este reportero deja la corrida en fallo si algún recorrido queda omitido
 * (skip o fixme), inestable (pasó al reintentar), interrumpido o sin correr, y dice cuál y por qué. Un recorrido que
 * aún no puede correr no se recoge (``testIgnore`` en la configuración, con su motivo); no se omite.
 */
export default class SinOmitidas {
  constructor() {
    /** @type {string[]} */
    this.malas = [];
  }

  printsToStdio() {
    return false;
  }

  onTestEnd(test, result) {
    const desenlace = test.outcome();
    const nota = (test.annotations ?? []).map((a) => a.type).filter((t) => ['skip', 'fixme', 'fail', 'slow'].includes(t));
    if (desenlace === 'skipped' || result.status === 'skipped') {
      this.malas.push(`omitido${nota.length ? ` (${nota.join(', ')})` : ''}: ${test.titlePath().filter(Boolean).join(' › ')}`);
    } else if (desenlace === 'flaky') {
      this.malas.push(`inestable: ${test.titlePath().filter(Boolean).join(' › ')}`);
    } else if (result.status === 'interrupted') {
      this.malas.push(`interrumpido: ${test.titlePath().filter(Boolean).join(' › ')}`);
    }
  }

  onEnd(resultado) {
    if (resultado.status === 'interrupted' || resultado.status === 'timedout') {
      this.malas.push(`la corrida terminó «${resultado.status}»: puede haber recorridos sin correr`);
    }
    if (!this.malas.length) return undefined;
    console.error(`\nsin_omitidas: ${this.malas.length} recorrido(s) que no pasaron de verdad:`);
    for (const m of this.malas) console.error(`  - ${m}`);
    console.error('Un recorrido que aún no puede correr va a testIgnore con su motivo; no se omite.');
    return { status: 'failed' };
  }
}
