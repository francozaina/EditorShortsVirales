# -*- coding: utf-8 -*-
"""
Módulo de alto rendimiento y utilidades optimizadas para Shorts Studio.
Contiene caché de máscaras, semántica de colores de subtítulos, validación de ritmo
y conteo de palabras (3.7 pal/s), recorte de silencios TTS y micro-color grading.
"""

import os
import re
import sys
import subprocess
from pathlib import Path
from typing import Union, Optional, List, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont

WIN_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
WIN_STARTUPINFO = None
if sys.platform == "win32":
    WIN_STARTUPINFO = subprocess.STARTUPINFO()
    WIN_STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    WIN_STARTUPINFO.wShowWindow = subprocess.SW_HIDE

# =====================================================================
# 1. CACHÉ GLOBAL DE MÁSCARAS Y COLORES SEMÁNTICOS
# =====================================================================
_RADIAL_MASK_CACHE = {}

PALABRAS_PELIGRO = {
    "trampa", "peligro", "cuidado", "error", "venganza", "golpe", "caída",
    "mira", "secreto", "falso", "engaño", "engaña", "nunca", "jamás", "peor",
    "destroza", "explosión", "robo", "culpa", "miedo", "terror", "ataque"
}

PALABRAS_EXITO = {
    "victoria", "ganador", "épica", "épico", "genial", "increíble", "dinero",
    "premio", "millones", "fortuna", "perfecta", "perfecto", "logra", "triunfo",
    "maestro", "campeón", "oro", "récord", "inteligente", "astuta", "astuto"
}

def obtener_mascara_radial(h: int, w: int) -> np.ndarray:
    """Devuelve la máscara radial precalculada en float32 (evita np.ogrid en cada frame)."""
    key = (h, w)
    if key not in _RADIAL_MASK_CACHE:
        Y, X = np.ogrid[:h, :w]
        cy, cx = h / 2.0, w / 2.0
        max_dist = np.sqrt(cx**2 + cy**2)
        dist = np.sqrt((X - cx)**2 + (Y - cy)**2) / max_dist
        mask = np.clip((dist - 0.35) / 0.65, 0.0, 1.0).astype(np.float32)
        _RADIAL_MASK_CACHE[key] = mask[:, :, np.newaxis]
    return _RADIAL_MASK_CACHE[key]

def aplicar_alerta_roja_rapida(frame: np.ndarray, t: float) -> np.ndarray:
    """Aplica la viñeta alerta_roja usando la máscara en caché a máxima velocidad."""
    h, w = frame.shape[:2]
    mask = obtener_mascara_radial(h, w)
    pulso = 0.55 + 0.45 * np.sin(t * 10.0)
    intensidad = mask * (0.65 * pulso)

    out = frame.astype(np.float32)
    out[:, :, 0] = out[:, :, 0] * (1.0 - intensidad[:, :, 0]) + 255.0 * intensidad[:, :, 0]
    out[:, :, 1] = out[:, :, 1] * (1.0 - intensidad[:, :, 0] * 0.85)
    out[:, :, 2] = out[:, :, 2] * (1.0 - intensidad[:, :, 0] * 0.85)
    return np.clip(out, 0, 255).astype(np.uint8)

def obtener_color_semantico(palabra: str, idx_global: int) -> tuple:
    """Determina el color RGBA de la palabra activa según su semántica viral."""
    limpia = re.sub(r'[^\wáéíóúñÁÉÍÓÚÑ]', '', palabra).lower()
    if limpia in PALABRAS_PELIGRO:
        return (255, 45, 45, 255)   # Rojo Neón (Peligro / Tensión)
    if limpia in PALABRAS_EXITO:
        return (0, 255, 102, 255)   # Verde Vibrante (Éxito / Premio)
    if "!" in palabra or "¡" in palabra or "?" in palabra or "¿" in palabra:
        return (255, 230, 0, 255)   # Amarillo MrBeast
    return (255, 230, 0, 255) if idx_global % 2 == 0 else (0, 245, 255, 255)


# =====================================================================
# 2. VALIDADOR DE RITMO Y CONTEO DE PALABRAS (3.7 PALABRAS / SEG)
# =====================================================================
def parsear_segundos_rango(rango_str: str) -> float:
    """Convierte '00:00 - 00:05' en la duración en segundos (ej. 5.0)."""
    try:
        partes = rango_str.split("-")
        def a_seg(mm_ss):
            p = mm_ss.strip().split(":")
            return int(p[0]) * 60 + float(p[1])
        return max(0.5, a_seg(partes[1]) - a_seg(partes[0]))
    except Exception:
        return 5.0

def evaluar_ritmo_bloque(rango_tiempo: str, texto: str) -> dict:
    """
    Evalúa si el bloque cumple la regla de 3.7 palabras/segundo.
    Retorna dict con: palabras, duracion, pps, estado ('OK', 'CORTO', 'LARGO'), etiqueta.
    """
    dur = parsear_segundos_rango(rango_tiempo)
    palabras_lista = [p for p in texto.strip().split() if p]
    n_pal = len(palabras_lista)
    pps = n_pal / dur if dur > 0 else 0.0

    # Rangos ideales según duración (base 3.7 pal/seg)
    min_ideal = max(1, int(round(dur * 3.4)))
    max_ideal = int(round(dur * 4.0))

    if n_pal < min_ideal:
        estado = "CORTO"
        icono = "⚠️ Corto"
    elif n_pal > max_ideal:
        estado = "LARGO"
        icono = "🚨 Largo"
    else:
        estado = "OK"
        icono = "✅ OK"

    etiqueta = f"{n_pal} pal ({pps:.1f}/s) {icono}"
    return {
        "palabras": n_pal,
        "duracion": dur,
        "pps": round(pps, 2),
        "min_ideal": min_ideal,
        "max_ideal": max_ideal,
        "estado": estado,
        "etiqueta": etiqueta
    }


# =====================================================================
# 3. LIMPIEZA DE SILENCIOS TTS Y AJUSTE PRECISO DE AUDIO CON FFMPEG
# =====================================================================
def recortar_silencios_tts(input_audio: str, output_audio: str, ffmpeg_exe: str = "ffmpeg") -> bool:
    """
    Elimina los silencios muertos al inicio y al final que deja edge-tts
    para que los bloques se encadenen sin pausas artificiales.
    """
    try:
        filtro = (
            "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-42dB,"
            "areverse,"
            "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-42dB,"
            "areverse"
        )
        cmd = [
            ffmpeg_exe, "-y", "-i", input_audio,
            "-af", filtro,
            output_audio
        ]
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            creationflags=WIN_NO_WINDOW,
            startupinfo=WIN_STARTUPINFO,
        )
        return os.path.exists(output_audio) and os.path.getsize(output_audio) > 512
    except Exception:
        return False


# =====================================================================
# 4. MICRO-COLOR GRADING RÁPIDO (ANTI-REUSED CONTENT Y MAYOR IMPACTO)
# =====================================================================
_LUT_CONTRASTE = np.clip((np.arange(256, dtype=np.float32) - 128.0) * 1.06 + 130.0, 0, 255).astype(np.uint8)

def realzar_frame_viral(frame: np.ndarray) -> np.ndarray:
    """Aplica una tabla LUT instantánea (+6% contraste y brillo sutil) en <0.6ms con SIMD in-place."""
    try:
        import cv2
        return cv2.LUT(frame, _LUT_CONTRASTE, dst=frame)
    except Exception:
        return _LUT_CONTRASTE[frame]


# =====================================================================
# 5. BLENDING VECTORIZADO ZERO-COPY POR ROI (SUBTÍTULOS Y PLACAS)
# =====================================================================
def pegar_placa_rgba_rapida(frame_rgb: np.ndarray, placa_rgba: np.ndarray, y_top: int = 0) -> np.ndarray:
    """
    Alpha-blending ultrarrápido en uint16 sobre la ROI sin convertir a float32
    ni tocar píxeles fuera de la caja del subtítulo.
    """
    h_f, w_f, _ = frame_rgb.shape
    h_p, w_p, _ = placa_rgba.shape
    y1 = max(0, y_top)
    y2 = min(h_f, y1 + h_p)
    x2 = min(w_f, w_p)
    if y2 <= y1 or x2 <= 0:
        return frame_rgb

    sub_placa = placa_rgba[:(y2 - y1), :x2]
    alpha = sub_placa[:, :, 3:4]
    if not np.any(alpha > 2):
        return frame_rgb

    out = frame_rgb if frame_rgb.flags.writeable else frame_rgb.copy()
    roi = out[y1:y2, :x2].astype(np.uint16)
    fg = sub_placa[:, :, :3].astype(np.uint16)
    a = alpha.astype(np.uint16)
    out[y1:y2, :x2] = ((fg * a + roi * (255 - a)) // 255).astype(np.uint8)
    return out


# =====================================================================
# 6. PLANTILLA MANUAL DE GUIONES Y CÁLCULO DE DURACIÓN
# =====================================================================
def obtener_duracion_video_segundos(ruta_video: Union[str, Path]) -> float:
    """Devuelve la duración exacta en segundos de un archivo de video."""
    try:
        import cv2
        cap = cv2.VideoCapture(str(ruta_video))
        if not cap.isOpened():
            return 15.0
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        frames = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
        if fps > 0 and frames > 0:
            return round(frames / fps, 2)
    except Exception:
        pass
    return 15.0


def _segundos_a_mm_ss(segundos: float) -> str:
    s = max(0, int(round(segundos)))
    m = s // 60
    resto = s % 60
    return f"{m:02d}:{resto:02d}"


def generar_plantilla_guion_manual(
    ruta_video: Union[str, Path],
    titulo_sugerido: str = "",
    sched_str: str = "auto",
    modo_priv: str = "privado",
    modo_encuadre: str = "full",
    descripcion_custom: str = "",
) -> str:
    """
    Genera un archivo de guion base listo para el modo de Edición Manual.
    Segmenta el video en bloques de 3.5 a 4.5 segundos cubriendo la duración exacta,
    dejando el texto vacío para redacción manual directa del usuario.
    """
    dur_total = obtener_duracion_video_segundos(ruta_video)
    if dur_total < 3.0:
        dur_total = 15.0

    dur_bloque = 4.0
    num_bloques = max(1, int(round(dur_total / dur_bloque)))
    paso = dur_total / num_bloques

    tit_limpio = (titulo_sugerido or Path(ruta_video).stem).replace("_", " ").title()
    desc_final = descripcion_custom or f"{tit_limpio} #shorts #viral"
    if "#shorts" not in desc_final.lower():
        desc_final += " #shorts"

    lineas = [
        f"TITULO_SUPERIOR: {tit_limpio}",
        f"TITULO_YOUTUBE: {tit_limpio} #shorts",
        f"MODO_ENCUADRE: {modo_encuadre}",
        "VOLUMEN_VIDEO_ORIGINAL: 0",
        "ARCHIVO_SALIDA: auto",
        f"DESCRIPCION_YOUTUBE: {desc_final}",
        f"ESTADO_PUBLICACION: {modo_priv}",
        f"SCHEDULE: {sched_str}",
        "PARA_NINOS: no",
        "TONO_VIDEO: auto",
        "",
        "[GUION]",
        "TIEMPO | EFECTO | SFX | EMOJI | FLECHA | CIRCULO | ALTURA | TEXTO",
    ]

    t_actual = 0.0
    for i in range(num_bloques):
        t_sig = min(dur_total, t_actual + paso) if i < num_bloques - 1 else dur_total
        t_inicio_str = _segundos_a_mm_ss(t_actual)
        t_fin_str = _segundos_a_mm_ss(t_sig)
        efecto = "zoom_impacto" if i == 0 else "normal"
        lineas.append(f"{t_inicio_str} - {t_fin_str} | {efecto} | ninguno | ninguno | ninguno | ninguno | 70% | ")
        t_actual = t_sig

    return "\n".join(lineas) + "\n"


# =====================================================================
# 7. GESTOR DE ACTUALIZACIONES AUTOMÁTICAS DESDE GIT
# =====================================================================
def comprobar_actualizacion_repo(raiz_dir: Optional[Union[str, Path]] = None) -> Tuple[bool, int, str]:
    """
    Comprueba de forma silenciosa si el repositorio remoto (origin/main) tiene nuevos commits.
    Devuelve (hay_actualizacion, cantidad_commits, mensaje).
    """
    if raiz_dir is None:
        raiz_dir = Path(__file__).resolve().parent

    try:
        fetch_res = subprocess.run(
            ["git", "fetch", "origin", "main", "--quiet"],
            cwd=str(raiz_dir),
            capture_output=True,
            text=True,
            timeout=8,
            startupinfo=WIN_STARTUPINFO,
            creationflags=WIN_NO_WINDOW,
        )
        if fetch_res.returncode != 0:
            return False, 0, "No se pudo conectar con el repositorio remoto."

        count_res = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            cwd=str(raiz_dir),
            capture_output=True,
            text=True,
            timeout=5,
            startupinfo=WIN_STARTUPINFO,
            creationflags=WIN_NO_WINDOW,
        )
        if count_res.returncode == 0:
            cant = int(count_res.stdout.strip() or 0)
            if cant > 0:
                return True, cant, f"Hay {cant} cambio{'s' if cant != 1 else ''} nuevo{'s' if cant != 1 else ''} en GitHub"
            return False, 0, "Al día"
    except Exception as e:
        return False, 0, f"Error: {e}"
    return False, 0, "Al día"


def ejecutar_actualizacion_repo(raiz_dir: Optional[Union[str, Path]] = None) -> Tuple[bool, str]:
    """
    Ejecuta git pull origin main para actualizar el código local a la última versión.
    Devuelve (exito, mensaje).
    """
    if raiz_dir is None:
        raiz_dir = Path(__file__).resolve().parent

    try:
        res = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=str(raiz_dir),
            capture_output=True,
            text=True,
            timeout=30,
            startupinfo=WIN_STARTUPINFO,
            creationflags=WIN_NO_WINDOW,
        )
        if res.returncode == 0:
            out = res.stdout.strip()
            if "Already up to date" in out or "Ya está actualizado" in out:
                return True, "La app ya está en la última versión disponible."
            return True, "Actualización completada con éxito."
        else:
            err = res.stderr.strip() or res.stdout.strip()
            return False, f"Fallo al actualizar: {err[:140]}"
    except Exception as e:
        return False, f"Excepción durante actualización: {e}"



