import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { api, TIPOS_INSUMO, type ApuDetalleOut, type ApuInsumoIn } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { SidePanel } from "../../components/Layout";
import { ancho, Cargando, ErrorBox, Kpi, Vacio } from "../../components/ui";
import { cop, decIn, fraccionAPct, hoyISO, num, pct, pctAFraccion, toNum } from "../../lib/format";

interface FilaEdicion {
  insumo_id: number;
  cantidad: string;
  desperdicio: string; // % humano
}

function filasDesde(apu: ApuDetalleOut): FilaEdicion[] {
  return apu.insumos.map((i) => ({ insumo_id: i.insumo_id, cantidad: i.cantidad, desperdicio: fraccionAPct(i.desperdicio_pct) }));
}

export default function ApuPage() {
  const { itemId } = useParams();
  const navigate = useNavigate();
  const { puede } = useAuth();
  const qc = useQueryClient();
  const item = itemId ? Number(itemId) : null;

  const [q, setQ] = useState("");
  const [ciudadId, setCiudadId] = useState<number | null>(null);
  const [fechaP, setFechaP] = useState(hoyISO());
  const [editando, setEditando] = useState(false);
  const [filas, setFilas] = useState<FilaEdicion[]>([]);

  const ciudades = useQuery({ queryKey: ["ciudades"], queryFn: () => api.maestros.ciudades({ activo: true }) });
  useEffect(() => {
    if (ciudadId === null && ciudades.data?.length) setCiudadId(ciudades.data[0].id);
  }, [ciudades.data, ciudadId]);

  const lista = useQuery({
    queryKey: ["apus", q],
    queryFn: () => api.apu.lista({ q, limit: 100 }),
    placeholderData: keepPreviousData,
  });
  const apu = useQuery({ queryKey: ["apu-item", item], queryFn: () => api.apu.porItem(item as number), enabled: item !== null });
  const val = useQuery({
    queryKey: ["apu-val", apu.data?.id, ciudadId, fechaP],
    queryFn: () => api.apu.valorizacion(apu.data!.id, { ciudad_id: ciudadId ?? undefined, fecha: fechaP }),
    enabled: !!apu.data && ciudadId !== null,
  });

  useEffect(() => {
    setEditando(false);
    if (apu.data) setFilas(filasDesde(apu.data));
  }, [apu.data]);

  const guardar = useMutation({
    mutationFn: () => {
      const insumos: ApuInsumoIn[] = filas.map((f, idx) => ({
        insumo_id: f.insumo_id,
        cantidad: decIn(f.cantidad) || "0",
        desperdicio_pct: pctAFraccion(f.desperdicio),
        orden: idx + 1,
      }));
      return api.apu.reemplazarInsumos(apu.data!.id, insumos);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["apu-item", item] });
      qc.invalidateQueries({ queryKey: ["apu-val"] });
      setEditando(false);
    },
  });

  const v = val.data;
  const total = toNum(v?.valor_unitario);
  const subtotales = useMemo(
    () => TIPOS_INSUMO.map((t) => ({ tipo: t, valor: toNum(v?.subtotales_por_tipo?.[t]) })).filter((s) => s.valor > 0),
    [v],
  );
  const maxSub = Math.max(0, ...subtotales.map((s) => s.valor));

  return (
    <>
      <SidePanel>
        <h2><span className="chev">&gt;</span>Análisis de precio unitario</h2>
        <p className="sub">Selecciona el ítem y la base de precios (ciudad y fecha).</p>
        <input type="text" placeholder="Buscar ítem o APU…" value={q} onChange={(e) => setQ(e.target.value)} />
        <ul className="lst">
          {lista.data?.items.map((a) => (
            <li key={a.id} className={a.item_id === item ? "on" : ""} onClick={() => navigate(`/apu/item/${a.item_id}`)}>
              {a.item_codigo} · {a.item_descripcion}
              <small>{a.unidad_codigo} · {a.num_insumos} insumos</small>
            </li>
          ))}
          {lista.data && lista.data.items.length === 0 && <li>Sin resultados</li>}
        </ul>
        <label className="lbl">Ciudad de precios</label>
        <select value={ciudadId ?? ""} onChange={(e) => setCiudadId(Number(e.target.value))}>
          {ciudades.data?.map((c) => (
            <option key={c.id} value={c.id}>{c.codigo} · {c.nombre}</option>
          ))}
        </select>
        <label className="lbl">Fecha de precios</label>
        <input type="date" value={fechaP} onChange={(e) => setFechaP(e.target.value)} />
        {puede.maestros && apu.data && (
          <>
            <button
              className="btn"
              type="button"
              disabled={!editando || guardar.isPending}
              onClick={() => guardar.mutate()}
            >
              {guardar.isPending && <span className="spin" />}💾 Guardar composición
            </button>
            <p className="hint">
              {editando ? "Edita cantidades y desperdicios en la tabla." : "Activa la edición desde la tabla de composición."}
            </p>
          </>
        )}
      </SidePanel>

      {item === null ? (
        <div className="card intro">
          <p><span className="badge">APU</span>Elige un ítem en el panel izquierdo o desde el árbol EDT.</p>
          <p className="note">
            Valor unitario = Σ cantidad × (1 + % desperdicio) × precio vigente del insumo en la ciudad y fecha elegidas.
          </p>
        </div>
      ) : (
        <>
          <ErrorBox error={apu.error} />
          {apu.isLoading && <Cargando />}
          {apu.data && (
            <>
              <div className="kpis">
                <Kpi k="Valor unitario" v={v ? cop(v.valor_unitario) : "…"} s={`por ${apu.data.unidad_codigo}`} />
                <Kpi k="Insumos" v={apu.data.num_insumos} tono="b" />
                <Kpi
                  k="Insumos sin precio"
                  v={v?.insumos_sin_precio.length ?? "…"}
                  s={v && v.insumos_sin_precio.length ? "revisar lista de precios" : "base completa"}
                  tono={v && v.insumos_sin_precio.length ? "r" : "g"}
                />
              </div>

              <div className="card">
                <h3>
                  {apu.data.item_codigo} · {apu.data.item_descripcion}
                  <span className="tag">{apu.data.descripcion ?? ""}</span>
                </h3>
                <ErrorBox error={val.error ?? guardar.error} />
                <div className="toolbar mt0">
                  <span className="note">Unidad del ítem: <b>{apu.data.unidad_codigo}</b></span>
                  <span className="sp" />
                  {puede.maestros && !editando && (
                    <button className="btn-s gh" type="button" onClick={() => setEditando(true)}>✏ Editar composición</button>
                  )}
                  {editando && (
                    <button
                      className="btn-s gh"
                      type="button"
                      onClick={() => {
                        setFilas(filasDesde(apu.data!));
                        setEditando(false);
                      }}
                    >
                      ✕ Descartar cambios
                    </button>
                  )}
                </div>
                {apu.data.insumos.length === 0 ? (
                  <Vacio>El APU no tiene insumos.</Vacio>
                ) : (
                  <div className="tw">
                    <table>
                      <thead>
                        <tr>
                          <th>Código</th><th>Insumo</th><th>Und</th><th>Tipo</th>
                          <th>Cantidad</th><th>% Desp.</th><th>Precio vigente</th><th>Valor parcial</th><th>Part.</th>
                        </tr>
                      </thead>
                      <tbody>
                        {apu.data.insumos.map((ins, idx) => {
                          const comp = v?.componentes.find((c) => c.insumo_id === ins.insumo_id);
                          const fila = filas[idx];
                          return (
                            <tr key={ins.id} className={comp?.precio_faltante ? "par" : ""}>
                              <td>{ins.insumo_codigo}</td>
                              <td>{ins.insumo_descripcion}</td>
                              <td className="c">{ins.unidad_codigo}</td>
                              <td className="c">{ins.tipo}</td>
                              <td className="n">
                                {editando && fila ? (
                                  <input
                                    className="in"
                                    value={fila.cantidad}
                                    onChange={(e) => setFilas(filas.map((f, i) => (i === idx ? { ...f, cantidad: e.target.value } : f)))}
                                  />
                                ) : (
                                  num(ins.cantidad, 6)
                                )}
                              </td>
                              <td className="n">
                                {editando && fila ? (
                                  <input
                                    className="in"
                                    value={fila.desperdicio}
                                    onChange={(e) => setFilas(filas.map((f, i) => (i === idx ? { ...f, desperdicio: e.target.value } : f)))}
                                  />
                                ) : (
                                  pct(ins.desperdicio_pct, 1)
                                )}
                              </td>
                              <td className="n">{comp?.precio_faltante ? <span className="pos">sin precio</span> : cop(comp?.precio_unitario)}</td>
                              <td className="n">{cop(comp?.valor_unitario)}</td>
                              <td className="n">{total > 0 && comp ? pct(toNum(comp.valor_unitario) / total) : "—"}</td>
                            </tr>
                          );
                        })}
                        <tr className="tot">
                          <td colSpan={7}>Valor unitario del ítem ({apu.data.unidad_codigo})</td>
                          <td className="n">{cop(v?.valor_unitario)}</td>
                          <td className="n">100 %</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                )}
                {v && <p className="note">Precios a {v.fecha} · filas amarillas = insumo sin precio vigente.</p>}
              </div>

              {subtotales.length > 0 && (
                <div className="card">
                  <h3>Composición por tipo de insumo</h3>
                  <div className="bars">
                    {subtotales.map((s) => (
                      <div className="bar" key={s.tipo}>
                        <div className="nm">{s.tipo} · {pct(total ? s.valor / total : 0)}</div>
                        <div className="tr"><div className="f1" style={{ width: ancho(s.valor, maxSub) }} /></div>
                        <div className="vv">{cop(s.valor)}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </>
      )}
    </>
  );
}
