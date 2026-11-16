import { useEffect } from 'react';

/**
 * Manejo por teclado de la web (WCAG 2.2 AA: 2.1.1 Teclado y 2.5.7 Movimientos de arrastre).
 * Funciones puras para que las pruebas las comprueben sin navegador; los componentes solo las aplican.
 */

/** Altura mínima del Registro en píxeles; por debajo deja de verse su cabecera. */
export const REGISTRO_MIN = 80;
/** Altura del Registro la primera vez, sin nada guardado. */
export const REGISTRO_INICIAL = 220;
/** Paso de las flechas y de Re Pág / Av Pág sobre el separador del Registro. */
const PASO = 20;
const PASO_LARGO = 100;

/**
 * El índice al que lleva una tecla en una lista de ``n`` elementos, con vuelta al principio y al final.
 * ``vertical``: también valen ↑ y ↓ (grupos de opciones). En las pestañas, horizontales, ↑ y ↓ no se capturan
 * para no robarle a la página el desplazamiento. ``null``: la tecla no es de navegación o no hay elementos.
 */
export function indicePorTecla(n: number, actual: number, tecla: string, vertical = false): number | null {
  if (!Number.isInteger(n) || n <= 0) return null;
  const i = Number.isInteger(actual) && actual >= 0 && actual < n ? actual : 0;
  switch (tecla) {
    case 'ArrowRight': return (i + 1) % n;
    case 'ArrowLeft': return (i - 1 + n) % n;
    case 'ArrowDown': return vertical ? (i + 1) % n : null;
    case 'ArrowUp': return vertical ? (i - 1 + n) % n : null;
    case 'Home': return 0;
    case 'End': return n - 1;
    default: return null;
  }
}

/** La altura del Registro tras una tecla sobre su separador, dentro de [REGISTRO_MIN, max]; ``null`` si no es suya. */
export function alturaPorTecla(altura: number, tecla: string, max: number): number | null {
  const tope = Math.max(REGISTRO_MIN, Math.floor(max));
  const limitar = (h: number) => Math.min(tope, Math.max(REGISTRO_MIN, Math.round(h)));
  switch (tecla) {
    case 'ArrowUp': return limitar(altura + PASO);       // el Registro está abajo: subir el borde lo agranda
    case 'ArrowDown': return limitar(altura - PASO);
    case 'PageUp': return limitar(altura + PASO_LARGO);
    case 'PageDown': return limitar(altura - PASO_LARGO);
    case 'Home': return REGISTRO_MIN;
    case 'End': return tope;
    default: return null;
  }
}

/**
 * La alternativa a arrastrar (2.5.7): una pulsación sin mover el puntero pliega el Registro a su mínimo y la
 * siguiente lo devuelve a la altura que tenía antes de plegarlo (o a la inicial si no había otra).
 */
export function alturaAlPulsar(altura: number, previa: number | null): number {
  if (altura > REGISTRO_MIN) return REGISTRO_MIN;
  return previa !== null && previa > REGISTRO_MIN ? previa : REGISTRO_INICIAL;
}

/** Píxeles que el puntero puede moverse y seguir contando como pulsación, no como arrastre. */
export const UMBRAL_PULSACION = 3;

/** Los ``role="radio"`` activos de un grupo, sin los de un grupo anidado. */
function radiosDelGrupo(grupo: Element): HTMLElement[] {
  return Array.from(grupo.querySelectorAll<HTMLElement>('[role="radio"]')).filter((r) =>
    r.closest('[role="radiogroup"]') === grupo && !r.hasAttribute('disabled') && r.getAttribute('aria-disabled') !== 'true');
}

/**
 * Flechas en todos los ``role="radiogroup"`` de la web, también los que se añadan después: mueven el foco a la opción
 * siguiente o anterior y la eligen, como un grupo de opciones nativo. Las desactivadas se saltan.
 */
export function useFlechasEnGrupos(): void {
  useEffect(() => {
    const alPulsar = (e: KeyboardEvent) => {
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      const el = e.target instanceof HTMLElement ? e.target : null;
      if (!el || el.getAttribute('role') !== 'radio') return;
      const grupo = el.closest('[role="radiogroup"]');
      if (!grupo) return;
      const radios = radiosDelGrupo(grupo);
      const i = radios.indexOf(el);
      if (i < 0) return;
      const j = indicePorTecla(radios.length, i, e.key, true);
      if (j === null || j === i) return;
      e.preventDefault();
      radios[j].focus();
      radios[j].click();
    };
    document.addEventListener('keydown', alPulsar);
    return () => document.removeEventListener('keydown', alPulsar);
  }, []);
}
