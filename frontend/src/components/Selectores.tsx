import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type VersionOut } from "../api/client";

/** Selector de presupuesto (todas las obras) para el sidebar. */
export function SelectorPresupuesto(props: { value: number | null; onChange: (id: number | null) => void; label?: string }) {
  const lista = useQuery({ queryKey: ["presupuestos", null], queryFn: () => api.presupuestos.lista() });
  useEffect(() => {
    if (props.value === null && lista.data?.length) props.onChange(lista.data[0].id);
  }, [lista.data]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <>
      {props.label && <label className="lbl">{props.label}</label>}
      <select value={props.value ?? ""} onChange={(e) => props.onChange(e.target.value ? Number(e.target.value) : null)}>
        <option value="">Selecciona…</option>
        {lista.data?.map((p) => (
          <option key={p.id} value={p.id}>
            {p.proyecto_codigo} · {p.codigo} · {p.nombre}
          </option>
        ))}
      </select>
    </>
  );
}

/** Selector de versión de un presupuesto. `soloAprobadas` filtra BORRADOR. */
export function SelectorVersion(props: {
  presupuestoId: number | null;
  value: number | null;
  onChange: (id: number | null, v?: VersionOut) => void;
  soloAprobadas?: boolean;
  soloBorrador?: boolean;
  vacio?: string;
}) {
  const det = useQuery({
    queryKey: ["presupuesto", props.presupuestoId],
    queryFn: () => api.presupuestos.detalle(props.presupuestoId as number),
    enabled: props.presupuestoId !== null,
  });
  const versiones = (det.data?.versiones ?? []).filter(
    (v) => (!props.soloAprobadas || v.estado !== "BORRADOR") && (!props.soloBorrador || v.estado === "BORRADOR"),
  );
  return (
    <select
      value={props.value ?? ""}
      onChange={(e) => {
        const id = e.target.value ? Number(e.target.value) : null;
        props.onChange(id, versiones.find((v) => v.id === id));
      }}
    >
      <option value="">{props.vacio ?? "Selecciona versión…"}</option>
      {versiones.map((v) => (
        <option key={v.id} value={v.id}>
          v{v.numero} · {v.tipo} · {v.nombre} ({v.estado})
        </option>
      ))}
    </select>
  );
}
