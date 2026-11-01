# -*- coding: utf-8 -*-
"""
shorts_engine/gemini_ia.py
Módulo de generación de guiones virales con Gemini API / Argon 4.
Arquitectura de Alta Disponibilidad:
- Fast-Probing asíncrono (<800ms) sobre pool multi-cuenta.
- Single-Pass Master Prompt con video inline en RAM (Part.from_bytes).
- Conmutación instantánea a Mosaico JPEG (16 frames Contact Sheet) ante saturación 503.
- Auditoría determinista local en Python (0 tokens, <5ms).
"""

import os
import sys
import cv2
import numpy as np
import json
import re
import time
import asyncio
import logging
import threading
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Set


def _llamar_gemini_cancelable(fn_llamada: Callable, cancelar_check: Optional[Callable[[], bool]] = None):
    """Ejecuta generate_content en un hilo daemon y permite abortar en <150ms si el usuario frena."""
    if not cancelar_check:
        return fn_llamada()

    resultado = {"resp": None, "err": None, "listo": False}

    def _worker():
        try:
            resultado["resp"] = fn_llamada()
        except Exception as ex:
            resultado["err"] = ex
        finally:
            resultado["listo"] = True

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    while not resultado["listo"]:
        if cancelar_check():
            raise InterruptedError("Generación de guion con IA cancelada instantáneamente por el usuario.")
        time.sleep(0.12)

    if resultado["err"] is not None:
        raise resultado["err"]
    return resultado["resp"]
from PIL import Image, ImageDraw
from google import genai
from google.genai import types
from google.genai.errors import APIError

from .video_render import obtener_info_video
from .youtube_manager import ULTIMA_INFO_YTDLP
from .config import (
    BASE_DIR, TEMP_DIR, DEFAULT_GUION_TXT, PROMPT_IA_PATH, PROMPT_COMPACTO_PATH,
    WIN_NO_WINDOW, WIN_STARTUPINFO
)
from motor_optimizado import evaluar_ritmo_bloque

logger = logging.getLogger("ShortsStudio.GeminiIA")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

GEMINI_KEY_FILE = BASE_DIR / "gemini_api_key.txt"

# =====================================================================
# CONFIGURACIÓN DE JERARQUÍA DE MODELOS Y CATÁLOGOS ESTRICTOS
# =====================================================================
MODEL_HIERARCHY = [
    "gemini-4-argon",        # Prioridad 1: Cuentas con facturación / Tier superior
    "gemini-3.8-flash",      # Prioridad 2: Razonamiento top
    "gemini-3.6-flash",      # Prioridad 3: Fallback ultra-estable
    "gemini-3.5-flash-lite", # Prioridad 4: Cuota muy amplia
    "gemini-3.1-flash-lite", # Prioridad 5: Fallback ligero
    "gemini-flash-lite-latest",
]

NOMBRES_UI = {
    "gemini-4-argon": "Argon 4",
    "gemini-3.8-flash": "Gemini 3.8 Flash",
    "gemini-3.6-flash": "Gemini 3.6 Flash",
    "gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite",
    "gemini-3.1-flash-lite": "Gemini 3.1 Flash Lite",
    "gemini-flash-lite-latest": "Gemini Flash Lite",
}

EFECTOS_VALIDOS = {
    "zoom_impacto", "zoom_in", "zoom_out", "flash", "temblor",
    "alerta_roja", "brillo_epico", "blanco_negro", "spotlight", "ninguno"
}

SFX_VALIDOS = {
    "crowd_shocked", "whoosh", "riser_suction", "vine_boom", "metal_pipe",
    "heartbeat_fast", "record_scratch", "suspense_hit", "ding", "good_idea",
    "cash_ting", "punch", "boxing_bell", "camera_flash", "camera_shooter",
    "cartoon_laugh", "kids_yeyy", "party_horn", "awww", "error",
    "xp_Error", "fart", "click", "pop", "ninguno"
}

EMOJIS_VALIDOS = {
    "sorprendido", "risa", "fiesta", "diablo", "enojo", "lloro", "sueno",
    "calavera", "fuego", "ojos", "cerebro", "ninguno"
}


# =====================================================================
# GESTIÓN Y PERSISTENCIA DE API KEYS
# =====================================================================
def extraer_gemini_api_keys(raw: Any) -> List[str]:
    """Extrae y limpia claves de Gemini desde strings o listas."""
    if not raw:
        return []
    if isinstance(raw, (list, tuple, set)):
        candidatos = list(raw)
    else:
        candidatos = re.split(r"[\r\n,;]+", str(raw).strip())
    resultado: List[str] = []
    vistos = set()
    for c in candidatos:
        limpio = str(c).strip().strip("'\"")
        if len(limpio) >= 20 and limpio not in vistos:
            vistos.add(limpio)
            resultado.append(limpio)
    return resultado


def obtener_gemini_api_keys() -> List[str]:
    """Devuelve la lista completa de API Keys configuradas (entorno o archivo)."""
    keys: List[str] = []
    env_k = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_k:
        keys.extend(extraer_gemini_api_keys(env_k))
    if GEMINI_KEY_FILE.exists():
        try:
            content = GEMINI_KEY_FILE.read_text(encoding="utf-8-sig")
            keys.extend(extraer_gemini_api_keys(content))
        except Exception:
            pass
    final_keys: List[str] = []
    vistos = set()
    for k in keys:
        if k not in vistos:
            vistos.add(k)
            final_keys.append(k)
    return final_keys


def obtener_gemini_api_key() -> str:
    """Devuelve la clave principal disponible."""
    keys = obtener_gemini_api_keys()
    return keys[0] if keys else ""


def guardar_gemini_api_key(api_key: str) -> None:
    """Guarda las claves en el archivo de texto del proyecto."""
    keys = extraer_gemini_api_keys(api_key)
    if keys:
        GEMINI_KEY_FILE.write_text("\n".join(keys), encoding="utf-8")
    else:
        GEMINI_KEY_FILE.write_text(api_key.strip(), encoding="utf-8")


# =====================================================================
# GENERADORES MULTIMODALES EN MEMORIA (VIDEO COMPACTO Y MOSAICO JPEG)
# =====================================================================
def generar_mosaico_video(ruta_video: Path, cols: int = 4, rows: int = 2) -> Tuple[bytes, float]:
    """
    Extrae fotogramas clave espaciados con decodificación secuencial rápida (cap.grab())
    y genera un mosaico JPEG en memoria con OpenCV (~0.12s).
    """
    import io
    dur_seg, w_src, h_src, fps_src = obtener_info_video(ruta_video)
    num_tiles = cols * rows
    tile_w, tile_h = 270, 480
    canvas = np.zeros((rows * tile_h, cols * tile_w, 3), dtype=np.uint8)
    canvas[:] = (23, 17, 15)  # Fondo oscuro en BGR

    cap = None
    try:
        cap = cv2.VideoCapture(str(ruta_video), cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap = cv2.VideoCapture(str(ruta_video))
    except (Exception, SystemError, BaseException):
        cap = None

    tiles_cargados = 0
    if cap is not None and cap.isOpened():
        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            fps = float(cap.get(cv2.CAP_PROP_FPS) or fps_src or 30.0)
            if total_frames > 0:
                indices_list = list(np.linspace(0, max(0, total_frames - 2), num_tiles, dtype=int))
                target_map: Dict[int, List[int]] = {}
                for pos, f_idx in enumerate(indices_list):
                    target_map.setdefault(int(f_idx), []).append(pos)

                max_target = max(target_map.keys()) if target_map else 0
                cur_idx = 0
                while cur_idx <= max_target:
                    if not cap.grab():
                        break
                    if cur_idx in target_map:
                        ret, frame = cap.retrieve()
                        if ret and frame is not None:
                            resized = cv2.resize(frame, (tile_w, tile_h), interpolation=cv2.INTER_AREA)
                            seg_actual = cur_idx / fps if fps > 0 else (cur_idx * (dur_seg / max(1, total_frames)))
                            mm = int(seg_actual // 60)
                            ss = seg_actual % 60
                            etiqueta = f"{mm:02d}:{ss:04.1f}s"
                            cv2.rectangle(resized, (0, 0), (min(tile_w, 140), 30), (0, 0, 0), -1)
                            cv2.putText(
                                resized, etiqueta, (6, 22),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2, cv2.LINE_AA
                            )
                            for idx_pos in target_map[cur_idx]:
                                r = idx_pos // cols
                                c = idx_pos % cols
                                y1, y2 = r * tile_h, (r + 1) * tile_h
                                x1, x2 = c * tile_w, (c + 1) * tile_w
                                canvas[y1:y2, x1:x2] = resized
                                tiles_cargados += 1
                    cur_idx += 1
        except Exception as e_cap:
            logger.warning(f"Error en extracción secuencial cap.grab: {e_cap}")
        finally:
            try:
                cap.release()
            except Exception:
                pass

    # Fallback por FFmpeg si no se pudieron cargar todos los tiles
    if tiles_cargados < num_tiles // 2:
        for i in range(num_tiles):
            r = i // cols
            c = i % cols
            y1, y2 = r * tile_h, (r + 1) * tile_h
            x1, x2 = c * tile_w, (c + 1) * tile_w
            if np.mean(canvas[y1:y2, x1:x2]) > 25:
                continue
            t_sec = min(max(0.15, (i + 0.5) * (dur_seg / num_tiles)), max(0.2, dur_seg - 0.15))
            try:
                cmd_ff = [
                    "ffmpeg", "-v", "error",
                    "-ss", f"{max(0.0, t_sec):.3f}",
                    "-i", str(ruta_video),
                    "-frames:v", "1",
                    "-vf", f"scale={tile_w}:{tile_h}:force_original_aspect_ratio=increase:flags=fast_bilinear,crop={tile_w}:{tile_h}",
                    "-f", "image2pipe",
                    "-vcodec", "rawvideo",
                    "-pix_fmt", "bgr24",
                    "-",
                ]
                proc_ff = subprocess.run(
                    cmd_ff,
                    capture_output=True,
                    check=False,
                    creationflags=WIN_NO_WINDOW,
                    startupinfo=WIN_STARTUPINFO,
                )
                if proc_ff.returncode == 0 and len(proc_ff.stdout) == tile_w * tile_h * 3:
                    frame_ff = np.frombuffer(proc_ff.stdout, dtype=np.uint8).reshape((tile_h, tile_w, 3))
                    mm = int(t_sec) // 60
                    ss = int(t_sec) % 60
                    etiqueta = f"{mm:02d}:{ss:02d}s"
                    cv2.rectangle(frame_ff, (0, 0), (min(tile_w, 140), 30), (0, 0, 0), -1)
                    cv2.putText(
                        frame_ff, etiqueta, (6, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2, cv2.LINE_AA
                    )
                    canvas[y1:y2, x1:x2] = frame_ff
            except Exception:
                pass

    ok_enc, enc_bytes = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    jpeg_bytes = enc_bytes.tobytes() if ok_enc else b""

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    ruta_mosaico = TEMP_DIR / "mosaico_analisis.jpg"
    try:
        ruta_mosaico.write_bytes(jpeg_bytes)
    except Exception:
        pass

    return jpeg_bytes, dur_seg


def generar_video_compacto_ia(ruta_video: Path) -> Tuple[Optional[bytes], float]:
    """
    Comprime el video original a un proxy ultrarrápido (480p @ 10 FPS, ~900 KB - 1.5 MB).
    Permite enviarlo inline a la API (Part.from_bytes) en memoria RAM con mínima latencia de subida y tokenización.
    """
    dur_seg, w_v, h_v, _ = obtener_info_video(ruta_video)

    # Bypass: si el video original ya pesa menos de 4.5 MB, no re-codificar.
    try:
        peso_original = ruta_video.stat().st_size
        if peso_original <= int(4.5 * 1024 * 1024):
            return ruta_video.read_bytes(), dur_seg
    except Exception:
        pass

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    ruta_low = TEMP_DIR / "video_analisis_ia.mp4"
    if ruta_low.exists():
        try:
            ruta_low.unlink()
        except OSError:
            pass

    # Remuestreo relámpago a 480p @ 10 FPS sin audio
    cmd_proxy = [
        "ffmpeg", "-y",
        "-i", str(ruta_video),
        "-vf", "scale=-2:480,fps=10",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "30",
        "-an",
        "-threads", "0",
        str(ruta_low),
    ]
    res = subprocess.run(
        cmd_proxy,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        creationflags=WIN_NO_WINDOW,
        startupinfo=WIN_STARTUPINFO,
    )
    if res.returncode == 0 and ruta_low.exists() and 1000 < ruta_low.stat().st_size < 18_000_000:
        return ruta_low.read_bytes(), dur_seg
    return None, dur_seg

# =====================================================================
# AUDITOR Y AUTO-SANITIZADOR DETERMINISTA EN PYTHON (0 TOKENS, <5ms)
# =====================================================================
def sanitizar_y_auditar_guion(raw_text: str, duracion_total: float) -> Tuple[str, List[str]]:
    """
    Limpia bloques markdown, valida que SFX/Efectos/Emojis pertenezcan al catálogo cerrado
    y audita la métrica de palabras por bloque.
    """
    limpio = re.sub(r"```[a-zA-Z]*", "", raw_text).replace("```", "").strip()
    lineas_salida = []
    advertencias = []
    en_guion = False
    circulos_usados = 0

    for linea in limpio.splitlines():
        l_strip = linea.strip()
        if not l_strip:
            continue

        if l_strip.startswith("[GUION]"):
            en_guion = True
            lineas_salida.append("[GUION]")
            continue

        if not en_guion or l_strip.startswith("TIEMPO"):
            lineas_salida.append(l_strip)
            continue

        partes = [p.strip() for p in l_strip.split("|")]
        if len(partes) < 7:
            lineas_salida.append(l_strip)
            continue

        tiempo, efecto, sfx, emoji, flecha, circulo, texto = partes[:7]

        # 1. Validar Efecto
        if efecto not in EFECTOS_VALIDOS:
            efecto = "zoom_in"

        # 2. Validar SFX (soporta combinaciones con '+')
        sfx_parts = [s.strip() for s in sfx.split("+") if s.strip() in SFX_VALIDOS]
        sfx = "+".join(sfx_parts[:2]) if sfx_parts else "whoosh"

        # 3. Validar Emoji (con posible sufijo :derecha, etc.)
        emoji_base = emoji.split(":")[0].strip()
        if emoji_base not in EMOJIS_VALIDOS:
            emoji = "sorprendido:derecha"

        # 4. Límite estricto de círculos (máx 2)
        if circulo.lower() != "ninguno":
            circulos_usados += 1
            if circulos_usados > 2:
                circulo = "ninguno"

        # Normalizar flecha y círculo: purgar 'centro', 'medio' o 'auto' para evitar flechas estáticas clavadas
        flecha_clean = flecha.strip().lower()
        if flecha_clean in ("centro", "center", "medio", "auto"):
            flecha = "ninguna"

        circulo_clean = circulo.strip().lower()
        if circulo_clean in ("centro", "center", "medio", "auto"):
            circulo = "ninguno"

        # 5. Auditar conteo de palabras (2.8 - 4.0 palabras/seg)
        try:
            t_ini_str, t_fin_str = tiempo.split("-")
            def _to_sec(val: str) -> float:
                parts = val.strip().split(":")
                return int(parts[0]) * 60 + float(parts[1])
            dur_bloque = max(1.0, _to_sec(t_fin_str) - _to_sec(t_ini_str))
        except Exception:
            dur_bloque = 4.0

        # Sanitizar texto: prohibir oraciones truncadas con '...', conjunciones colgantes
        # o cláusulas subordinadas incompletas (ej: "...para reírse porque este niño!")
        texto_limpio = texto.strip()
        texto_limpio = re.sub(r'[\.\s\u2026]+[!\?]*$', '', texto_limpio).strip()

        # Detección inteligente de cláusulas subordinadas inconclusas al final de la oración
        pat_inconclusa = (
            r'[,;]?\s*\b(porque|ya que|puesto que|cuando|mientras|donde|si|para que|así que|asi que|'
            r'y todo por|todo por|hasta que|que)\s+([^.!?]+)[.!?]*$'
        )
        m_inc = re.search(pat_inconclusa, texto_limpio, re.IGNORECASE)
        if m_inc:
            tail_words = [w.lower().rstrip(',;:¡!¿?') for w in m_inc.group(2).split()]
            verbos_clave = {
                'era', 'fue', 'es', 'son', 'eran', 'había', 'habia', 'tiene', 'tenia', 'tenía',
                'cayó', 'cayo', 'hizo', 'vio', 'salió', 'salio', 'dio', 'quedó', 'quedo',
                'pudo', 'supo', 'dijo', 'vino', 'está', 'esta', 'estaba', 'están', 'estan',
                'pasó', 'paso', 'ocurrió', 'ocurrio', 'terminó', 'termino', 'empezó', 'empezo',
                'gritó', 'grito', 'rio', 'rió', 'lloró', 'lloro', 'escapó', 'escapo', 'cruces',
                'sea', 'fuera', 'vaya', 'haga', 'tenga', 'pueda', 'llegó', 'llego', 'quiere',
                'quieren', 'quisieron', 'decidió', 'decidio', 'supieron', 'vieron', 'salieron'
            }
            has_verb = any(w in verbos_clave or w.endswith(('ó', 'ió', 'aba', 'ía', 'aron', 'ieron', 'ará', 'erá', 'irá', 'an', 'en')) for w in tail_words)
            if not has_verb and len(tail_words) <= 5:
                texto_limpio = texto_limpio[:m_inc.start()].rstrip(',;: ')

        colgantes = {'cuando', 'porque', 'pero', 'y', 'o', 'ya que', 'donde', 'si', 'sin', 'asi que', 'así que', 'que', 'para', 'de', 'con', 'a', 'jamas', 'jamás', 'nunca', 'repente', 'este', 'esta', 'estos', 'estas', 'el', 'la', 'los', 'las', 'un', 'una'}
        palabras_temp = texto_limpio.split()
        while palabras_temp and palabras_temp[-1].lower().rstrip(',;:¡!¿?') in colgantes:
            palabras_temp.pop()
            texto_limpio = ' '.join(palabras_temp).rstrip(',;:')
        if texto_limpio and not texto_limpio.endswith(('.', '!', '?')):
            texto_limpio += '!'
        texto = texto_limpio

        palabras = [w for w in texto.split() if w]
        min_p = int(round(dur_bloque * 2.8))
        max_p = int(round(dur_bloque * 4.0))

        if len(palabras) < min_p or len(palabras) > max_p:
            advertencias.append(
                f"Bloque ({tiempo}) [{dur_bloque:.0f}s]: {len(palabras)} palabras (ideal: {min_p}-{max_p})"
            )

        linea_reconstruida = f"{tiempo} | {efecto} | {sfx} | {emoji} | {flecha} | {circulo} | {texto}"
        lineas_salida.append(linea_reconstruida)

    return "\n".join(lineas_salida), advertencias


# =====================================================================
# GESTOR INTELIGENTE DE POOL DE API KEYS Y ROTACIÓN MULTIMODAL
# =====================================================================
class GeminiPoolOrchestrator:
    """
    Orquestador de alta disponibilidad para múltiples API Keys de Google AI Studio.
    Incluye Fast-Probing asíncrono (<800ms), caché de estado de cuentas/modelos,
    inyección de Video Inline en RAM y Fallback instantáneo a Mosaico JPEG.
    """

    def __init__(self, api_keys: List[str], models: Optional[List[str]] = None):
        self.api_keys = [k.strip() for k in api_keys if k and k.strip()]
        if not self.api_keys:
            raise ValueError("Se requiere al menos una API Key válida de Gemini.")

        self.models = models or list(MODEL_HIERARCHY)
        self.clients: Dict[int, genai.Client] = {
            idx: genai.Client(api_key=key) for idx, key in enumerate(self.api_keys)
        }
        self.cooldown_until: Dict[Tuple[int, str], float] = {}
        self.unsupported_pairs: Set[Tuple[int, str]] = set()
        self.paid_tier_only: Set[Tuple[int, str]] = set()
        self.key_latency: Dict[int, float] = {idx: 0.5 for idx in range(len(self.api_keys))}
        self.last_probe_cache: Dict[str, Tuple[float, List[int]]] = {}

    def _mask_key(self, key_idx: int) -> str:
        k = self.api_keys[key_idx]
        return f"Cuenta {key_idx + 1}"

    def _is_available(self, key_idx: int, model: str) -> bool:
        if (key_idx, model) in self.unsupported_pairs:
            return False
        unlock_time = self.cooldown_until.get((key_idx, model), 0.0)
        return time.time() >= unlock_time

    def _mark_error(self, key_idx: int, model: str, status_code: int):
        if status_code in (404, 400):
            self.unsupported_pairs.add((key_idx, model))
            logger.info(f"{self._mask_key(key_idx)} no soporta '{model}' ({status_code}). Descartado en sesión.")
        elif status_code == 401:
            for m in self.models:
                self.unsupported_pairs.add((key_idx, m))
            logger.error(f"{self._mask_key(key_idx)} clave inválida ({status_code}).")
        elif status_code == 403:
            # 403 suele ser por modelo restringido o que requiere billing, no deshabilitar otros modelos
            self.unsupported_pairs.add((key_idx, model))
            logger.error(f"{self._mask_key(key_idx)} sin permisos en '{model}' ({status_code}).")
        elif status_code == 429:
            self.cooldown_until[(key_idx, model)] = time.time() + 65.0
            logger.info(f"{self._mask_key(key_idx)} sin cuota en '{model}' (429). Cooldown 65s.")
        elif status_code >= 500:
            self.cooldown_until[(key_idx, model)] = time.time() + 20.0
            logger.info(f"Servidor saturado ({status_code}) en {self._mask_key(key_idx)} con '{model}'.")

    async def _probe_single_key(
        self, key_idx: int, model: str, timeout_sec: float = 3.0, ignorar_cooldown: bool = False
    ) -> Tuple[int, bool, float, str]:
        """
        Retorna (key_idx, ok, latencia, estado_detalle).
        estado_detalle: 'ok', 'cuota' (429), 'trafico' (503/timeout/500), 'tier_pago' (limit:0), 'error'.
        """
        if not ignorar_cooldown and not self._is_available(key_idx, model):
            return key_idx, False, 999.0, "cooldown"

        client = self.clients[key_idx]
        t0 = time.perf_counter()
        try:
            await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model,
                    contents="1",
                    config=types.GenerateContentConfig(
                        max_output_tokens=1,
                        temperature=0.0,
                    ),
                ),
                timeout=timeout_sec,
            )
            lat = time.perf_counter() - t0
            self.key_latency[key_idx] = lat
            return key_idx, True, lat, "ok"
        except asyncio.TimeoutError:
            self._mark_error(key_idx, model, 504)
            return key_idx, False, 999.0, "trafico"
        except APIError as e:
            code = getattr(e, "code", 500) or 500
            msg = str(e).lower()
            if "limit: 0" in msg or ("free" in msg and "limit: 0" in msg):
                self.paid_tier_only.add((key_idx, model))
                self._mark_error(key_idx, model, code)
                return key_idx, False, 999.0, "tier_pago"
            self._mark_error(key_idx, model, code)
            if code == 429 or "quota" in msg or "resource_exhausted" in msg:
                return key_idx, False, 999.0, "cuota"
            elif code in (500, 502, 503, 504) or "unavailable" in msg or "overloaded" in msg:
                return key_idx, False, 999.0, "trafico"
            else:
                return key_idx, False, 999.0, "error"
        except Exception as e:
            msg = str(e).lower()
            if "timeout" in msg:
                return key_idx, False, 999.0, "trafico"
            return key_idx, False, 999.0, "error"

    def fast_probe_accounts(self, target_model: str) -> List[int]:
        """
        Ejecuta un micro-ping paralelo sobre todas las cuentas para `target_model`.
        Devuelve la lista de índices de cuentas VIVAS ordenadas por menor latencia.
        Usa caché de 180s para evitar re-probar cuentas que ya respondieron OK recientemente.
        """
        cached = self.last_probe_cache.get(target_model)
        if cached:
            ts_cache, lista_previa = cached
            if (time.time() - ts_cache) < 180.0:
                vivas_ahora = [idx for idx in lista_previa if self._is_available(idx, target_model)]
                if vivas_ahora:
                    return vivas_ahora

        async def _run_probes():
            tasks = [self._probe_single_key(idx, target_model, timeout_sec=4.0) for idx in range(len(self.api_keys))]
            return await asyncio.gather(*tasks)

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(_run_probes())
        finally:
            try:
                loop.close()
            except Exception:
                pass

        vivas = [idx for idx, ok, _, _ in sorted(results, key=lambda x: x[2]) if ok]
        if vivas:
            self.last_probe_cache[target_model] = (time.time(), vivas)
            return vivas

        # Fallback de resiliencia: si el micro-ping falló o tuvo timeout por congestión de red,
        # no descartar el modelo completo; intentar con las cuentas que no estén en cooldown activo
        disponibles = [idx for idx in range(len(self.api_keys)) if self._is_available(idx, target_model)]
        return disponibles

    def auditar_modelos_en_vivo(self) -> List[Dict[str, Any]]:
        """
        Prueba cada modelo en paralelo sobre todas las cuentas sin aplicar cooldowns previos,
        para entregar un diagnóstico en tiempo real de disponibilidad, cuota y tráfico de Google.
        """
        self.cooldown_until.clear()
        self.unsupported_pairs.clear()
        self.paid_tier_only.clear()
        self.last_probe_cache.clear()

        modelos_test = [
            ("gemini-4-argon", "Argon 4", "Argon"),
            ("gemini-3.8-flash", "Gemini 3.8 Flash", "3.8"),
            ("gemini-3.6-flash", "Gemini 3.6 Flash", "3.6"),
            ("gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite", "3.5"),
        ]

        resultados = []
        total_k = len(self.api_keys)

        for m_id, m_nombre, m_corto in modelos_test:
            async def _run_test_model(mod=m_id):
                tasks = [self._probe_single_key(idx, mod, timeout_sec=3.5, ignorar_cooldown=True) for idx in range(total_k)]
                return await asyncio.gather(*tasks)

            res_keys: List[Tuple[int, bool, float, str]] = []
            if total_k > 0:
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    res_keys = loop.run_until_complete(_run_test_model())
                finally:
                    try:
                        loop.close()
                    except Exception:
                        pass

            vivas = [idx for idx, ok, _, _ in res_keys if ok]
            caidas = [res for res in res_keys if not res[1]]
            n_vivas = len(vivas)
            mejor_lat = min((lat for idx, ok, lat, _ in res_keys if ok), default=999.0)

            # Clasificación de fallas
            estados_caidas = [res[3] for res in caidas]
            hay_trafico = any(st in ("trafico", "timeout") for st in estados_caidas) or (n_vivas > 0 and mejor_lat >= 1.6)
            es_tier_pago = (
                any((k, m_id) in self.paid_tier_only for k in range(total_k))
                or (m_id == "gemini-4-argon" and n_vivas == 0 and any(st in ("tier_pago", "error") for st in estados_caidas))
            )

            if total_k == 0:
                tipo = "sin_claves"
                tag = "SIN CLAVES"
                desc = "Carga tu API Key"
                borde = "#475569"
                bg = "#182030"
                pill_bg = "#243048"
                txt_col = "#94a3b8"
                label_box = m_corto
            elif es_tier_pago:
                tipo = "tier_pago"
                tag = "PLAN PAGO"
                desc = "Requiere Facturación"
                borde = "#818cf8"
                bg = "#16182e"
                pill_bg = "#252849"
                txt_col = "#a5b4fc"
                label_box = m_corto
            elif n_vivas == 0:
                tipo = "agotado"
                tag = "AGOTADO"
                desc = "Sin cuota diaria (429)"
                borde = "#ef4444"
                bg = "#280d12"
                pill_bg = "#3d161d"
                txt_col = "#f87171"
                label_box = f"{m_corto} (0/{total_k})" if total_k > 1 else m_corto
            elif hay_trafico:
                # El usuario pierde cuentas o tiene demora por congestión de servidores de Google
                tipo = "con_demora"
                tag = "MUCHO TRÁFICO"
                desc = f"{n_vivas}/{total_k} con congestión ({mejor_lat:.1f}s)"
                borde = "#f59e0b"
                bg = "#281b09"
                pill_bg = "#3d2b0e"
                txt_col = "#fbbf24"
                label_box = f"{m_corto} ({n_vivas}/{total_k})" if total_k > 1 else m_corto
            else:
                # Cuentas vivas con cuota activa; si se gastó alguna fue por cuota diaria 429
                tipo = "disponible"
                tag = "DISPONIBLE"
                desc = f"{n_vivas}/{total_k} listas (<1s)"
                borde = "#10b981"
                bg = "#072419"
                pill_bg = "#0c3827"
                txt_col = "#34d399"
                label_box = f"{m_corto} ({n_vivas}/{total_k})" if (total_k > 1 and n_vivas < total_k) else m_corto

            resultados.append({
                "id": m_id,
                "nombre": m_nombre,
                "nombre_corto": label_box,
                "vivas": n_vivas,
                "total": total_k,
                "tipo": tipo,
                "tag": tag,
                "desc": desc,
                "color_borde": borde,
                "color_bg": bg,
                "color_pill_bg": pill_bg,
                "color_texto": txt_col,
            })

        return resultados

    def generar_guion_completo(
        self,
        video_path: Path,
        prompt_maestro: str,
        progreso_cb: Optional[Any] = None,
        timeout_video_seg: float = 40.0,
        modelo_preferido: Optional[str] = None,
        cancelar_check: Optional[Callable[[], bool]] = None,
        triple_pasada: bool = True,
    ) -> str:
        """
        Ejecuta el Single-Pass Master Prompt:
        1. Fast-Probe para detectar cuentas listas en <800ms.
        2. Inyección directa de Video Inline en memoria RAM.
        3. Conmutación instantánea a Mosaico JPEG ante 503/Timeout.
        4. Validación y auto-reparación determinista local.
        """
        if cancelar_check and cancelar_check():
            raise InterruptedError("Generación de guion cancelada por el usuario.")

        def _notif(frac: float, msg: str):
            if callable(progreso_cb):
                try:
                    progreso_cb(frac, msg)
                except Exception:
                    pass
            logger.info(msg)

        dur_seg, _, _, _ = obtener_info_video(video_path)
        if cancelar_check and cancelar_check():
            raise InterruptedError("Generación de guion cancelada por el usuario.")
        video_bytes, _ = generar_video_compacto_ia(video_path)

        video_part: Optional[types.Part] = None
        if video_bytes:
            video_part = types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")

        mosaico_part: Optional[types.Part] = None

        # Orden de modelos a probar: el modelo preferido del usuario se intenta PRIMERO (Regla 5 de AGENTS.md)
        if modelo_preferido and modelo_preferido.strip():
            mod_p = modelo_preferido.strip()
            resto = [m for m in self.models if m != mod_p]
            modelos_ordenados = [mod_p] + resto
        else:
            modelos_ordenados = list(self.models)

        # Filtrar modelos obsoletos dados de baja por Google
        modelos_ordenados = [m for m in modelos_ordenados if "2.5" not in m]

        total_cuentas = len(self.api_keys)
        ultimo_err = None

        # Si el modelo preferido es Lite (ej. gemini-3.5-flash-lite), entra directo en Fase 1
        if modelo_preferido and "lite" in modelo_preferido.lower():
            mod_p = modelo_preferido.strip()
            modelos_principales = [mod_p] + [m for m in modelos_ordenados if "lite" not in m and m != mod_p]
            modelos_lite = [m for m in modelos_ordenados if "lite" in m and m != mod_p]
        else:
            modelos_principales = [m for m in modelos_ordenados if "lite" not in m]
            modelos_lite = [m for m in modelos_ordenados if "lite" in m]

        def _intentar_paso(lista_mods: List[str], modo_nombre: str, contenidos: List[Any], timeout_seg_actual: float) -> Optional[str]:
            nonlocal ultimo_err
            for idx_m, model in enumerate(lista_mods):
                if cancelar_check and cancelar_check():
                    raise InterruptedError("Generación de guion cancelada por el usuario.")
                nom_mod = NOMBRES_UI.get(model, model)
                _notif(0.12 + (idx_m * 0.05), f"Comprobando {nom_mod} en {modo_nombre} ({total_cuentas} cuentas)...")

                cuentas_vivas = self.fast_probe_accounts(model)
                if not cuentas_vivas:
                    continue

                # Si el modelo a usar es gemini-3.6-flash o gemini-3.5-flash-lite, ejecutar el pipeline multi-agente adaptativo de 3 instancias
                if triple_pasada and model in ("gemini-3.6-flash", "gemini-3.5-flash-lite") and ("video" in modo_nombre or video_part is not None):
                    try:
                        res_3inst = self._generar_guion_3_instancias_adaptativo(
                            modelo_objetivo=model,
                            video_part=video_part,
                            mosaico_part=mosaico_part,
                            video_path=video_path,
                            prompt_maestro=prompt_maestro,
                            timeout_seg=timeout_seg_actual,
                            dur_seg=dur_seg,
                            _notif=_notif,
                            cancelar_check=cancelar_check,
                        )
                        if res_3inst:
                            return res_3inst
                    except InterruptedError:
                        raise
                    except Exception as e_3:
                        logger.warning(f"Error en pipeline 3 instancias adaptativo ({model}): {e_3}. Probando flujo normal...")

                for key_idx in cuentas_vivas:
                    if cancelar_check and cancelar_check():
                        raise InterruptedError("Generación de guion cancelada por el usuario.")
                    client = self.clients[key_idx]
                    etiqueta_cuenta = f"Cuenta API {key_idx + 1}" + (f" de {total_cuentas}" if total_cuentas > 1 else "")

                    try:
                        _notif(0.30, f"Analizando {modo_nombre} con {nom_mod} ({etiqueta_cuenta})...")
                        http_timeout = int(timeout_seg_actual * 1000)

                        response = _llamar_gemini_cancelable(
                            lambda: client.models.generate_content(
                                model=model,
                                contents=contenidos,
                                config=types.GenerateContentConfig(
                                    temperature=0.35,
                                    http_options=types.HttpOptions(timeout=http_timeout),
                                ),
                            ),
                            cancelar_check=cancelar_check,
                        )

                        if response and response.text and len(response.text.strip()) > 80:
                            _notif(0.85, f"Validando cadencia y catálogo de efectos ({nom_mod})...")
                            guion_limpio, advertencias = sanitizar_y_auditar_guion(response.text, dur_seg)

                            if len(advertencias) >= 2:
                                guion_limpio = self._reparar_conteo_palabras(client, model, guion_limpio, advertencias)

                            _notif(1.0, f"✔ Guion completado con {nom_mod} ({etiqueta_cuenta}).")
                            return guion_limpio

                    except InterruptedError:
                        raise
                    except APIError as e:
                        code = getattr(e, "code", 500) or 500
                        self._mark_error(key_idx, model, code)
                        ultimo_err = e
                        _notif(0.35, f"{nom_mod} ({etiqueta_cuenta}) con error {code}. Probando otra cuenta...")
                        continue
                    except Exception as e:
                        ultimo_err = e
                        _notif(0.35, f"{nom_mod} no respondió en {etiqueta_cuenta}. Probando siguiente cuenta...")
                        continue
            return None

        # ── FASE 1: Probar modelos de alta fidelidad (Argon, 3.8, 3.6) con VIDEO COMPLETO ──
        if video_part is not None:
            res_v = _intentar_paso(modelos_principales, "video completo", [video_part, prompt_maestro], timeout_video_seg)
            if res_v:
                return res_v

        # ── FASE 2: Probar modelos de alta fidelidad (Argon, 3.8, 3.6) con MOSAICO JPEG ──
        # ¡Crucial! 3.6 con Mosaico se prueba ANTES de degradar a 3.5 Lite
        if mosaico_part is None:
            _notif(0.40, "Optimizando análisis con Mosaico para modelos de alta fidelidad...")
            jpg_bytes, _ = generar_mosaico_video(video_path)
            mosaico_part = types.Part.from_bytes(data=jpg_bytes, mime_type="image/jpeg")

        nota_mosaico = "\n[NOTA: Se adjunta mosaico cronológico del video con segundo exacto estampado]."
        contenido_mosaico = [mosaico_part, prompt_maestro + nota_mosaico]

        res_m = _intentar_paso(modelos_principales, "mosaico storyboard", contenido_mosaico, 25.0)
        if res_m:
            return res_m

        # ── FASE 3: Solo si 3.8 y 3.6 fallaron en video Y mosaico, recurrir a modelos Lite (3.5) ──
        _notif(0.50, "Modelos principales saturados. Recurriendo a fallback Lite...")
        if video_part is not None:
            res_l_v = _intentar_paso(modelos_lite, "video (lite)", [video_part, prompt_maestro], timeout_video_seg)
            if res_l_v:
                return res_l_v

        res_l_m = _intentar_paso(modelos_lite, "mosaico (lite)", contenido_mosaico, 25.0)
        if res_l_m:
            return res_l_m

        det_err = str(ultimo_err) if ultimo_err else "Sin respuesta"
        raise RuntimeError(
            f"Todas las cuentas y modelos consultados están temporalmente sin cuota o saturados.\n"
            f"Verifica tus API Keys en Google AI Studio (aistudio.google.com/apikey). Detalle: {det_err}"
        )

    def _reparar_conteo_palabras(
        self, client: genai.Client, model: str, guion_actual: str, advertencias: List[str]
    ) -> str:
        """Micro-llamada solo de texto (~1.5s) que calibra la columna TEXTO de los bloques fuera de ritmo."""
        prompt_fix = (
            "Corrige ÚNICAMENTE la columna TEXTO (última columna) de las siguientes líneas del guion "
            "para que cumplan estrictamente entre 2.8 y 3.8 palabras por segundo. Mantén intactas las primeras 6 columnas.\n\n"
            "BLOQUES A CALIBRAR:\n- " + "\n- ".join(advertencias) + "\n\n"
            f"GUION COMPLETO:\n{guion_actual}"
        )
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt_fix,
                config=types.GenerateContentConfig(temperature=0.2),
            )
            if resp and resp.text and "[GUION]" in resp.text:
                corregido, _ = sanitizar_y_auditar_guion(resp.text, 0.0)
                return corregido
        except Exception:
            pass
        return guion_actual

    def _generar_guion_3_instancias_adaptativo(
        self,
        modelo_objetivo: str,
        video_part: Optional[types.Part],
        mosaico_part: Optional[types.Part],
        video_path: Path,
        prompt_maestro: str,
        timeout_seg: float,
        dur_seg: float,
        _notif: Callable[[float, str], None],
        cancelar_check: Optional[Callable[[], bool]] = None,
    ) -> Optional[str]:
        """
        Pipeline multi-agente adaptativo de triple revisión con IA (Gemini 3.6 Flash / 3.5 Lite):
        - Evalúa dinámicamente la disponibilidad de cuota en vivo para Gemini 3.6 Flash y 3.5 Lite:
          * 3+ cuentas 3.6 disponibles -> 3.6 (Borrador 1) + 3.6 (Borrador 2) -> 3.6 (Síntesis con Video)
          * 2 cuentas 3.6 disponibles  -> 3.6 (Borrador 1) + 3.5 Lite (Borrador 2) -> 3.6 (Síntesis con Video)
          * 1 cuenta 3.6 disponible    -> 3.5 Lite (Borrador 1) + 3.5 Lite (Borrador 2) -> 3.6 (Síntesis con Video)
          * 0 cuentas 3.6 disponibles  -> 3x 3.5 Flash Lite
        - Fallback transparente a Mosaico Storyboard si el envío del video inline falla o es rechazado.
        - Instancia 3 sintetiza ambos borradores + inspección visual garantizando un cierre 100% conclusivo.
        """
        if cancelar_check and cancelar_check():
            raise InterruptedError("Generación de guion cancelada por el usuario.")

        es_36 = ("3.6" in modelo_objetivo)
        cuentas_36 = self.fast_probe_accounts("gemini-3.6-flash") if es_36 else []
        cuentas_35 = self.fast_probe_accounts("gemini-3.5-flash-lite")
        n_36 = len(cuentas_36)
        n_35 = len(cuentas_35)

        if es_36:
            if n_36 >= 3:
                mod_1, idx_c1 = "gemini-3.6-flash", cuentas_36[0]
                mod_2, idx_c2 = "gemini-3.6-flash", cuentas_36[1]
                mod_3, idx_c3 = "gemini-3.6-flash", cuentas_36[2]
                desc_combo = "3x Gemini 3.6 Flash"
            elif n_36 == 2:
                mod_1, idx_c1 = "gemini-3.6-flash", cuentas_36[0]
                mod_2, idx_c2 = "gemini-3.5-flash-lite", (cuentas_35[0] if cuentas_35 else cuentas_36[0])
                mod_3, idx_c3 = "gemini-3.6-flash", cuentas_36[1]
                desc_combo = "Híbrido (Draft 1: 3.6 + Draft 2: 3.5 Lite -> Síntesis: 3.6 Flash)"
            elif n_36 == 1:
                mod_1, idx_c1 = "gemini-3.5-flash-lite", (cuentas_35[0] if cuentas_35 else cuentas_36[0])
                mod_2, idx_c2 = "gemini-3.5-flash-lite", (cuentas_35[1 % n_35] if n_35 > 1 else (cuentas_35[0] if cuentas_35 else cuentas_36[0]))
                mod_3, idx_c3 = "gemini-3.6-flash", cuentas_36[0]
                desc_combo = "Borradores 3.5 Lite + Síntesis Maestra con 3.6 Flash"
            else:
                mod_1, idx_c1 = "gemini-3.5-flash-lite", (cuentas_35[0] if cuentas_35 else 0)
                mod_2, idx_c2 = "gemini-3.5-flash-lite", (cuentas_35[1 % n_35] if n_35 > 1 else (cuentas_35[0] if cuentas_35 else 0))
                mod_3, idx_c3 = "gemini-3.5-flash-lite", (cuentas_35[2 % n_35] if n_35 > 2 else (cuentas_35[0] if cuentas_35 else 0))
                desc_combo = "Fallback 3x Gemini 3.5 Flash Lite"
        else:
            mod_1, idx_c1 = "gemini-3.5-flash-lite", (cuentas_35[0] if cuentas_35 else 0)
            mod_2, idx_c2 = "gemini-3.5-flash-lite", (cuentas_35[1 % n_35] if n_35 > 1 else (cuentas_35[0] if cuentas_35 else 0))
            mod_3, idx_c3 = "gemini-3.5-flash-lite", (cuentas_35[2 % n_35] if n_35 > 2 else (cuentas_35[0] if cuentas_35 else 0))
            desc_combo = "3x Gemini 3.5 Flash Lite"

        _notif(0.20, f"Multi-Agente ({desc_combo}): Generando 2 borradores virales en simultáneo...")

        client_1 = self.clients[idx_c1]
        client_2 = self.clients[idx_c2]
        client_3 = self.clients[idx_c3]

        _mosaico_cache = mosaico_part

        def _obtener_mosaico():
            nonlocal _mosaico_cache
            if _mosaico_cache is None:
                try:
                    jpg_bytes, _ = generar_mosaico_video(video_path)
                    _mosaico_cache = types.Part.from_bytes(data=jpg_bytes, mime_type="image/jpeg")
                except Exception as ex_m:
                    logger.warning(f"No se pudo crear mosaico de respaldo: {ex_m}")
            return _mosaico_cache

        def _ejecutar_llamada_con_fallback(client, model, prompt_txt, temp, timeout_ms):
            # Intento 1: Video completo inline
            if video_part is not None:
                try:
                    r = client.models.generate_content(
                        model=model,
                        contents=[video_part, prompt_txt],
                        config=types.GenerateContentConfig(
                            temperature=temp,
                            http_options=types.HttpOptions(timeout=timeout_ms),
                        ),
                    )
                    if r and r.text and len(r.text.strip()) > 80:
                        return r.text
                except Exception as ex_v:
                    logger.info(f"Video rechazado en {model} ({ex_v}). Probando con mosaico...")

            # Intento 2: Fallback relámpago con mosaico storyboard
            m_part = _obtener_mosaico()
            if m_part is not None:
                try:
                    nota = "\n[NOTA: Se adjunta mosaico cronológico del video con segundo exacto estampado]."
                    r = client.models.generate_content(
                        model=model,
                        contents=[m_part, prompt_txt + nota],
                        config=types.GenerateContentConfig(
                            temperature=temp,
                            http_options=types.HttpOptions(timeout=int(timeout_ms * 0.7)),
                        ),
                    )
                    if r and r.text and len(r.text.strip()) > 80:
                        return r.text
                except Exception as ex_m:
                    logger.warning(f"Error en fallback de mosaico ({model}): {ex_m}")
            return None

        prompt_d1 = (
            prompt_maestro
            + "\n\n[DIRECTIVA DE ESTILO BORRADOR 1]: "
            + "Enfócate en máxima tensión desde el segundo 0, gancho potente directo al grano, "
            + "comentarios con ironía filosa y ritmo acelerado."
        )
        prompt_d2 = (
            prompt_maestro
            + "\n\n[DIRECTIVA DE ESTILO BORRADOR 2]: "
            + "Enfócate en intriga psicológica, curiosidad extrema ('nadie esperaba lo que pasó'), "
            + "remate inesperado y humor sarcástico."
        )

        resp_d1: Dict[str, Any] = {"text": None, "err": None}
        resp_d2: Dict[str, Any] = {"text": None, "err": None}
        http_timeout = int(timeout_seg * 1000)

        def _worker_d1():
            try:
                res1 = _ejecutar_llamada_con_fallback(client_1, mod_1, prompt_d1, 0.45, http_timeout)
                if res1:
                    resp_d1["text"] = res1
            except Exception as ex:
                resp_d1["err"] = ex

        def _worker_d2():
            try:
                res2 = _ejecutar_llamada_con_fallback(client_2, mod_2, prompt_d2, 0.55, http_timeout)
                if res2:
                    resp_d2["text"] = res2
            except Exception as ex:
                resp_d2["err"] = ex

        t1 = threading.Thread(target=_worker_d1, daemon=True)
        t2 = threading.Thread(target=_worker_d2, daemon=True)
        t1.start()
        t2.start()

        while t1.is_alive() or t2.is_alive():
            if cancelar_check and cancelar_check():
                raise InterruptedError("Generación de guion cancelada por el usuario.")
            time.sleep(0.12)

        txt_d1 = resp_d1.get("text")
        txt_d2 = resp_d2.get("text")

        if not txt_d1 and not txt_d2:
            return None

        if txt_d1 and txt_d2:
            bloque_borradores = (
                "=== BORRADOR 1 (Tensión e Impacto) ===\n"
                + txt_d1.strip()
                + "\n\n=== BORRADOR 2 (Intriga y Curiosidad) ===\n"
                + txt_d2.strip()
            )
        else:
            txt_unico = txt_d1 or txt_d2
            bloque_borradores = "=== BORRADOR BASE ===\n" + txt_unico.strip()

        nom_mod3 = NOMBRES_UI.get(mod_3, mod_3)
        _notif(0.55, f"Multi-Agente ({desc_combo}): Instancia 3 ({nom_mod3}) sintetizando guion definitivo con el video...")

        instruccion_sintesis = (
            "Eres el Editor Jefe de YouTube Shorts y Revisor de Retención Viral de Google.\n"
            "Has recibido el video original y borradores independientes de guion creados por dos IAs:\n\n"
            + bloque_borradores
            + "\n\nMISIÓN DE REVISIÓN Y SÍNTESIS FINAL:\n"
            + "1. Inspecciona el video adjunto y revisa los borradores generados.\n"
            + "2. Extrae el gancho inicial (primeros 3 segundos) más potente e irresistible de cualquiera de los dos.\n"
            + "3. Combina la mejor narración, las observaciones visuales más precisas y los momentos de mayor impacto de ambos borradores (cero spoilers, narración en tiempo real).\n"
            + "4. Elige los mejores SFX, emojis, flechas/círculos y zooms que maximicen la retención y la sincronización con lo que pasa en pantalla (recuerda: NUNCA uses 'centro' ni 'auto' para flecha; pon 'ninguna' si no hay un objeto específico que apuntar).\n"
            + "5. Asegura una cadencia perfecta (ritmo dinámico de 2.8 a 3.8 palabras por segundo por bloque).\n"
            + "6. CIERRE PERFECTO Y CONCLUSIVO: La última oración del último bloque DEBE quedar 100% terminada sintácticamente con sentido completo, remate contundente y signo de exclamación (!) o punto final. NUNCA cortes la última oración dejando palabras a medias ni conectores colgantes.\n\n"
            + prompt_maestro
        )

        resp_s3: Dict[str, Any] = {"text": None, "err": None}

        def _worker_s3():
            try:
                res3 = _ejecutar_llamada_con_fallback(client_3, mod_3, instruccion_sintesis, 0.30, http_timeout)
                if res3:
                    resp_s3["text"] = res3
            except Exception as ex:
                resp_s3["err"] = ex

        t3 = threading.Thread(target=_worker_s3, daemon=True)
        t3.start()

        while t3.is_alive():
            if cancelar_check and cancelar_check():
                raise InterruptedError("Generación de guion cancelada por el usuario.")
            time.sleep(0.12)

        txt_final = resp_s3.get("text")
        if not txt_final:
            txt_final = txt_d1 or txt_d2

        if txt_final and len(txt_final.strip()) > 80:
            _notif(0.85, f"Multi-Agente ({desc_combo}): Validando cadencia y catálogo de efectos...")
            guion_limpio, advertencias = sanitizar_y_auditar_guion(txt_final, dur_seg)
            if len(advertencias) >= 2:
                guion_limpio = self._reparar_conteo_palabras(client_3, mod_3, guion_limpio, advertencias)
            _notif(1.0, f"✓ Guion completado con éxito ({desc_combo}).")
            return guion_limpio

        return None

    def _generar_guion_3_instancias_lite(self, *args, **kwargs):
        """Alias para compatibilidad hacia atrás."""
        return self._generar_guion_3_instancias_adaptativo(*args, **kwargs)

# Instancia única en memoria para conservar la caché de salud durante la sesión
_ORCHESTRATOR_INSTANCE: Optional[GeminiPoolOrchestrator] = None


# =====================================================================
# FUNCIÓN PRINCIPAL DE ENTRADA (COMPATIBLE CON TODA LA APLICACIÓN)
# =====================================================================
PROMPT_COMPACTO_INTERNO = """Actúa como el mejor Director de Retención Viral y Guionista de YouTube Shorts del mundo (especialista en psicología de la atención estilo MrBeast, Reacciones, Bromas, Curiosidades y Gaming).

Tu única misión es VER Y ANALIZAR segundo a segundo el video y redactar un guion adictivo, milimétricamente sincronizado y diseñado para destruir las dos métricas clave del algoritmo de YouTube:
1. Superar el 85% de "Viewed vs. Swiped Away" (Gancho hipnótico en los primeros 2 segundos).
2. Superar el 110% de Retención Promedio (APV) mediante tensión creciente y un LOOP INFINITO PERFECTO entre el final y el principio.

🚫 REGLAS DE ORO INQUEBRANTABLES:
- PROHIBIDO INCLUIR LLAMADAS A LA ACCIÓN (CTA): Jamás digas "suscríbete", "dale like", "comenta", "comparte" ni despedidas.
- PROHIBIDO INVENTAR ASSETS: Solo puedes usar los EFECTOS, SFX, EMOJIS, FLECHAS y CÍRCULOS listados estrictamente abajo.
- PROHIBIDO TERMINAR EN PUNTOS SUSPENSIVOS "..." O DEJAR ORACIONES INCOMPLETAS: Cada frase debe estar 100% terminada sintácticamente con signo de exclamación (!) o punto final. NUNCA cortes la última oración dejando palabras a medias como "porque jamás...", "cuando descubrió que..." o "y todo por...". La última oración debe cerrar con un remate ingenioso y completo.
- PROHIBIDO DEJAR BLOQUES SIN NARRACIÓN: La voz en español debe hablar de corrido en todos los bloques sin silencios.

================================================================================
🔥 FÓRMULA ALGORÍTMICA DE RETENCIÓN Y LOOP PERFECTO
================================================================================
1. GANCHO DEMOLEDOR (00:00 - 00:04):
   - Abre INMEDIATAMENTE en medio de la acción planteando un peligro, trampa o pregunta visual urgente.
   - El primer bloque abre con gancho explosivo con `zoom_impacto` o `zoom_in` + SFX (`crowd_shocked` o `boxing_bell`). Si NO hay un objeto físico clave y concreto que señalar en pantalla, pon 'ninguna' en FLECHA. NUNCA fuerces una flecha vacía.
2. ESCALADA DE CURIOSIDAD (Bloques intermedios):
   - Conectores de tensión: "¡Pero mira con atención lo que hace!", "¡Lo que no imagina es que...", "¡Cuidado porque el plan recién empieza!".
3. REMATE CONCLUSIVO Y REDONDO + LOOP INFINITO (Último bloque):
   - Narra hasta el último milisegundo, pero la última oración del último bloque DEBE quedar 100% terminada sintácticamente con sentido completo, remate contundente y signo de exclamación (!) o punto final. NUNCA dejes frases cortadas ni conectores subordinados inconclusos (ejemplos prohibidos: "...porque este...", "...cuando la...", "...para que...").

================================================================================
🎯 SINCRONIZACIÓN VISUAL REAL (PROHIBIDO ADELANTARSE A LOS HECHOS)
================================================================================
- La narración debe ir ESTRICTAMENTE SINCRONIZADA con lo que el espectador está viendo en pantalla en ese segundo exacto.
- PROHIBIDO EL SPOILER TEMPRANO: Si la caída, susto, giro o error ocurre en el segundo 00:08, no lo digas en el bloque de 00:00-00:05.
- En los bloques previos crea intriga, expectativa y describe la preparación ('Mira con atención lo que está a punto de pasar...').
- Relata el impacto, revelación o desenlace ÚNICAMENTE en el bloque de tiempo en que físicamente ocurre en el video.
- Los tramos MM:SS - MM:SS son DINÁMICOS: ajústalos a los cortes reales de acción del video (bloques de entre 3.0s y 6.0s según si la escena es rápida o lenta).

================================================================================
🎭 HUMOR NEGRO, CHISTES SORPRENDENTES Y PICARDÍA (MUY DIVERTIDO Y MÁXIMA RETENCIÓN)
================================================================================
- El guion DEBE ser muy entretenido, con humor negro, chistes que sorprendan, comentarios mordaces, sarcásticos y un poco groseros o atrevidos burlándose del karma, de los errores y de las ridiculeces de los protagonistas en escena.
- Remates cómicos contundentes y desopilantes que hagan reír o asombren al espectador por lo directos y ocurrentes.

================================================================================
⏱️ MATEMÁTICA EXACTA DE TIEMPOS (1x) Y CONTEO DE PALABRAS (3.0 - 3.7 pal/seg)
================================================================================
- Bloque de 3s -> EXACTAMENTE entre 9 y 11 palabras.
- Bloque de 4s -> EXACTAMENTE entre 12 y 15 palabras.
- Bloque de 5s -> EXACTAMENTE entre 15 y 18 palabras.
- Bloque de 6s -> EXACTAMENTE entre 18 y 22 palabras.
Redacta 1 o 2 oraciones continuas, ultra expresivas con signos ¡! y ¿?.

================================================================================
🛠️ CATÁLOGO ESTRICTO DE LAS 7 COLUMNAS:
================================================================================
TIEMPO | EFECTO | SFX | EMOJI | FLECHA | CIRCULO | TEXTO

1. TIEMPO: MM:SS - MM:SS continuo cubriendo de 00:00 al segundo final real.
2. EFECTO: zoom_impacto, zoom_in, zoom_out, flash, temblor, alerta_roja, brillo_epico, blanco_negro, spotlight, ninguno.
3. SFX: crowd_shocked, whoosh, riser_suction, vine_boom, metal_pipe, heartbeat_fast, record_scratch, suspense_hit, ding, good_idea, cash_ting, punch, boxing_bell, camera_flash, camera_shooter, cartoon_laugh, kids_yeyy, party_horn, awww, error, xp_Error, fart, click, pop, ninguno (máx 2 combinados con +).
4. EMOJI: sorprendido, risa, fiesta, diablo, enojo, lloro, sueno, calavera, cerebro, fuego, ojos, ninguno (opcional :derecha, :izquierda, :arriba_der, :arriba_izq, :centro, :abajo).
5. FLECHA: ninguna, X,Y porcentual (ej: 45,60), izquierda, derecha, arriba, abajo. PROHIBIDO usar 'centro' o 'auto'. Máx 1 o 2 en el video, nunca al final.
6. CIRCULO: 'box:[ymin,xmin,ymax,xmax]@t_ancla:etiqueta' o 'ninguno'. Máx 1 en todo el video.
7. TEXTO: Narración continua cumpliendo la tabla exacta de palabras sin CTA.

================================================================================
PLANTILLA DE ENTREGA OBLIGATORIA:
================================================================================
TITULO_SUPERIOR: [Nombre corto para el archivo MP4]
TITULO_YOUTUBE: [Título viral con emoji y #shorts]
DESCRIPCION_YOUTUBE: [Descripción intrigante de 2 oraciones + pregunta + hashtags #shorts #viral]
ESTADO_PUBLICACION: privado
SCHEDULE: auto
PARA_NINOS: no
MODO_ENCUADRE: full
TONO_VIDEO: fondo
ARCHIVO_SALIDA: auto

[GUION]
TIEMPO | EFECTO | SFX | EMOJI | FLECHA | CIRCULO | TEXTO
00:00 - 00:04 | zoom_impacto | crowd_shocked | sorprendido:derecha | ninguna | ninguno | [12 a 15 palabras exactas con gancho explosivo]
00:04 - 00:08 | alerta_roja | riser_suction | diablo:izquierda | izquierda | ninguno | [12 a 15 palabras aumentando intriga]
00:08 - 00:13 | temblor | punch+xp_Error | risa:derecha | derecha | ninguno | [15 a 18 palabras narrando el clímax con máxima energía]
00:13 - 00:17 | brillo_epico | cash_ting+party_horn | fiesta:derecha | ninguna | ninguno | [12 a 15 palabras cerrando con remate completo y conectando en loop con el inicio]"""


def obtener_modelos_plantilla() -> List[Dict[str, Any]]:
    """Devuelve la estructura de modelos lista para renderizado inicial o sin claves."""
    return [
        {
            "id": m_id,
            "nombre": m_nombre,
            "nombre_corto": m_corto,
            "vivas": 0,
            "total": 0,
            "tipo": "standby",
            "tag": "COMPROBAR",
            "desc": "Toca Refrescar",
            "color_borde": "#334155",
            "color_bg": "#151a2d",
            "color_pill_bg": "#1e293b",
            "color_texto": "#94a3b8",
        }
        for m_id, m_nombre, m_corto in [
            ("gemini-4-argon", "Argon 4", "Argon"),
            ("gemini-3.8-flash", "Gemini 3.8 Flash", "3.8"),
            ("gemini-3.6-flash", "Gemini 3.6 Flash", "3.6"),
            ("gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite", "3.5"),
        ]
    ]


def auditar_estado_pool_en_vivo() -> List[Dict[str, Any]]:
    """Función pública para verificar el estado de cuotas de todos los modelos en vivo."""
    keys = obtener_gemini_api_keys()
    if not keys:
        res = obtener_modelos_plantilla()
        for r in res:
            r["tipo"] = "sin_claves"
            r["tag"] = "SIN CLAVES"
            r["desc"] = "Carga tu API Key"
        return res
    orch = GeminiPoolOrchestrator(api_keys=keys)
    return orch.auditar_modelos_en_vivo()


def generar_guion_con_gemini_flash(
    ruta_video: Path,
    api_key: str,
    schedule_str: str = "auto",
    modo_privacidad: str = "privado",
    contexto_titulo_orig: str = "",
    modelo_preferido: str = "gemini-3.8-flash",
    progreso_cb: Optional[object] = None,
    contexto_feedback: str = "",
    auto_auditoria_retrospectiva: bool = False,
    guion_previo: Optional[str] = None,
    cancelar_check: Optional[Callable[[], bool]] = None,
    modo_pasadas: str = "Triple Pasada (3x)",
) -> str:
    """
    Punto de entrada maestro para generar guiones virales:
    - Inicializa el orquestador con Fast-Probing paralelo multi-cuenta.
    - Ejecuta el Single-Pass Master Prompt de alta retención.
    - Persiste el guion en DEFAULT_GUION_TXT y realiza validación de ritmo.
    """
    global _ORCHESTRATOR_INSTANCE

    keys_pool: List[str] = []
    for k in obtener_gemini_api_keys():
        if k not in keys_pool:
            keys_pool.append(k)
    if api_key:
        for k in extraer_gemini_api_keys(api_key):
            if k not in keys_pool:
                keys_pool.append(k)
    if not keys_pool:
        raise ValueError("No ingresaste tu GEMINI_API_KEY gratuita de Google AI Studio.")

    # Reusar o refrescar el orquestador si las claves cambiaron
    if _ORCHESTRATOR_INSTANCE is None or set(_ORCHESTRATOR_INSTANCE.api_keys) != set(keys_pool):
        _ORCHESTRATOR_INSTANCE = GeminiPoolOrchestrator(api_keys=keys_pool)

    dur_seg, _, _, _ = obtener_info_video(ruta_video)
    dur_redondeada = max(5, int(round(dur_seg)))

    # Recuperar metadatos originales
    if not ULTIMA_INFO_YTDLP.get("titulo") or not ULTIMA_INFO_YTDLP.get("descripcion"):
        candidatos_info = [ruta_video.with_suffix(".info.json"), BASE_DIR / "video_input.info.json"]
        for c_path in candidatos_info:
            if c_path.exists():
                try:
                    d_json = json.loads(c_path.read_text(encoding="utf-8", errors="replace"))
                    if not ULTIMA_INFO_YTDLP.get("titulo"):
                        ULTIMA_INFO_YTDLP["titulo"] = str(d_json.get("title") or "").strip()
                    if not ULTIMA_INFO_YTDLP.get("descripcion"):
                        ULTIMA_INFO_YTDLP["descripcion"] = str(d_json.get("description") or "").strip()[:800]
                    break
                except Exception:
                    pass

    tit_ctx = (ULTIMA_INFO_YTDLP.get("titulo") or "").strip()
    if contexto_titulo_orig and not contexto_titulo_orig.lower().startswith("video link"):
        tit_ctx = contexto_titulo_orig.strip() or tit_ctx
    desc_ctx = (ULTIMA_INFO_YTDLP.get("descripcion") or "").strip()

    bloque_contexto_real = ""
    if tit_ctx or desc_ctx:
        bloque_contexto_real = (
            f"\nCONTEXTO REAL DEL VIDEO ORIGINAL:\n"
            + (f"- TÍTULO ORIGINAL: {tit_ctx}\n" if tit_ctx else "")
            + (f"- DESCRIPCIÓN ORIGINAL: {desc_ctx}\n" if desc_ctx else "")
        )

    bloque_feedback = ""
    if contexto_feedback and contexto_feedback.strip():
        bloque_previo_str = f"\n--- [GUION PREVIO]:\n{guion_previo.strip()}\n" if (guion_previo and guion_previo.strip()) else ""
        bloque_feedback = (
            f"\nCORRECCIONES DEL USUARIO (PALABRA SAGRADA):\n\"{contexto_feedback.strip()}\"\n"
            f"Usa exactamente sus palabras tal cual las escribió sin inventar sinónimos.\n{bloque_previo_str}"
        )

    instruccion_extra = (
        f"{bloque_contexto_real}\n{bloque_feedback}\n"
        f"DATOS TÉCNICOS Y DIRECTIVAS DE EDICIÓN:\n"
        f"- Duración total exacta: {dur_redondeada} segundos (00:00 a 00:{dur_redondeada:02d}).\n"
        f"- TIMING DINÁMICO POR ACCIÓN REAL: No uses bloques rígidos idénticos. Ajusta los tramos MM:SS - MM:SS al ritmo real del video (bloques entre 3.0s y 6.0s según si la escena es pausada o acelerada), cubriendo desde 00:00 hasta 00:{dur_redondeada:02d}.\n"
        f"- PROHIBIDO ADELANTARSE (CERO SPOILERS): Narra en tiempo real lo que está en pantalla. Si algo ocurre en el segundo 8, narra la preparación antes y el impacto recién en el segundo 8.\n"
        f"- HUMOR SARCÁSTICO / NEGRO (1 O 2 VECES): Incorpora 1 o 2 comentarios irónicos, ácidos o de humor negro sobre lo que pasa, dosificados para dar impacto sin cansar.\n"
        f"- En ESTADO_PUBLICACION escribe: {modo_privacidad}\n"
        f"- En SCHEDULE escribe: {schedule_str.strip() if schedule_str.strip() else 'no'}\n"
        f"- En PARA_NINOS escribe: no\n"
        f"- En TONO_VIDEO escribe 'triste', 'inspiracional' o 'fondo'.\n"
        f"- En TITULO_YOUTUBE incluye 1 o 2 emojis llamativos y #shorts al final.\n"
    )

    prompt_maestro = (
        PROMPT_COMPACTO_INTERNO + "\n\n" + instruccion_extra +
        "\nEntrega ÚNICAMENTE el bloque estructurado del guion final con la plantilla obligatoria:"
    )

    es_triple = ("triple" in str(modo_pasadas).lower() or "3x" in str(modo_pasadas).lower() or "3" in str(modo_pasadas).lower())
    texto_respuesta = _ORCHESTRATOR_INSTANCE.generar_guion_completo(
        video_path=ruta_video,
        prompt_maestro=prompt_maestro,
        progreso_cb=progreso_cb,
        timeout_video_seg=38.0,
        modelo_preferido=modelo_preferido,
        cancelar_check=cancelar_check,
        triple_pasada=es_triple,
    )

    DEFAULT_GUION_TXT.write_text(texto_respuesta + "\n", encoding="utf-8")

    try:
        en_bloques = False
        resumen_ritmo = []
        for ln in texto_respuesta.splitlines():
            if "[GUION]" in ln:
                en_bloques = True
                continue
            if en_bloques and "|" in ln:
                partes = [p.strip() for p in ln.split("|")]
                if len(partes) >= 7 and "-" in partes[0] and ":" in partes[0]:
                    resumen_ritmo.append(evaluar_ritmo_bloque(partes[0], partes[6]))
        if resumen_ritmo:
            ok_cnt = sum(1 for r in resumen_ritmo if r["estado"] == "OK")
            logger.info(f"Auditoría de ritmo: {ok_cnt}/{len(resumen_ritmo)} bloques calibrados.")
    except Exception:
        pass

    return texto_respuesta
