/** Formato es-CO. Los decimales llegan como string (contrato §0); se convierten SOLO para mostrar. */
import type { Dec } from "../api/client";

const fmtCop = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });
const fmtCopCompacto = new Intl.NumberFormat("es-CO", { notation: "compact", maximumFractionDigits: 1 });

export function toNum(v: Dec | number | null | undefined): number {
  if (v === null || v === undefined || v === "") return 0;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}

/** $ 1.250.000 */
export function cop(v: Dec | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  return fmtCop.format(toNum(v));
}

/** 1,2 mil M (para KPIs) */
export function copCompacto(v: Dec | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  return `$ ${fmtCopCompacto.format(toNum(v))}`;
}

/** Número con hasta `dec` decimales. */
export function num(v: Dec | number | null | undefined, dec = 4): string {
  if (v === null || v === undefined || v === "") return "—";
  return new Intl.NumberFormat("es-CO", { maximumFractionDigits: dec }).format(toNum(v));
}

/** Fracción → "12,5 %" (el contrato envía porcentajes como fracción). */
export function pct(v: Dec | number | null | undefined, dec = 1): string {
  if (v === null || v === undefined || v === "") return "—";
  return `${new Intl.NumberFormat("es-CO", { minimumFractionDigits: dec, maximumFractionDigits: dec }).format(toNum(v) * 100)} %`;
}

/** Porcentaje humano ("5") → fracción string ("0.05") con precisión decimal exacta en texto. */
export function pctAFraccion(humano: string): string {
  const s = humano.trim().replace(",", ".");
  if (s === "") return "0";
  const n = Number(s);
  if (!Number.isFinite(n)) return "0";
  return (n / 100).toFixed(6).replace(/\.?0+$/, "") || "0";
}

/** Fracción ("0.05") → texto humano ("5"). */
export function fraccionAPct(frac: Dec | null | undefined): string {
  const n = toNum(frac) * 100;
  return String(Math.round(n * 10000) / 10000);
}

// Formatos numéricos aceptados (MISMA regla que backend/app/modules/adpro/control/excel.py:parse_decimal):
const RE_CO_MILES = /^-?\d{1,3}(\.\d{3})+(,\d+)?$/; // "250.000", "1.250,5", "1.250.000,75"
const RE_COMA_DECIMAL = /^-?\d+,\d+$/; // "1250,5"
const RE_PUNTO_DECIMAL = /^-?(\d+(\.\d+)?|\.\d+)$/; // "1250.5", "0.25"

/**
 * Normaliza entrada numérica es-CO a string para la API (punto decimal, sin miles):
 * "250.000" -> "250000" (punto de miles), "1.250,5" -> "1250.5", "1250,5" -> "1250.5",
 * "1250.5" -> "1250.5". Devuelve `null` si el formato es ambiguo o inválido (p. ej. "1,250.50"):
 * nunca adivina un separador, para no registrar valores mil veces mayores o menores.
 */
export function parseDecimalCO(s: string): string | null {
  const t = s.trim().replace(/[\s\u00a0$]/g, "");
  if (t === "") return "";
  if (RE_CO_MILES.test(t)) return t.replace(/\./g, "").replace(",", ".");
  if (RE_COMA_DECIMAL.test(t)) return t.replace(",", ".");
  if (RE_PUNTO_DECIMAL.test(t)) return t;
  return null;
}

/**
 * Igual que `parseDecimalCO`, pero si el formato no es válido devuelve el texto tal cual: el
 * backend lo rechaza con 422 (VALIDATION_ERROR) y la pantalla muestra el error.
 */
export function decIn(s: string): string {
  const r = parseDecimalCO(s);
  return r === null ? s.trim() : r;
}

export function fecha(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v.length === 10 ? `${v}T00:00:00` : v);
  if (Number.isNaN(d.getTime())) return v;
  return d.toLocaleDateString("es-CO", { year: "numeric", month: "short", day: "2-digit" });
}

export function hoyISO(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function periodoActual(): string {
  return hoyISO().slice(0, 7);
}

/** Clase css-pro para variaciones: al alza = .pos (rojo, sobrecosto), a la baja = .neg (verde, ahorro). */
export function claseVariacion(v: Dec | number | null | undefined): string {
  const n = toNum(v);
  if (n > 0) return "pos";
  if (n < 0) return "neg";
  return "";
}
