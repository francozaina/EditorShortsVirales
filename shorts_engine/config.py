# -*- coding: utf-8 -*-
import os
import re
import sys
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WIN_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
WIN_STARTUPINFO = None
if sys.platform == "win32":
    WIN_STARTUPINFO = subprocess.STARTUPINFO()
    WIN_STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    WIN_STARTUPINFO.wShowWindow = subprocess.SW_HIDE

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

WIDTH = 1080
HEIGHT = 1920
FPS = 60
CPU_THREADS = max(4, (os.cpu_count() or 8))

MODO_ENCUADRE_DEFAULT = "full"
VOLUMEN_VOZ_NARRADOR = 1.48
VOLUMEN_AUDIO_VIDEO_ORIGINAL = 0.0
VOLUMEN_MUSICA_FONDO = 0.18
SUBTITLE_OFFSET_SEC = -0.02
DURACION_CALLOUTS_DEFAULT = 1.8

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")

VOCES_DISPONIBLES: Dict[str, str] = {
    "Giuseppe (YouTuber Hype - Recomendada)": "it-IT-GiuseppeMultilingualNeural",
    "Tomás (Argentina Dinámico)": "es-AR-TomasNeural",
    "Jorge (México Dinámico)": "es-MX-JorgeNeural",
    "Álvaro (España Intenso)": "es-ES-AlvaroNeural",
    "Dalia (Femenina Expresiva)": "es-MX-DaliaNeural",
}
EDGE_VOICE_DEFAULT = "it-IT-GiuseppeMultilingualNeural"
EDGE_PITCH_DEFAULT = "+0Hz"

BASE_DIR = Path(__file__).resolve().parent.parent

ASSETS_DIR = BASE_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

def _resolver_carpeta_asset(nombre: str) -> Path:
    en_assets = ASSETS_DIR / nombre
    if en_assets.exists():
        return en_assets
    directa = BASE_DIR / nombre
    if directa.exists():
        return directa
    en_assets.mkdir(parents=True, exist_ok=True)
    return en_assets

EMOJIS_DIR = _resolver_carpeta_asset("emojis")
FONTS_DIR = _resolver_carpeta_asset("fonts")
FOTOS_DIR = _resolver_carpeta_asset("fotos")
SFX_DIR = _resolver_carpeta_asset("sfx")
MUSICA_DIR = _resolver_carpeta_asset("musica")
TEMP_DIR = BASE_DIR / "temp_build"
OUTPUT_DIR = BASE_DIR / "output_shorts"

DEFAULT_VIDEO_INPUT = BASE_DIR / "video_input.mp4"
DEFAULT_GUION_TXT = BASE_DIR / "guion_video.txt"
PROMPT_IA_PATH = BASE_DIR / "PROMPT_PARA_IA_GUIONES.txt"
PROMPT_COMPACTO_PATH = BASE_DIR / "PROMPT_ARGON_COMPACTO.txt"

# Constantes de estilos visuales CustomTkinter
BG_DARK = "#0a0d14"
CARD_BG = "#131825"
CARD_BORDER = "#1f2637"
PURPLE_MAIN = "#7c3aed"
CYAN_ACCENT = "#06b6d4"
GREEN_ACCENT = "#10b981"
TEXT_MAIN = "#f1f5f9"
TEXT_MUTED = "#94a3b8"
INPUT_BG = "#0f1420"
MESES_ES = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"
}

@dataclass
class SegmentoVideoGuion:
    id_segmento: str
    texto_voz: str
    efecto_visual: str = "ninguno"
    t_inicio_video: Optional[float] = None
    t_fin_video: Optional[float] = None
    pausa_final_seg: float = 0.16
    sfx_lista: List[str] = field(default_factory=list)
    emoji: Optional[str] = None
    posicion_emoji: str = "auto"
    flecha: Optional[str] = None
    circulo: Optional[str] = None
    tamano_circulo: str = "medio"
    track_flecha_activo: bool = False
    track_circulo_activo: bool = False
    callout_flecha: Optional[str] = None
    callout_circulo: Optional[str] = None
    tiene_circulo: bool = False
    tiene_flecha: bool = False
    tiene_emoji: bool = False
    tiene_foto: bool = False
    emoji_nombre: Optional[str] = None
    foto_nombre: Optional[str] = None
    y_subtitulos: int = 1340

    def __post_init__(self) -> None:
        raw_f = str(self.flecha or "").strip().lower()
        if raw_f and raw_f not in ("ninguna", "ninguno", "none", "no", "false", "-", "0", "centro", "auto"):
            self.track_flecha_activo = True
            self.tiene_flecha = True
            if not self.callout_flecha:
                self.callout_flecha = self.flecha
        else:
            self.flecha = None
            self.tiene_flecha = False
            self.track_flecha_activo = False

        raw_c = str(self.circulo or "").strip().lower()
        if raw_c and raw_c not in ("ninguna", "ninguno", "none", "no", "false", "-", "0", "centro", "auto"):
            self.track_circulo_activo = True
            self.tiene_circulo = True
            if not self.callout_circulo:
                self.callout_circulo = self.circulo
        else:
            self.circulo = None
            self.tiene_circulo = False
            self.track_circulo_activo = False

        if self.emoji:
            self.tiene_emoji = True
            if not self.emoji_nombre:
                self.emoji_nombre = self.emoji

@dataclass
class ConfigGuion:
    titulo_superior: str = ""
    titulo_youtube: str = ""
    descripcion_youtube: str = ""
    estado_publicacion: str = "privado"
    schedule: Optional[str] = None
    para_ninos: bool = False
    tags_youtube: List[str] = field(default_factory=list)
    modo_encuadre: str = MODO_ENCUADRE_DEFAULT
    voz_narrador: str = EDGE_VOICE_DEFAULT
    archivo_salida: Optional[str] = None
    volumen_video_original: float = VOLUMEN_AUDIO_VIDEO_ORIGINAL
    volumen_musica: float = VOLUMEN_MUSICA_FONDO
    tono_video: str = "fondo"
    duracion_callouts: float = DURACION_CALLOUTS_DEFAULT
    incluir_outro_like: bool = True
    palabras_verdes_extra: Set[str] = field(default_factory=set)
    palabras_rojas_extra: Set[str] = field(default_factory=set)
    palabras_cian_extra: Set[str] = field(default_factory=set)
    segmentos: List[SegmentoVideoGuion] = field(default_factory=list)

@dataclass
class PalabraSubtitulo:
    texto: str
    inicio_seg: float
    fin_seg: float
    forzar_destaque: bool = False

@dataclass
class ObjetivoCirculoIA:
    activo: bool
    xc_pct: float = 50.0
    yc_pct: float = 50.0
    ancho_pct: float = 18.0
    alto_pct: float = 18.0
    tamanoPreset: str = "medio"
    t_ancla: Optional[float] = None
    etiqueta: str = ""
    formato_legacy: str = "ninguno"

def parsear_altura_subtitulos(altura_val: Any) -> int:
    """Convierte un valor de altura (ej: '70%', '1340', 'arriba', 'medio', 'abajo') a píxeles Y sobre 1920."""
    if not altura_val:
        return 1340
    raw = str(altura_val).strip().lower()
    if not raw or raw in ("default", "auto", "normal", "estandar", "estándar", "-"):
        return 1340
    if "arriba" in raw or "top" in raw:
        return 576  # 30%
    if "medio" in raw or "centro" in raw or "center" in raw:
        return 960  # 50%
    if "muy_abajo" in raw or "fondo" in raw:
        return 1574  # 82%
    if "abajo" in raw or "bottom" in raw:
        return 1340  # 70%

    m = re.search(r"(\d+(?:\.\d+)?)", raw)
    if m:
        num = float(m.group(1))
        if "%" in raw or num <= 100.0:
            y_px = int(round((num / 100.0) * 1920.0))
        else:
            y_px = int(round(num))
        return max(240, min(1740, y_px))
    return 1340


def parsear_directiva_circulo(
    texto_columna_circulo: str,
    t_inicio_bloque: float = 0.0,
    t_fin_bloque: float = 5.0,
) -> ObjetivoCirculoIA:
    import re
    raw = str(texto_columna_circulo or "").strip()
    if not raw or raw.lower() in ("ninguno", "none", "no", "false", "-", "0"):
        return ObjetivoCirculoIA(activo=False)

    patron_box = re.compile(
        r"box:\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]"
        r"(?:@(\d+(?:\.\d+)?))?"
        r"(?::([a-zA-Z0-9_\-]+))?",
        re.IGNORECASE
    )
    match = patron_box.search(raw)
    if match:
        ymin, xmin, ymax, xmax = [int(match.group(i)) for i in range(1, 5)]
        t_str = match.group(5)
        etiqueta = match.group(6) or "objeto"

        ymin_p = max(0.0, min(100.0, ymin / 10.0))
        xmin_p = max(0.0, min(100.0, xmin / 10.0))
        ymax_p = max(0.0, min(100.0, ymax / 10.0))
        xmax_p = max(0.0, min(100.0, xmax / 10.0))

        ancho_p = xmax_p - xmin_p
        alto_p = ymax_p - ymin_p
        area_p = (ancho_p * alto_p) / 100.0

        if ancho_p < 1.5 or alto_p < 1.5 or area_p > 42.0 or ancho_p > 75.0 or alto_p > 75.0:
            return ObjetivoCirculoIA(activo=False)

        etiquetas_prohibidas = {"persona", "hombre", "mujer", "chico", "chica", "fondo", "pantalla", "rostro", "cara"}
        if etiqueta.lower() in etiquetas_prohibidas:
            return ObjetivoCirculoIA(activo=False)

        dim_media = (ancho_p + alto_p) / 2.0
        if dim_media < 14.0:
            tamano = "chico"
        elif dim_media < 28.0:
            tamano = "medio"
        else:
            tamano = "grande"

        if t_str is not None:
            t_ancla = float(t_str)
            t_ancla = max(t_inicio_bloque, min(t_fin_bloque, t_ancla))
        else:
            t_ancla = t_inicio_bloque + (t_fin_bloque - t_inicio_bloque) * 0.35

        xc_p = xmin_p + (ancho_p / 2.0)
        yc_p = ymin_p + (alto_p / 2.0)
        return ObjetivoCirculoIA(
            activo=True,
            xc_pct=xc_p,
            yc_pct=yc_p,
            ancho_pct=ancho_p,
            alto_pct=alto_p,
            tamanoPreset=tamano,
            t_ancla=t_ancla,
            etiqueta=etiqueta,
            formato_legacy=f"{xc_p:.1f},{yc_p:.1f}:{tamano}"
        )

    patron_legacy = re.compile(r"^(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)(?::(chico|medio|grande))?$", re.IGNORECASE)
    match_leg = patron_legacy.match(raw)
    if match_leg:
        xc_p = float(match_leg.group(1))
        yc_p = float(match_leg.group(2))
        tamano = (match_leg.group(3) or "medio").lower()
        t_ancla = t_inicio_bloque + (t_fin_bloque - t_inicio_bloque) * 0.35
        return ObjetivoCirculoIA(
            activo=True,
            xc_pct=xc_p,
            yc_pct=yc_p,
            ancho_pct=18.0,
            alto_pct=18.0,
            tamanoPreset=tamano,
            t_ancla=t_ancla,
            etiqueta="legacy_coord",
            formato_legacy=f"{xc_p:.1f},{yc_p:.1f}:{tamano}"
        )

    return ObjetivoCirculoIA(activo=False)

# Horarios pico dinámicos según el día de la semana (0=Lunes, ..., 6=Domingo)
HORARIOS_PICO_POR_DIA: Dict[str, Dict[int, List[str]]] = {
    # Lunes y Martes (Arranque semanal: almuerzo y desconexión tarde/noche)
    "lunes_martes": {
        1: ["19:30"],
        2: ["13:30", "20:00"],
        3: ["13:00", "18:30", "21:00"],
        4: ["12:30", "15:30", "19:00", "21:30"],
        5: ["11:30", "13:30", "17:00", "19:30", "22:00"],
        6: ["10:30", "12:30", "15:00", "17:30", "20:00", "22:00"],
    },
    # Miércoles y Jueves (Mitad de semana: pausas activas y relax nocturno)
    "miercoles_jueves": {
        1: ["20:30"],
        2: ["13:00", "20:30"],
        3: ["12:30", "17:30", "21:00"],
        4: ["11:30", "14:30", "18:00", "21:30"],
        5: ["11:00", "13:30", "16:30", "19:00", "22:00"],
        6: ["10:00", "12:30", "15:00", "17:30", "19:30", "22:00"],
    },
    # Viernes (Jornada que termina temprano y noche de inicio de fin de semana)
    "viernes": {
        1: ["21:00"],
        2: ["13:00", "20:30"],
        3: ["12:30", "17:00", "21:30"],
        4: ["11:30", "14:30", "18:00", "21:30"],
        5: ["11:00", "13:30", "16:30", "19:30", "22:30"],
        6: ["10:00", "12:30", "15:00", "17:00", "19:30", "22:30"],
    },
    # Sábado y Domingo (Fin de semana: ocio matutino tardío, tarde de descanso y prime time nocturno)
    "fin_de_semana": {
        1: ["19:30"],
        2: ["11:30", "20:00"],
        3: ["11:00", "16:00", "20:30"],
        4: ["10:30", "14:30", "18:00", "21:00"],
        5: ["10:00", "12:30", "15:30", "18:30", "21:30"],
        6: ["09:30", "11:30", "14:00", "16:30", "19:00", "21:30"],
    },
}

HORARIOS_PICO_OPTIMOS: Dict[int, List[str]] = HORARIOS_PICO_POR_DIA["miercoles_jueves"]


def _quitar_acentos(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
