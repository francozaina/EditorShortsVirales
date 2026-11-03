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

def realzar_frame_viral(frame: np.ndarray, modo_color: str = "Vibrante Estándar") -> np.ndarray:
    """Realza contraste y saturación con huella visual diferenciada por canal."""
    try:
        import cv2
        if modo_color == "Cálido Intenso":
            alpha_c, beta_c, sat_m = 1.08, 4, 1.18
        elif modo_color == "Frío Cinematográfico":
            alpha_c, beta_c, sat_m = 1.09, -2, 1.08
        elif modo_color == "Alto Contraste Punch":
            alpha_c, beta_c, sat_m = 1.12, 2, 1.15
        else:
            alpha_c, beta_c, sat_m = 1.06, 2, 1.12

        out = cv2.convertScaleAbs(frame, alpha=alpha_c, beta=beta_c)
        hsv = cv2.cvtColor(out, cv2.COLOR_RGB2HSV)
        h, s, v = cv2.split(hsv)
        s = cv2.multiply(s, sat_m)
        out = cv2.cvtColor(cv2.merge((h, s, v)), cv2.COLOR_HSV2RGB)
        if modo_color == "Cálido Intenso":
            out[:, :, 0] = cv2.add(out[:, :, 0], 5)
        elif modo_color == "Frío Cinematográfico":
            out[:, :, 2] = cv2.add(out[:, :, 2], 6)
        return out
    except Exception:
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
        "OUTRO_LIKE: si",
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


def recortar_frame_916_pil(frame_rgb: np.ndarray, w: int = 270, h: int = 480) -> Image.Image:
    """
    Recorta el fotograma centrando en relación 9:16 (idéntico al filtro scale+crop de FFmpeg en modo 'full')
    y lo redimensiona a (w, h) para que la vista previa del editor manual coincida píxel a píxel con el render final.
    """
    fh, fw = frame_rgb.shape[:2]
    if fh > 0 and fw > 0:
        target_ratio = float(w) / float(h)
        curr_ratio = float(fw) / float(fh)
        if abs(curr_ratio - target_ratio) > 0.015:
            if curr_ratio > target_ratio:
                new_w = max(1, int(round(fh * target_ratio)))
                x0 = (fw - new_w) // 2
                frame_rgb = frame_rgb[:, x0 : x0 + new_w]
            else:
                new_h = max(1, int(round(fw / target_ratio)))
                y0 = (fh - new_h) // 2
                frame_rgb = frame_rgb[y0 : y0 + new_h, :]
    return Image.fromarray(frame_rgb).resize((w, h), Image.Resampling.LANCZOS)


def parsear_directiva_asset_manual(
    raw_str: Optional[str],
    tipo: str = "circulo",
    t_ini_bloque: float = 0.0,
    t_fin_bloque: float = 4.0,
) -> dict:
    """
    Parsea de forma unificada cualquier especificación de flecha, círculo o emoji:
    Soporta coordenadas X,Y porcentuales, prefijo fijo:, rotación @grados,
    escala exacta *factor (o :chico/:medio/:grande) y ventana temporal ~ini-fin.
    """
    dur_bloque = max(0.2, float(t_fin_bloque) - float(t_ini_bloque))
    res = {
        "activo": False,
        "tipo": tipo,
        "nombre": tipo,
        "tracking": False,
        "es_coord_manual": False,
        "es_manual": False,
        "tiene_timing": False,
        "tiene_rot": False,
        "tiene_escala": False,
        "x": 50.0,
        "y": 45.0 if tipo == "circulo" else 50.0,
        "scale": 1.0,
        "tamano_label": "medio",
        "rot": 315.0 if tipo == "flecha" else 0.0,
        "t_ini_rel": 0.0,
        "t_fin_rel": dur_bloque,
        "spec_rastreo": "",
    }
    if not raw_str:
        return res
    s = str(raw_str).strip()
    if not s or s.lower() in ("ninguno", "ninguna", "none", "no", "false", "-", "0"):
        return res

    res["activo"] = True
    s_work = s

    # 1. Detectar prefijo fijo: / static:
    s_low = s_work.lower()
    if "fijo:" in s_low or "static:" in s_low:
        res["tracking"] = False
        res["es_manual"] = True
        s_work = re.sub(r"(?i)\b(fijo|static):", "", s_work).strip()
    else:
        res["tracking"] = True

    # 2. Extraer ventana de tiempo ~ini-fin (en segundos relativos al bloque o absolutos del video)
    m_time = re.search(r"~(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", s_work)
    if m_time:
        res["tiene_timing"] = True
        res["es_manual"] = True
        t1 = float(m_time.group(1))
        t2 = float(m_time.group(2))
        s_work = (s_work[: m_time.start()] + s_work[m_time.end() :]).strip()
        # Si los valores están en el rango absoluto [t_ini_bloque, t_fin_bloque] y t_ini_bloque > 0
        if t_ini_bloque > 0.05 and t1 >= t_ini_bloque - 0.05 and t2 <= t_fin_bloque + 0.25 and t2 > dur_bloque + 0.05:
            t1_rel = max(0.0, t1 - t_ini_bloque)
            t2_rel = min(dur_bloque, t2 - t_ini_bloque)
        else:
            t1_rel = max(0.0, min(dur_bloque - 0.05, t1))
            t2_rel = max(t1_rel + 0.1, min(dur_bloque, t2))
        res["t_ini_rel"] = round(t1_rel, 2)
        res["t_fin_rel"] = round(t2_rel, 2)

    # 3. Extraer escala exacta *factor (si no es box:[...])
    if "box:" not in s_work.lower():
        m_sc = re.search(r"\*(\d+(?:\.\d+)?)", s_work)
        if m_sc:
            res["scale"] = max(0.3, min(3.5, float(m_sc.group(1))))
            res["tiene_escala"] = True
            res["es_manual"] = True
            s_work = (s_work[: m_sc.start()] + s_work[m_sc.end() :]).strip()

        # 4. Extraer rotación @grados
        m_rot = re.search(r"@(-?\d+(?:\.\d+)?)", s_work)
        if m_rot:
            res["rot"] = float(m_rot.group(1)) % 360.0
            res["tiene_rot"] = True
            res["es_manual"] = True
            s_work = (s_work[: m_rot.start()] + s_work[m_rot.end() :]).strip()

    # 5. Extraer modificador de tamaño nominal (:chico, :medio, :grande)
    m_tam = re.search(r":(chico|pequeno|small|min|medio|normal|med|grande|big|large|max)\b", s_work, re.IGNORECASE)
    if m_tam:
        lbl_t = m_tam.group(1).lower()
        if lbl_t in ("chico", "pequeno", "small", "min"):
            res["tamano_label"] = "chico"
            if "*".join(str(raw_str)) and "*" not in str(raw_str):
                res["scale"] = 0.70
        elif lbl_t in ("grande", "big", "large", "max"):
            res["tamano_label"] = "grande"
            if "*" not in str(raw_str):
                res["scale"] = 1.35
        else:
            res["tamano_label"] = "medio"
        s_work = (s_work[: m_tam.start()] + s_work[m_tam.end() :]).strip()
    else:
        if res["scale"] < 0.82:
            res["tamano_label"] = "chico"
        elif res["scale"] > 1.22:
            res["tamano_label"] = "grande"
        else:
            res["tamano_label"] = "medio"

    # 6. Si es emoji, separar nombre:posicion
    if tipo == "emoji":
        if ":" in s_work:
            nom_p, pos_p = s_work.split(":", 1)
            res["nombre"] = nom_p.strip().lower().replace("emoji_", "")
            s_work = pos_p.strip()
        else:
            res["nombre"] = s_work.strip().lower().replace("emoji_", "")
            s_work = "derecha"

    # 7. Coordenadas X,Y o zona nominal
    pos_keyword_map = {
        "derecha": (78.0, 32.0),
        "izquierda": (22.0, 32.0),
        "centro": (50.0, 45.0),
        "arriba": (50.0, 20.0),
        "abajo": (50.0, 80.0),
        "arriba_der": (78.0, 20.0),
        "arriba_izq": (22.0, 20.0),
        "abajo_der": (78.0, 80.0),
        "abajo_izq": (22.0, 80.0),
        "auto": (78.0, 32.0),
    }

    if "box:" in s_work.lower():
        res["spec_rastreo"] = s_work
        m_box = re.search(
            r"\[\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\]",
            s_work,
        )
        if m_box:
            b_ymin, b_xmin, b_ymax, b_xmax = (
                float(m_box.group(1)),
                float(m_box.group(2)),
                float(m_box.group(3)),
                float(m_box.group(4)),
            )
            divisor = 10.0 if max(b_ymin, b_xmin, b_ymax, b_xmax) > 100.0 else 1.0
            xc_b = ((b_xmin + b_xmax) * 0.5) / divisor
            yc_b = ((b_ymin + b_ymax) * 0.5) / divisor
            res["x"] = round(max(5.0, min(95.0, xc_b)), 1)
            res["y"] = round(max(5.0, min(95.0, yc_b)), 1)
        m_anc = re.search(r"@(\d+(?:\.\d+)?)", s_work)
        if m_anc and not res["tiene_timing"]:
            t_anc = float(m_anc.group(1))
            t_rel_a = (t_anc - t_ini_bloque) if (t_ini_bloque > 0.05 and t_anc >= t_ini_bloque - 0.05) else t_anc
            t_rel_a = max(0.0, min(dur_bloque - 0.3, t_rel_a - 0.1))
            res["t_ini_rel"] = round(t_rel_a, 2)
            res["t_fin_rel"] = round(min(dur_bloque, t_rel_a + 1.8), 2)
        return res

    m_xy = re.search(r"(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)", s_work)
    if m_xy:
        res["es_coord_manual"] = True
        res["es_manual"] = True
        res["x"] = max(2.0, min(98.0, float(m_xy.group(1))))
        res["y"] = max(2.0, min(98.0, float(m_xy.group(2))))
        pref_r = "" if res["tracking"] else "fijo:"
        res["spec_rastreo"] = f"{pref_r}{res['x']:.1f},{res['y']:.1f}"
    else:
        k_clean = s_work.split(":")[0].strip().lower()
        res["x"], res["y"] = pos_keyword_map.get(k_clean, (50.0, 45.0))
        pref_r = "" if res["tracking"] else "fijo:"
        res["spec_rastreo"] = f"{pref_r}{k_clean}"

    res["es_manual"] = bool(
        res["es_coord_manual"]
        or (not res["tracking"])
        or res["tiene_timing"]
        or res["tiene_rot"]
        or res["tiene_escala"]
    )
    return res


def formatear_directiva_asset_manual(
    tipo: str,
    nombre: str,
    x: float,
    y: float,
    scale: float = 1.0,
    rot: float = 0.0,
    tracking: bool = False,
    t_ini_rel: Optional[float] = None,
    t_fin_rel: Optional[float] = None,
    dur_bloque: float = 4.0,
) -> str:
    """
    Formatea las propiedades exactas de un sprite manual (posición, escala, rotación,
    tracking y segundo exacto de aparición/desaparición) en la sintaxis del guion.
    """
    pref = "" if tracking else "fijo:"
    sc_val = max(0.3, min(3.5, float(scale)))
    sc_str = f"*{sc_val:.2f}" if abs(sc_val - 1.0) > 0.02 else "*1.00"

    time_str = ""
    if t_ini_rel is not None and t_fin_rel is not None:
        t0 = max(0.0, float(t_ini_rel))
        t1 = max(t0 + 0.1, min(float(dur_bloque), float(t_fin_rel)))
        time_str = f"~{t0:.2f}-{t1:.2f}"

    if tipo == "circulo":
        tam = "chico" if sc_val < 0.82 else ("grande" if sc_val > 1.22 else "medio")
        return f"{pref}{x:.1f},{y:.1f}{sc_str}{time_str}:{tam}"
    elif tipo == "flecha":
        rot_int = int(round(float(rot))) % 360
        return f"{pref}{x:.1f},{y:.1f}@{rot_int}{sc_str}{time_str}"
    else:
        rot_int = int(round(float(rot))) % 360
        rot_str = f"@{rot_int}" if abs(rot_int) > 1 else ""
        return f"{pref}{nombre}:{x:.1f},{y:.1f}{rot_str}{sc_str}{time_str}"


def construir_prompt_argon_con_link(
    url_video: str,
    ruta_video: Optional[Union[str, Path]] = None,
    bloques_actuales: Optional[List[dict]] = None,
    incluir_outro_like: bool = True,
) -> str:
    """
    Construye el prompt completo para Argon incluyendo el link del video, la duración
    exacta detectada, los bloques de tiempo actuales y el catálogo completo de assets y tiempos.
    """
    raiz = Path(__file__).resolve().parent
    ruta_prompt = raiz / "PROMPT_PARA_IA_GUIONES.txt"
    link_limpio = str(url_video or "").strip()
    if not link_limpio or (not link_limpio.startswith("http") and Path(link_limpio).exists()):
        link_limpio = "[PEGA_AQUI_EL_LINK_DE_YOUTUBE_DEL_SHORT]"

    dur_seg = obtener_duracion_video_segundos(ruta_video) if ruta_video else 16.0
    outro_str = "si" if incluir_outro_like else "no"

    if ruta_prompt.exists():
        try:
            texto_base = ruta_prompt.read_text(encoding="utf-8", errors="replace")
        except Exception:
            texto_base = ""
    else:
        texto_base = ""

    if "[PEGAR_LINK_AQUI]" in texto_base:
        texto_base = texto_base.replace("[PEGAR_LINK_AQUI]", link_limpio)
    elif link_limpio:
        texto_base = f"LINK DEL VIDEO A EDITAR: {link_limpio}\n\n" + texto_base

    lineas_bloques = []
    if bloques_actuales:
        for b in bloques_actuales:
            ti = _segundos_a_mm_ss(float(b.get("t_ini", 0.0)))
            tf = _segundos_a_mm_ss(float(b.get("t_fin", 4.0)))
            dur_b = max(1.0, float(b.get("t_fin", 4.0)) - float(b.get("t_ini", 0.0)))
            pal_min = max(3, int(round(dur_b * 3.4)))
            pal_max = max(pal_min + 1, int(round(dur_b * 4.0)))
            lineas_bloques.append(f"  * {ti} - {tf} ({dur_b:.1f}s -> exactamente entre {pal_min} y {pal_max} palabras)")

    contexto_app = [
        "",
        "================================================================================",
        "⚙️ DATOS EXACTOS DETECTADOS POR SHORTS STUDIO PARA ESTE VIDEO:",
        "================================================================================",
        f"- LINK DEL VIDEO: {link_limpio}",
        f"- DURACIÓN EXACTA DEL VIDEO: {dur_seg:.1f} segundos (00:00 hasta {_segundos_a_mm_ss(dur_seg)})",
        f"- ESCENA FINAL DE LIKE (OUTRO_LIKE): {outro_str}",
        "- SINTAXIS AVANZADA DE ASSETS (OPCIONAL):",
        "  * Puedes indicar segundo exacto de aparición y desaparición dentro del bloque con ~ini-fin (ej: derecha~0.4-2.2).",
        "  * Puedes indicar posición exacta X,Y porcentual (ej: 45.0,60.0), giro con @grados (ej: @315) y escala con *factor (ej: *1.20).",
        "  * En el encabezado antes de [GUION] incluye: OUTRO_LIKE: " + outro_str,
    ]
    if lineas_bloques:
        contexto_app.append("- BLOQUES DE TIEMPO ACTUALES EN EL EDITOR:")
        contexto_app.extend(lineas_bloques)

    return texto_base.strip() + "\n" + "\n".join(contexto_app) + "\n"



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
    Limpia de forma segura archivos autogenerados (como guion_video.txt) para evitar conflictos.
    Devuelve (exito, mensaje).
    """
    if raiz_dir is None:
        raiz_dir = Path(__file__).resolve().parent

    try:
        # 1. Restaurar archivos autogenerados o de trabajo que bloquean el pull
        archivos_generados = ["guion_video.txt"]
        for arch in archivos_generados:
            p_arch = Path(raiz_dir) / arch
            if p_arch.exists():
                subprocess.run(
                    ["git", "checkout", "--", arch],
                    cwd=str(raiz_dir),
                    capture_output=True,
                    text=True,
                    timeout=5,
                    startupinfo=WIN_STARTUPINFO,
                    creationflags=WIN_NO_WINDOW,
                )

        # 2. Si todavía hay cambios locales que colisionen, hacer un stash automático
        stashed = False
        stat = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(raiz_dir),
            capture_output=True,
            text=True,
            timeout=5,
            startupinfo=WIN_STARTUPINFO,
            creationflags=WIN_NO_WINDOW,
        )
        if stat.returncode == 0 and stat.stdout.strip():
            stash_res = subprocess.run(
                ["git", "stash", "push", "-m", "backup_auto_update"],
                cwd=str(raiz_dir),
                capture_output=True,
                text=True,
                timeout=10,
                startupinfo=WIN_STARTUPINFO,
                creationflags=WIN_NO_WINDOW,
            )
            stashed = (stash_res.returncode == 0)

        # 3. Pull limpio desde origin main
        res = subprocess.run(
            ["git", "pull", "--no-rebase", "origin", "main"],
            cwd=str(raiz_dir),
            capture_output=True,
            text=True,
            timeout=30,
            startupinfo=WIN_STARTUPINFO,
            creationflags=WIN_NO_WINDOW,
        )

        if stashed:
            try:
                subprocess.run(
                    ["git", "stash", "pop", "--quiet"],
                    cwd=str(raiz_dir),
                    capture_output=True,
                    text=True,
                    timeout=5,
                    startupinfo=WIN_STARTUPINFO,
                    creationflags=WIN_NO_WINDOW,
                )
            except Exception:
                pass

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


# =====================================================================
# 8. AUTOCOMPLETADO INTELIGENTE DE ASSETS Y SINCRONIZACIÓN DE GUION
# =====================================================================
def completar_assets_automaticos_en_guion(
    raw_script: str,
    auto_efectos: bool = False,
    auto_sfx: bool = False,
    auto_emojis: bool = False,
    auto_flechas: bool = False,
    auto_circulos: bool = False,
) -> str:
    """
    Completa de forma inteligente y coherente con la narración las categorías de assets
    que el usuario haya marcado como automáticas en Edición Manual, respetando SIEMPRE
    cualquier asset que el usuario ya haya colocado manualmente en cada bloque.
    """
    if not raw_script or not any((auto_efectos, auto_sfx, auto_emojis, auto_flechas, auto_circulos)):
        return raw_script

    import unicodedata

    def _norm(txt: str) -> str:
        return "".join(
            c for c in unicodedata.normalize("NFD", str(txt or "").lower())
            if unicodedata.category(c) != "Mn"
        )

    def _es_vacio(val: str) -> bool:
        return _norm(val).strip() in ("", "-", "ninguno", "ninguna", "none", "no", "normal", "false", "0")

    def _es_altura_col(s: str) -> bool:
        s_c = _norm(s).strip()
        return s_c in ("arriba", "medio", "centro", "abajo", "muy_abajo", "fondo") or bool(
            re.match(r"^(y:)?\d{1,4}%?$", s_c)
        )

    lineas = raw_script.splitlines()
    en_guion = False
    indices_filas_guion = []
    bloques_parsed = []

    for idx_l, ln in enumerate(lineas):
        l_strip = ln.strip()
        if not l_strip:
            continue
        if l_strip.upper() in ("[GUION]", "[GUIÓN]", "[SCRIPT]", "[SEGMENTOS]"):
            en_guion = True
            continue
        if not en_guion or "|" not in l_strip or l_strip.upper().startswith("TIEMPO"):
            continue

        partes = [p.strip() for p in l_strip.split("|")]
        if len(partes) >= 8 and _es_altura_col(partes[6]):
            b = {
                "tiempo": partes[0],
                "efecto": partes[1],
                "sfx": partes[2],
                "emoji": partes[3],
                "flecha": partes[4],
                "circulo": partes[5],
                "altura": partes[6],
                "texto": " | ".join(partes[7:]).strip(),
            }
        elif len(partes) >= 7:
            b = {
                "tiempo": partes[0],
                "efecto": partes[1],
                "sfx": partes[2],
                "emoji": partes[3],
                "flecha": partes[4],
                "circulo": partes[5],
                "altura": "70%",
                "texto": " | ".join(partes[6:]).strip(),
            }
        else:
            continue
        indices_filas_guion.append(idx_l)
        bloques_parsed.append(b)

    n_b = len(bloques_parsed)
    if n_b == 0:
        return raw_script

    # 1. Auto Flechas (máx 2 en el video, nunca en el último bloque, respetando las manuales)
    if auto_flechas:
        flechas_activas = [i for i, b in enumerate(bloques_parsed) if not _es_vacio(b["flecha"])]
        cupo_f = max(0, 2 - len(flechas_activas))
        if cupo_f > 0:
            candidatos_f = []
            for i in range(max(1, n_b - 1)):
                if i in flechas_activas:
                    continue
                if any(abs(i - fa) <= 1 for fa in flechas_activas):
                    continue
                t_n = _norm(bloques_parsed[i]["texto"])
                score_f = 1
                if any(k in t_n for k in ("mira", "alli", "ahi", "detalle", "esconde", "centro", "secreto", "arriba", "abajo", "fondo", "lado", "puerta", "espejo", "cara", "mano")):
                    score_f += 3
                if i == 0 or i == n_b // 2:
                    score_f += 1
                candidatos_f.append((score_f, i))
            candidatos_f.sort(key=lambda x: (-x[0], x[1]))
            elegidos_f = []
            for _, idx_c in candidatos_f:
                if len(elegidos_f) >= cupo_f:
                    break
                if any(abs(idx_c - ef) <= 1 for ef in elegidos_f):
                    continue
                elegidos_f.append(idx_c)
                dir_f = "izquierda" if (idx_c % 2 == 0) else "derecha"
                bloques_parsed[idx_c]["flecha"] = dir_f

    # 2. Auto Círculos (máx 1 en el video en el momento clave, respetando los manuales)
    if auto_circulos:
        circulos_activos = [i for i, b in enumerate(bloques_parsed) if not _es_vacio(b["circulo"])]
        if len(circulos_activos) == 0:
            mejor_idx_c = min(max(0, n_b // 2), max(0, n_b - 2))
            mejor_score_c = -1
            for i in range(max(1, n_b - 1)):
                t_n = _norm(bloques_parsed[i]["texto"])
                sc = 1
                if any(k in t_n for k in ("centro", "justo", "exacto", "oculto", "error", "truco", "clave", "objeto", "punto", "detalle")):
                    sc += 3
                if _es_vacio(bloques_parsed[i]["flecha"]):
                    sc += 1
                if sc > mejor_score_c:
                    mejor_score_c = sc
                    mejor_idx_c = i
            bloques_parsed[mejor_idx_c]["circulo"] = "50.0,45.0:medio"

    # 3. Auto Efectos, SFX y Emojis por bloque (respetando los ya puestos por el usuario)
    prev_efecto = ""
    prev_sfx = ""
    prev_emoji = ""

    efectos_ciclo = ["zoom_in", "spotlight", "zoom_out", "alerta_roja", "temblor"]
    sfx_ciclo = ["whoosh", "riser_suction", "metal_pipe", "vine_boom", "pop"]
    emojis_ciclo = ["sorprendido", "ojos", "fuego", "cerebro", "risa", "diablo"]

    for i, b in enumerate(bloques_parsed):
        t_n = _norm(b["texto"])

        # A) EFECTO
        if auto_efectos and _es_vacio(b["efecto"]):
            if i == 0:
                ef_nuevo = "zoom_impacto"
            elif i == n_b - 1:
                ef_nuevo = "brillo_epico"
            elif any(k in t_n for k in ("peligro", "trampa", "error", "mal", "peor", "alarma", "fuego", "fatal", "muerte", "encerrado", "atrapado")):
                ef_nuevo = "alerta_roja"
            elif any(k in t_n for k in ("golpe", "choca", "cae", "rompe", "explota", "impacto", "temblor", "fuerza", "salta", "corre")):
                ef_nuevo = "temblor" if prev_efecto != "temblor" else "zoom_impacto"
            elif any(k in t_n for k in ("mira", "secreto", "detalle", "oculto", "esconde", "centro", "observa", "nadie")):
                ef_nuevo = "spotlight" if prev_efecto != "spotlight" else "zoom_in"
            elif any(k in t_n for k in ("triste", "solo", "perdido", "oscuridad", "llora", "pena")):
                ef_nuevo = "blanco_negro"
            elif any(k in t_n for k in ("repente", "increible", "imposible", "sorpresa", "flash", "espejo", "reflejo")):
                ef_nuevo = "flash" if prev_efecto != "flash" else "zoom_in"
            else:
                ef_nuevo = efectos_ciclo[i % len(efectos_ciclo)]
                if ef_nuevo == prev_efecto:
                    ef_nuevo = efectos_ciclo[(i + 1) % len(efectos_ciclo)]
            b["efecto"] = ef_nuevo
        prev_efecto = b["efecto"]

        # B) SFX
        if auto_sfx and _es_vacio(b["sfx"]):
            if any(k in t_n for k in ("idea", "genio", "inteligente", "solucion", "logra", "descubre", "truco", "plan", "astuto", "ingenio")):
                sfx_nuevo = "good_idea" if prev_sfx != "good_idea" else "ding"
            elif any(k in t_n for k in ("dinero", "millon", "oro", "caro", "fortuna", "gana", "premio", "rico", "dolar")):
                sfx_nuevo = "cash_ting"
            elif any(k in t_n for k in ("golpe", "punetazo", "rompe", "choca", "patea", "aplasta", "cae")):
                sfx_nuevo = "punch" if prev_sfx != "punch" else "metal_pipe"
            elif any(k in t_n for k in ("error", "falla", "equivoca", "trampa", "fracaso", "mal", "inutil")):
                sfx_nuevo = "xp_Error" if prev_sfx != "xp_Error" else "error"
            elif any(k in t_n for k in ("risa", "gracioso", "ridiculo", "burla", "karma", "tonto", "payaso", "chiste")):
                sfx_nuevo = "cartoon_laugh" if prev_sfx != "cartoon_laugh" else "pop"
            elif any(k in t_n for k in ("llora", "triste", "atrapado", "encerrado", "pena", "pobre", "perdido")):
                sfx_nuevo = "heartbeat_fast" if prev_sfx != "heartbeat_fast" else "awww"
            elif any(k in t_n for k in ("miedo", "tension", "corazon", "laberinto", "peligro", "cuidado", "nervios", "pavor")):
                sfx_nuevo = "heartbeat_fast" if prev_sfx != "heartbeat_fast" else "riser_suction"
            elif any(k in t_n for k in ("foto", "camara", "espejo", "reflejo", "imagen", "brillo")):
                sfx_nuevo = "camera_flash"
            elif i == n_b - 1 or any(k in t_n for k in ("fiesta", "celebra", "victoria", "escapar", "escapo", "libre", "exito", "logro")):
                sfx_nuevo = "party_horn" if prev_sfx != "party_horn" else "kids_yeyy"
            elif any(k in t_n for k in ("espera", "frena", "detiene", "imposible")):
                sfx_nuevo = "record_scratch"
            elif i == 0:
                sfx_nuevo = "crowd_shocked"
            else:
                sfx_nuevo = sfx_ciclo[i % len(sfx_ciclo)]
                if sfx_nuevo == prev_sfx:
                    sfx_nuevo = sfx_ciclo[(i + 1) % len(sfx_ciclo)]
            b["sfx"] = sfx_nuevo
        prev_sfx = b["sfx"]

        # C) EMOJI
        if auto_emojis and _es_vacio(b["emoji"]):
            if any(k in t_n for k in ("idea", "cerebro", "inteligente", "genio", "plan", "truco", "penso", "mente", "estrategia", "astuto")):
                em_nom = "cerebro"
            elif any(k in t_n for k in ("mira", "ojos", "ver", "espejo", "reflejo", "observa", "detalle", "oculto", "busca")):
                em_nom = "ojos"
            elif any(k in t_n for k in ("llora", "triste", "atrapado", "perdido", "encerrado", "solo", "dolor", "pena")):
                em_nom = "lloro"
            elif any(k in t_n for k in ("risa", "reir", "gracioso", "burla", "tonto", "ridiculo", "chiste", "divertido")):
                em_nom = "risa"
            elif any(k in t_n for k in ("diablo", "karma", "trampa", "maldad", "venganza", "castigo", "engano", "confundir")):
                em_nom = "diablo"
            elif any(k in t_n for k in ("enojo", "enojado", "furia", "bronca", "pelea", "odio", "grita", "furioso")):
                em_nom = "enojo"
            elif any(k in t_n for k in ("muerte", "peligro", "fatal", "calavera", "imposible", "miedo", "terror", "peor")):
                em_nom = "calavera"
            elif any(k in t_n for k in ("sueno", "dormir", "cansado", "lento", "aburrido", "horas", "tiempo")):
                em_nom = "sueno"
            elif any(k in t_n for k in ("fuego", "epico", "brutal", "increible", "explosion", "calor", "llama", "potencia")):
                em_nom = "fuego"
            elif i == n_b - 1 or any(k in t_n for k in ("fiesta", "escapar", "escapo", "logro", "gano", "exito", "salida", "libre", "celebra", "victoria")):
                em_nom = "fiesta"
            else:
                em_nom = emojis_ciclo[i % len(emojis_ciclo)]
            if em_nom == prev_emoji:
                for alt_em in emojis_ciclo:
                    if alt_em != prev_emoji:
                        em_nom = alt_em
                        break

            # Elegir lado opuesto a la flecha o círculo del bloque para evitar superposición
            lado_em = "derecha" if (i % 2 == 0) else "izquierda"
            for ref_raw, ref_tipo in ((b["flecha"], "flecha"), (b["circulo"], "circulo")):
                if not _es_vacio(ref_raw):
                    m_ref = parsear_directiva_asset_manual(ref_raw, ref_tipo, 0.0, 4.0)
                    if m_ref.get("activo"):
                        lado_em = "izquierda" if float(m_ref.get("x", 50.0)) >= 50.0 else "derecha"
                        break
            b["emoji"] = f"{em_nom}:{lado_em}"
        prev_emoji = b["emoji"].split(":")[0].replace("fijo:", "").strip()

    for idx_fila, b in zip(indices_filas_guion, bloques_parsed):
        lineas[idx_fila] = (
            f"{b['tiempo']} | {b['efecto']} | {b['sfx']} | "
            f"{b['emoji']} | {b['flecha']} | {b['circulo']} | {b['altura']} | {b['texto']}"
        )

    return "\n".join(lineas) + "\n"


def sincronizar_guion_renderizado_en_disco(ruta_guion: Union[str, Path], segmentos_renderizados: list) -> None:
    """
    Actualiza las filas de [GUION] en ruta_guion con los efectos, SFX, emojis, flechas,
    círculos y tiempos que efectivamente quedaron aplicados tras el renderizado,
    para que al abrir el menú de revisión/edición manual aparezcan por defecto tal cual.
    """
    try:
        p_guion = Path(ruta_guion)
        if not p_guion.exists() or not segmentos_renderizados:
            return
        contenido = p_guion.read_text(encoding="utf-8", errors="replace")
        if contenido.lstrip().startswith("{"):
            return

        lineas_cabecera = []
        for ln in contenido.splitlines():
            l_strip = ln.strip()
            if l_strip.upper() in ("[GUION]", "[GUIÓN]", "[SCRIPT]", "[SEGMENTOS]"):
                break
            lineas_cabecera.append(ln)

        def _fmt_mmss(seg_f: float) -> str:
            s_tot = max(0, int(round(float(seg_f or 0.0))))
            return f"{s_tot // 60:02d}:{s_tot % 60:02d}"

        lineas_out = list(lineas_cabecera)
        if lineas_out and lineas_out[-1].strip() != "":
            lineas_out.append("")
        lineas_out.append("[GUION]")
        lineas_out.append("TIEMPO | EFECTO | SFX | EMOJI | FLECHA | CIRCULO | ALTURA | TEXTO")

        for seg in segmentos_renderizados:
            t_i = float(getattr(seg, "t_inicio_video", 0.0) or 0.0)
            t_f = float(getattr(seg, "t_fin_video", t_i + 4.0) or (t_i + 4.0))
            tiempo_str = f"{_fmt_mmss(t_i)} - {_fmt_mmss(t_f)}"

            ef_str = str(getattr(seg, "efecto_visual", "ninguno") or "ninguno").strip()
            if ef_str.lower() in ("", "-", "none", "normal"):
                ef_str = "ninguno"

            sfx_list = getattr(seg, "sfx_lista", None) or []
            sfx_str = "+".join(str(x).strip() for x in sfx_list if str(x).strip()) if sfx_list else "ninguno"

            em_raw = getattr(seg, "emoji", None)
            pos_em = str(getattr(seg, "posicion_emoji", "auto") or "auto").strip()
            if em_raw and str(em_raw).strip().lower() not in ("", "-", "ninguno", "ninguna", "none"):
                em_s = str(em_raw).strip()
                if "+" in em_s or ":" in em_s:
                    em_str = em_s
                elif pos_em and pos_em.lower() not in ("", "auto", "multi"):
                    if pos_em.lower().startswith("fijo:"):
                        em_str = f"fijo:{em_s}:{pos_em[5:]}"
                    else:
                        em_str = f"{em_s}:{pos_em}"
                else:
                    em_str = f"{em_s}:derecha"
            else:
                em_str = "ninguno"

            fl_raw = getattr(seg, "flecha", None)
            fl_str = str(fl_raw).strip() if (fl_raw and str(fl_raw).strip().lower() not in ("", "-", "ninguno", "ninguna", "none")) else "ninguna"

            ci_raw = getattr(seg, "circulo", None)
            tam_ci = str(getattr(seg, "tamano_circulo", "medio") or "medio").strip()
            if ci_raw and str(ci_raw).strip().lower() not in ("", "-", "ninguno", "ninguna", "none"):
                ci_s = str(ci_raw).strip()
                if not re.search(r":(chico|medio|grande)\b", ci_s, re.IGNORECASE) and "box:" not in ci_s.lower():
                    ci_str = f"{ci_s}:{tam_ci}"
                else:
                    ci_str = ci_s
            else:
                ci_str = "ninguno"

            y_sub = int(getattr(seg, "y_subtitulos", 1344) or 1344)
            alt_pct = max(15, min(85, int(round((y_sub / 1920.0) * 100.0))))
            alt_str = f"{alt_pct}%"

            txt_voz = str(getattr(seg, "texto_voz", "") or "").strip()
            lineas_out.append(
                f"{tiempo_str} | {ef_str} | {sfx_str} | {em_str} | {fl_str} | {ci_str} | {alt_str} | {txt_voz}"
            )

        p_guion.write_text("\n".join(lineas_out) + "\n", encoding="utf-8")
    except Exception:
        pass




