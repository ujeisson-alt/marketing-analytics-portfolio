"""Estilo común de gráficos para todo el portafolio (paleta validada para daltonismo)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

AZUL, NARANJA, AQUA, AMARILLO, MAGENTA, VERDE, VIOLETA, ROJO = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
TEXTO, TEXTO_2, GRIS, FONDO = "#0b0b0b", "#52514e", "#b8b7b1", "#fcfcfb"

# Color fijo por entidad (nunca por ranking)
COLOR_PLATAFORMA = {"Google Ads": AZUL, "Meta Ads": NARANJA, "TikTok Ads": AQUA}


def aplicar_estilo():
    plt.rcParams.update({
        "figure.facecolor": FONDO, "axes.facecolor": FONDO, "savefig.facecolor": FONDO,
        "axes.edgecolor": GRIS, "axes.labelcolor": TEXTO_2, "axes.titlecolor": TEXTO,
        "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": "#e6e5e0", "grid.linewidth": 0.8,
        "xtick.color": TEXTO_2, "ytick.color": TEXTO_2, "font.size": 10,
        "legend.frameon": False, "lines.linewidth": 2,
    })


def guardar(fig, ruta):
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def cop(x, _=None):
    """Formato de pesos colombianos abreviado: $1,2 M / $350 K."""
    if abs(x) >= 1e9:
        return f"${x/1e9:,.1f} MM".replace(".", ",")
    if abs(x) >= 1e6:
        return f"${x/1e6:,.1f} M".replace(".", ",")
    if abs(x) >= 1e3:
        return f"${x/1e3:,.0f} K"
    return f"${x:,.0f}"
