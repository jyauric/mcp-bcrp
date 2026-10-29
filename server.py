"""Servidor MCP del BCRP. Empiecen aquí: buscar_series ya funciona; completen los TODO hasta que pasen las pruebas.

    uv run pytest                                           # el contrato: las 8 pruebas deben pasar
    uv run server.py                                        # el servidor, por stdio
    claude mcp add --scope project bcrp -- uv run server.py # conectarlo a Claude Code

Las cuentas las hace Python, no el modelo: así cada cifra sale de una llamada que se puede repetir.
"""
import json
import time
import re
import unicodedata
from functools import cache
from pathlib import Path

import httpx
import pandas as pd
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

AQUI = Path(__file__).parent
CATALOGO = AQUI / "datos" / "catalogo_bcrp.csv"
URL_CATALOGO = "https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata"
API = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
SOLO_LECTURA = {"readOnlyHint": True, "openWorldHint": True}

mcp = FastMCP("bcrp", instructions=(
    "Series oficiales del Banco Central de Reserva del Perú (BCRP). Primero busca el código con buscar_series; "
    "luego usa resumen para variaciones, promedios y extremos, y serie para los datos. No calcules a mano: "
    "cita siempre el código de la serie y el periodo."))


def _sin_tildes(s):
    return unicodedata.normalize("NFD", str(s).lower()).encode("ascii", "ignore").decode()


@cache
def catalogo():
    """El catálogo oficial: 17 mil series en unos 7 MB. Se baja una vez y queda en datos/."""
    if not CATALOGO.exists():
        CATALOGO.parent.mkdir(exist_ok=True)
        r = httpx.get(URL_CATALOGO, timeout=120)
        r.raise_for_status()
        CATALOGO.write_text(r.content.decode("latin-1"), encoding="utf-8")
    df = pd.read_csv(CATALOGO, sep=";", dtype=str).fillna("")
    df = df.rename(columns={"Código de serie": "codigo", "Categoría de serie": "categoria", "Grupo de serie": "grupo",
                            "Nombre de serie": "nombre", "Frecuencia": "frecuencia",
                            "Fecha de actualización": "actualizada", "Fecha de inicio": "inicio"})
    df["texto"] = (df.categoria + " " + df.grupo + " " + df.nombre).map(_sin_tildes)
    return df


def _ficha(codigo):
    fila = catalogo().query("codigo == @codigo")
    if fila.empty:
        raise ToolError(f"No existe el código de serie {codigo!r}. Búsquenlo con buscar_series.")
    f = fila.iloc[0]
    return {"codigo": f.codigo, "nombre": f"{f.grupo} - {f.nombre}", "categoria": f.categoria,
            "frecuencia": f.frecuencia, "inicio": f.inicio, "actualizada": f.actualizada}


@mcp.tool(annotations=SOLO_LECTURA)
def buscar_series(texto: str, frecuencia: str | None = None, limite: int = 10) -> list[dict]:
    """Busca series del BCRP por palabras: todas deben aparecer en la categoría, el grupo o el nombre.

    Ejemplos: "ipc 12 meses", "tipo de cambio interbancario venta", "reservas internacionales netas",
    "tasa de referencia", "cobre precio". frecuencia: "Diaria", "Mensual", "Trimestral" o "Anual".
    Devuelve el código, el nombre completo, la frecuencia y desde cuándo hay datos. Si no hay resultados,
    prueben con menos palabras.
    """
    df = catalogo()
    m = pd.Series(True, index=df.index)
    for palabra in _sin_tildes(texto).split():
        m &= df.texto.str.contains(re.escape(palabra))
    if frecuencia:
        m &= df.frecuencia.str.lower() == frecuencia.lower()
    # primero las series vigentes y, entre ellas, las de nombre más corto (las más generales)
    sel = df[m]
    orden = sel.assign(vieja=sel.actualizada < "2025", largo=(sel.grupo + sel.nombre).str.len())
    return [_ficha(c) for c in orden.sort_values(["vieja", "largo"]).head(limite).codigo]

MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
         "jul": 7, "ago": 8, "set": 9, "sep": 9, "oct": 10, "nov": 11, "dic": 12}


def _fecha_api(fecha, frecuencia):
    """'2025-01', '2025-T1' o '2026-10-01' al formato que pide la API según la frecuencia."""
    n = [int(x) for x in re.findall(r"\d+", str(fecha))]
    if frecuencia == "Diaria":
        a, m, d = (n + [1, 1])[:3]
        return f"{a}-{m:02d}-{d:02d}"
    if frecuencia in ("Mensual", "Trimestral"):
        a, m = (n + [1])[:2]
        return f"{a}-{m}"
    return str(n[0])


def _periodo(nombre, frecuencia):
    """El nombre que devuelve la API ('Ene.2025', '01.Oct.26', 'T1.25', '2025') en formato ISO."""
    if frecuencia == "Diaria":
        d, m, a = nombre.split(".")
        return f"20{a}-{MESES[m.lower()[:3]]:02d}-{int(d):02d}"
    if frecuencia == "Mensual":
        m, a = nombre.split(".")
        return f"{a}-{MESES[m.lower()[:3]]:02d}"
    if frecuencia == "Trimestral":
        t, a = nombre.split(".")
        return f"20{a}-{t}"
    return nombre


@cache
def _pedir(url):
    """GET con reintentos: si el BCRP limita los pedidos responde HTML en vez de JSON."""
    for intento in range(4):
        r = httpx.get(url, timeout=60)
        try:
            return r.json()
        except ValueError:
            time.sleep(2 * (intento + 1))
    raise ToolError(f"El BCRP no respondió con datos: {url}. Esperen unos segundos y reintenten.")


def _serie(codigo, desde, hasta):
    ficha = _ficha(codigo)
    f = ficha["frecuencia"]
    url = f"{API}/{codigo}/json/{_fecha_api(desde, f)}/{_fecha_api(hasta, f)}"
    datos = []
    for p in _pedir(url).get("periods", []):
        try:
            valor = float(p["values"][0])
        except (ValueError, IndexError):     # "n.d." o vacío
            continue
        datos.append({"periodo": _periodo(p["name"], f), "valor": valor})
    return {"codigo": codigo, "nombre": ficha["nombre"], "frecuencia": f, "datos": datos, "fuente": url}


@mcp.tool(annotations=SOLO_LECTURA)
def serie(codigo: str, desde: str, hasta: str) -> dict:
    """Descarga los datos de una serie del BCRP entre dos fechas, con la URL de la fuente.

    Fechas: "2025-01" en series mensuales, "2025-T1" en trimestrales, "2026-10-01" en diarias y "2025" en anuales.
    Primero busquen el código con buscar_series. Para variaciones, promedios o extremos usen resumen.
    Ejemplo: codigo="PN01273PM", desde="2026-01", hasta="2026-09".
    """
    return _serie(codigo, desde, hasta)

@mcp.tool(annotations=SOLO_LECTURA)
def resumen(codigo: str, desde: str, hasta: str) -> dict:
    """Resume una serie del BCRP entre dos fechas: primer y último dato, cambio, variación %, promedio, máximo y mínimo.

    Úsenla para cualquier pregunta de variaciones, promedios o extremos, en vez de calcular a mano.
    Mismas fechas que serie. Ejemplo: codigo="PN01273PM", desde="2025-12", hasta="2026-09".
    """
    s = _serie(codigo, desde, hasta)
    d = pd.DataFrame(s["datos"])
    if d.empty:
        raise ToolError(f"La serie {codigo} no tiene datos entre {desde} y {hasta}.")

    def punto(i):
        return {"periodo": d.periodo[i], "valor": float(d.valor[i])}

    primero, ultimo = d.valor.iloc[0], d.valor.iloc[-1]
    return {"codigo": codigo, "nombre": s["nombre"], "n_datos": len(d),
            "primero": punto(0), "ultimo": punto(len(d) - 1),
            "cambio": round(float(ultimo - primero), 4),
            "variacion_pct": round(float((ultimo / primero - 1) * 100), 4) if primero else None,
            "promedio": round(float(d.valor.mean()), 4),
            "maximo": punto(d.valor.idxmax()), "minimo": punto(d.valor.idxmin()),
            "fuente": s["fuente"]}

@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": True})
def grafico(codigo: str, desde: str, hasta: str) -> dict:
    """Dibuja una serie del BCRP entre dos fechas y guarda un PNG en salidas/.

    Úsenla cuando pidan ver la evolución o la tendencia de una serie; para una cifra puntual usen serie o resumen.
    Mismas fechas que serie. Ejemplo: codigo="PN01273PM", desde="2024-01", hasta="2026-09".
    Devuelve la ruta del PNG, cuántos datos dibujó y la URL de la fuente.
    """
    import matplotlib
    matplotlib.use("Agg")                     # sin ventana: el servidor no tiene pantalla
    import matplotlib.pyplot as plt

    s = _serie(codigo, desde, hasta)
    d = pd.DataFrame(s["datos"])
    if d.empty:
        raise ToolError(f"La serie {codigo} no tiene datos entre {desde} y {hasta}.")
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(d.periodo, d.valor, marker="o", markersize=3)
    ax.set_xticks(d.periodo[::max(1, len(d) // 12)])
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    ax.set_title(f"{s['nombre']} ({codigo})", fontsize=9)
    ax.grid(alpha=0.3)
    fig.text(0.01, 0.01, f"Fuente: BCRP, serie {codigo}", fontsize=7)
    fig.tight_layout()
    ruta = AQUI / "salidas" / f"{codigo}_{desde}_{hasta}.png"
    ruta.parent.mkdir(exist_ok=True)
    fig.savefig(ruta, dpi=120)
    plt.close(fig)
    return {"ruta": str(ruta), "n_datos": len(d), "fuente": s["fuente"]}

@mcp.resource("bcrp://serie/{codigo}")
def ficha_serie(codigo: str) -> str:
    """Ficha de una serie del BCRP: nombre, categoría, frecuencia, desde cuándo hay datos y última actualización."""
    return json.dumps(_ficha(codigo), ensure_ascii=False, indent=2)


@mcp.prompt
def informe(tema: str) -> str:
    """Informe breve sobre un tema económico del Perú con cifras oficiales del BCRP."""
    return (f"Escribe un informe breve sobre {tema} en el Perú con cifras oficiales del BCRP. "
            "Busca las series con buscar_series; usa resumen para variaciones y promedios y serie para los datos. "
            "No hagas cuentas a mano. Cita el código de la serie, el periodo y el link de la fuente de cada cifra. "
            "Cierra con tres conclusiones en viñetas.")

if __name__ == "__main__":
    mcp.run()
