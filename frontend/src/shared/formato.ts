/** Con GB desde 2026-11-16: la previa de la copia (086:RF-82) habla de unos 20 GB, que eran «20480.0 MB». */
export const fmtBytes = (n: number) =>
  n < 1024 ? `${n} B` : n < 1024 ** 2 ? `${(n / 1024).toFixed(1)} KB`
    : n < 1024 ** 3 ? `${(n / 1024 ** 2).toFixed(1)} MB` : `${(n / 1024 ** 3).toFixed(1)} GB`;

export const fmtNum = (n: number | null | undefined, digits = 0) =>
  n == null ? '—' : n.toLocaleString('es-PE', { maximumFractionDigits: digits, minimumFractionDigits: digits });
