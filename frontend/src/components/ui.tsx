import type { ReactNode } from "react";
import { ApiError, type EstadoVersion, type EstadoComparativo } from "../api/client";

export function Kpi(props: { k: string; v: ReactNode; s?: ReactNode; tono?: "" | "g" | "r" | "b" }) {
  return (
    <div className={`kpi ${props.tono ?? ""}`}>
      <div className="k">{props.k}</div>
      <div className="v">{props.v}</div>
      {props.s !== undefined && <div className="s">{props.s}</div>}
    </div>
  );
}

export function Cargando({ texto = "Cargando…" }: { texto?: string }) {
  return <div className="empty">{texto}</div>;
}

export function Vacio({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function mensajeError(e: unknown): string {
  if (e instanceof ApiError) {
    const det = Array.isArray(e.details)
      ? (e.details as { loc?: unknown[]; msg?: string; mensaje?: string }[])
          .map((d) => d.msg ?? d.mensaje ?? JSON.stringify(d))
          .slice(0, 5)
          .join(" · ")
      : "";
    return det ? `${e.message} (${det})` : e.message;
  }
  if (e instanceof Error) return e.message;
  return String(e);
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return <div className="err">{mensajeError(error)}</div>;
}

export function PillEstado({ estado }: { estado: EstadoVersion }) {
  const cls = estado === "APROBADO" ? "ok" : estado === "CERRADO" ? "rv" : "br";
  return <span className={`pill ${cls}`}>{estado}</span>;
}

export function PillComparativo({ estado }: { estado: EstadoComparativo }) {
  const cls = estado === "IGUAL" ? "br" : estado === "NUEVO" ? "ap" : estado === "ELIMINADO" ? "no" : "rv";
  return <span className={`pill ${cls}`}>{estado}</span>;
}

/** Porcentaje 0..100 acotado para el ancho de una barra. */
export function ancho(valor: number, maximo: number): string {
  if (maximo <= 0) return "0%";
  return `${Math.max(0, Math.min(100, (valor / maximo) * 100)).toFixed(2)}%`;
}
