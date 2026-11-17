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

/** Normaliza entrada numérica de usuario a string para la API: "1.250,5" -> "1250.5"; "1250.5" -> "1250.5". */
export function decIn(s: string): string {
  const t = s.trim().replace(/\s/g, "");
  if (t.includes(",")) return t.replace(/\./g, "").replace(",", ".");
  return t;
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
