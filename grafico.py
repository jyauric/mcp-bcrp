import matplotlib.pyplot as plt
import pandas as pd

res = pd.read_csv("resultados.csv")
tabla = res.groupby("modo").resultado.value_counts().unstack(fill_value=0)
ax = tabla.plot.bar(stacked=True, figsize=(6, 4), rot=0)
ax.set_title("Respuestas de Claude (Haiku) por modo")
ax.set_ylabel("Preguntas")
ax.set_xlabel("")
plt.tight_layout()
plt.savefig("grafico.png", dpi=120)