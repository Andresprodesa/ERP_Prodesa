import { useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, TIPOS_INSUMO, type InsumoCreate, type TipoInsumo } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { SidePanel } from "../../components/Layout";
import { Cargando, ErrorBox, Kpi, mensajeError, Vacio } from "../../components/ui";
import { cop, fecha } from "../../lib/format";

export const NOMBRE_TIPO: Record<TipoInsumo, string> = {
  MAT: "Material",
  MO: "Mano de obra",
  EQ: "Equipo",
  TR: "Transporte",
  SUB: "Subcontrato",
};
const LIMIT = 50;

export default function InsumosPage() {
  const { puede } = useAuth();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [tipo, setTipo] = useState<TipoInsumo | "">("");
  const [offset, setOffset] = useState(0);
  const [sel, setSel] = useState<number | null>(null);
  const [nuevo, setNuevo] = useState<InsumoCreate>({ codigo: "", descripcion: "", unidad_id: 0, tipo: "MAT" });

  const insumos = useQuery({
    queryKey: ["insumos", q, tipo, offset],
    queryFn: () => api.maestros.insumos({ q, tipo, limit: LIMIT, offset }),
    placeholderData: keepPreviousData,
  });
  const unidades = useQuery({ queryKey: ["unidades"], queryFn: () => api.maestros.unidades({ activo: true }) });
  const precios = useQuery({
    queryKey: ["insumo-precios", sel],
    queryFn: () => api.maestros.preciosInsumo(sel as number),
    enabled: sel !== null,
  });
  const listas = useQuery({ queryKey: ["listas-precios"], queryFn: () => api.maestros.listasPrecios() });

  const crear = useMutation({
    mutationFn: (body: InsumoCreate) => api.maestros.crearInsumo(body),
    onSuccess: (ins) => {
      qc.invalidateQueries({ queryKey: ["insumos"] });
      setSel(ins.id);
      setNuevo((n) => ({ codigo: "", descripcion: "", unidad_id: n.unidad_id, tipo: n.tipo }));
    },
  });

  const seleccionado = insumos.data?.items.find((i) => i.id === sel) ?? null;
  const total = insumos.data?.total ?? 0;

  return (
    <>
      <SidePanel>
        <h2><span className="chev">&gt;</span>Buscar insumos</h2>
        <p className="sub">Código o descripción; filtra por tipo.</p>
        <input
          type="text"
          placeholder="Ej. concreto, acero, oficial…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOffset(0);
          }}
        />
        <select
          value={tipo}
          onChange={(e) => {
            setTipo(e.target.value as TipoInsumo | "");
            setOffset(0);
          }}
        >
          <option value="">Todos los tipos</option>
          {TIPOS_INSUMO.map((t) => (
            <option key={t} value={t}>{t} · {NOMBRE_TIPO[t]}</option>
          ))}
        </select>

        {puede.maestros && (
          <>
            <hr className="sep" />
            <h2><span className="chev">&gt;</span>Nuevo insumo</h2>
            <input type="text" placeholder="Código" value={nuevo.codigo} onChange={(e) => setNuevo({ ...nuevo, codigo: e.target.value })} />
            <input type="text" placeholder="Descripción" value={nuevo.descripcion} onChange={(e) => setNuevo({ ...nuevo, descripcion: e.target.value })} />
            <div className="row2">
              <select value={nuevo.unidad_id || ""} onChange={(e) => setNuevo({ ...nuevo, unidad_id: Number(e.target.value) })}>
                <option value="">Unidad…</option>
                {unidades.data?.map((u) => (
                  <option key={u.id} value={u.id}>{u.codigo}</option>
                ))}
              </select>
              <select value={nuevo.tipo} onChange={(e) => setNuevo({ ...nuevo, tipo: e.target.value as TipoInsumo })}>
                {TIPOS_INSUMO.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <button
              className="btn"
              type="button"
              disabled={crear.isPending || !nuevo.codigo || !nuevo.descripcion || !nuevo.unidad_id}
              onClick={() => crear.mutate(nuevo)}
            >
              {crear.isPending && <span className="spin" />}+ Crear insumo
            </button>
            {crear.error && <p className="hint">⚠ {mensajeError(crear.error)}</p>}
          </>
        )}
      </SidePanel>

      <div className="kpis">
        <Kpi k="Insumos encontrados" v={total.toLocaleString("es-CO")} s={tipo ? NOMBRE_TIPO[tipo] : "todos los tipos"} tono="b" />
        <Kpi k="Listas de precios" v={listas.data?.length ?? "—"} s="vigencias por ciudad" tono="b" />
      </div>

      <div className="card">
        <h3>Insumos <span className="tag">clic en una fila para ver su histórico de precios</span></h3>
        <ErrorBox error={insumos.error} />
        {insumos.isLoading ? (
          <Cargando />
        ) : total === 0 ? (
          <Vacio>No hay insumos con ese filtro.</Vacio>
        ) : (
          <>
            <div className="tw">
              <table>
                <thead>
                  <tr><th>Código</th><th>Descripción</th><th>Und</th><th>Tipo</th><th>Estado</th></tr>
                </thead>
                <tbody>
                  {insumos.data?.items.map((i) => (
                    <tr key={i.id} className={i.id === sel ? "sel" : ""} onClick={() => setSel(i.id)}>
                      <td>{i.codigo}</td>
                      <td>{i.descripcion}</td>
                      <td className="c">{i.unidad_codigo}</td>
                      <td className="c">{i.tipo}</td>
                      <td className="c">
                        {i.activo ? <span className="pill ok">ACTIVO</span> : <span className="pill no">INACTIVO</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="toolbar">
              <span className="note">{offset + 1}–{Math.min(offset + LIMIT, total)} de {total}</span>
              <span className="sp" />
              <button className="btn-s gh" type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>
                ◀ Anterior
              </button>
              <button className="btn-s gh" type="button" disabled={offset + LIMIT >= total} onClick={() => setOffset(offset + LIMIT)}>
                Siguiente ▶
              </button>
            </div>
          </>
        )}

        {seleccionado && (
          <div className="det">
            <div className="dh">
              <b>{seleccionado.codigo} · {seleccionado.descripcion}</b>
              <span className="m">{seleccionado.unidad_codigo} · {NOMBRE_TIPO[seleccionado.tipo]}</span>
              <button className="x" type="button" onClick={() => setSel(null)}>✕ cerrar</button>
            </div>
            {seleccionado.observaciones && <p className="note">{seleccionado.observaciones}</p>}
            <h4>Histórico de precios por ciudad y vigencia</h4>
            <ErrorBox error={precios.error} />
            {precios.isLoading ? (
              <Cargando />
            ) : !precios.data?.length ? (
              <Vacio>Sin precios registrados.</Vacio>
            ) : (
              <div className="tw">
                <table>
                  <thead>
                    <tr><th>Ciudad</th><th>Lista</th><th>Vigente desde</th><th>Precio</th></tr>
                  </thead>
                  <tbody>
                    {precios.data.map((p, idx) => (
                      <tr key={`${p.lista_id}-${idx}`}>
                        <td>{p.ciudad_codigo}</td>
                        <td>{p.lista_codigo} · {p.lista_nombre}</td>
                        <td className="c">{fecha(p.fecha_desde)}</td>
                        <td className="n">{cop(p.precio)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}
