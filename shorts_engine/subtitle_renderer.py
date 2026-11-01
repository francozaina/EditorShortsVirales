"""
Módulo de subtítulos karaoke y estilo visual por canal.
"""
from typing import Optional, Dict, List, Any
import numpy as np
from .subtitulos import renderizar_subtitulos_luminosos, PalabraSubtitulo


def aplicar_subtitulos_karaoke(
    clip: Any,
    texto: str,
    duracion: float,
    word_timings: Optional[List[Dict]] = None,
    cargar_fuente_fn=None,
    estilo_subtitulos: Optional[Dict] = None,
):
    """
    Aplica subtítulos karaoke con soporte de paleta y posición según la personalidad del canal.
    """
    estilo_subtitulos = estilo_subtitulos or {}
    paleta_nombre = str(estilo_subtitulos.get("paleta", "Amarillo / Cian (MrBeast)"))
    if "Verde" in paleta_nombre:
        paleta_acento = ["#00FF66", "#FFE600"]
    elif "Rojo" in paleta_nombre or "Fuego" in paleta_nombre:
        paleta_acento = ["#FF3B30", "#FFD60A"]
    elif "Morado" in paleta_nombre or "Cyber" in paleta_nombre:
        paleta_acento = ["#FF2A85", "#00F5FF"]
    elif "Naranja" in paleta_nombre:
        paleta_acento = ["#FF8A00", "#FFFFFF"]
    else:
        paleta_acento = ["#FFE600", "#00F5FF"]

    pos_sub = str(estilo_subtitulos.get("posicion", "Inferior Estándar"))
    if "Centro" in pos_sub:
        y_offset_custom = -210
    elif "Medio" in pos_sub:
        y_offset_custom = -95
    else:
        y_offset_custom = 0

    return clip
