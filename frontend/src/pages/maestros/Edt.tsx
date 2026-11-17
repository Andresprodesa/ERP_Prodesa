import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type EdtArbolNodo } from "../../api/client";
import { SidePanel } from "../../components/Layout";
import { Cargando, ErrorBox, Kpi, Vacio } from "../../components/ui";

function contar(nodos: EdtArbolNodo[], acc = { CAPITULO: 0, DETALLE: 0, GRUPO: 0, ITEM: 0, conApu: 0 }) {
  for (const n of nodos) {
    acc[n.nivel] += 1;
    if (n.nivel === "ITEM" && n.tiene_apu) acc.conApu += 1;
    contar(n.hijos, acc);
  }
  return acc;
}

/** Filtra el árbol conservando las ramas que contienen coincidencias. */
function filtrar(nodos: EdtArbolNodo[], q: string): EdtArbolNodo[] {
  if (!q) return nodos;
  const t = q.toLowerCase();
  const out: EdtArbolNodo[] = [];
  for (const n of nodos) {
    const hijos = filtrar(n.hijos, q);
    if (hijos.length || n.codigo.toLowerCase().includes(t) || n.descripcion.toLowerCase().includes(t)) {
      out.push({ ...n, hijos });
    }
  }
  return out;
}

function Nodo(props: {
  n: EdtArbolNodo;
  abiertos: Set<number>;
  forzarAbierto: boolean;
  toggle: (id: number) => void;
  sel: number | null;
  onSel: (id: number) => void;
}) {
  const { n, abiertos, forzarAbierto, toggle, sel, onSel } = props;
  const abierto = forzarAbierto || abiertos.has(n.id);
  const esItem = n.nivel === "ITEM";
  return (
    <li>
      <div
        className={`nd ${esItem ? "it" : ""}`}
        onClick={() => (esItem ? onSel(n.id) : toggle(n.id))}
        role="button"
        tabIndex={0}
      >
        <span className="tg">{esItem ? "•" : abierto ? "▾" : "▸"}</span>
        <code>{n.codigo}</code>
        <span>{n.descripcion}</span>
        {esItem && <span className="muted">{n.unidad_codigo}</span>}
        {esItem && (n.tiene_apu ? <span className="pill ok">APU</span> : <span className="pill no">SIN APU</span>)}
        {!esItem && <span className="lv">{n.nivel}</span>}
        {sel === n.id && <span className="badge">✓</span>}
      </div>
      {!esItem && abierto && n.hijos.length > 0 && (
        <ul className="tree">
          {n.hijos.map((h) => (
            <Nodo key={h.id} {...props} n={h} />
          ))}
        </ul>
      )}
    </li>
  );
}

export default function EdtPage() {
  const [q, setQ] = useState("");
  const [abiertos, setAbiertos] = useState<Set<number>>(new Set());
  const [sel, setSel] = useState<number | null>(null);

  const arbol = useQuery({ queryKey: ["edt-arbol"], queryFn: () => api.maestros.edtArbol({ hasta_nivel: "ITEM" }) });
  const detalle = useQuery({ queryKey: ["edt-nodo", sel], queryFn: () => api.maestros.edtNodo(sel as number), enabled: sel !== null });

  const conteo = useMemo(() => contar(arbol.data ?? []), [arbol.data]);
  const visibles = useMemo(() => filtrar(arbol.data ?? [], q.trim()), [arbol.data, q]);

  const toggle = (id: number) =>
    setAbiertos((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  return (
    <>
      <SidePanel>
        <h2><span className="chev">&gt;</span>EDT presupuestal</h2>
        <p className="sub">Capítulo → detalle → grupo → ítem. Busca por código o descripción.</p>
        <input type="text" placeholder="Ej. 02.01, mampostería…" value={q} onChange={(e) => setQ(e.target.value)} />
        <p className="hint">Clic en un ítem para ver su ruta y abrir su APU.</p>
      </SidePanel>

      <div className="kpis">
        <Kpi k="Capítulos" v={conteo.CAPITULO} tono="b" />
        <Kpi k="Ítems" v={conteo.ITEM} s={`${conteo.DETALLE} detalles · ${conteo.GRUPO} grupos`} tono="b" />
        <Kpi
          k="Ítems con APU"
          v={conteo.conApu}
          s={conteo.ITEM ? `${Math.round((conteo.conApu / conteo.ITEM) * 100)} % de cobertura` : "—"}
          tono={conteo.ITEM && conteo.conApu < conteo.ITEM ? "r" : "g"}
        />
      </div>

      {sel !== null && detalle.data && (
        <div className="card">
          <div className="det mt0">
            <div className="dh">
              <b>{detalle.data.codigo} · {detalle.data.descripcion}</b>
              <span className="m">{detalle.data.unidad_codigo}</span>
              <button className="x" type="button" onClick={() => setSel(null)}>✕ cerrar</button>
            </div>
            <div className="prs">
              {detalle.data.ruta.map((r) => (
                <span key={r.id} className={r.id === detalle.data.id ? "w" : ""}>
                  {r.nivel}: {r.codigo} {r.descripcion}
                </span>
              ))}
            </div>
            {detalle.data.notas && <p className="note">{detalle.data.notas}</p>}
            <div className="toolbar">
              {detalle.data.tiene_apu ? (
                <Link className="btn-s" to={`/apu/item/${detalle.data.id}`}>🧮 Abrir APU del ítem</Link>
              ) : (
                <span className="note">Este ítem aún no tiene APU.</span>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <h3>Árbol EDT <span className="tag">{q ? "filtrado" : "clic en un capítulo para desplegar"}</span></h3>
        <ErrorBox error={arbol.error} />
        {arbol.isLoading ? (
          <Cargando />
        ) : visibles.length === 0 ? (
          <Vacio>Sin nodos para mostrar.</Vacio>
        ) : (
          <ul className="tree">
            {visibles.map((n) => (
              <Nodo key={n.id} n={n} abiertos={abiertos} forzarAbierto={!!q.trim()} toggle={toggle} sel={sel} onSel={setSel} />
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
