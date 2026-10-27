#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
EDITOR SHORTS STUDIO v1.0 - Automatización de YouTube Shorts con IA
================================================================================
- Descarga automática de videos/Shorts de YouTube con yt-dlp (o archivo MP4 local).
- Narración con Voz IA expresiva + Masterización de estudio con FFmpeg.
- Subtítulos dinámicos ultra llamativos con efectos luminosos (Resplandor Neón
  multicapa, brillo especular y pulso reactivo a la voz).
- Seguimiento inteligente de objetivos (Optical Flow + Saliencia en movimiento)
  para Flechas Rojas (flecha.png) y Círculos Rojos (circulo_rojo.png).
- Efectos de cámara y color sincronizados con los 19 SFX y 7 Emojis animados.
================================================================================
"""

import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.request
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False


# ==============================================================================
# 1. CONFIGURACIÓN GENERAL Y RUTAS DE ASSETS
# ==============================================================================
WIDTH = 1080
HEIGHT = 1920
FPS = 60
CPU_THREADS = max(4, (os.cpu_count() or 8))

MODO_ENCUADRE_DEFAULT = "full"  # "full" (9:16 crop-fill) o "blur" (fondo borroso para horizontales)
VOLUMEN_VOZ_NARRADOR = 1.48
VOLUMEN_AUDIO_VIDEO_ORIGINAL = 0.0
SUBTITLE_OFFSET_SEC = -0.02
DURACION_CALLOUTS_DEFAULT = 1.8  # Segundos que permanecen visibles las flechas y círculos (Shorts ágiles)

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

BASE_DIR = Path(__file__).resolve().parent


def _resolver_carpeta_asset(nombre: str) -> Path:
    directa = BASE_DIR / nombre
    if directa.exists():
        return directa
    en_assets = BASE_DIR / "assets" / nombre
    if en_assets.exists():
        return en_assets
    directa.mkdir(parents=True, exist_ok=True)
    return directa


EMOJIS_DIR = _resolver_carpeta_asset("emojis")
FONTS_DIR = _resolver_carpeta_asset("fonts")
FOTOS_DIR = _resolver_carpeta_asset("fotos")
SFX_DIR = _resolver_carpeta_asset("sfx")
TEMP_DIR = BASE_DIR / "temp_build"
OUTPUT_DIR = BASE_DIR / "output_shorts"

DEFAULT_VIDEO_INPUT = BASE_DIR / "video_input.mp4"
DEFAULT_GUION_TXT = BASE_DIR / "guion_video.txt"
PROMPT_IA_PATH = BASE_DIR / "PROMPT_PARA_IA_GUIONES.txt"


# ==============================================================================
# 2. ESTRUCTURAS DE DATOS
# ==============================================================================
@dataclass
class SegmentoVideoGuion:
    id_segmento: str
    texto_voz: str
    efecto_visual: str = "ninguno"          # "zoom_impacto", "zoom_in", "zoom_out", "flash", "temblor", "alerta_roja", "brillo_epico", "blanco_negro", "ninguno"
    t_inicio_video: Optional[float] = None  # Segundos en el video original (None = reparto automático)
    t_fin_video: Optional[float] = None     # Segundos en el video original (None = reparto automático)
    pausa_final_seg: float = 0.16
    sfx_lista: List[str] = field(default_factory=list)
    emoji: Optional[str] = None             # "diablo", "enojo", "fiesta", "lloro", "risa", "sorprendido", "sueno"
    posicion_emoji: str = "auto"            # "auto", "derecha", "izquierda", "arriba_der", "arriba_izq", "centro"
    flecha: Optional[str] = None            # "centro", "izquierda", "derecha", "arriba", "abajo", "auto", "x,y", "x1,y1->x2,y2", None
    circulo: Optional[str] = None           # "centro", "izquierda", "derecha", "arriba", "abajo", "auto", "x,y", "si", None
    tamano_circulo: str = "medio"           # "chico", "medio", "grande"


@dataclass
class ConfigGuion:
    titulo_superior: str = ""
    modo_encuadre: str = MODO_ENCUADRE_DEFAULT
    voz_narrador: str = EDGE_VOICE_DEFAULT
    archivo_salida: Optional[str] = None
    volumen_video_original: float = VOLUMEN_AUDIO_VIDEO_ORIGINAL
    duracion_callouts: float = DURACION_CALLOUTS_DEFAULT
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


# ==============================================================================
# 3. PARSER INTELIGENTE DE GUIONES Y NORMALIZACIÓN DE ASSETS
# ==============================================================================
PLANTILLA_GUION_DEFAULT = """TITULO_SUPERIOR: Abuela Venganza Epica Troleo
MODO_ENCUADRE: full
VOLUMEN_VIDEO_ORIGINAL: 0
ARCHIVO_SALIDA: auto

[GUION]
TIEMPO | EFECTO | SFX | EMOJI | FLECHA | CIRCULO | TEXTO
00:00 - 00:05 | zoom_impacto | crowd_shocked | sorprendido:derecha | izquierda | ninguno | ¡Mira cómo esta nieta traviesa engaña a su abuela escondiendo la pelota de tenis! ¡La pobre no entiende absolutamente nada!
00:05 - 00:10 | zoom_in | whoosh+xp_Error | enojo:izquierda | centro | ninguno | ¡La broma sigue cuando hace desaparecer otro objeto frente a su cara! ¡Su abuela busca confundida por toda la mesa!
00:10 - 00:15 | alerta_roja | riser_suction | diablo:derecha | izquierda | izquierda:grande | ¡Pero cuidado porque la abuela ya tenía preparada una trampa secreta! ¡Prepárate para ver la venganza más épica de todas!
00:15 - 00:20 | temblor | punch+cartoon_laugh | risa:izquierda | derecha | ninguno | ¡Toma esto por tramposa! ¡La nieta termina con toda la cara completamente llena de harina blanca en un segundo!
00:20 - 00:25 | brillo_epico | cash_ting+party_horn | fiesta:derecha | ninguna | ninguno | ¡La abuela celebra su victoria mientras la nieta no puede creer lo que acaba de pasar! ¡Una venganza perfecta!
"""


def _quitar_acentos(texto: str) -> str:
    norm = unicodedata.normalize("NFD", str(texto))
    return "".join(c for c in norm if unicodedata.category(c) != "Mn")


def _parsear_tiempo_a_segundos(t_str: str) -> Optional[float]:
    t_str = str(t_str).strip()
    if not t_str or t_str.lower() in ("auto", "-", "none", "null"):
        return None
    if ":" in t_str:
        partes = t_str.split(":")
        try:
            if len(partes) == 2:
                return int(partes[0]) * 60.0 + float(partes[1].replace(",", "."))
            elif len(partes) == 3:
                return int(partes[0]) * 3600.0 + int(partes[1]) * 60.0 + float(partes[2].replace(",", "."))
        except ValueError:
            return None
    try:
        return float(t_str.replace(",", "."))
    except ValueError:
        return None


def _normalizar_efecto(efecto_raw: Optional[str]) -> str:
    if not efecto_raw:
        return "ninguno"
    e = _quitar_acentos(str(efecto_raw).strip().lower()).replace(" ", "_")
    if not e or e in ("ninguno", "ninguna", "none", "no", "-", "normal"):
        return "ninguno"

    mapa_efectos = {
        "zoom_impacto": "zoom_impacto",
        "impacto": "zoom_impacto",
        "punch": "zoom_impacto",
        "golpe": "zoom_impacto",
        "choque": "zoom_impacto",
        "shock": "zoom_impacto",
        "saludo": "zoom_impacto",
        "zoom_in": "zoom_in",
        "zoom": "zoom_in",
        "acercar": "zoom_in",
        "hablando": "zoom_in",
        "zoom_out": "zoom_out",
        "alejar": "zoom_out",
        "hablando2": "zoom_out",
        "flash": "flash",
        "destello": "flash",
        "camara": "flash",
        "foto": "flash",
        "temblor": "temblor",
        "shake": "temblor",
        "terremoto": "temblor",
        "vibracion": "temblor",
        "alerta_roja": "alerta_roja",
        "alerta": "alerta_roja",
        "peligro": "alerta_roja",
        "rojo": "alerta_roja",
        "error": "alerta_roja",
        "brillo_epico": "brillo_epico",
        "epico": "brillo_epico",
        "glow": "brillo_epico",
        "dorado": "brillo_epico",
        "victoria": "brillo_epico",
        "fiesta": "brillo_epico",
        "like": "brillo_epico",
        "blanco_negro": "blanco_negro",
        "gris": "blanco_negro",
        "triste": "blanco_negro",
        "sad": "blanco_negro",
        "fail": "blanco_negro",
        "bn": "blanco_negro",
    }
    return mapa_efectos.get(e, "zoom_in")


def _normalizar_sfx_lista(sfx_raw: Optional[str]) -> List[str]:
    if not sfx_raw:
        return []
    raw_clean = _quitar_acentos(str(sfx_raw).strip().lower())
    raw_clean = raw_clean.replace(".mp3", "").replace(".wav", "").replace(".ogg", "")
    if not raw_clean or raw_clean in ("ninguno", "ninguna", "none", "no", "false", "-", "sin_sfx"):
        return []

    sinonimos_sfx = {
        "shock": "crowd_shocked",
        "sorpresa": "crowd_shocked",
        "asombro": "crowd_shocked",
        "multitud": "crowd_shocked",
        "campana": "boxing_bell",
        "bell": "boxing_bell",
        "boxeo": "boxing_bell",
        "round": "boxing_bell",
        "flash": "camera_flash",
        "destello": "camera_flash",
        "foto": "camera_shooter",
        "camara": "camera_shooter",
        "screenshot": "camera_shooter",
        "risa": "cartoon_laugh",
        "risas": "cartoon_laugh",
        "laugh": "cartoon_laugh",
        "dinero": "cash_ting",
        "caja": "cash_ting",
        "cash": "cash_ting",
        "moneda": "cash_ting",
        "robux": "cash_ting",
        "idea": "good_idea",
        "brillante": "good_idea",
        "correcto": "ding",
        "acierto": "ding",
        "festejo": "kids_yeyy",
        "celebracion": "kids_yeyy",
        "yey": "kids_yeyy",
        "ninos": "kids_yeyy",
        "corneta": "party_horn",
        "fiesta": "party_horn",
        "party": "party_horn",
        "golpe": "punch",
        "impacto": "punch",
        "pelea": "punch",
        "subida": "riser_suction",
        "riser": "riser_suction",
        "suction": "riser_suction",
        "tension": "riser_suction",
        "tictac": "riser_suction",
        "timer": "riser_suction",
        "transicion": "whoosh",
        "viento": "whoosh",
        "windows": "xp_error",
        "xp": "xp_error",
        "bug": "xp_error",
        "fallo": "error",
        "fail": "xp_error",
        "pedo": "fart",
        "broma": "fart",
        "tierno": "awww",
        "triste": "awww",
        "aww": "awww",
    }

    partes = re.split(r"[+,;/]", raw_clean)
    resultado: List[str] = []
    for p in partes:
        item = p.strip().replace(" ", "_")
        if not item or item in ("ninguno", "no", "-"):
            continue
        item_norm = sinonimos_sfx.get(item, item)
        if item_norm not in resultado:
            resultado.append(item_norm)
    return resultado


def _normalizar_emoji(emoji_raw: Optional[str]) -> Tuple[Optional[str], str]:
    if not emoji_raw:
        return None, "auto"
    raw = str(emoji_raw).strip()
    posicion = "auto"
    if ":" in raw:
        raw, pos_part = raw.split(":", 1)
        pos_clean = _quitar_acentos(pos_part.strip().lower())
        if pos_clean in ("izquierda", "derecha", "centro", "arriba", "abajo", "arriba_izq", "arriba_der"):
            posicion = pos_clean

    e = _quitar_acentos(raw.strip().lower())
    e = e.replace(".png", "").replace(".webp", "").replace(".jpg", "")
    if e.startswith("emoji_"):
        e = e[len("emoji_"):]

    if not e or e in ("ninguno", "ninguna", "none", "no", "false", "-", "flecha", "circulo"):
        return None, posicion

    sinonimos_emoji = {
        "diablito": "diablo",
        "malvado": "diablo",
        "enojado": "enojo",
        "furia": "enojo",
        "rabia": "enojo",
        "festejo": "fiesta",
        "celebracion": "fiesta",
        "llorando": "lloro",
        "triste": "lloro",
        "tristeza": "lloro",
        "risas": "risa",
        "riendo": "risa",
        "gracioso": "risa",
        "lol": "risa",
        "sorpresa": "sorprendido",
        "shock": "sorprendido",
        "impactado": "sorprendido",
        "dormido": "sueno",
        "aburrido": "sueno",
        "zzz": "sueno",
    }
    return sinonimos_emoji.get(e, e), posicion


def _normalizar_objetivo(obj_raw: Optional[str]) -> Tuple[Optional[str], str]:
    """
    Normaliza la especificación de FLECHA o CIRCULO.
    Devuelve (objetivo_normalizado, tamano_modificador).
    Ejemplo: 'centro:grande' -> ('centro', 'grande')
             'izquierda'     -> ('izquierda', 'medio')
             'ninguno'       -> (None, 'medio')
    """
    if not obj_raw:
        return None, "medio"
    raw = _quitar_acentos(str(obj_raw).strip().lower())
    raw = raw.replace(".png", "").replace("circulo_rojo", "si").replace("flecha", "si")

    tamano = "medio"
    if ":" in raw:
        base_part, mod_part = raw.split(":", 1)
        mod_clean = mod_part.strip()
        if mod_clean in ("chico", "pequeno", "small", "min"):
            tamano = "chico"
            raw = base_part.strip()
        elif mod_clean in ("grande", "big", "large", "max"):
            tamano = "grande"
            raw = base_part.strip()
        elif mod_clean in ("medio", "normal", "med"):
            tamano = "medio"
            raw = base_part.strip()
        else:
            raw = mod_clean

    if not raw or raw in ("ninguno", "ninguna", "none", "no", "false", "-", "0"):
        return None, tamano

    if raw in ("si", "yes", "true", "1", "activo", "activar", "mismo", "igual"):
        return "si", tamano

    sinonimos_zona = {
        "izq": "izquierda",
        "left": "izquierda",
        "der": "derecha",
        "right": "derecha",
        "center": "centro",
        "medio": "centro",
        "top": "arriba",
        "bottom": "abajo",
        "movimiento": "auto",
        "automatico": "auto",
        "objetivo": "auto",
    }
    return sinonimos_zona.get(raw, raw), tamano


def cargar_guion_video(ruta_guion: Path) -> ConfigGuion:
    if not ruta_guion.exists():
        DEFAULT_GUION_TXT.write_text(PLANTILLA_GUION_DEFAULT.strip() + "\n", encoding="utf-8")
        ruta_guion = DEFAULT_GUION_TXT

    contenido = ruta_guion.read_text(encoding="utf-8-sig").strip()
    if contenido.startswith("```"):
        lineas_md = contenido.splitlines()
        if lineas_md and lineas_md[0].startswith("```"):
            lineas_md = lineas_md[1:]
        if lineas_md and lineas_md[-1].strip().startswith("```"):
            lineas_md = lineas_md[:-1]
        contenido = "\n".join(lineas_md).strip()

    config = ConfigGuion()

    # Soporte para JSON si el usuario pega un bloque JSON
    if contenido.startswith("{"):
        datos = json.loads(contenido)
        config.titulo_superior = str(datos.get("titulo_superior", "") or "").strip()
        config.modo_encuadre = str(datos.get("modo_encuadre", datos.get("modo_pantalla", MODO_ENCUADRE_DEFAULT))).strip().lower()
        salida_raw = str(datos.get("archivo_salida", "") or "").strip()
        config.archivo_salida = None if salida_raw.lower() in ("", "auto", "none", "null") else salida_raw
        if "volumen_video_original" in datos:
            try:
                config.volumen_video_original = float(datos["volumen_video_original"])
            except (ValueError, TypeError):
                pass
        if "duracion_callouts" in datos:
            try:
                config.duracion_callouts = max(0.5, float(datos["duracion_callouts"]))
            except (ValueError, TypeError):
                pass
        for idx, seg in enumerate(datos.get("segmentos", [])):
            t_ini, t_fin = None, None
            if "tiempo" in seg and "-" in str(seg["tiempo"]):
                p1, p2 = str(seg["tiempo"]).split("-", 1)
                t_ini = _parsear_tiempo_a_segundos(p1)
                t_fin = _parsear_tiempo_a_segundos(p2)
            efecto = _normalizar_efecto(seg.get("efecto", seg.get("gesto", "ninguno")))
            sfx_lista = _normalizar_sfx_lista(seg.get("sfx", None))
            emoji, pos_emoji = _normalizar_emoji(seg.get("emoji", None))
            flecha, _ = _normalizar_objetivo(seg.get("flecha", None))
            circulo, tam_c = _normalizar_objetivo(seg.get("circulo", None))
            texto = str(seg.get("texto", seg.get("texto_voz", ""))).strip()
            if flecha == "si" and circulo and circulo != "si":
                flecha = circulo
            elif circulo == "si" and flecha and flecha != "si":
                circulo = flecha
            elif flecha == "si":
                flecha = "auto"
            elif circulo == "si":
                circulo = "auto"

            if texto:
                config.segmentos.append(
                    SegmentoVideoGuion(
                        id_segmento=f"{len(config.segmentos) + 1:02d}_seg",
                        texto_voz=texto,
                        efecto_visual=efecto,
                        t_inicio_video=t_ini,
                        t_fin_video=t_fin,
                        sfx_lista=sfx_lista,
                        emoji=emoji,
                        posicion_emoji=pos_emoji,
                        flecha=flecha,
                        circulo=circulo,
                        tamano_circulo=tam_c,
                    )
                )
        return config

    # Formato de texto estructurado separado por '|'
    en_guion = False
    for linea in contenido.splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith("#") or limpia.startswith("//"):
            continue
        if limpia.upper() in ("[GUION]", "[GUIÓN]", "[SCRIPT]", "[SEGMENTOS]"):
            en_guion = True
            continue

        if not en_guion and ":" in limpia and "|" not in limpia:
            k, v = limpia.split(":", 1)
            k_up = _quitar_acentos(k.strip().upper())
            v_str = v.strip()
            if k_up in ("TITULO_SUPERIOR", "TITULO"):
                config.titulo_superior = "" if v_str.lower() in ("ninguno", "none", "-", "vacio") else v_str
            elif k_up in ("MODO_ENCUADRE", "MODO_PANTALLA", "ENCUADRE"):
                config.modo_encuadre = "blur" if "blur" in v_str.lower() or "borroso" in v_str.lower() else "full"
            elif k_up in ("VOZ", "VOZ_NARRADOR"):
                for label_v, id_v in VOCES_DISPONIBLES.items():
                    if v_str.lower() in label_v.lower() or v_str.lower() == id_v.lower():
                        config.voz_narrador = id_v
                        break
            elif k_up in ("ARCHIVO_SALIDA", "SALIDA", "OUTPUT"):
                config.archivo_salida = None if v_str.lower() in ("", "auto", "none", "-") else v_str
            elif k_up == "VOLUMEN_VIDEO_ORIGINAL":
                try:
                    config.volumen_video_original = float(v_str.replace(",", "."))
                except ValueError:
                    pass
            elif k_up in ("DURACION_CALLOUTS", "DURACION_FLECHAS", "DURACION_CIRCULOS", "DURACION_FLECHAS_CIRCULOS"):
                try:
                    config.duracion_callouts = max(0.5, float(v_str.replace(",", ".")))
                except ValueError:
                    pass
            elif k_up == "PALABRAS_VERDES":
                for w in v_str.split(","):
                    if w.strip():
                        config.palabras_verdes_extra.add(w.strip().upper())
            elif k_up == "PALABRAS_ROJAS":
                for w in v_str.split(","):
                    if w.strip():
                        config.palabras_rojas_extra.add(w.strip().upper())
            continue

        partes = [p.strip() for p in limpia.split("|")]
        if len(partes) >= 2 and _quitar_acentos(partes[0].upper()) in ("TIEMPO", "TIEMPOS", "TIME"):
            continue

        t_ini, t_fin = None, None
        efecto = "ninguno"
        sfx_lista: List[str] = []
        emoji: Optional[str] = None
        pos_emoji = "auto"
        flecha: Optional[str] = None
        circulo: Optional[str] = None
        tam_circulo = "medio"
        texto_voz = ""

        if len(partes) >= 8 and _quitar_acentos(partes[5].lower()) in ("si", "no", "true", "false") and _quitar_acentos(partes[6].lower()) in ("si", "no", "true", "false"):
            # Compatibilidad con guiones antiguos de 8 columnas:
            # TIEMPO | GESTO | SFX | EMOJI | FLECHA | LIKE_SUB | TIMER | TEXTO
            rango_t, gesto_str, sfx_str, emoji_str, flecha_str, likesub_str, timer_str = partes[:7]
            texto_voz = " | ".join(partes[7:]).strip()
            if "-" in rango_t and rango_t.lower() != "-":
                t1, t2 = rango_t.split("-", 1)
                t_ini = _parsear_tiempo_a_segundos(t1)
                t_fin = _parsear_tiempo_a_segundos(t2)
            efecto = _normalizar_efecto(gesto_str)
            sfx_lista = _normalizar_sfx_lista(sfx_str)
            emoji, pos_emoji = _normalizar_emoji(emoji_str)
            flecha, _ = _normalizar_objetivo(flecha_str)
        elif len(partes) >= 7:
            # FORMATO OFICIAL DE 7 COLUMNAS:
            # TIEMPO | EFECTO | SFX | EMOJI | FLECHA | CIRCULO | TEXTO
            rango_t, efecto_str, sfx_str, emoji_str, flecha_str, circulo_str = partes[:6]
            texto_voz = " | ".join(partes[6:]).strip()
            if "-" in rango_t and rango_t.lower() != "-":
                t1, t2 = rango_t.split("-", 1)
                t_ini = _parsear_tiempo_a_segundos(t1)
                t_fin = _parsear_tiempo_a_segundos(t2)
            efecto = _normalizar_efecto(efecto_str)
            sfx_lista = _normalizar_sfx_lista(sfx_str)
            emoji, pos_emoji = _normalizar_emoji(emoji_str)
            flecha, _ = _normalizar_objetivo(flecha_str)
            circulo, tam_circulo = _normalizar_objetivo(circulo_str)
            # Compatibilidad si en la columna 6 pusieron "si/no" de un guion viejo de 7 columnas sin querer
            if circulo == "si" and not flecha:
                circulo = None
        elif len(partes) == 6:
            # TIEMPO | EFECTO | SFX | EMOJI | FLECHA | TEXTO
            rango_t, efecto_str, sfx_str, emoji_str, flecha_str, texto_voz = partes
            if "-" in rango_t and rango_t.lower() != "-":
                t1, t2 = rango_t.split("-", 1)
                t_ini = _parsear_tiempo_a_segundos(t1)
                t_fin = _parsear_tiempo_a_segundos(t2)
            efecto = _normalizar_efecto(efecto_str)
            sfx_lista = _normalizar_sfx_lista(sfx_str)
            emoji, pos_emoji = _normalizar_emoji(emoji_str)
            flecha, _ = _normalizar_objetivo(flecha_str)
        elif len(partes) >= 2:
            rango_t = partes[0]
            if "-" in rango_t and rango_t.lower() != "-":
                t1, t2 = rango_t.split("-", 1)
                t_ini = _parsear_tiempo_a_segundos(t1)
                t_fin = _parsear_tiempo_a_segundos(t2)
            texto_voz = partes[-1]
        else:
            texto_voz = limpia

        # Sincronizar cuando uno dice "si" y el otro tiene la ubicación del objetivo
        if flecha == "si" and circulo and circulo != "si":
            flecha = circulo
        elif circulo == "si" and flecha and flecha != "si":
            circulo = flecha
        elif flecha == "si":
            flecha = "auto"
        elif circulo == "si":
            circulo = "auto"

        if texto_voz:
            config.segmentos.append(
                SegmentoVideoGuion(
                    id_segmento=f"{len(config.segmentos) + 1:02d}_seg",
                    texto_voz=texto_voz,
                    efecto_visual=efecto,
                    t_inicio_video=t_ini,
                    t_fin_video=t_fin,
                    sfx_lista=sfx_lista,
                    emoji=emoji,
                    posicion_emoji=pos_emoji,
                    flecha=flecha,
                    circulo=circulo,
                    tamano_circulo=tam_circulo,
                )
            )

    return config


# ==============================================================================
# 4. TIPOGRAFÍA Y MOTOR DE SUBTÍTULOS LUMINOSOS (RESPLANDOR NEÓN MULTICAPA)
# ==============================================================================
_FONT_CACHE: Dict[int, ImageFont.FreeTypeFont] = {}
_RUTA_FUENTE_ACTIVA: Optional[str] = None
_WORD_SPRITE_CACHE: Dict[Tuple[str, int, Tuple[int, int, int], Tuple[int, int, int], bool], Image.Image] = {}

PALABRAS_VERDES_BASE = {
    "CARO", "DÓLARES", "DOLARES", "MILLONES", "MIL", "DINERO", "PRECIO",
    "VALE", "PRO", "PROS", "VICTORIA", "GANAR", "GANÉ", "GRATIS", "ORO",
    "ROBUX", "MUCHÍSIMO", "MUCHISIMO", "MEJOR", "FAVORITA", "FAVORITO",
    "PREMIO", "SORTEO", "100", "99", "NOVENTA", "NUEVE",
}
PALABRAS_ROJAS_BASE = {
    "IMPOSIBLE", "LOCURA", "DIFÍCIL", "DIFICIL", "NUNCA", "SECRETO",
    "SUSCRÍBETE", "SUSCRIBETE", "SUSCRIBITE", "LIKE", "PELIGRO", "PROHIBIDO",
    "MUERTE", "ERROR", "ESTAFA", "POCO", "NADA", "PEOR", "OCULTO", "FALLA",
    "CORTA", "CUIDADO", "JAMÁS", "JAMAS",
}
PALABRAS_CIAN_BASE = {
    "2050", "2026", "2000", "CINCUENTA", "VEINTISÉIS", "VEINTISEIS",
    "CÓMO", "COMO", "QUÉ", "QUE", "CUÁL", "CUAL", "FUTURO", "TIEMPO",
    "AÑO", "ANO", "NIVEL", "MIRA", "MIRÁ", "ATENCIÓN", "ATENCION",
}


def asegurar_fuente_mrbeast() -> Optional[str]:
    global _RUTA_FUENTE_ACTIVA
    if _RUTA_FUENTE_ACTIVA and os.path.exists(_RUTA_FUENTE_ACTIVA):
        return _RUTA_FUENTE_ACTIVA

    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    preferidas = [
        "MrBeast_Gaming_Font.ttf",
        "KomikaAxis.ttf",
        "KOMIKAX_.ttf",
        "MrBeast.ttf",
        "Burbank.ttf",
        "ObelixPro.ttf",
    ]
    for nombre in preferidas:
        candidata = FONTS_DIR / nombre
        if candidata.exists():
            _RUTA_FUENTE_ACTIVA = str(candidata)
            return _RUTA_FUENTE_ACTIVA

    for archivo in sorted(FONTS_DIR.glob("*.[to]tf")):
        if archivo.stat().st_size > 10_000:
            _RUTA_FUENTE_ACTIVA = str(archivo)
            return _RUTA_FUENTE_ACTIVA

    sistema = [
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/ariblk.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for s in sistema:
        if os.path.exists(s):
            _RUTA_FUENTE_ACTIVA = s
            return _RUTA_FUENTE_ACTIVA
    return None


def cargar_fuente(tamano: int) -> ImageFont.FreeTypeFont:
    if tamano in _FONT_CACHE:
        return _FONT_CACHE[tamano]
    ruta = asegurar_fuente_mrbeast()
    if ruta:
        try:
            _FONT_CACHE[tamano] = ImageFont.truetype(ruta, tamano)
            return _FONT_CACHE[tamano]
        except Exception:
            pass
    _FONT_CACHE[tamano] = ImageFont.load_default()
    return _FONT_CACHE[tamano]


def _obtener_sprite_palabra_luminosa(
    texto_up: str,
    tam_fuente: int,
    color_relleno: Tuple[int, int, int],
    color_glow: Tuple[int, int, int],
    es_activa: bool,
) -> Image.Image:
    """
    Construye y cachea un sprite RGBA para una palabra con:
    1) Sombra 3D profunda en la capa inferior (para no tapar la luz neón)
    2) Resplandor Neón Exterior amplio (GaussianBlur radio 22, trazo ancho)
    3) Halo Neón Incandescente intenso por fuera del borde negro (GaussianBlur radio 7)
    4) Contorno exterior luminoso + Borde negro nítido
    5) Relleno vibrante + Brillo especular superior cristalino
    """
    clave = (texto_up, tam_fuente, color_relleno, color_glow, es_activa)
    if clave in _WORD_SPRITE_CACHE:
        return _WORD_SPRITE_CACHE[clave]

    fuente = cargar_fuente(tam_fuente)
    grosor_borde_negro = 9 if es_activa else 8
    pad = 58 if es_activa else 42

    dummy = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    d_dummy = ImageDraw.Draw(dummy)
    bbox = d_dummy.textbbox((0, 0), texto_up, font=fuente, stroke_width=grosor_borde_negro + 16)
    w_txt = max(1, bbox[2] - bbox[0])
    h_txt = max(1, bbox[3] - bbox[1])

    w_canvas = w_txt + pad * 2
    h_canvas = h_txt + pad * 2
    cx = w_canvas // 2
    cy = h_canvas // 2

    lienzo_palabra = Image.new("RGBA", (w_canvas, h_canvas), (0, 0, 0, 0))

    # 1. Sombra 3D profunda al fondo (detrás del resplandor neón)
    capa_sombra = Image.new("RGBA", (w_canvas, h_canvas), (0, 0, 0, 0))
    d_sombra = ImageDraw.Draw(capa_sombra)
    sx, sy = (6, 10) if es_activa else (5, 8)
    d_sombra.text(
        (cx + sx, cy + sy),
        texto_up,
        font=fuente,
        fill=(0, 0, 0, 220),
        anchor="mm",
        stroke_width=grosor_borde_negro + 4,
        stroke_fill=(0, 0, 0, 220),
    )
    capa_sombra = capa_sombra.filter(ImageFilter.GaussianBlur(radius=3.5))
    lienzo_palabra = Image.alpha_composite(lienzo_palabra, capa_sombra)

    # 2. Resplandor Neón Exterior Amplio (Aura luminosa que sobresale del borde negro)
    capa_aura = Image.new("RGBA", (w_canvas, h_canvas), (0, 0, 0, 0))
    d_aura = ImageDraw.Draw(capa_aura)
    alpha_aura = 250 if es_activa else 135
    d_aura.text(
        (cx, cy),
        texto_up,
        font=fuente,
        fill=(*color_glow, alpha_aura),
        anchor="mm",
        stroke_width=grosor_borde_negro + (18 if es_activa else 10),
        stroke_fill=(*color_glow, alpha_aura),
    )
    capa_aura = capa_aura.filter(ImageFilter.GaussianBlur(radius=20 if es_activa else 12))
    lienzo_palabra = Image.alpha_composite(lienzo_palabra, capa_aura)

    # 3. Halo Neón Interior Incandescente (Luz concentrada pegada al exterior del trazo)
    if es_activa:
        capa_halo = Image.new("RGBA", (w_canvas, h_canvas), (0, 0, 0, 0))
        d_halo = ImageDraw.Draw(capa_halo)
        color_halo_claro = (
            min(255, color_glow[0] + 75),
            min(255, color_glow[1] + 75),
            min(255, color_glow[2] + 75),
            255,
        )
        d_halo.text(
            (cx, cy),
            texto_up,
            font=fuente,
            fill=color_halo_claro,
            anchor="mm",
            stroke_width=grosor_borde_negro + 9,
            stroke_fill=color_halo_claro,
        )
        capa_halo = capa_halo.filter(ImageFilter.GaussianBlur(radius=6.0))
        lienzo_palabra = Image.alpha_composite(lienzo_palabra, capa_halo)

    # 4. Contorno luminoso fino + Borde negro nítido + Relleno vibrante
    capa_texto = Image.new("RGBA", (w_canvas, h_canvas), (0, 0, 0, 0))
    d_txt = ImageDraw.Draw(capa_texto)

    if es_activa:
        color_rim = (
            min(255, color_glow[0] + 95),
            min(255, color_glow[1] + 95),
            min(255, color_glow[2] + 95),
            235,
        )
        d_txt.text(
            (cx, cy),
            texto_up,
            font=fuente,
            fill=color_rim,
            anchor="mm",
            stroke_width=grosor_borde_negro + 3,
            stroke_fill=color_rim,
        )

    d_txt.text(
        (cx, cy),
        texto_up,
        font=fuente,
        fill=(*color_relleno, 255),
        anchor="mm",
        stroke_width=grosor_borde_negro,
        stroke_fill=(8, 8, 14, 255),
    )

    # 5. Brillo especular superior en letras activas (efecto luminoso cristalino)
    if es_activa:
        mascara_interior = Image.new("L", (w_canvas, h_canvas), 0)
        d_mask = ImageDraw.Draw(mascara_interior)
        d_mask.text((cx, cy), texto_up, font=fuente, fill=255, anchor="mm", stroke_width=0)
        grad_np = np.zeros((h_canvas, w_canvas), dtype=np.uint8)
        y_top = max(0, cy - h_txt // 2)
        y_mid = min(h_canvas, cy + 4)
        if y_mid > y_top:
            rampa = np.linspace(155, 0, y_mid - y_top, dtype=np.float32)
            grad_np[y_top:y_mid, :] = rampa[:, None].astype(np.uint8)
        grad_img = Image.fromarray(grad_np, mode="L")
        brillo_alpha = ImageChops.multiply(mascara_interior, grad_img)
        capa_brillo = Image.new("RGBA", (w_canvas, h_canvas), (255, 255, 255, 0))
        capa_brillo.putalpha(brillo_alpha)
        capa_texto = Image.alpha_composite(capa_texto, capa_brillo)

    sprite_final = Image.alpha_composite(lienzo_palabra, capa_texto)
    if len(_WORD_SPRITE_CACHE) > 600:
        _WORD_SPRITE_CACHE.clear()
    _WORD_SPRITE_CACHE[clave] = sprite_final
    return sprite_final


def _clasificar_color_palabra(
    palabra_limpia: str,
    texto_original: str,
    forzar_destaque: bool,
    verdes: Set[str],
    rojas: Set[str],
    cianes: Set[str],
) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """
    Devuelve (color_relleno_rgb, color_glow_neon_rgb) para la palabra activa.
    """
    if palabra_limpia in verdes:
        # Verde Esmeralda Luminoso
        return (65, 255, 120), (0, 240, 85)
    if palabra_limpia in rojas:
        # Rojo / Magenta Neón Intenso
        return (255, 72, 88), (255, 15, 55)
    if palabra_limpia in cianes or "?" in texto_original or "¿" in texto_original or palabra_limpia.isdigit():
        # Cian Eléctrico Luminoso
        return (75, 242, 255), (0, 185, 255)
    if forzar_destaque:
        # Dorado Solar Brillante
        return (255, 248, 90), (255, 165, 0)
    # Amarillo Ciber / Dorado Luminoso por defecto para la palabra activa
    return (255, 238, 25), (255, 175, 0)


def _agrupar_palabras_subtitulos(palabras: List[PalabraSubtitulo]) -> List[List[Tuple[int, PalabraSubtitulo]]]:
    """
    Agrupa las palabras en bloques de 2 a 3 palabras (o 1 si es muy larga)
    para que nunca se desborden del ancho de 1080px y mantengan un ritmo rápido.
    """
    grupos: List[List[Tuple[int, PalabraSubtitulo]]] = []
    grupo_actual: List[Tuple[int, PalabraSubtitulo]] = []
    chars_actual = 0

    for idx, p in enumerate(palabras):
        largo = len(p.texto)
        max_palabras = 2 if largo >= 9 or any(len(x[1].texto) >= 9 for x in grupo_actual) else 3
        if grupo_actual and (len(grupo_actual) >= max_palabras or chars_actual + largo > 18):
            grupos.append(grupo_actual)
            grupo_actual = []
            chars_actual = 0

        grupo_actual.append((idx, p))
        chars_actual += largo + 1

        if p.texto.endswith(("!", "?", ".", ":", ";")) and len(grupo_actual) >= 1:
            grupos.append(grupo_actual)
            grupo_actual = []
            chars_actual = 0

    if grupo_actual:
        grupos.append(grupo_actual)
    return grupos


_BACKDROP_PILL_CACHE: Dict[Tuple[int, int], Image.Image] = {}


def _obtener_backdrop_subtitulo(ancho_bloque: int, alto_bloque: int = 160) -> Image.Image:
    w_q = min(WIDTH, max(320, ((ancho_bloque + 140) // 40) * 40))
    clave = (w_q, alto_bloque)
    if clave in _BACKDROP_PILL_CACHE:
        return _BACKDROP_PILL_CACHE[clave]
    img = Image.new("RGBA", (w_q, alto_bloque), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        [28, 28, w_q - 28, alto_bloque - 28],
        radius=50,
        fill=(4, 6, 14, 118),
    )
    img = img.filter(ImageFilter.GaussianBlur(radius=20))
    _BACKDROP_PILL_CACHE[clave] = img
    return img


def renderizar_subtitulos_luminosos(
    lienzo: Image.Image,
    palabras: List[PalabraSubtitulo],
    t_actual: float,
    nivel_voz_rms: float = 0.0,
    y_centro: int = 1340,
    palabras_verdes_extra: Optional[Set[str]] = None,
    palabras_rojas_extra: Optional[Set[str]] = None,
    palabras_cian_extra: Optional[Set[str]] = None,
) -> None:
    if not palabras:
        return
    if t_actual < (palabras[0].inicio_seg - 0.06) or t_actual > (palabras[-1].fin_seg + 0.20):
        return

    idx_activa = 0
    for i, p in enumerate(palabras):
        if p.inicio_seg <= t_actual <= p.fin_seg:
            idx_activa = i
            break
        if t_actual > p.fin_seg:
            idx_activa = i

    grupos = _agrupar_palabras_subtitulos(palabras)
    grupo_mostrar = grupos[0]
    for g in grupos:
        indices_g = [item[0] for item in g]
        if idx_activa in indices_g:
            grupo_mostrar = g
            break

    verdes = PALABRAS_VERDES_BASE | (palabras_verdes_extra or set())
    rojas = PALABRAS_ROJAS_BASE | (palabras_rojas_extra or set())
    cianes = PALABRAS_CIAN_BASE | (palabras_cian_extra or set())

    tam_base_activa = 86
    tam_base_inactiva = 70
    espaciado_base = 20

    sprites_info = []
    for idx_global, p in grupo_mostrar:
        es_activa = (idx_global == idx_activa)
        txt_up = p.texto.upper().replace("*", "")
        limpia = re.sub(r"[^A-ZÁÉÍÓÚÜÑ0-9]", "", txt_up)

        if es_activa:
            color_fill, color_glow = _clasificar_color_palabra(
                limpia, txt_up, p.forzar_destaque, verdes, rojas, cianes
            )
            sprite_base = _obtener_sprite_palabra_luminosa(
                txt_up, tam_base_activa, color_fill, color_glow, True
            )
            edad = max(0.0, t_actual - p.inicio_seg)
            # Rebote elástico + pulso reactivo a la energía de la voz
            pulso_voz = min(0.09, nivel_voz_rms * 0.45)
            factor_pop = 1.0 + 0.18 * math.exp(-edad * 13.0) * math.cos(edad * 16.0) + pulso_voz
            pad_sprite = 58
        else:
            # Palabras acompañantes en blanco brillante con sutil aura azul hielo
            sprite_base = _obtener_sprite_palabra_luminosa(
                txt_up, tam_base_inactiva, (255, 255, 255), (120, 195, 255), False
            )
            factor_pop = 1.0
            pad_sprite = 42

        ancho_logico = max(20, sprite_base.width - pad_sprite * 2)
        sprites_info.append((idx_global, p, sprite_base, factor_pop, ancho_logico, pad_sprite, es_activa))

    ancho_total_logico = (
        sum(int(round(x[4] * x[3])) for x in sprites_info)
        + espaciado_base * max(0, len(sprites_info) - 1)
    )

    # Auto-ajuste para que jamás se corte una palabra en los bordes de los 1080px
    max_ancho_permitido = WIDTH - 84
    escala_ajuste = min(1.0, max_ancho_permitido / float(max(1, ancho_total_logico)))

    espaciado_final = int(round(espaciado_base * escala_ajuste))
    anchos_finales = [int(round(x[4] * x[3] * escala_ajuste)) for x in sprites_info]
    ancho_grupo_final = sum(anchos_finales) + espaciado_final * max(0, len(anchos_finales) - 1)

    # Fondo suave semitransparente detrás del subtítulo para contraste total
    backdrop = _obtener_backdrop_subtitulo(ancho_grupo_final, 165)
    bx = (WIDTH - backdrop.width) // 2
    by = y_centro - backdrop.height // 2
    lienzo.alpha_composite(backdrop, dest=(max(0, bx), max(0, min(HEIGHT - backdrop.height, by))))

    x_cursor = (WIDTH - ancho_grupo_final) // 2

    for (idx_global, p, sprite_base, factor_pop, ancho_logico, pad_sprite, es_activa), ancho_f in zip(
        sprites_info, anchos_finales
    ):
        escala_total = factor_pop * escala_ajuste
        if abs(escala_total - 1.0) > 0.015:
            nw = max(16, int(round(sprite_base.width * escala_total)))
            nh = max(16, int(round(sprite_base.height * escala_total)))
            sprite_render = sprite_base.resize((nw, nh), Image.Resampling.LANCZOS)
        else:
            sprite_render = sprite_base

        if es_activa:
            # Ligera inclinación dinámica en la primera fracción de segundo de la palabra activa
            edad = max(0.0, t_actual - p.inicio_seg)
            signo_ang = 1.0 if (idx_global % 2 == 0) else -1.0
            angulo_pop = signo_ang * 2.8 * math.exp(-edad * 10.0)
            if abs(angulo_pop) > 0.35:
                sprite_render = sprite_render.rotate(angulo_pop, resample=Image.Resampling.BICUBIC, expand=True)

        cx_palabra = x_cursor + ancho_f // 2
        cy_palabra = (y_centro - 10) if es_activa else y_centro

        dest_x = cx_palabra - sprite_render.width // 2
        dest_y = cy_palabra - sprite_render.height // 2
        dest_x = max(-30, min(WIDTH - sprite_render.width + 30, dest_x))
        dest_y = max(0, min(HEIGHT - sprite_render.height, dest_y))

        # Si dest_x es ligeramente negativo por el pad del resplandor, recortamos limpiamente
        if dest_x < 0:
            sprite_render = sprite_render.crop((-dest_x, 0, sprite_render.width, sprite_render.height))
            dest_x = 0
        if dest_x + sprite_render.width > WIDTH:
            sprite_render = sprite_render.crop((0, 0, WIDTH - dest_x, sprite_render.height))

        lienzo.alpha_composite(sprite_render, dest=(dest_x, dest_y))
        x_cursor += ancho_f + espaciado_final


# ==============================================================================
# 5. MOTOR DE VOZ NEURONAL Y ALINEACIÓN ACÚSTICA EXACTA
# ==============================================================================
def _peso_silabico_palabra(palabra: str) -> float:
    limpia = re.sub(r"[^a-záéíóúüñA-ZÁÉÍÓÚÜÑ0-9]", "", palabra)
    vocales = len(re.findall(r"[aeiouáéíóúüAEIOUÁÉÍÓÚÜ]+", limpia))
    peso = max(1.0, float(vocales) * 0.9 + len(limpia) * 0.12)
    if palabra.endswith((",", "...", ":", ";")):
        peso += 0.85
    elif palabra.endswith(("!", "?", ".")):
        peso += 1.10
    return peso


def detectar_limites_voz_real_wav(ruta_wav: Path) -> Tuple[float, float, float]:
    with wave.open(str(ruta_wav), "r") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        dur_total = n / float(sr)
        audio = np.frombuffer(wf.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0

    if len(audio) == 0:
        return 0.0, dur_total, dur_total

    win = max(1, int(sr * 0.01))
    n_wins = len(audio) // win
    if n_wins < 2:
        return 0.0, dur_total, dur_total

    recorte = audio[: n_wins * win].reshape(n_wins, win)
    rms = np.sqrt(np.mean(recorte ** 2, axis=1))
    umbral = max(0.012, float(np.max(rms)) * 0.06)

    activos = np.where(rms > umbral)[0]
    if len(activos) == 0:
        return 0.0, dur_total, dur_total

    ini_seg = max(0.0, float(activos[0]) * 0.01 - 0.02)
    fin_seg = min(dur_total, float(activos[-1] + 1) * 0.01 + 0.03)
    return ini_seg, fin_seg, dur_total


def alinear_palabras_con_onda_real(
    texto: str,
    ruta_wav: Path,
    palabras_edge: List[PalabraSubtitulo],
) -> List[PalabraSubtitulo]:
    ini_voz, fin_voz, dur_total = detectar_limites_voz_real_wav(ruta_wav)
    dur_hablada = max(0.25, fin_voz - ini_voz)

    if palabras_edge:
        primero = palabras_edge[0].inicio_seg
        ultimo = palabras_edge[-1].fin_seg
        rango_raw = max(0.1, ultimo - primero)
        escala = dur_hablada / rango_raw
        calibradas: List[PalabraSubtitulo] = []
        for p in palabras_edge:
            t0 = ini_voz + (p.inicio_seg - primero) * escala + SUBTITLE_OFFSET_SEC
            t1 = ini_voz + (p.fin_seg - primero) * escala + SUBTITLE_OFFSET_SEC
            t0 = max(0.0, t0)
            t1 = max(t0 + 0.08, min(dur_total, t1))
            if calibradas and t0 > calibradas[-1].fin_seg and (t0 - calibradas[-1].fin_seg) < 0.18:
                calibradas[-1].fin_seg = t0
            calibradas.append(
                PalabraSubtitulo(
                    texto=p.texto,
                    inicio_seg=t0,
                    fin_seg=t1,
                    forzar_destaque=p.forzar_destaque,
                )
            )
        return calibradas

    tokens = texto.split()
    if not tokens:
        return []
    pesos = [_peso_silabico_palabra(tok) for tok in tokens]
    suma_pesos = sum(pesos)
    cursor = ini_voz
    resultado: List[PalabraSubtitulo] = []
    for tok, peso in zip(tokens, pesos):
        dur_p = (peso / suma_pesos) * dur_hablada
        t0 = max(0.0, cursor + SUBTITLE_OFFSET_SEC)
        t1 = min(dur_total, cursor + dur_p + SUBTITLE_OFFSET_SEC)
        destaque = tok.startswith("*") and tok.endswith("*")
        tok_limpio = tok.strip("*")
        resultado.append(
            PalabraSubtitulo(
                texto=tok_limpio,
                inicio_seg=t0,
                fin_seg=max(t0 + 0.08, t1),
                forzar_destaque=destaque,
            )
        )
        cursor += dur_p
    return resultado


_REEMPLAZOS_FONETICOS_TTS = [
    (r"\*", ""),
    (r"\bPCs\b", "PC"),
    (r"\bpcs\b", "PC"),
    (r"\bRoblox\b", "Róblox"),
    (r"\broblox\b", "Róblox"),
    (r"\bRobux\b", "Róbux"),
    (r"\brobux\b", "Róbux"),
    (r"\bShorts\b", "Shórts"),
    (r"\bshorts\b", "shórts"),
    (r"\bShort\b", "Shórt"),
    (r"\bshort\b", "shórt"),
    (r"\bpros\b", "prós"),
    (r"\bPros\b", "Prós"),
    (r"\bPROS\b", "PRÓS"),
    (r"\bpro\b", "pró"),
    (r"\bPro\b", "Pró"),
    (r"\bPRO\b", "PRÓ"),
    (r"\bsuvs\b", "súbs"),
    (r"\bsubs\b", "súbs"),
]

_PALABRAS_HYPE_YOUTUBER = {
    "mira", "mirá", "miren", "increíble", "imposible", "locura", "pero", "ahora",
    "suscríbete", "suscribite", "comenta", "comentá", "like", "secreto", "nunca",
    "jamás", "épico", "épica", "ganar", "perder", "cuidado", "rápido", "estafa",
}


def _normalizar_fonetica_youtuber(texto: str) -> str:
    res = texto
    for patron, reemplazo in _REEMPLAZOS_FONETICOS_TTS:
        res = re.sub(patron, reemplazo, res)
    return res


def _dividir_clausulas_expresivas(texto: str) -> List[str]:
    partes = re.split(r"(?<=[!?.])\s+", texto.strip())
    return [p.strip() for p in partes if p.strip()]


def _prosodia_dinamica_clausula(
    clausula: str,
    idx: int,
    total: int,
    palabras_por_seg_objetivo: Optional[float] = None,
) -> Tuple[str, str, str, float]:
    es_exclamacion = "!" in clausula or "¡" in clausula
    es_pregunta = "?" in clausula or "¿" in clausula
    palabras_low = set(re.findall(r"[a-záéíóúüñ]+", clausula.lower()))
    tiene_hype = bool(palabras_low & _PALABRAS_HYPE_YOUTUBER)
    pitch = EDGE_PITCH_DEFAULT

    # Adaptamos la velocidad base de síntesis al número de palabras que debe decir en este tramo real del video.
    # Las pausas entre oraciones se mantienen mínimas (narración de corrido, sin huecos de silencio).
    ajuste_vel = 0
    pausa_extra = 0.0
    if palabras_por_seg_objetivo is not None:
        if palabras_por_seg_objetivo < 2.6:
            ajuste_vel = -10
        elif palabras_por_seg_objetivo < 3.2:
            ajuste_vel = -5
        elif palabras_por_seg_objetivo > 3.9:
            # Si la IA escribió una línea larga para este bloque, aumentamos el ritmo proporcionalmente
            ajuste_vel = min(42, int(round((palabras_por_seg_objetivo - 3.5) * 12.0)))
            pausa_extra = -0.01

    if es_exclamacion:
        if idx == 0:
            r_num = max(0, 14 + ajuste_vel)
            return f"+{r_num}%", pitch, "+8%", max(0.015, 0.030 + pausa_extra)
        elif idx == total - 1:
            r_num = max(0, 15 + ajuste_vel)
            return f"+{r_num}%", pitch, "+10%", max(0.015, 0.030 + pausa_extra)
        else:
            r_num = max(0, 16 + ajuste_vel)
            return f"+{r_num}%", pitch, "+6%", max(0.015, 0.030 + pausa_extra)
    elif es_pregunta:
        r_num = max(0, 13 + ajuste_vel)
        return f"+{r_num}%", pitch, "+6%", max(0.015, 0.035 + pausa_extra)
    else:
        base_n = 13 if tiene_hype else 11
        r_num = max(0, base_n + ajuste_vel)
        return f"+{r_num}%", pitch, "+0%", max(0.015, 0.035 + pausa_extra)


def _recortar_silencio_clausula_pcm(
    pcm_float: np.ndarray,
    sr: int = 44100,
) -> Tuple[np.ndarray, float, float]:
    if len(pcm_float) == 0:
        return pcm_float, 0.0, 0.0
    win = max(1, int(sr * 0.005))
    n_wins = len(pcm_float) // win
    if n_wins < 2:
        dur = len(pcm_float) / float(sr)
        return pcm_float, 0.0, dur

    rms = np.sqrt(np.mean(pcm_float[: n_wins * win].reshape(n_wins, win) ** 2, axis=1))
    umbral = max(0.007, float(np.max(rms)) * 0.03)
    activos = np.where(rms > umbral)[0]
    if len(activos) == 0:
        dur = len(pcm_float) / float(sr)
        return pcm_float, 0.0, dur

    pad_ini = int(sr * 0.016)
    pad_fin = int(sr * 0.024)
    i0 = max(0, int(activos[0]) * win - pad_ini)
    i1 = min(len(pcm_float), int(activos[-1] + 1) * win + pad_fin)
    recortado = pcm_float[i0:i1].copy()

    fade_len = min(int(sr * 0.008), len(recortado) // 4)
    if fade_len > 1:
        recortado[:fade_len] *= np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
        recortado[-fade_len:] *= np.linspace(1.0, 0.0, fade_len, dtype=np.float32)

    return recortado, i0 / float(sr), len(recortado) / float(sr)


def _construir_cadena_atempo(factor: float) -> str:
    """
    Construye filtros `atempo` encadenados para FFmpeg manteniendo el tono natural de la voz.
    """
    f = float(np.clip(factor, 0.55, 3.2))
    if abs(f - 1.0) <= 0.012:
        return ""
    partes: List[str] = []
    while f > 2.0:
        partes.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        partes.append("atempo=0.5")
        f /= 0.5
    partes.append(f"atempo={f:.4f}")
    return ",".join(partes) + ","


def masterizar_voz_estudio_ffmpeg(
    ruta_entrada: Path,
    ruta_wav_salida: Path,
    factor_atempo: float = 1.0,
) -> None:
    prefijo_tempo = _construir_cadena_atempo(factor_atempo)
    filtro_audio = (
        f"{prefijo_tempo}"
        "highpass=f=80,"
        "equalizer=f=135:width_type=o:width=1.1:g=2.4,"
        "equalizer=f=320:width_type=o:width=1.2:g=-1.2,"
        "equalizer=f=3150:width_type=o:width=1.3:g=-2.2,"
        "equalizer=f=5200:width_type=o:width=1.5:g=1.6,"
        "treble=g=2.0:f=8200,"
        "acompressor=threshold=-19dB:ratio=2.5:attack=10:release=110:makeup=5.2dB,"
        "alimiter=limit=0.98"
    )
    res = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(ruta_entrada),
            "-af", filtro_audio,
            "-ar", "44100", "-ac", "1",
            str(ruta_wav_salida),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if res.returncode != 0 or not ruta_wav_salida.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(ruta_entrada), "-ar", "44100", "-ac", "1", str(ruta_wav_salida)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def intentar_voz_elevenlabs(texto: str, ruta_mp3: Path) -> bool:
    if not ELEVENLABS_API_KEY:
        return False
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    payload = json.dumps({
        "text": _normalizar_fonetica_youtuber(texto),
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.32,
            "similarity_boost": 0.82,
            "style": 0.68,
            "use_speaker_boost": True,
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            datos = resp.read()
            if len(datos) > 1000:
                ruta_mp3.write_bytes(datos)
                return True
    except Exception:
        pass
    return False


async def generar_voz_y_timestamps_segmento(
    texto: str,
    ruta_audio_salida: Path,
    voz_edge: str = EDGE_VOICE_DEFAULT,
    dur_objetivo_seg: Optional[float] = None,
) -> Tuple[float, List[PalabraSubtitulo], float, float]:
    palabras_raw: List[PalabraSubtitulo] = []
    genero_audio = False
    ruta_wav = ruta_audio_salida.with_suffix(".wav")
    if ruta_audio_salida.exists():
        ruta_audio_salida.unlink()
    if ruta_wav.exists():
        ruta_wav.unlink()

    if ELEVENLABS_API_KEY:
        genero_audio = intentar_voz_elevenlabs(texto, ruta_audio_salida)
        if genero_audio:
            masterizar_voz_estudio_ffmpeg(ruta_audio_salida, ruta_wav)

    if not genero_audio and HAS_EDGE_TTS:
        try:
            clausulas_orig = _dividir_clausulas_expresivas(texto)
            if not clausulas_orig:
                clausulas_orig = [texto.strip()]

            total_palabras_seg = max(1, len(texto.split()))
            pps_obj = (total_palabras_seg / dur_objetivo_seg) if (dur_objetivo_seg and dur_objetivo_seg > 0.5) else None

            sr = 44100
            bloques_pcm: List[np.ndarray] = []
            cursor_seg = 0.0

            for c_idx, cl_orig in enumerate(clausulas_orig):
                cl_tts = _normalizar_fonetica_youtuber(cl_orig)
                rate_c, pitch_c, vol_c, pausa_post = _prosodia_dinamica_clausula(
                    cl_orig, c_idx, len(clausulas_orig), palabras_por_seg_objetivo=pps_obj
                )
                tmp_mp3 = ruta_audio_salida.parent / f"{ruta_audio_salida.stem}_c{c_idx}.mp3"
                tmp_wav = ruta_audio_salida.parent / f"{ruta_audio_salida.stem}_c{c_idx}.wav"
                palabras_clausula: List[PalabraSubtitulo] = []

                try:
                    communicate = edge_tts.Communicate(
                        cl_tts,
                        voz_edge,
                        rate=rate_c,
                        pitch=pitch_c,
                        volume=vol_c,
                        boundary="WordBoundary",
                    )
                except TypeError:
                    communicate = edge_tts.Communicate(
                        cl_tts,
                        voz_edge,
                        rate=rate_c,
                        pitch=pitch_c,
                    )

                with open(tmp_mp3, "wb") as audio_file:
                    async for chunk in communicate.stream():
                        ctype = chunk.get("type")
                        if ctype == "audio":
                            audio_file.write(chunk["data"])
                        elif ctype == "WordBoundary":
                            ini = chunk["offset"] / 10_000_000.0
                            dur = chunk["duration"] / 10_000_000.0
                            palabras_clausula.append(
                                PalabraSubtitulo(
                                    texto=chunk["text"],
                                    inicio_seg=ini,
                                    fin_seg=ini + max(dur, 0.08),
                                )
                            )

                if tmp_mp3.exists() and tmp_mp3.stat().st_size > 0:
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", str(tmp_mp3), "-ar", str(sr), "-ac", "1", str(tmp_wav)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                if tmp_wav.exists() and tmp_wav.stat().st_size > 0:
                    with wave.open(str(tmp_wav), "r") as wf_c:
                        pcm_c = (
                            np.frombuffer(wf_c.readframes(wf_c.getnframes()), dtype=np.int16).astype(np.float32)
                            / 32768.0
                        )
                    pcm_rec, offset_rec, dur_rec = _recortar_silencio_clausula_pcm(pcm_c, sr)

                    if "!" in cl_orig or "¡" in cl_orig:
                        progreso_c = np.linspace(0.0, 1.0, len(pcm_rec), dtype=np.float32)
                        env_punch = 1.0 + 0.09 * np.exp(-progreso_c * 3.2) + 0.05 * np.sin(progreso_c * math.pi)
                        pcm_rec = pcm_rec * env_punch

                    tokens_orig = cl_orig.split()
                    if palabras_clausula:
                        t_first = palabras_clausula[0].inicio_seg
                        t_last = palabras_clausula[-1].fin_seg
                        span_raw = max(0.08, t_last - t_first)
                        escala_c = max(0.10, dur_rec - 0.02) / span_raw
                        for w_i, p_w in enumerate(palabras_clausula):
                            tok_o = tokens_orig[w_i] if w_i < len(tokens_orig) else p_w.texto
                            destaque = tok_o.startswith("*") and tok_o.endswith("*")
                            txt_mostrar = tok_o.strip("*")
                            t0 = cursor_seg + max(0.0, (p_w.inicio_seg - t_first) * escala_c)
                            t1 = cursor_seg + min(dur_rec, max(0.08, (p_w.fin_seg - t_first) * escala_c))
                            palabras_raw.append(
                                PalabraSubtitulo(
                                    texto=txt_mostrar,
                                    inicio_seg=t0,
                                    fin_seg=max(t0 + 0.07, t1),
                                    forzar_destaque=destaque,
                                )
                            )

                    bloques_pcm.append(pcm_rec)
                    cursor_seg += dur_rec

                    if c_idx < len(clausulas_orig) - 1:
                        bloques_pcm.append(np.zeros(int(sr * pausa_post), dtype=np.float32))
                        cursor_seg += pausa_post

                for f_tmp in (tmp_mp3, tmp_wav):
                    if f_tmp.exists():
                        try:
                            f_tmp.unlink()
                        except OSError:
                            pass

            if bloques_pcm:
                audio_crudo = np.clip(np.concatenate(bloques_pcm), -0.98, 0.98)
                dur_cruda = len(audio_crudo) / float(sr)

                # Ajuste exacto de tempo (sin cambiar el tono) para que la voz LLENE su tramo real de video
                # de corrido (sin huecos de silencio al final) y nunca lo exceda.
                factor_atempo = 1.0
                if dur_objetivo_seg and dur_objetivo_seg > 0.5 and dur_cruda > 0.15:
                    dur_ideal_voz = max(0.35, dur_objetivo_seg - 0.06)
                    factor_atempo = float(np.clip(dur_cruda / dur_ideal_voz, 0.80, 2.4))

                if abs(factor_atempo - 1.0) > 0.012 and palabras_raw:
                    for p_w in palabras_raw:
                        p_w.inicio_seg /= factor_atempo
                        p_w.fin_seg /= factor_atempo

                ruta_crudo_wav = ruta_audio_salida.parent / f"{ruta_audio_salida.stem}_raw.wav"
                with wave.open(str(ruta_crudo_wav), "w") as wf_raw:
                    wf_raw.setnchannels(1)
                    wf_raw.setsampwidth(2)
                    wf_raw.setframerate(sr)
                    wf_raw.writeframes((audio_crudo * 32767).astype(np.int16).tobytes())
                masterizar_voz_estudio_ffmpeg(ruta_crudo_wav, ruta_wav, factor_atempo=factor_atempo)
                if ruta_crudo_wav.exists():
                    try:
                        ruta_crudo_wav.unlink()
                    except OSError:
                        pass
                genero_audio = ruta_wav.exists() and ruta_wav.stat().st_size > 0
        except Exception as e:
            print(f"[!] Error en Edge-TTS: {e}")

    if not ruta_wav.exists() or ruta_wav.stat().st_size == 0:
        tokens = texto.split()
        dur_estimada = max(1.8, len(tokens) * 0.28)
        sr = 44100
        t = np.linspace(0, dur_estimada, int(sr * dur_estimada), False)
        audio_sim = np.sin(2 * np.pi * 195 * t) * 0.25
        pcm = (audio_sim * 32767).astype(np.int16)
        with wave.open(str(ruta_wav), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(pcm.tobytes())

    with wave.open(str(ruta_wav), "r") as wf:
        duracion_real = wf.getnframes() / float(wf.getframerate())

    ini_voz, fin_voz, _ = detectar_limites_voz_real_wav(ruta_wav)
    if palabras_raw and not ELEVENLABS_API_KEY:
        palabras_alineadas: List[PalabraSubtitulo] = []
        for p in palabras_raw:
            t0 = max(0.0, p.inicio_seg + SUBTITLE_OFFSET_SEC)
            t1 = min(duracion_real, max(t0 + 0.07, p.fin_seg + SUBTITLE_OFFSET_SEC))
            if palabras_alineadas and t0 > palabras_alineadas[-1].fin_seg and (t0 - palabras_alineadas[-1].fin_seg) < 0.16:
                palabras_alineadas[-1].fin_seg = t0
            palabras_alineadas.append(
                PalabraSubtitulo(
                    texto=p.texto,
                    inicio_seg=t0,
                    fin_seg=t1,
                    forzar_destaque=p.forzar_destaque,
                )
            )
    else:
        palabras_alineadas = alinear_palabras_con_onda_real(texto, ruta_wav, palabras_raw)

    return duracion_real, palabras_alineadas, ini_voz, fin_voz


# ==============================================================================
# 6. SEGUIMIENTO INTELIGENTE DE OBJETIVOS (OPTICAL FLOW + SALIENCIA EN MOVIMIENTO)
# ==============================================================================
class RastreadorObjetivosVideo:
    """
    Motor de visión artificial (OpenCV) que permite que las flechas rojas (flecha.png)
    y los círculos rojos (circulo_rojo.png) localicen y sigan suavemente al objetivo
    real dentro del segmento de video:
      1) Adquisición inteligente del objetivo en movimiento/saliencia dentro de la zona
         solicitada ('izquierda', 'derecha', 'centro', 'arriba', 'abajo', 'auto' o 'X,Y').
      2) Seguimiento cuadro a cuadro con Flujo Óptico Piramidal de Lucas-Kanade
         (cv2.calcOpticalFlowPyrLK) con verificación forward-backward y respaldo
         por Template Matching ante desenfoques rápidos.
      3) Suavizado Gaussiano bidireccional sin retardo (zero-lag) a 60 FPS.
    """

    ESC_TRACK = 3.0
    W_TR = int(WIDTH // ESC_TRACK)   # 360
    H_TR = int(HEIGHT // ESC_TRACK)  # 640

    ZONAS_NOMINALES: Dict[str, Tuple[float, float, float]] = {
        # nombre_zona: (x_norm 0..1, y_norm 0..1, radio_busqueda_px_en_360x640)
        "centro": (0.50, 0.45, 65.0),
        "izquierda": (0.28, 0.45, 60.0),
        "derecha": (0.72, 0.45, 60.0),
        "arriba": (0.50, 0.26, 62.0),
        "abajo": (0.50, 0.61, 60.0),
        "arriba_izq": (0.28, 0.27, 58.0),
        "arriba_der": (0.72, 0.27, 58.0),
        "abajo_izq": (0.28, 0.59, 58.0),
        "abajo_der": (0.72, 0.59, 58.0),
        "auto": (0.50, 0.45, 130.0),
    }

    @classmethod
    def _parsear_punto_base(cls, spec: str) -> Tuple[float, float, float, bool]:
        """
        Devuelve (x_360, y_640, radio_busqueda_360, es_coordenada_exacta).
        """
        s = _quitar_acentos(spec.strip().lower())
        if "," in s:
            try:
                px_s, py_s = s.split(",", 1)
                px = float(px_s.strip())
                py = float(py_s.strip())
                if px <= 100.0 and py <= 100.0:
                    x_tr = (px / 100.0) * cls.W_TR
                    y_tr = (py / 100.0) * cls.H_TR
                else:
                    x_tr = px / cls.ESC_TRACK
                    y_tr = py / cls.ESC_TRACK
                x_tr = float(np.clip(x_tr, 36.0, cls.W_TR - 36.0))
                y_tr = float(np.clip(y_tr, 48.0, cls.H_TR - 140.0))
                return x_tr, y_tr, 36.0, True
            except ValueError:
                pass

        nx, ny, rad = cls.ZONAS_NOMINALES.get(s, cls.ZONAS_NOMINALES["centro"])
        return nx * cls.W_TR, ny * cls.H_TR, rad, False

    @classmethod
    def _adquirir_objetivo_saliente(
        cls,
        grises_iniciales: List[np.ndarray],
        rgb_inicial: Optional[np.ndarray],
        x_nom: float,
        y_nom: float,
        radio_busq: float,
        es_exacta: bool,
    ) -> Tuple[float, float]:
        if not grises_iniciales or es_exacta:
            return x_nom, y_nom

        g0 = grises_iniciales[0].astype(np.float32)
        h, w = g0.shape

        # 1. Mapa de energía de movimiento en los primeros cuadros del segmento
        mov_acum = np.zeros((h, w), dtype=np.float32)
        for i in range(1, len(grises_iniciales)):
            diff = cv2.absdiff(grises_iniciales[i], grises_iniciales[i - 1]).astype(np.float32)
            mov_acum += diff
        if len(grises_iniciales) > 1:
            mov_acum /= float(len(grises_iniciales) - 1)
        mov_norm = mov_acum / (float(np.max(mov_acum)) + 1e-5)

        # 2. Mapa de saturación de color + contraste de objetos (para detectar sujetos/objetos y no bordes vacíos)
        if rgb_inicial is not None:
            hsv = cv2.cvtColor(rgb_inicial, cv2.COLOR_RGB2HSV).astype(np.float32)
            sat_norm = hsv[:, :, 1] / 255.0
        else:
            sat_norm = np.zeros((h, w), dtype=np.float32)

        gx = cv2.Sobel(g0, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(g0, cv2.CV_32F, 0, 1, ksize=3)
        grad_mag = cv2.magnitude(gx, gy)
        grad_norm = grad_mag / (float(np.max(grad_mag)) + 1e-5)

        saliencia = cv2.GaussianBlur(mov_norm * 1.85 + sat_norm * 1.10 + grad_norm * 0.45, (19, 19), 0)

        # 3. Ventana Gaussiana centrada en la zona pedida (evitando bordes y zona de subtítulos)
        yy, xx = np.meshgrid(np.arange(h, dtype=np.float32), np.arange(w, dtype=np.float32), indexing="ij")
        peso_zona = np.exp(-(((xx - x_nom) ** 2 + (yy - y_nom) ** 2) / (2.0 * (radio_busq ** 2))))

        limite_y_inf = int(h * 0.67) if y_nom < h * 0.54 else int(h * 0.75)
        mascara_segura = np.zeros((h, w), dtype=np.float32)
        mascara_segura[44:limite_y_inf, 36 : w - 36] = 1.0

        mapa_final = saliencia * peso_zona * mascara_segura
        max_val = float(np.max(mapa_final))
        if max_val < 1e-4:
            return x_nom, y_nom

        umbral = max_val * 0.78
        ys, xs = np.where(mapa_final >= umbral)
        if len(xs) == 0:
            return x_nom, y_nom
        pesos = mapa_final[ys, xs]
        cx_sal = float(np.sum(xs * pesos) / np.sum(pesos))
        cy_sal = float(np.sum(ys * pesos) / np.sum(pesos))

        # Anclar con firmeza al centro de la zona para evitar imprecisiones hacia objetos vecinos
        tx = 0.60 * cx_sal + 0.40 * x_nom
        ty = 0.60 * cy_sal + 0.40 * y_nom
        return float(np.clip(tx, 42.0, w - 42.0)), float(np.clip(ty, 50.0, limite_y_inf))

    @classmethod
    def _extraer_puntos_locales(cls, gray: np.ndarray, cx: float, cy: float, radio: int = 44) -> Optional[np.ndarray]:
        h, w = gray.shape
        x0 = max(8, int(round(cx - radio)))
        x1 = min(w - 8, int(round(cx + radio)))
        y0 = max(8, int(round(cy - radio)))
        y1 = min(h - 8, int(round(cy + radio)))
        if x1 - x0 < 12 or y1 - y0 < 12:
            return None

        mask = np.zeros_like(gray)
        mask[y0:y1, x0:x1] = 255
        pts = cv2.goodFeaturesToTrack(
            gray,
            maxCorners=28,
            qualityLevel=0.04,
            minDistance=5,
            mask=mask,
            blockSize=5,
        )
        return pts

    @classmethod
    def _suavizar_serie_1d(cls, valores: np.ndarray, sigma: float = 4.2) -> np.ndarray:
        if len(valores) < 5:
            return valores
        rad = max(2, int(math.ceil(sigma * 2.5)))
        k_x = np.arange(-rad, rad + 1, dtype=np.float32)
        kernel = np.exp(-(k_x ** 2) / (2.0 * sigma * sigma))
        kernel /= np.sum(kernel)
        pad_v = np.pad(valores, (rad, rad), mode="edge")
        return np.convolve(pad_v, kernel, mode="valid")

    @classmethod
    def calcular_trayectoria(
        cls,
        frames_rgb: List[np.ndarray],
        especificacion: Optional[str],
    ) -> List[Tuple[float, float]]:
        """
        Devuelve una lista de coordenadas [(vx, vy), ...] en espacio 1080x1920
        para cada fotograma del segmento.
        """
        n_frames = len(frames_rgb)
        if n_frames == 0 or not especificacion:
            return [(WIDTH / 2.0, HEIGHT * 0.44)] * max(1, n_frames)

        spec_clean = _quitar_acentos(especificacion.strip().lower())

        # Submuestreo cada 2 cuadros a resolución 360x640 para máxima velocidad y precisión
        paso = 2 if n_frames > 12 else 1
        indices_muestra = list(range(0, n_frames, paso))
        if indices_muestra[-1] != n_frames - 1:
            indices_muestra.append(n_frames - 1)

        grises: List[np.ndarray] = []
        rgbs_peq: List[np.ndarray] = []
        for idx in indices_muestra:
            peq = cv2.resize(frames_rgb[idx], (cls.W_TR, cls.H_TR), interpolation=cv2.INTER_AREA)
            rgbs_peq.append(peq)
            grises.append(cv2.cvtColor(peq, cv2.COLOR_RGB2GRAY))

        # Caso A: Trayectoria explícita "inicio->fin" (ej. "izquierda->derecha" o "25,50->75,50")
        if "->" in spec_clean:
            p_ini_str, p_fin_str = spec_clean.split("->", 1)
            x0_tr, y0_tr, _, _ = cls._parsear_punto_base(p_ini_str)
            x1_tr, y1_tr, _, _ = cls._parsear_punto_base(p_fin_str)
            xs_full = np.zeros(n_frames, dtype=np.float32)
            ys_full = np.zeros(n_frames, dtype=np.float32)
            for i in range(n_frames):
                u = i / float(max(1, n_frames - 1))
                # Curva ease-in-out suave
                u_s = u * u * (3.0 - 2.0 * u)
                xs_full[i] = (x0_tr + (x1_tr - x0_tr) * u_s) * cls.ESC_TRACK
                ys_full[i] = (y0_tr + (y1_tr - y0_tr) * u_s) * cls.ESC_TRACK
            return list(zip(xs_full.tolist(), ys_full.tolist()))

        # Caso B: Seguimiento real de objetivo con Optical Flow + Saliencia
        x_nom, y_nom, radio_busq, es_exacta = cls._parsear_punto_base(spec_clean)
        tx, ty = cls._adquirir_objetivo_saliente(
            grises[: min(8, len(grises))], rgbs_peq[0], x_nom, y_nom, radio_busq, es_exacta
        )

        limite_y_inf = float(cls.H_TR * 0.68) if y_nom < cls.H_TR * 0.54 else float(cls.H_TR * 0.76)
        pts_activos = cls._extraer_puntos_locales(grises[0], tx, ty, radio=48)

        xs_m: List[float] = [tx]
        ys_m: List[float] = [ty]

        lk_params = dict(
            winSize=(23, 23),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 15, 0.03),
        )

        for k in range(1, len(grises)):
            g_prev = grises[k - 1]
            g_curr = grises[k]

            # Detectar si hubo un corte brusco de escena dentro del segmento
            diff_medio = float(np.mean(cv2.absdiff(g_curr, g_prev)))
            if diff_medio > 26.0:
                tx, ty = cls._adquirir_objetivo_saliente(
                    grises[k : min(len(grises), k + 5)], rgbs_peq[k], x_nom, y_nom, radio_busq, es_exacta
                )
                pts_activos = cls._extraer_puntos_locales(g_curr, tx, ty, radio=48)
                xs_m.append(tx)
                ys_m.append(ty)
                continue

            if pts_activos is None or len(pts_activos) < 6:
                pts_activos = cls._extraer_puntos_locales(g_prev, tx, ty, radio=48)

            desplazado = False
            if pts_activos is not None and len(pts_activos) >= 4:
                pts_next, st_f, _ = cv2.calcOpticalFlowPyrLK(g_prev, g_curr, pts_activos, None, **lk_params)
                if pts_next is not None and st_f is not None:
                    pts_back, st_b, _ = cv2.calcOpticalFlowPyrLK(g_curr, g_prev, pts_next, None, **lk_params)
                    if pts_back is not None and st_b is not None:
                        err_fb = np.linalg.norm(pts_activos - pts_back, axis=2).reshape(-1)
                        validos = (st_f.reshape(-1) == 1) & (st_b.reshape(-1) == 1) & (err_fb < 2.4)
                        if np.count_nonzero(validos) >= 3:
                            p0_v = pts_activos[validos].reshape(-1, 2)
                            p1_v = pts_next[validos].reshape(-1, 2)
                            deltas = p1_v - p0_v
                            mags = np.linalg.norm(deltas, axis=1)
                            buenos = mags < 30.0
                            if np.count_nonzero(buenos) >= 3:
                                dx = float(np.median(deltas[buenos, 0]))
                                dy = float(np.median(deltas[buenos, 1]))
                                # Seguimiento con resorte suave hacia la zona para evitar deriva de fondo
                                tx = tx + dx * 0.88 + (x_nom - tx) * 0.065
                                ty = ty + dy * 0.88 + (y_nom - ty) * 0.065
                                pts_activos = p1_v[buenos].reshape(-1, 1, 2)
                                desplazado = True

            # Respaldo por Template Matching si hay pocos vértices pero existe textura local
            if not desplazado:
                r_tpl = 22
                r_search = 38
                x0_t = max(0, int(round(tx - r_tpl)))
                x1_t = min(cls.W_TR, int(round(tx + r_tpl)))
                y0_t = max(0, int(round(ty - r_tpl)))
                y1_t = min(cls.H_TR, int(round(ty + r_tpl)))

                x0_s = max(0, int(round(tx - r_search)))
                x1_s = min(cls.W_TR, int(round(tx + r_search)))
                y0_s = max(0, int(round(ty - r_search)))
                y1_s = min(cls.H_TR, int(round(ty + r_search)))

                tpl = g_prev[y0_t:y1_t, x0_t:x1_t]
                srch = g_curr[y0_s:y1_s, x0_s:x1_s]
                if tpl.shape[0] >= 12 and tpl.shape[1] >= 12 and srch.shape[0] > tpl.shape[0] and srch.shape[1] > tpl.shape[1]:
                    res_tm = cv2.matchTemplate(srch, tpl, cv2.TM_CCOEFF_NORMED)
                    _, max_v, _, max_loc = cv2.minMaxLoc(res_tm)
                    if max_v > 0.62:
                        nuevo_x = x0_s + max_loc[0] + tpl.shape[1] * 0.5
                        nuevo_y = y0_s + max_loc[1] + tpl.shape[0] * 0.5
                        tx = 0.75 * tx + 0.25 * nuevo_x
                        ty = 0.75 * ty + 0.25 * nuevo_y

            tx = float(np.clip(tx, 38.0, cls.W_TR - 38.0))
            ty = float(np.clip(ty, 46.0, limite_y_inf))
            xs_m.append(tx)
            ys_m.append(ty)

            if k % 4 == 0:
                nuevos = cls._extraer_puntos_locales(g_curr, tx, ty, radio=40)
                if nuevos is not None and len(nuevos) >= 6:
                    pts_activos = nuevos

        # Interpolar a todos los fotogramas de 60 FPS y aplicar suavizado Gaussiano sin retardo
        t_todos = np.arange(n_frames, dtype=np.float32)
        t_muestras = np.array(indices_muestra, dtype=np.float32)
        xs_interp = np.interp(t_todos, t_muestras, np.array(xs_m, dtype=np.float32)) * cls.ESC_TRACK
        ys_interp = np.interp(t_todos, t_muestras, np.array(ys_m, dtype=np.float32)) * cls.ESC_TRACK

        xs_suave = cls._suavizar_serie_1d(xs_interp, sigma=4.5)
        ys_suave = cls._suavizar_serie_1d(ys_interp, sigma=4.5)

        return list(zip(xs_suave.tolist(), ys_suave.tolist()))


# ==============================================================================
# 7. MOTOR DE ASSETS VISUALES (FLECHA, CÍRCULO ROJO, EMOJIS) Y EFECTOS DE CÁMARA
# ==============================================================================
class GestorEfectosYAssets:
    """
    Gestiona:
    - Emojis animados de `emojis/` con sombra y rebote elástico (evitando colisión con objetivos).
    - Flecha roja (`fotos/flecha.png`) y Círculo rojo (`fotos/circulo_rojo.png`) mejorados con
      resplandor neón, borde de contraste y seguimiento sincronizado de objetivos.
    - Efectos visuales de cámara y color sobre el video (`zoom_impacto`, `zoom_in`, `zoom_out`,
      `flash`, `temblor`, `alerta_roja`, `brillo_epico`, `blanco_negro`).
    """

    def __init__(self, emojis_dir: Path, fotos_dir: Path, duracion_callouts: float = DURACION_CALLOUTS_DEFAULT):
        self.emojis_cache: Dict[str, Image.Image] = {}
        self.flecha_base: Optional[Image.Image] = None
        self.circulo_base: Optional[Image.Image] = None
        self.vineta_roja_base: Image.Image = self._crear_vineta_color((255, 18, 35), max_alpha=150)
        self.vineta_oscura_base: Image.Image = self._crear_vineta_color((0, 0, 0), max_alpha=145)
        self.duracion_callouts: float = float(duracion_callouts)

        self._cargar_emojis(emojis_dir)
        self._cargar_flecha_y_circulo(fotos_dir, emojis_dir)

    @staticmethod
    def _crear_vineta_color(color_rgb: Tuple[int, int, int], max_alpha: int = 140) -> Image.Image:
        w_peq, h_peq = 270, 480
        yy, xx = np.meshgrid(
            np.linspace(-1.0, 1.0, h_peq, dtype=np.float32),
            np.linspace(-1.0, 1.0, w_peq, dtype=np.float32),
            indexing="ij",
        )
        dist = np.sqrt(xx ** 2 + (yy * 0.92) ** 2)
        alpha = np.clip((dist - 0.58) / 0.65, 0.0, 1.0) ** 1.6 * float(max_alpha)
        rgba = np.zeros((h_peq, w_peq, 4), dtype=np.uint8)
        rgba[:, :, 0] = color_rgb[0]
        rgba[:, :, 1] = color_rgb[1]
        rgba[:, :, 2] = color_rgb[2]
        rgba[:, :, 3] = alpha.astype(np.uint8)
        return Image.fromarray(rgba, mode="RGBA").resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)

    @staticmethod
    def _estilizar_asset_luminoso_rojo(img_orig: Image.Image, tam_lienzo: int = 420) -> Image.Image:
        """
        Realza `flecha.png` o `circulo_rojo.png` con un rojo vibrante, borde blanco/negro
        de alto contraste y resplandor neón rojo + sombra proyectada para que destaque
        sobre cualquier fondo de video.
        """
        img_resized = img_orig.resize((tam_lienzo, tam_lienzo), Image.Resampling.LANCZOS)
        np_im = np.array(img_resized, dtype=np.uint8)
        alpha = np_im[:, :, 3]

        # Asegurar rojo brillante e intenso en todos los píxeles opacos
        mascara = alpha > 20
        np_im[mascara, 0] = 255
        np_im[mascara, 1] = 26
        np_im[mascara, 2] = 36
        nucleo = Image.fromarray(np_im, mode="RGBA")

        # Crear borde blanco/negro y resplandor exterior rojo usando dilatación de máscara
        alpha_img = Image.fromarray(alpha, mode="L")
        borde_ext = alpha_img.filter(ImageFilter.MaxFilter(9))
        sombra_alpha = borde_ext.filter(ImageFilter.GaussianBlur(radius=9))
        glow_alpha = borde_ext.filter(ImageFilter.GaussianBlur(radius=14))

        lienzo = Image.new("RGBA", (tam_lienzo, tam_lienzo), (0, 0, 0, 0))

        # 1. Sombra oscura desplazada
        capa_sombra = Image.new("RGBA", (tam_lienzo, tam_lienzo), (0, 0, 0, 0))
        sombra_negra = Image.new("RGBA", (tam_lienzo, tam_lienzo), (0, 0, 0, 210))
        sombra_negra.putalpha(ImageChops.multiply(sombra_alpha, Image.new("L", (tam_lienzo, tam_lienzo), 195)))
        capa_sombra.paste(sombra_negra, (6, 8))
        lienzo = Image.alpha_composite(lienzo, capa_sombra)

        # 2. Resplandor Neón Rojo
        capa_glow = Image.new("RGBA", (tam_lienzo, tam_lienzo), (255, 20, 40, 0))
        capa_glow.putalpha(glow_alpha)
        lienzo = Image.alpha_composite(lienzo, capa_glow)

        # 3. Contorno blanco fino de alto contraste alrededor de la figura roja
        capa_borde = Image.new("RGBA", (tam_lienzo, tam_lienzo), (255, 245, 245, 0))
        capa_borde.putalpha(alpha_img.filter(ImageFilter.MaxFilter(5)))
        lienzo = Image.alpha_composite(lienzo, capa_borde)

        # 4. Núcleo rojo brillante encima
        lienzo = Image.alpha_composite(lienzo, nucleo)
        return lienzo

    @staticmethod
    def _estilizar_emoji_con_sombra(img_orig: Image.Image, tam_base: int = 240) -> Image.Image:
        pad = 24
        esc = tam_base - pad * 2
        nucleo = img_orig.resize((esc, esc), Image.Resampling.LANCZOS)
        lienzo = Image.new("RGBA", (tam_base, tam_base), (0, 0, 0, 0))
        alpha = nucleo.split()[3]
        sombra_a = alpha.filter(ImageFilter.GaussianBlur(radius=8))
        sombra = Image.new("RGBA", (esc, esc), (0, 0, 0, 0))
        sombra.putalpha(sombra_a.point(lambda p: int(p * 0.72)))
        lienzo.alpha_composite(sombra, dest=(pad + 5, pad + 8))
        lienzo.alpha_composite(nucleo, dest=(pad, pad))
        return lienzo

    def _cargar_emojis(self, emojis_dir: Path) -> None:
        if not emojis_dir.exists():
            return
        for ruta_png in sorted(emojis_dir.glob("*.png")):
            stem_norm = _quitar_acentos(ruta_png.stem.strip().lower())
            if stem_norm in ("flecha", "circulo_rojo", "circulo"):
                continue
            try:
                img = Image.open(ruta_png).convert("RGBA")
                img_est = self._estilizar_emoji_con_sombra(img, 240)
            except Exception:
                continue
            clave_corta = stem_norm[len("emoji_"):] if stem_norm.startswith("emoji_") else stem_norm
            self.emojis_cache[clave_corta] = img_est
            self.emojis_cache[stem_norm] = img_est

        nombres_unicos = sorted({k for k in self.emojis_cache if not k.startswith("emoji_")})
        print(f"[*] Emojis cargados ({len(nombres_unicos)}): {nombres_unicos}")

    def _cargar_flecha_y_circulo(self, fotos_dir: Path, emojis_dir: Path) -> None:
        rutas_flecha = [
            fotos_dir / "flecha.png",
            emojis_dir / "flecha.png",
        ]
        for rf in rutas_flecha:
            if rf.exists():
                try:
                    img_f = Image.open(rf).convert("RGBA")
                    self.flecha_base = self._estilizar_asset_luminoso_rojo(img_f, 480)
                    break
                except Exception:
                    pass

        rutas_circulo = [
            fotos_dir / "circulo_rojo.png",
            fotos_dir / "circulo.png",
            emojis_dir / "circulo_rojo.png",
        ]
        for rc in rutas_circulo:
            if rc.exists():
                try:
                    img_c = Image.open(rc).convert("RGBA")
                    self.circulo_base = self._estilizar_asset_luminoso_rojo(img_c, 580)
                    break
                except Exception:
                    pass

        print(
            f"[*] Assets de señalamiento listos -> Flecha Roja: {'Sí' if self.flecha_base else 'No'} | "
            f"Círculo Rojo: {'Sí' if self.circulo_base else 'No'}"
        )

    def aplicar_efecto_camara_y_transformar_puntos(
        self,
        frame_rgb: np.ndarray,
        efecto: str,
        t_seg: float,
        dur_seg: float,
        foco_video: Tuple[float, float],
        puntos_rastreados: List[Tuple[float, float]],
    ) -> Tuple[Image.Image, List[Tuple[float, float]]]:
        """
        Aplica el efecto visual elegido sobre `frame_rgb` (1080x1920) y transforma
        las coordenadas de los objetivos rastreados `(vx, vy) -> (screen_x, screen_y)`
        para que las flechas y círculos rojos permanezcan 100% clavados sobre el objeto
        incluso durante un zoom o sacudida de cámara.
        """
        progreso = min(1.0, max(0.0, t_seg / max(0.1, dur_seg)))
        fx, fy = foco_video

        zoom = 1.0
        shake_x, shake_y = 0.0, 0.0

        if efecto == "zoom_impacto":
            # Golpe de zoom rápido al inicio + leve sacudida de impacto
            pulso_ini = math.sin(min(1.0, t_seg / 0.26) * math.pi) if t_seg < 0.26 else 0.0
            zoom = 1.0 + 0.14 * pulso_ini + 0.08 * progreso
            if t_seg < 0.28:
                amort = math.exp(-t_seg * 12.0)
                shake_x = 16.0 * math.sin(t_seg * 68.0) * amort
                shake_y = 12.0 * math.cos(t_seg * 54.0) * amort
        elif efecto == "zoom_in":
            # Acercamiento cinematográfico suave hacia el objetivo
            curva = progreso * progreso * (3.0 - 2.0 * progreso)
            zoom = 1.0 + 0.19 * curva
        elif efecto == "zoom_out":
            curva = progreso * progreso * (3.0 - 2.0 * progreso)
            zoom = 1.19 - 0.19 * curva
        elif efecto == "temblor":
            zoom = 1.08 + 0.04 * math.sin(t_seg * 6.0)
            amort = math.exp(-t_seg * 2.2) if t_seg < 1.2 else 0.25
            shake_x = 22.0 * math.sin(t_seg * 58.0) * amort
            shake_y = 18.0 * math.cos(t_seg * 47.0) * amort
        elif efecto == "alerta_roja":
            zoom = 1.04 + 0.04 * abs(math.sin(t_seg * 4.5))
        elif efecto == "brillo_epico":
            zoom = 1.0 + 0.10 * progreso
        elif efecto == "blanco_negro":
            zoom = 1.02 + 0.08 * progreso
        else:
            # Movimiento orgánico sutil para que el video nunca quede estático
            zoom = 1.0 + 0.05 * progreso

        # Calcular ventana de recorte [x0, y0, crop_w, crop_h] centrada hacia el objetivo
        crop_w = WIDTH / zoom
        crop_h = HEIGHT / zoom

        # Acercar el centro de cámara suavemente hacia el objetivo (foco_video)
        cx_cam = 0.55 * (WIDTH / 2.0) + 0.45 * fx + shake_x
        cy_cam = 0.55 * (HEIGHT / 2.0) + 0.45 * fy + shake_y

        x0 = float(np.clip(cx_cam - crop_w / 2.0, 0.0, WIDTH - crop_w))
        y0 = float(np.clip(cy_cam - crop_h / 2.0, 0.0, HEIGHT - crop_h))

        ix0 = int(round(x0))
        iy0 = int(round(y0))
        ix1 = min(WIDTH, max(ix0 + 16, int(round(x0 + crop_w))))
        iy1 = min(HEIGHT, max(iy0 + 16, int(round(y0 + crop_h))))

        if ix0 > 0 or iy0 > 0 or ix1 < WIDTH or iy1 < HEIGHT:
            recorte = frame_rgb[iy0:iy1, ix0:ix1]
            frame_zoomed = cv2.resize(recorte, (WIDTH, HEIGHT), interpolation=cv2.INTER_LINEAR)
        else:
            frame_zoomed = frame_rgb

        # Transformar cada punto rastreado (vx, vy) al espacio de pantalla (screen_x, screen_y)
        escala_x = WIDTH / float(max(1, ix1 - ix0))
        escala_y = HEIGHT / float(max(1, iy1 - iy0))
        puntos_pantalla: List[Tuple[float, float]] = []
        for vx, vy in puntos_rastreados:
            sx = (vx - ix0) * escala_x
            sy = (vy - iy0) * escala_y
            sx = float(np.clip(sx, 55.0, WIDTH - 55.0))
            sy = float(np.clip(sy, 75.0, HEIGHT - 280.0))
            puntos_pantalla.append((sx, sy))

        # Efecto de aberración cromática RGB durante impactos fuertes (temblor / zoom_impacto inicial)
        if (efecto == "temblor" and t_seg < 0.7) or (efecto == "zoom_impacto" and t_seg < 0.18):
            shift = int(round(7.0 * math.exp(-t_seg * 6.0)))
            if shift >= 2:
                out_rgb = frame_zoomed.copy()
                out_rgb[:, shift:, 0] = frame_zoomed[:, :-shift, 0]
                out_rgb[:, :-shift, 2] = frame_zoomed[:, shift:, 2]
                frame_zoomed = out_rgb

        img_pil = Image.fromarray(frame_zoomed, mode="RGB").convert("RGBA")

        # Efectos de color y atmósfera
        if efecto == "blanco_negro":
            gris = img_pil.convert("L")
            gris_contraste = ImageEnhance.Contrast(gris).enhance(1.22)
            img_pil = Image.merge("RGBA", (gris_contraste, gris_contraste, gris_contraste, Image.new("L", (WIDTH, HEIGHT), 255)))
            img_pil = Image.alpha_composite(img_pil, self.vineta_oscura_base)

        elif efecto == "alerta_roja":
            pulso_rojo = 0.45 + 0.55 * abs(math.sin(t_seg * 6.5))
            r, g, b, a = self.vineta_roja_base.split()
            a_mod = a.point(lambda p: int(p * pulso_rojo))
            vineta_p = Image.merge("RGBA", (r, g, b, a_mod))
            img_pil = Image.alpha_composite(img_pil, vineta_p)

        elif efecto == "brillo_epico":
            rgb_temp = ImageEnhance.Color(img_pil.convert("RGB")).enhance(1.26)
            rgb_temp = ImageEnhance.Contrast(rgb_temp).enhance(1.08)
            img_pil = rgb_temp.convert("RGBA")
            if t_seg < 0.30:
                alpha_dorado = int(round(90.0 * (1.0 - t_seg / 0.30)))
                capa_dorada = Image.new("RGBA", (WIDTH, HEIGHT), (255, 215, 60, alpha_dorado))
                img_pil = Image.alpha_composite(img_pil, capa_dorada)

        elif efecto == "flash":
            if t_seg < 0.32:
                alpha_flash = int(round(220.0 * ((1.0 - t_seg / 0.32) ** 1.8)))
                capa_blanca = Image.new("RGBA", (WIDTH, HEIGHT), (255, 255, 255, alpha_flash))
                img_pil = Image.alpha_composite(img_pil, capa_blanca)

        # Micro-destello de transición suave en los primeros 3 fotogramas de cada segmento
        if t_seg < 0.06 and efecto != "flash":
            alpha_tr = int(round(55.0 * (1.0 - t_seg / 0.06)))
            if alpha_tr > 4:
                img_pil = Image.alpha_composite(
                    img_pil, Image.new("RGBA", (WIDTH, HEIGHT), (255, 255, 255, alpha_tr))
                )

        return img_pil, puntos_pantalla

    def dibujar_circulo_rojo(
        self,
        lienzo: Image.Image,
        activo: bool,
        target_xy: Tuple[float, float],
        tamano_mod: str,
        t_seg: float,
        dur_seg: float,
    ) -> float:
        """
        Dibuja `circulo_rojo.png` centrado exactamente sobre `target_xy` y devuelve
        el radio exterior actual en píxeles (para que la flecha apunte al borde del círculo).
        """
        if not activo or self.circulo_base is None:
            return 0.0

        dur_mostrar = max(0.8, min(dur_seg - 0.15, self.duracion_callouts))
        if t_seg < 0.04 or t_seg > dur_mostrar:
            return 0.0

        mapa_diametro = {
            "chico": 370,
            "medio": 475,
            "grande": 580,
        }
        diam_base = mapa_diametro.get(tamano_mod, 475)

        if t_seg < 0.22:
            p_in = (t_seg - 0.04) / 0.18
            escala = 0.25 + 0.88 * math.sin(p_in * math.pi * 0.65)
            alpha_f = min(1.0, p_in * 1.6)
        elif t_seg > dur_mostrar - 0.18:
            p_out = max(0.0, (dur_mostrar - t_seg) / 0.18)
            escala = 0.75 + 0.25 * p_out
            alpha_f = p_out
        else:
            # Pulso rítmico llamativo alrededor del objetivo
            escala = 1.0 + 0.075 * math.sin(t_seg * 11.5)
            alpha_f = 1.0

        diam_actual = max(48, int(round(diam_base * escala)))
        circ_img = self.circulo_base.resize((diam_actual, diam_actual), Image.Resampling.LANCZOS)

        if alpha_f < 0.99:
            r, g, b, a = circ_img.split()
            a = a.point(lambda p: int(p * alpha_f))
            circ_img = Image.merge("RGBA", (r, g, b, a))

        tx, ty = int(round(target_xy[0])), int(round(target_xy[1]))
        pos_x = max(0, min(WIDTH - diam_actual, tx - diam_actual // 2))
        pos_y = max(0, min(HEIGHT - diam_actual, ty - diam_actual // 2))
        lienzo.alpha_composite(circ_img, dest=(pos_x, pos_y))

        # Radio visible real del anillo rojo (0.406 del ancho de la imagen)
        return diam_actual * 0.406

    def dibujar_flecha_roja(
        self,
        lienzo: Image.Image,
        activo: bool,
        target_xy: Tuple[float, float],
        radio_circulo_activo: float,
        t_seg: float,
        dur_seg: float,
    ) -> None:
        """
        Dibuja `flecha.png` apuntando con precisión trigonométrica hacia `target_xy`
        y persiguiéndolo cuadro a cuadro. Si hay un círculo rojo sobre el mismo objetivo,
        la punta de la flecha señala justo al borde exterior del círculo.
        """
        if not activo or self.flecha_base is None:
            return

        dur_mostrar = max(0.8, min(dur_seg - 0.15, self.duracion_callouts))
        if t_seg < 0.04 or t_seg > dur_mostrar:
            return

        tx, ty = target_xy

        # Elegir el vector unitario u = (ux, uy) que va DESDE el objetivo HACIA la cola de la flecha,
        # apuntando siempre desde el lado de la pantalla con mayor espacio libre para que la cola
        # jamás se salga del lienzo 1080x1920.
        dx_centro = (WIDTH * 0.50) - tx
        dy_centro = (HEIGHT * 0.42) - ty

        if abs(dx_centro) < 95.0 and abs(dy_centro) < 95.0:
            # Si el objetivo está en el centro, apuntar en diagonal desde arriba-derecha (-32°)
            ux, uy = 0.848, -0.530
        else:
            # Apuntar desde el espacio abierto hacia el objetivo con una inclinación diagonal atractiva
            ux = dx_centro
            uy = dy_centro - 90.0 if ty > 420 else dy_centro + 110.0
            norm = math.hypot(ux, uy)
            if norm < 1e-3:
                ux, uy = 0.848, -0.530
            else:
                ux /= norm
                uy /= norm

        # En `flecha.png`, la punta apunta a la IZQUIERDA (-1, 0) y la cola está hacia (+1, 0).
        # Para orientar el eje de la cola hacia (ux, uy), el ángulo de rotación en PIL es -atan2(uy, ux).
        angulo_pil = -math.degrees(math.atan2(uy, ux))

        if t_seg < 0.20:
            p_in = (t_seg - 0.04) / 0.16
            escala_in = 0.45 + 0.62 * math.sin(p_in * math.pi * 0.65)
            alpha_f = min(1.0, p_in * 1.6)
        elif t_seg > dur_mostrar - 0.18:
            p_out = max(0.0, (dur_mostrar - t_seg) / 0.18)
            escala_in = 0.75 + 0.25 * p_out
            alpha_f = p_out
        else:
            escala_in = 1.0
            alpha_f = 1.0

        tam_flecha = max(96, int(round(355 * escala_in)))
        flecha_scaled = self.flecha_base.resize((tam_flecha, tam_flecha), Image.Resampling.LANCZOS)
        flecha_rot = flecha_scaled.rotate(angulo_pil, resample=Image.Resampling.BICUBIC, expand=True)

        if alpha_f < 0.99:
            r, g, b, a = flecha_rot.split()
            a = a.point(lambda p: int(p * alpha_f))
            flecha_rot = Image.merge("RGBA", (r, g, b, a))

        # Distancia desde el objetivo hasta la punta de la flecha + rebote rítmico a lo largo de su eje
        gap_objetivo = (radio_circulo_activo + 8.0) if radio_circulo_activo > 10.0 else 32.0
        rebote = 36.0 * abs(math.sin(t_seg * 10.5))
        dist_centro_a_punta = tam_flecha * 0.455
        dist_total = gap_objetivo + rebote + dist_centro_a_punta

        cx = int(round(tx + ux * dist_total))
        cy = int(round(ty + uy * dist_total))

        fw, fh = flecha_rot.size
        pos_x = max(8, min(WIDTH - fw - 8, cx - fw // 2))
        pos_y = max(16, min(HEIGHT - fh - 16, cy - fh // 2))
        lienzo.alpha_composite(flecha_rot, dest=(pos_x, pos_y))

    def dibujar_emoji(
        self,
        lienzo: Image.Image,
        nombre_emoji: Optional[str],
        posicion_solicitada: str,
        target_principal_xy: Optional[Tuple[float, float]],
        t_seg: float,
        dur_seg: float,
    ) -> None:
        if not nombre_emoji:
            return
        clave = _quitar_acentos(nombre_emoji.strip().lower())
        img_base = self.emojis_cache.get(clave)
        if img_base is None:
            return

        dur_mostrar = max(1.2, min(dur_seg - 0.05, 3.6))
        if t_seg < 0.05 or t_seg > dur_mostrar:
            return

        if t_seg < 0.24:
            p_in = (t_seg - 0.05) / 0.19
            escala_anim = 0.22 + 0.90 * math.sin(p_in * math.pi * 0.65)
            alpha_factor = min(1.0, p_in * 1.6)
        elif t_seg > dur_mostrar - 0.20:
            p_out = max(0.0, (dur_mostrar - t_seg) / 0.20)
            escala_anim = 0.65 + 0.35 * p_out
            alpha_factor = p_out
        else:
            escala_anim = 1.0 + 0.065 * math.sin(t_seg * 7.5)
            alpha_factor = 1.0

        tam_base = 245
        tam_actual = max(32, int(round(tam_base * escala_anim)))
        emoji_img = img_base.resize((tam_actual, tam_actual), Image.Resampling.LANCZOS)

        angulo = 7.5 * math.sin(t_seg * 5.8)
        emoji_img = emoji_img.rotate(angulo, resample=Image.Resampling.BICUBIC, expand=True)

        if alpha_factor < 0.99:
            r, g, b, a = emoji_img.split()
            a = a.point(lambda p: int(p * alpha_factor))
            emoji_img = Image.merge("RGBA", (r, g, b, a))

        # Evitar que el emoji se superponga con el círculo/flecha si están del mismo lado
        pos_efectiva = posicion_solicitada
        if target_principal_xy is not None:
            tx, ty = target_principal_xy
            if pos_efectiva == "auto":
                pos_efectiva = "izquierda" if tx >= WIDTH * 0.5 else "derecha"
            elif pos_efectiva == "derecha" and tx > WIDTH * 0.62 and abs(ty - 340) < 230:
                pos_efectiva = "izquierda"
            elif pos_efectiva == "izquierda" and tx < WIDTH * 0.38 and abs(ty - 340) < 230:
                pos_efectiva = "derecha"
        elif pos_efectiva == "auto":
            pos_efectiva = "derecha"

        pos_map = {
            "derecha": (WIDTH - 195, 330),
            "izquierda": (195, 330),
            "arriba_der": (WIDTH - 190, 240),
            "arriba_izq": (190, 240),
            "centro": (WIDTH // 2, 340),
            "abajo": (WIDTH - 195, 1060),
        }
        cx, cy = pos_map.get(pos_efectiva, pos_map["derecha"])
        cy += int(round(9.0 * math.sin(t_seg * 6.2)))

        ew, eh = emoji_img.size
        lienzo.alpha_composite(emoji_img, dest=(max(0, cx - ew // 2), max(0, cy - eh // 2)))


# ==============================================================================
# 8. GESTOR DE AUDIO/SFX (.MP3/.WAV) Y PIPELINE DE RENDERIZADO POR SEGMENTO
# ==============================================================================
class GestorAudioSFX:
    """
    Decodifica y cachea todos los archivos de `sfx/` (.mp3, .MP3, .wav, .ogg) usando FFmpeg,
    recorta silencios muertos al inicio/final para sincronización instantánea y normaliza
    sus picos para una mezcla profesional junto a la voz IA.
    """

    def __init__(self, sfx_dir: Path, sr: int = 44100):
        self.sfx_dir = sfx_dir
        self.sr = sr
        self.cache_pcm: Dict[str, np.ndarray] = {}
        self._cargar_todos_los_sfx()

    def _cargar_todos_los_sfx(self) -> None:
        if not self.sfx_dir.exists():
            return
        for archivo in sorted(self.sfx_dir.glob("*.*")):
            if archivo.suffix.lower() not in (".mp3", ".wav", ".ogg", ".m4a"):
                continue
            clave = _quitar_acentos(archivo.stem.strip().lower())
            try:
                res = subprocess.run(
                    [
                        "ffmpeg", "-v", "error",
                        "-i", str(archivo),
                        "-f", "s16le", "-ac", "1", "-ar", str(self.sr), "-",
                    ],
                    capture_output=True,
                    check=False,
                )
                if res.returncode != 0 or len(res.stdout) < 100:
                    continue
                pcm = np.frombuffer(res.stdout, dtype=np.int16).astype(np.float32) / 32768.0
                peak = float(np.max(np.abs(pcm)))
                if peak < 1e-4:
                    continue

                # Recortar silencio muerto inicial y final (ej. xp_Error o riser_suction)
                umbral = max(0.008, peak * 0.045)
                activos = np.where(np.abs(pcm) > umbral)[0]
                if len(activos) > 0:
                    pad_ini = int(self.sr * 0.012)
                    pad_fin = int(self.sr * 0.040)
                    i0 = max(0, int(activos[0]) - pad_ini)
                    i1 = min(len(pcm), int(activos[-1]) + pad_fin)
                    pcm = pcm[i0:i1].copy()

                # Normalizar pico a 0.85 para consistencia entre efectos
                pcm = pcm * (0.85 / peak)

                # Fade-out suave en los últimos 25ms
                fade_n = min(int(self.sr * 0.025), len(pcm) // 4)
                if fade_n > 2:
                    pcm[-fade_n:] *= np.linspace(1.0, 0.0, fade_n, dtype=np.float32)

                self.cache_pcm[clave] = pcm
            except Exception:
                continue

        print(f"[*] Efectos de sonido (SFX) cargados ({len(self.cache_pcm)}): {sorted(self.cache_pcm.keys())}")

    def obtener_pcm(self, nombre_sfx: str) -> Optional[np.ndarray]:
        clave = _quitar_acentos(nombre_sfx.strip().lower())
        return self.cache_pcm.get(clave)

    def mezclar_audio_segmento(
        self,
        ruta_voz_wav: Path,
        duracion_total_seg: float,
        sfx_lista: List[str],
        tiene_emoji_o_flecha: bool,
        ruta_salida_wav: Path,
    ) -> None:
        n_total = int(round(duracion_total_seg * self.sr))
        mezcla = np.zeros(n_total, dtype=np.float32)

        with wave.open(str(ruta_voz_wav), "r") as wf:
            voz_pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
            n_copy = min(n_total, len(voz_pcm))
            voz_fuerte = np.tanh(voz_pcm[:n_copy] * VOLUMEN_VOZ_NARRADOR)
            mezcla[:n_copy] += voz_fuerte

        # Superponer los SFX solicitados (con ligero escalonamiento si hay más de uno)
        for idx_s, nombre_sfx in enumerate(sfx_lista):
            sfx_pcm = self.obtener_pcm(nombre_sfx)
            if sfx_pcm is None or len(sfx_pcm) == 0:
                continue
            offset_samples = int(round(idx_s * 0.14 * self.sr))
            if offset_samples >= n_total:
                continue
            n_disp = min(n_total - offset_samples, len(sfx_pcm))
            # Limitar duración máxima de SFX muy largos para no ensuciar toda la frase
            max_samples_sfx = int(round(2.4 * self.sr))
            n_usar = min(n_disp, max_samples_sfx)
            bloque_sfx = sfx_pcm[:n_usar].copy()
            if n_usar < len(sfx_pcm) and n_usar > 400:
                bloque_sfx[-400:] *= np.linspace(1.0, 0.0, 400, dtype=np.float32)

            ganancia_sfx = 0.34 if idx_s == 0 else 0.28
            mezcla[offset_samples : offset_samples + n_usar] += bloque_sfx * ganancia_sfx

        # Si aparece un emoji o flecha y no se pidió 'pop', añadir un sutil pop acústico a los 60ms
        if tiene_emoji_o_flecha and "pop" not in sfx_lista:
            pop_pcm = self.obtener_pcm("pop")
            if pop_pcm is not None:
                off_pop = int(round(0.06 * self.sr))
                n_pop = min(max(0, n_total - off_pop), len(pop_pcm))
                if n_pop > 0:
                    mezcla[off_pop : off_pop + n_pop] += pop_pcm[:n_pop] * 0.18

        mezcla = np.clip(mezcla, -0.98, 0.98)
        pcm_out = (mezcla * 32767).astype(np.int16)
        with wave.open(str(ruta_salida_wav), "w") as wf_out:
            wf_out.setnchannels(1)
            wf_out.setsampwidth(2)
            wf_out.setframerate(self.sr)
            wf_out.writeframes(pcm_out.tobytes())


def obtener_info_video(ruta_video: Path) -> Tuple[float, int, int, float]:
    """
    Devuelve (duracion_seg, ancho, alto, fps) exactos del video de entrada.
    """
    if not ruta_video.exists():
        raise FileNotFoundError(f"No se encontró el archivo de video: {ruta_video}")
    cap = cv2.VideoCapture(str(ruta_video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1080)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1920)
    cap.release()

    dur = 0.0
    try:
        res = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(ruta_video),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        dur = float(res.stdout.strip())
    except Exception:
        dur = 0.0

    if dur <= 0.1 and n_frames > 0 and fps > 0:
        dur = float(n_frames) / float(fps)
    if dur <= 0.1:
        dur = 15.0
    return max(0.5, dur), w, h, float(fps)


def _asignar_tiempos_reales_segmentos(
    segmentos: List[SegmentoVideoGuion],
    dur_video_origen: float,
) -> List[Tuple[int, float]]:
    """
    Asigna a cada segmento su tramo exacto `[t_inicio_video, t_fin_video]` dentro de
    `[0.0, dur_video_origen]` a velocidad 1.0x real (sin cámara lenta ni estiramientos),
    garantizando que la suma de fotogramas de todos los segmentos coincida exactamente
    con la duración de `video_input`.
    Devuelve una lista de `(total_frames_seg, dur_seg_exacta)` por cada segmento.
    """
    n_segs = len(segmentos)
    total_frames_video = max(n_segs, int(round(dur_video_origen * FPS)))
    dur_exacta_total = total_frames_video / float(FPS)

    todos_explicitos = all(
        (s.t_inicio_video is not None and s.t_fin_video is not None and s.t_fin_video > s.t_inicio_video)
        for s in segmentos
    )

    limites_seg: List[float] = [0.0]
    if todos_explicitos:
        t_max_guion = float(segmentos[-1].t_fin_video or dur_exacta_total)
        penultimo_fin = float(segmentos[-2].t_fin_video or 0.0) if n_segs > 1 else 0.0

        # Si los tiempos del guion coinciden con el video (salvo redondeo de ±3.5s en el último bloque)
        if penultimo_fin < (dur_exacta_total - 0.8) and abs(t_max_guion - dur_exacta_total) <= 3.5:
            cursor_t = 0.0
            for idx_s, s in enumerate(segmentos):
                if idx_s == n_segs - 1:
                    limites_seg.append(dur_exacta_total)
                else:
                    t_f = float(np.clip(float(s.t_fin_video or cursor_t + 1.0), cursor_t + 0.4, dur_exacta_total - 0.4))
                    limites_seg.append(t_f)
                    cursor_t = t_f
        else:
            # Escalar proporcionalmente las duraciones solicitadas para cubrir exactamente [0, dur_exacta_total]
            pesos = [max(0.5, float(s.t_fin_video - s.t_inicio_video)) for s in segmentos]
            suma_p = sum(pesos)
            acum = 0.0
            for idx_s, p in enumerate(pesos):
                acum += p
                if idx_s == n_segs - 1:
                    limites_seg.append(dur_exacta_total)
                else:
                    limites_seg.append((acum / suma_p) * dur_exacta_total)
    else:
        # Si algún segmento tiene 'auto', repartir [0, dur_exacta_total] proporcionalmente a las palabras
        pesos = []
        for s in segmentos:
            if s.t_inicio_video is not None and s.t_fin_video is not None and s.t_fin_video > s.t_inicio_video:
                pesos.append(max(1.0, (s.t_fin_video - s.t_inicio_video) * 3.5))
            else:
                pesos.append(max(3.0, float(len(s.texto_voz.split()))))
        suma_p = sum(pesos)
        acum = 0.0
        for idx_s, p in enumerate(pesos):
            acum += p
            if idx_s == n_segs - 1:
                limites_seg.append(dur_exacta_total)
            else:
                limites_seg.append((acum / suma_p) * dur_exacta_total)

    # Convertir los límites de tiempo a índices de fotograma exactos a 60 FPS
    limites_frames: List[int] = [0]
    for idx_s in range(1, n_segs):
        f_ideal = int(round(limites_seg[idx_s] * FPS))
        f_min = limites_frames[-1] + 1
        f_max = total_frames_video - (n_segs - idx_s)
        limites_frames.append(max(f_min, min(f_max, f_ideal)))
    limites_frames.append(total_frames_video)

    resultado: List[Tuple[int, float]] = []
    for idx_s, seg in enumerate(segmentos):
        f0 = limites_frames[idx_s]
        f1 = limites_frames[idx_s + 1]
        n_frames_seg = max(1, f1 - f0)
        dur_seg = n_frames_seg / float(FPS)
        seg.t_inicio_video = f0 / float(FPS)
        seg.t_fin_video = f1 / float(FPS)
        resultado.append((n_frames_seg, dur_seg))

    return resultado


def extraer_frames_segmento_video(
    ruta_video: Path,
    t_ini: float,
    t_fin: float,
    total_frames_salida: int,
    modo_encuadre: str = "full",
) -> List[np.ndarray]:
    """
    Extrae el rango [t_ini, t_fin] a velocidad real 1.0x (60 FPS) sin cámara lenta
    y devuelve exactamente `total_frames_salida` fotogramas RGB (1080x1920).
    """
    dur_clip = max(0.05, t_fin - t_ini)
    fps_extraccion = float(FPS)

    if modo_encuadre == "blur":
        filtro_vf = (
            f"split[bg][fg];"
            f"[bg]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},boxblur=24:4,eq=brightness=-0.12[bg_b];"
            f"[fg]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease[fg_s];"
            f"[bg_b][fg_s]overlay=(W-w)/2:(H-h)/2,fps={fps_extraccion:.3f}"
        )
        cmd_ff = [
            "ffmpeg", "-v", "error",
            "-ss", f"{max(0.0, t_ini):.4f}",
            "-t", f"{dur_clip:.4f}",
            "-i", str(ruta_video),
            "-filter_complex", filtro_vf,
            "-pix_fmt", "rgb24",
            "-f", "rawvideo", "-",
        ]
    else:
        filtro_vf = (
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},"
            f"fps={fps_extraccion:.3f}"
        )
        cmd_ff = [
            "ffmpeg", "-v", "error",
            "-ss", f"{max(0.0, t_ini):.4f}",
            "-t", f"{dur_clip:.4f}",
            "-i", str(ruta_video),
            "-vf", filtro_vf,
            "-pix_fmt", "rgb24",
            "-f", "rawvideo", "-",
        ]

    frames_raw: List[np.ndarray] = []
    bytes_por_frame = WIDTH * HEIGHT * 3
    try:
        proc = subprocess.Popen(cmd_ff, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if proc.stdout:
            while True:
                buf = proc.stdout.read(bytes_por_frame)
                if len(buf) < bytes_por_frame:
                    break
                frame_np = np.frombuffer(buf, dtype=np.uint8).reshape((HEIGHT, WIDTH, 3)).copy()
                frames_raw.append(frame_np)
        proc.wait()
    except Exception:
        frames_raw.clear()

    # Fallback con OpenCV si FFmpeg no devolvió frames
    if not frames_raw:
        cap = cv2.VideoCapture(str(ruta_video))
        fps_orig = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t_ini) * 1000.0)
        max_leer = max(2, int(round(dur_clip * fps_orig)))
        for _ in range(max_leer):
            ret, frame_bgr = cap.read()
            if not ret:
                break
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            h, w, _ = frame_rgb.shape
            scale = max(WIDTH / float(w), HEIGHT / float(h))
            nw, nh = int(round(w * scale)), int(round(h * scale))
            resized = cv2.resize(frame_rgb, (nw, nh), interpolation=cv2.INTER_LINEAR)
            x0 = (nw - WIDTH) // 2
            y0 = (nh - HEIGHT) // 2
            frames_raw.append(resized[y0 : y0 + HEIGHT, x0 : x0 + WIDTH].copy())
        cap.release()

    if not frames_raw:
        if t_ini > 0.1:
            return extraer_frames_segmento_video(ruta_video, 0.0, dur_clip, total_frames_salida, modo_encuadre)
        raise RuntimeError(f"No se pudieron decodificar fotogramas de: {ruta_video}")

    if len(frames_raw) == total_frames_salida:
        return frames_raw
    if len(frames_raw) > total_frames_salida:
        return frames_raw[:total_frames_salida]

    # Si por redondeo de paquetes falta 1 o 2 cuadros al final, seleccionar sin blending fantasma
    resultado: List[np.ndarray] = []
    n_src = len(frames_raw)
    for f_idx in range(total_frames_salida):
        idx_src = min(n_src - 1, int(round((f_idx / float(max(1, total_frames_salida - 1))) * (n_src - 1))))
        resultado.append(frames_raw[idx_src])
    return resultado


def calcular_envolvente_rms(ruta_wav: Path, fps: int) -> np.ndarray:
    with wave.open(str(ruta_wav), "r") as wf:
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    muestras_por_frame = max(1, int(sr / fps))
    total_video_frames = int(math.ceil(len(audio) / muestras_por_frame))
    rms_por_frame = np.zeros(total_video_frames, dtype=np.float32)

    for i in range(total_video_frames):
        chunk = audio[i * muestras_por_frame : (i + 1) * muestras_por_frame]
        if len(chunk) > 0:
            rms_por_frame[i] = float(np.sqrt(np.mean(chunk ** 2)))
    return rms_por_frame


def detectar_encoder_nvidia() -> str:
    try:
        res = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, check=False)
        if "h264_nvenc" in res.stdout:
            return "h264_nvenc"
    except FileNotFoundError:
        pass
    return "libx264"


MAX_CIRCULOS_POR_VIDEO = 2


def _limitar_circulos_guion(segmentos: List[SegmentoVideoGuion], max_circulos: int = MAX_CIRCULOS_POR_VIDEO) -> None:
    """
    Limita el círculo rojo a `max_circulos` segmentos en todo el Short para que no aparezca
    siempre junto a la flecha. Se conservan primero los marcados como `:grande` y luego los
    más tempranos; en el resto se quita el círculo y, si no había flecha, la flecha pasa a
    señalar ese mismo objetivo.
    """
    con_circulo = [i for i, s in enumerate(segmentos) if s.circulo]
    if len(con_circulo) <= max_circulos:
        return
    prioridad = sorted(con_circulo, key=lambda i: (0 if segmentos[i].tamano_circulo == "grande" else 1, i))
    conservar = set(prioridad[:max_circulos])
    for i in con_circulo:
        if i in conservar:
            continue
        seg = segmentos[i]
        if not seg.flecha:
            seg.flecha = seg.circulo
        seg.circulo = None
    print(
        f"[*] Círculo rojo limitado a {max_circulos} segmento(s): "
        f"{', '.join(str(i + 1) for i in sorted(conservar))} (el resto usa solo la flecha)."
    )


async def editar_video_con_guion(
    ruta_video: Path,
    ruta_guion: Path,
    voz_override: Optional[str] = None,
    modo_encuadre_override: Optional[str] = None,
) -> Path:
    print("=" * 78)
    print(" EDITOR SHORTS STUDIO v1.0 - AUTOMATIZACIÓN DE SHORTS (VOZ IA + TRACKING)")
    print("=" * 78)

    for carpeta in [EMOJIS_DIR, FONTS_DIR, FOTOS_DIR, SFX_DIR, TEMP_DIR, OUTPUT_DIR]:
        carpeta.mkdir(parents=True, exist_ok=True)
    asegurar_fuente_mrbeast()

    config = cargar_guion_video(ruta_guion)
    if not config.segmentos:
        raise ValueError(f"El guión '{ruta_guion.name}' no contiene segmentos válidos.")

    if voz_override:
        config.voz_narrador = voz_override
    if modo_encuadre_override:
        config.modo_encuadre = modo_encuadre_override

    _limitar_circulos_guion(config.segmentos)

    dur_video_origen, w_orig, h_orig, fps_orig = obtener_info_video(ruta_video)
    print(
        f"[*] Video base: '{ruta_video.name}' ({w_orig}x{h_orig} a {fps_orig:.1f} FPS | Duración exacta: {dur_video_origen:.2f}s)"
    )

    # 1. Fijar los tramos reales 1.0x de cada segmento sobre `dur_video_origen` ANTES de generar la voz
    # para que el video de fondo NUNCA vaya en cámara lenta y dure exactamente lo mismo que `video_input`.
    tiempos_reales = _asignar_tiempos_reales_segmentos(config.segmentos, dur_video_origen)

    gestor_assets = GestorEfectosYAssets(EMOJIS_DIR, FOTOS_DIR, duracion_callouts=config.duracion_callouts)
    gestor_sfx = GestorAudioSFX(SFX_DIR)

    datos_segmentos = []
    archivos_audio_seg: List[Path] = []

    # 2. Generar voz IA ajustada a la duración real 1.0x de cada segmento, subtítulos y mezcla de SFX
    for idx, (seg, (total_frames_seg, dur_seg_exacta)) in enumerate(zip(config.segmentos, tiempos_reales)):
        sfx_str = "+".join(seg.sfx_lista) if seg.sfx_lista else "-"
        info_seg = (
            f"{seg.t_inicio_video:.1f}s-{seg.t_fin_video:.1f}s | efecto={seg.efecto_visual} | "
            f"sfx={sfx_str} | emoji={seg.emoji or '-'} | flecha={seg.flecha or '-'} | circulo={seg.circulo or '-'}"
        )
        print(f"[+] Segmento [{idx + 1}/{len(config.segmentos)}] ({info_seg}): {seg.texto_voz}")

        ruta_mp3 = TEMP_DIR / f"{seg.id_segmento}.mp3"
        dur_voz, palabras_sub, ini_voz, fin_voz = await generar_voz_y_timestamps_segmento(
            seg.texto_voz,
            ruta_mp3,
            voz_edge=config.voz_narrador,
            dur_objetivo_seg=dur_seg_exacta,
        )

        ruta_voz_wav = ruta_mp3.with_suffix(".wav")
        rms_env = calcular_envolvente_rms(ruta_voz_wav, FPS)

        ruta_mix_wav = TEMP_DIR / f"{seg.id_segmento}_mix.wav"
        tiene_overlay_pop = bool(seg.emoji or seg.flecha or seg.circulo)
        gestor_sfx.mezclar_audio_segmento(
            ruta_voz_wav=ruta_voz_wav,
            duracion_total_seg=dur_seg_exacta,
            sfx_lista=seg.sfx_lista,
            tiene_emoji_o_flecha=tiene_overlay_pop,
            ruta_salida_wav=ruta_mix_wav,
        )
        archivos_audio_seg.append(ruta_mix_wav)
        datos_segmentos.append([seg, total_frames_seg, dur_seg_exacta, palabras_sub, rms_env])

    # 3. Unir el audio maestro de la voz + SFX + audio de fondo del video original
    ruta_voz_maestra = TEMP_DIR / "voz_maestra.wav"
    bloques_pcm = []
    for ruta_w in archivos_audio_seg:
        with wave.open(str(ruta_w), "r") as wf:
            bloques_pcm.append(wf.readframes(wf.getnframes()))
    with wave.open(str(ruta_voz_maestra), "w") as wf_master:
        wf_master.setnchannels(1)
        wf_master.setsampwidth(2)
        wf_master.setframerate(44100)
        for b in bloques_pcm:
            wf_master.writeframes(b)

    ruta_audio_final = TEMP_DIR / "audio_final_combinado.wav"
    if config.volumen_video_original > 0.001:
        res_mix = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(ruta_voz_maestra),
                "-stream_loop", "-1", "-i", str(ruta_video),
                "-filter_complex",
                f"[1:a]volume={config.volumen_video_original}[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.98:level=disabled[aout]",
                "-map", "[aout]",
                "-ar", "44100", "-ac", "1",
                str(ruta_audio_final),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if res_mix.returncode != 0 or not ruta_audio_final.exists():
            ruta_audio_final = ruta_voz_maestra
    else:
        ruta_audio_final = ruta_voz_maestra

    # 4. Configurar nombre de archivo de salida y codificador FFmpeg (NVENC o libx264)
    if config.titulo_superior:
        titulo_limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", config.titulo_superior).strip().rstrip(".")
        nombre_out = titulo_limpio or config.archivo_salida or f"short_editado_{ruta_video.stem}.mp4"
    else:
        nombre_out = config.archivo_salida or f"short_editado_{ruta_video.stem}.mp4"

    if not nombre_out.lower().endswith(".mp4"):
        nombre_out += ".mp4"
    ruta_mp4_final = OUTPUT_DIR / nombre_out
    encoder = detectar_encoder_nvidia()
    print(f"[*] Renderizando Short final con {encoder} ({WIDTH}x{HEIGHT} a {FPS} FPS)...")

    if encoder == "h264_nvenc":
        args_codec = ["-c:v", "h264_nvenc", "-preset", "p4", "-b:v", "14M", "-pix_fmt", "yuv420p"]
    else:
        args_codec = [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-threads", str(CPU_THREADS), "-pix_fmt", "yuv420p",
        ]

    cmd_ffmpeg = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{WIDTH}x{HEIGHT}",
        "-pix_fmt", "rgb24",
        "-r", str(FPS),
        "-i", "-",
        "-i", str(ruta_audio_final),
        *args_codec,
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(ruta_mp4_final),
    ]

    proceso_ffmpeg = subprocess.Popen(cmd_ffmpeg, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    # Nota: `config.titulo_superior` se usa únicamente para darle nombre al archivo MP4 exportado
    # y NO se renderiza encima del video.

    # 5. Renderizar segmento por segmento con seguimiento de objetivos (Optical Flow) y subtítulos luminosos
    for idx_seg, (seg, total_frames_seg, dur_seg_exacta, palabras_sub, rms_env) in enumerate(datos_segmentos):
        t_vid_ini = float(seg.t_inicio_video or 0.0)
        t_vid_fin = float(seg.t_fin_video or dur_video_origen)

        frames_seg_rgb = extraer_frames_segmento_video(
            ruta_video=ruta_video,
            t_ini=t_vid_ini,
            t_fin=t_vid_fin,
            total_frames_salida=total_frames_seg,
            modo_encuadre=config.modo_encuadre,
        )

        # Calcular trayectorias rastreadas por visión artificial para FLECHA y CIRCULO
        mismo_objetivo = bool(
            seg.flecha and seg.circulo and (_quitar_acentos(seg.flecha) == _quitar_acentos(seg.circulo))
        )

        trayectoria_flecha: Optional[List[Tuple[float, float]]] = None
        trayectoria_circulo: Optional[List[Tuple[float, float]]] = None

        if seg.circulo:
            trayectoria_circulo = RastreadorObjetivosVideo.calcular_trayectoria(frames_seg_rgb, seg.circulo)
        if seg.flecha:
            if mismo_objetivo and trayectoria_circulo is not None:
                trayectoria_flecha = trayectoria_circulo
            else:
                trayectoria_flecha = RastreadorObjetivosVideo.calcular_trayectoria(frames_seg_rgb, seg.flecha)

        print(
            f"    -> Renderizando segmento {idx_seg + 1}/{len(datos_segmentos)} "
            f"({total_frames_seg} frames | video {t_vid_ini:.1f}s..{t_vid_fin:.1f}s)..."
        )

        for f_idx in range(total_frames_seg):
            t_seg = f_idx / float(FPS)
            rms_val = float(rms_env[f_idx]) if f_idx < len(rms_env) else 0.0
            frame_rgb = frames_seg_rgb[f_idx]

            pt_c_vid = trayectoria_circulo[f_idx] if trayectoria_circulo else (WIDTH / 2.0, HEIGHT * 0.44)
            pt_f_vid = trayectoria_flecha[f_idx] if trayectoria_flecha else pt_c_vid
            foco_camara = pt_c_vid if trayectoria_circulo else (pt_f_vid if trayectoria_flecha else (WIDTH / 2.0, HEIGHT * 0.46))

            lienzo, pts_pantalla = gestor_assets.aplicar_efecto_camara_y_transformar_puntos(
                frame_rgb=frame_rgb,
                efecto=seg.efecto_visual,
                t_seg=t_seg,
                dur_seg=dur_seg_exacta,
                foco_video=foco_camara,
                puntos_rastreados=[pt_c_vid, pt_f_vid],
            )
            pt_c_screen, pt_f_screen = pts_pantalla[0], pts_pantalla[1]

            # 1) Círculo Rojo siguiendo al objetivo
            radio_circulo = gestor_assets.dibujar_circulo_rojo(
                lienzo=lienzo,
                activo=bool(seg.circulo),
                target_xy=pt_c_screen,
                tamano_mod=seg.tamano_circulo,
                t_seg=t_seg,
                dur_seg=dur_seg_exacta,
            )

            # 2) Flecha Roja siguiendo al objetivo (si comparte objetivo con el círculo, apunta a su borde)
            radio_para_flecha = radio_circulo if mismo_objetivo else 0.0
            gestor_assets.dibujar_flecha_roja(
                lienzo=lienzo,
                activo=bool(seg.flecha),
                target_xy=pt_f_screen,
                radio_circulo_activo=radio_para_flecha,
                t_seg=t_seg,
                dur_seg=dur_seg_exacta,
            )

            # 3) Emoji animado (evitando superponerse con el objetivo rastreado)
            target_ref_emoji = pt_c_screen if seg.circulo else (pt_f_screen if seg.flecha else None)
            gestor_assets.dibujar_emoji(
                lienzo=lienzo,
                nombre_emoji=seg.emoji,
                posicion_solicitada=seg.posicion_emoji,
                target_principal_xy=target_ref_emoji,
                t_seg=t_seg,
                dur_seg=dur_seg_exacta,
            )

            # 4) Subtítulos dinámicos ultra llamativos con resplandor neón y pulso reactivo a la voz
            renderizar_subtitulos_luminosos(
                lienzo=lienzo,
                palabras=palabras_sub,
                t_actual=t_seg,
                nivel_voz_rms=rms_val,
                y_centro=1340,
                palabras_verdes_extra=config.palabras_verdes_extra,
                palabras_rojas_extra=config.palabras_rojas_extra,
                palabras_cian_extra=config.palabras_cian_extra,
            )

            if proceso_ffmpeg.stdin:
                proceso_ffmpeg.stdin.write(lienzo.convert("RGB").tobytes())

    if proceso_ffmpeg.stdin:
        proceso_ffmpeg.stdin.close()
    proceso_ffmpeg.wait()

    print("=" * 78)
    print(f"[ÉXITO] Short generado y listo en: {ruta_mp4_final}")
    print("=" * 78)
    return ruta_mp4_final


# ==============================================================================
# 9. DESCARGA CON YT-DLP E INTERFAZ GRÁFICA COMPLETA (APLICACIÓN DE ESCRITORIO)
# ==============================================================================
def descargar_video_youtube(url: str) -> Path:
    """
    Descarga el video o Short de YouTube usando yt-dlp en formato MP4 compatible.
    """
    url_limpia = url.strip()
    if not url_limpia:
        raise ValueError("La URL del video de YouTube está vacía.")

    for existente in BASE_DIR.glob("video_input.*"):
        try:
            existente.unlink()
        except OSError:
            pass

    ejecutable_ytdlp = shutil.which("yt-dlp")
    if ejecutable_ytdlp:
        cmd_base = [ejecutable_ytdlp]
    else:
        cmd_base = [sys.executable, "-m", "yt_dlp"]

    cmd = [
        *cmd_base,
        "-S", "res,ext:mp4:m4a",
        "-o", "video_input.%(ext)s",
        url_limpia,
    ]

    print("=" * 78)
    print(f"[*] Descargando video de YouTube con yt-dlp: {url_limpia}")
    print("=" * 78)

    proc = subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout:
        for linea in proc.stdout:
            linea_s = linea.rstrip()
            if linea_s:
                print(f"[yt-dlp] {linea_s}")
    proc.wait()

    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp terminó con código {proc.returncode}. Verifica que el link de YouTube sea válido.")

    if DEFAULT_VIDEO_INPUT.exists():
        return DEFAULT_VIDEO_INPUT

    descargados = sorted(BASE_DIR.glob("video_input.*"))
    if descargados:
        return descargados[0]

    raise FileNotFoundError("No se encontró el archivo 'video_input.mp4' luego de la descarga.")


def iniciar_aplicacion_gui() -> None:
    import queue
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    root = tk.Tk()
    root.title("Editor Shorts Studio v1.0 - Automatización de Shorts con IA")
    root.geometry("980x810")
    root.minsize(840, 680)
    root.configure(bg="#11131a")

    cola_logs: "queue.Queue[str]" = queue.Queue()
    editando_lock = threading.Lock()
    ultimo_video_generado: List[Optional[Path]] = [None]

    BG_MAIN = "#11131a"
    BG_CARD = "#1a1e2b"
    BG_INPUT = "#0d1017"
    FG_TEXT = "#f3f4f6"
    FG_MUTED = "#9ca3af"
    ACCENT_YELLOW = "#facc15"
    ACCENT_GREEN = "#22c55e"
    ACCENT_BLUE = "#3b82f6"
    ACCENT_PURPLE = "#8b5cf6"

    # Encabezado Principal
    header_frame = tk.Frame(root, bg=BG_MAIN, padx=20, pady=12)
    header_frame.pack(fill=tk.X)

    lbl_titulo = tk.Label(
        header_frame,
        text="⚡ EDITOR SHORTS STUDIO",
        font=("Segoe UI", 18, "bold"),
        fg=ACCENT_YELLOW,
        bg=BG_MAIN,
    )
    lbl_titulo.pack(side=tk.LEFT)

    lbl_sub = tk.Label(
        header_frame,
        text="Voz IA + Subtítulos Luminosos Neón + Flechas y Círculos Rojos con Seguimiento de Objetivos",
        font=("Segoe UI", 10),
        fg=FG_MUTED,
        bg=BG_MAIN,
        padx=12,
    )
    lbl_sub.pack(side=tk.LEFT, pady=(6, 0))

    # 1. Tarjeta de Link de YouTube y Configuración Rápida
    url_card = tk.Frame(root, bg=BG_CARD, padx=16, pady=12, highlightthickness=1, highlightbackground="#2e3446")
    url_card.pack(fill=tk.X, padx=20, pady=(0, 10))

    lbl_url = tk.Label(
        url_card,
        text="1. Link del Video / Short de YouTube (o ruta a un archivo MP4 local):",
        font=("Segoe UI", 11, "bold"),
        fg=FG_TEXT,
        bg=BG_CARD,
    )
    lbl_url.pack(anchor="w", pady=(0, 6))

    url_row = tk.Frame(url_card, bg=BG_CARD)
    url_row.pack(fill=tk.X)

    entry_url = tk.Entry(
        url_row,
        font=("Consolas", 11),
        bg=BG_INPUT,
        fg="#ffffff",
        insertbackground="#ffffff",
        relief=tk.FLAT,
        highlightthickness=1,
        highlightbackground="#374151",
        highlightcolor=ACCENT_YELLOW,
    )
    entry_url.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=7, padx=(0, 8))

    def pegar_url() -> None:
        try:
            texto_clip = root.clipboard_get().strip()
            entry_url.delete(0, tk.END)
            entry_url.insert(0, texto_clip)
        except Exception:
            pass

    def elegir_mp4_local() -> None:
        ruta = filedialog.askopenfilename(
            title="Seleccionar Video MP4 Local",
            filetypes=[("Archivos de Video", "*.mp4 *.mkv *.mov *.webm"), ("Todos los archivos", "*.*")],
        )
        if ruta:
            entry_url.delete(0, tk.END)
            entry_url.insert(0, ruta)

    btn_archivo = tk.Button(
        url_row,
        text="📁 Elegir MP4 Local",
        command=elegir_mp4_local,
        font=("Segoe UI", 9, "bold"),
        bg="#2d3348",
        fg=FG_TEXT,
        activebackground="#3e4663",
        activeforeground="#ffffff",
        relief=tk.FLAT,
        padx=12,
        pady=6,
        cursor="hand2",
    )
    btn_archivo.pack(side=tk.RIGHT)

    btn_pegar_url = tk.Button(
        url_row,
        text="📋 Pegar Link",
        command=pegar_url,
        font=("Segoe UI", 9, "bold"),
        bg="#2d3348",
        fg=FG_TEXT,
        activebackground="#3e4663",
        activeforeground="#ffffff",
        relief=tk.FLAT,
        padx=12,
        pady=6,
        cursor="hand2",
    )
    btn_pegar_url.pack(side=tk.RIGHT, padx=(0, 6))

    # Fila de Opciones Rápidas (Voz y Encuadre)
    opts_row = tk.Frame(url_card, bg=BG_CARD)
    opts_row.pack(fill=tk.X, pady=(10, 0))

    tk.Label(
        opts_row,
        text="Voz Narrador IA:",
        font=("Segoe UI", 9, "bold"),
        fg=FG_MUTED,
        bg=BG_CARD,
    ).pack(side=tk.LEFT, padx=(0, 6))

    voz_var = tk.StringVar(value=list(VOCES_DISPONIBLES.keys())[0])
    combo_voz = ttk.Combobox(
        opts_row,
        textvariable=voz_var,
        values=list(VOCES_DISPONIBLES.keys()),
        state="readonly",
        width=36,
        font=("Segoe UI", 9),
    )
    combo_voz.pack(side=tk.LEFT, padx=(0, 20))

    tk.Label(
        opts_row,
        text="Encuadre 9:16:",
        font=("Segoe UI", 9, "bold"),
        fg=FG_MUTED,
        bg=BG_CARD,
    ).pack(side=tk.LEFT, padx=(0, 6))

    encuadre_map = {
        "Pantalla Completa Vertical (Crop 9:16)": "full",
        "Fondo Borroso para Horizontales (Blur 9:16)": "blur",
    }
    encuadre_var = tk.StringVar(value=list(encuadre_map.keys())[0])
    combo_encuadre = ttk.Combobox(
        opts_row,
        textvariable=encuadre_var,
        values=list(encuadre_map.keys()),
        state="readonly",
        width=36,
        font=("Segoe UI", 9),
    )
    combo_encuadre.pack(side=tk.LEFT)

    # 2. Tarjeta de Guion Estructurado
    guion_card = tk.Frame(root, bg=BG_CARD, padx=16, pady=12, highlightthickness=1, highlightbackground="#2e3446")
    guion_card.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

    guion_top_row = tk.Frame(guion_card, bg=BG_CARD)
    guion_top_row.pack(fill=tk.X, pady=(0, 4))

    lbl_guion = tk.Label(
        guion_top_row,
        text="2. Guión Estructurado del Short (Assets, Efectos, Flechas, Círculos y Narración):",
        font=("Segoe UI", 11, "bold"),
        fg=FG_TEXT,
        bg=BG_CARD,
    )
    lbl_guion.pack(side=tk.LEFT)

    def copiar_prompt_ia() -> None:
        try:
            if PROMPT_IA_PATH.exists():
                texto_prompt = PROMPT_IA_PATH.read_text(encoding="utf-8-sig")
            else:
                texto_prompt = PLANTILLA_GUION_DEFAULT

            link_actual = entry_url.get().strip()
            if not link_actual:
                try:
                    clip_previo = root.clipboard_get().strip()
                    if clip_previo.startswith(("http://", "https://")) and (
                        "youtube.com" in clip_previo.lower() or "youtu.be" in clip_previo.lower()
                    ):
                        link_actual = clip_previo
                        entry_url.delete(0, tk.END)
                        entry_url.insert(0, link_actual)
                except Exception:
                    pass

            if link_actual:
                patron_link = re.compile(r"^LINK DEL VIDEO A EDITAR\s*:.*$", re.IGNORECASE | re.MULTILINE)
                if patron_link.search(texto_prompt):
                    texto_prompt = patron_link.sub(f"LINK DEL VIDEO A EDITAR: {link_actual}", texto_prompt)
                else:
                    texto_prompt = f"LINK DEL VIDEO A EDITAR: {link_actual}\n\n" + texto_prompt

            root.clipboard_clear()
            root.clipboard_append(texto_prompt)
            root.update()

            if link_actual:
                messagebox.showinfo(
                    "Prompt + Link Copiado para Gemini",
                    f"¡Se copió el Prompt completo con tu link ya incluido!\n\n"
                    f"🔗 Link insertado:\n{link_actual}\n\n"
                    f"Ahora solo ve a Gemini, pega el texto directamente y te devolverá el guion exacto.",
                )
            else:
                messagebox.showinfo(
                    "Prompt para IA Copiado",
                    "¡Se copió el Prompt completo al portapapeles!\n\n"
                    "💡 Tip: Si primero pegas el link de YouTube en la caja 1 de arriba y luego tocas este botón, "
                    "el link se agregará automáticamente dentro del prompt para mandárselo directo a Gemini.",
                )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo copiar el prompt: {e}")

    def mostrar_guia_assets() -> None:
        ventana_guia = tk.Toplevel(root)
        ventana_guia.title("Guía de Formato de Guion, Efectos y Assets")
        ventana_guia.geometry("760x580")
        ventana_guia.configure(bg=BG_MAIN)
        txt_g = scrolledtext.ScrolledText(
            ventana_guia,
            font=("Consolas", 10),
            bg=BG_INPUT,
            fg="#e5e7eb",
            padx=14,
            pady=14,
            wrap=tk.WORD,
        )
        txt_g.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)
        contenido_guia = PROMPT_IA_PATH.read_text(encoding="utf-8-sig") if PROMPT_IA_PATH.exists() else PLANTILLA_GUION_DEFAULT
        txt_g.insert("1.0", contenido_guia)
        txt_g.configure(state=tk.DISABLED)

    txt_guion = scrolledtext.ScrolledText(
        guion_card,
        font=("Consolas", 10),
        bg=BG_INPUT,
        fg="#e5e7eb",
        insertbackground="#ffffff",
        relief=tk.FLAT,
        height=13,
        wrap=tk.WORD,
        highlightthickness=1,
        highlightbackground="#374151",
        highlightcolor=ACCENT_YELLOW,
        padx=10,
        pady=10,
    )

    if DEFAULT_GUION_TXT.exists():
        try:
            contenido_inicial = DEFAULT_GUION_TXT.read_text(encoding="utf-8-sig").strip()
        except Exception:
            contenido_inicial = PLANTILLA_GUION_DEFAULT.strip()
    else:
        contenido_inicial = PLANTILLA_GUION_DEFAULT.strip()
    txt_guion.insert("1.0", contenido_inicial)

    def restaurar_plantilla() -> None:
        txt_guion.delete("1.0", tk.END)
        txt_guion.insert("1.0", PLANTILLA_GUION_DEFAULT.strip())

    def pegar_guion() -> None:
        try:
            clip = root.clipboard_get().strip()
            if clip:
                txt_guion.delete("1.0", tk.END)
                txt_guion.insert("1.0", clip)
        except Exception:
            pass

    btn_guia = tk.Button(
        guion_top_row,
        text="📘 Guía de Assets",
        command=mostrar_guia_assets,
        font=("Segoe UI", 9, "bold"),
        bg="#2d3348",
        fg=FG_TEXT,
        activebackground="#3e4663",
        activeforeground="#ffffff",
        relief=tk.FLAT,
        padx=10,
        pady=4,
        cursor="hand2",
    )
    btn_guia.pack(side=tk.RIGHT, padx=(6, 0))

    btn_plantilla = tk.Button(
        guion_top_row,
        text="🔄 Cargar Ejemplo",
        command=restaurar_plantilla,
        font=("Segoe UI", 9),
        bg="#2d3348",
        fg=FG_TEXT,
        activebackground="#3e4663",
        activeforeground="#ffffff",
        relief=tk.FLAT,
        padx=10,
        pady=4,
        cursor="hand2",
    )
    btn_plantilla.pack(side=tk.RIGHT, padx=(6, 0))

    btn_pegar_guion = tk.Button(
        guion_top_row,
        text="📋 Pegar Guión",
        command=pegar_guion,
        font=("Segoe UI", 9, "bold"),
        bg="#2d3348",
        fg=FG_TEXT,
        activebackground="#3e4663",
        activeforeground="#ffffff",
        relief=tk.FLAT,
        padx=10,
        pady=4,
        cursor="hand2",
    )
    btn_pegar_guion.pack(side=tk.RIGHT, padx=(6, 0))

    btn_prompt_ia = tk.Button(
        guion_top_row,
        text="🤖 Copiar Prompt para IA",
        command=copiar_prompt_ia,
        font=("Segoe UI", 9, "bold"),
        bg=ACCENT_PURPLE,
        fg="#ffffff",
        activebackground="#7c3aed",
        activeforeground="#ffffff",
        relief=tk.FLAT,
        padx=12,
        pady=4,
        cursor="hand2",
    )
    btn_prompt_ia.pack(side=tk.RIGHT)

    lbl_formato_hint = tk.Label(
        guion_card,
        text="Formato de columnas:  TIEMPO  |  EFECTO  |  SFX  |  EMOJI  |  FLECHA  |  CIRCULO  |  TEXTO",
        font=("Consolas", 9, "bold"),
        fg="#38bdf8",
        bg=BG_CARD,
    )
    lbl_formato_hint.pack(anchor="w", pady=(2, 6))

    txt_guion.pack(fill=tk.BOTH, expand=True)

    # 3. Barra de Acción Principal (Botón EMPEZAR A EDITAR)
    acciones_frame = tk.Frame(root, bg=BG_MAIN, padx=20, pady=4)
    acciones_frame.pack(fill=tk.X)

    btn_editar = tk.Button(
        acciones_frame,
        text="🎬  EMPEZAR A EDITAR SHORT",
        font=("Segoe UI", 13, "bold"),
        bg=ACCENT_GREEN,
        fg="#052e16",
        activebackground="#16a34a",
        activeforeground="#ffffff",
        relief=tk.FLAT,
        padx=28,
        pady=10,
        cursor="hand2",
    )
    btn_editar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

    def reproducir_ultimo_short() -> None:
        ruta_rep = ultimo_video_generado[0]
        if ruta_rep is None or not ruta_rep.exists():
            mp4s = sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
            if mp4s:
                ruta_rep = mp4s[0]
        if ruta_rep and ruta_rep.exists():
            try:
                os.startfile(str(ruta_rep))
            except Exception:
                pass
        else:
            messagebox.showinfo("Sin videos", "Aún no hay videos generados en 'output_shorts'.")

    def abrir_carpeta_salida() -> None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(OUTPUT_DIR))
        except Exception:
            pass

    btn_carpeta = tk.Button(
        acciones_frame,
        text="📂 Abrir Carpeta Output",
        command=abrir_carpeta_salida,
        font=("Segoe UI", 10, "bold"),
        bg=ACCENT_BLUE,
        fg="#ffffff",
        activebackground="#2563eb",
        activeforeground="#ffffff",
        relief=tk.FLAT,
        padx=14,
        pady=10,
        cursor="hand2",
    )
    btn_carpeta.pack(side=tk.RIGHT)

    btn_reproducir = tk.Button(
        acciones_frame,
        text="▶️ Ver Último Short",
        command=reproducir_ultimo_short,
        font=("Segoe UI", 10, "bold"),
        bg="#334155",
        fg="#ffffff",
        activebackground="#475569",
        activeforeground="#ffffff",
        relief=tk.FLAT,
        padx=14,
        pady=10,
        cursor="hand2",
    )
    btn_reproducir.pack(side=tk.RIGHT, padx=(0, 8))

    # 4. Consola de Progreso en Vivo
    log_card = tk.Frame(root, bg=BG_CARD, padx=14, pady=8, highlightthickness=1, highlightbackground="#2e3446")
    log_card.pack(fill=tk.X, padx=20, pady=(6, 16))

    lbl_estado = tk.Label(
        log_card,
        text="Estado: Listo para editar",
        font=("Segoe UI", 9, "bold"),
        fg=ACCENT_YELLOW,
        bg=BG_CARD,
    )
    lbl_estado.pack(anchor="w", pady=(0, 4))

    txt_logs = scrolledtext.ScrolledText(
        log_card,
        font=("Consolas", 9),
        bg="#080a0f",
        fg="#a7f3d0",
        relief=tk.FLAT,
        height=7,
        state=tk.DISABLED,
    )
    txt_logs.pack(fill=tk.X)

    class RedireccionadorStdout:
        def __init__(self, q: "queue.Queue[str]"):
            self.q = q

        def write(self, texto: str) -> None:
            if texto:
                self.q.put(texto)

        def flush(self) -> None:
            pass

    def actualizar_consola() -> None:
        while not cola_logs.empty():
            msg = cola_logs.get_nowait()
            txt_logs.configure(state=tk.NORMAL)
            txt_logs.insert(tk.END, msg)
            txt_logs.see(tk.END)
            txt_logs.configure(state=tk.DISABLED)
        root.after(80, actualizar_consola)

    def ejecutar_flujo_edicion() -> None:
        if not editando_lock.acquire(blocking=False):
            return

        entrada_video = entry_url.get().strip().strip('"')
        texto_guion_actual = txt_guion.get("1.0", tk.END).strip()
        voz_elegida = VOCES_DISPONIBLES.get(voz_var.get(), EDGE_VOICE_DEFAULT)
        encuadre_elegido = encuadre_map.get(encuadre_var.get(), "full")

        if not texto_guion_actual:
            messagebox.showwarning("Guión vacío", "Por favor ingresa o pega un guión antes de empezar a editar.")
            editando_lock.release()
            return

        btn_editar.configure(
            state=tk.DISABLED,
            text="⏳ PROCESANDO VOZ IA, TRACKING Y SUBTÍTULOS...",
            bg="#4b5563",
            fg="#ffffff",
        )
        lbl_estado.configure(text="Estado: Procesando y renderizando Short... (No cierres la ventana)", fg=ACCENT_YELLOW)
        txt_logs.configure(state=tk.NORMAL)
        txt_logs.delete("1.0", tk.END)
        txt_logs.configure(state=tk.DISABLED)

        def tarea_background() -> None:
            stdout_orig = sys.stdout
            stderr_orig = sys.stderr
            sys.stdout = RedireccionadorStdout(cola_logs)
            sys.stderr = RedireccionadorStdout(cola_logs)
            try:
                DEFAULT_GUION_TXT.write_text(texto_guion_actual + "\n", encoding="utf-8")
                print(f"[*] Guión guardado en: {DEFAULT_GUION_TXT.name}")

                if entrada_video:
                    posible_local = Path(entrada_video)
                    if posible_local.exists() and posible_local.is_file():
                        print(f"[*] Usando archivo de video local: {posible_local}")
                        ruta_video_usar = posible_local
                    else:
                        ruta_video_usar = descargar_video_youtube(entrada_video)
                else:
                    if not DEFAULT_VIDEO_INPUT.exists():
                        raise FileNotFoundError(
                            "No ingresaste un link de YouTube ni seleccionaste un MP4 local, "
                            "y tampoco existe 'video_input.mp4' en la carpeta."
                        )
                    print(f"[*] Sin link nuevo: usando '{DEFAULT_VIDEO_INPUT.name}' existente en la carpeta.")
                    ruta_video_usar = DEFAULT_VIDEO_INPUT

                ruta_final = asyncio.run(
                    editar_video_con_guion(
                        ruta_video=ruta_video_usar,
                        ruta_guion=DEFAULT_GUION_TXT,
                        voz_override=voz_elegida,
                        modo_encuadre_override=encuadre_elegido,
                    )
                )
                ultimo_video_generado[0] = ruta_final

                def on_success() -> None:
                    lbl_estado.configure(
                        text=f"¡Listo! Short exportado en: output_shorts/{ruta_final.name}",
                        fg=ACCENT_GREEN,
                    )
                    btn_editar.configure(
                        state=tk.NORMAL,
                        text="🎬  EMPEZAR A EDITAR SHORT",
                        bg=ACCENT_GREEN,
                        fg="#052e16",
                    )
                    messagebox.showinfo(
                        "¡Short Terminado!",
                        f"El video Short se editó con éxito en:\n\n{ruta_final}",
                    )

                root.after(0, on_success)

            except Exception as exc:
                print(f"\n[ERROR] {exc}\n")

                def on_error(err_msg: str = str(exc)) -> None:
                    lbl_estado.configure(text=f"Error: {err_msg}", fg="#ef4444")
                    btn_editar.configure(
                        state=tk.NORMAL,
                        text="🎬  EMPEZAR A EDITAR SHORT",
                        bg=ACCENT_GREEN,
                        fg="#052e16",
                    )
                    messagebox.showerror("Error durante la edición", err_msg)

                root.after(0, on_error)
            finally:
                sys.stdout = stdout_orig
                sys.stderr = stderr_orig
                editando_lock.release()

        hilo = threading.Thread(target=tarea_background, daemon=True)
        hilo.start()

    btn_editar.configure(command=ejecutar_flujo_edicion)
    root.after(80, actualizar_consola)
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg1 = sys.argv[1].strip()
        guion_arg = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else DEFAULT_GUION_TXT
        if arg1.startswith("http://") or arg1.startswith("https://") or "youtube.com" in arg1 or "youtu.be" in arg1:
            video_descargado = descargar_video_youtube(arg1)
            asyncio.run(editar_video_con_guion(video_descargado, guion_arg))
        else:
            video_arg = Path(arg1).resolve()
            asyncio.run(editar_video_con_guion(video_arg, guion_arg))
    else:
        iniciar_aplicacion_gui()
