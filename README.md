# MCP del BCRP

Servidor MCP hecho con [FastMCP](https://gofastmcp.com) que busca entre las 17,167 series oficiales del Banco Central
de Reserva del Perú (BCRP), las descarga y calcula variaciones. Está conectado a Claude Code y evaluado con
`claude -p`: ¿cuántas cifras acierta Claude sin el servidor y cuántas con él?

Proyecto de la sesión 04 del curso *Data Science con Python*
([enunciado original](https://github.com/d2cml-ai/Data-Science-Python/tree/main/sessions/04-mcp-claude-code/proyecto)).

**Resultado** (Haiku, 10 preguntas): de memoria acierta 0 de 10; con el MCP, 10 de 10, cada cifra con su fuente.
El detalle y el experimento extra están en [`informe.md`](informe.md).

## Qué ofrece el servidor

| Tipo | Nombre | Para qué |
|---|---|---|
| Herramienta | `buscar_series` | Buscar el código de una serie por palabras |
| Herramienta | `serie` | Datos de una serie entre dos fechas, con la URL de la fuente |
| Herramienta | `resumen` | Primero, último, cambio, variación %, promedio, máximo y mínimo |
| Herramienta | `grafico` | PNG con la evolución de una serie, guardado en `salidas/` |
| Recurso | `bcrp://serie/{codigo}` | Ficha de una serie (en Claude Code: `@bcrp:bcrp://serie/PN01273PM`) |
| Prompt | `informe(tema)` | Informe con cifras citadas (en Claude Code: `/mcp__bcrp__informe inflación`) |

## Cómo reproducirlo

Necesita [`uv`](https://docs.astral.sh/uv/), Claude Code con sesión iniciada e internet.

```bash
uv run pytest -q          # 8 pruebas con datos reales del BCRP; la primera vez baja el catálogo a datos/
claude                    # para usarlo en Claude Code: aprueben los servidores bcrp y fetch de .mcp.json
uv run evaluar.py         # memoria contra MCP, con Haiku; escribe resultados.csv
uv run grafico.py         # grafico.png a partir de resultados.csv
```

## Archivos

| Archivo | Qué es |
|---|---|
| `server.py` | El servidor MCP |
| `test_server.py` | Las 8 pruebas del curso, sin cambios |
| `.mcp.json` | Los servidores `bcrp` y `fetch` para Claude Code (sin claves) |
| `preguntas.csv` | 10 preguntas con la cifra oficial y su tolerancia (las 2 últimas son propias) |
| `evaluar.py` | Hace cada pregunta a Claude sin herramientas y con el MCP, y califica |
| `resultados.csv` | Corrida base; `resultados_base.csv` es su copia |
| `resultados_experimento.csv` | Corrida sin la instrucción de responder `null` |
| `grafico.py`, `grafico.png` | Respuestas por modo |
| `informe.md` | Análisis de resultados, cifras comprobadas a mano y conclusión |
