/** Con GB desde 2026-11-16: la previa de la copia (086:RF-82) habla de unos 20 GB, que eran «20480.0 MB». */
export const fmtBytes = (n: number) =>
  n < 1024 ? `${n} B` : n < 1024 ** 2 ? `${(n / 1024).toFixed(1)} KB`
    : n < 1024 ** 3 ? `${(n / 1024 ** 2).toFixed(1)} MB` : `${(n / 1024 ** 3).toFixed(1)} GB`;

export const fmtNum = (n: number | null | undefined, digits = 0) =>
  n == null ? '—' : n.toLocaleString('es-PE', { maximumFractionDigits: digits, minimumFractionDigits: digits });

/** 086:RF-110: la palabra que concuerda con la cuenta; la web no escribe «carga(s)». Con adjetivo, la frase entera:
 * `plural(n, 'libro nuevo', 'libros nuevos')`. */
export const plural = (n: number | null | undefined, uno: string, varios: string) => (n === 1 ? uno : varios);

/** La cuenta con su palabra: «1 carga», «3 cargas»; sin dato, «— cargas», como fmtNum. */
export const cuenta = (n: number | null | undefined, uno: string, varios: string) => `${fmtNum(n)} ${plural(n, uno, varios)}`;
