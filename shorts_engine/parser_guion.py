# -*- coding: utf-8 -*-
import re
import json
import unicodedata
from pathlib import Path
from typing import List, Optional, Set, Tuple
from .config import (
    DEFAULT_GUION_TXT, DEFAULT_VIDEO_INPUT,
    ConfigGuion, SegmentoVideoGuion, parsear_altura_subtitulos,
    MODO_ENCUADRE_DEFAULT, EDGE_VOICE_DEFAULT, VOCES_DISPONIBLES,
    VOLUMEN_AUDIO_VIDEO_ORIGINAL, VOLUMEN_MUSICA_FONDO,
    DURACION_CALLOUTS_DEFAULT
)

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


def _es_campo_altura(val: str) -> bool:
    v = str(val).strip().lower()
    if not v:
        return False
    if v in ("arriba", "medio", "centro", "abajo", "muy_abajo", "fondo", "auto", "default"):
        return True
    if re.match(r"^(y:)?\d{1,4}%?$", v):
        return True
    return False


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
    if not raw or raw.lower() in ("ninguno", "ninguna", "none", "no", "false", "-", "flecha", "circulo"):
        return None, "auto"

    if "+" in raw:
        return raw, "multi"

    posicion = "auto"
    if ":" in raw:
        raw, pos_part = raw.split(":", 1)
        pos_clean = _quitar_acentos(pos_part.strip().lower())
        posicion = pos_clean

    e = _quitar_acentos(raw.strip().lower())
    e = e.replace(".png", "").replace(".webp", "").replace(".jpg", "")
    if e.startswith("fijo:"):
        e = e[len("fijo:"):]
        posicion = f"fijo:{posicion}"
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
    Ejemplo: 'box:[450,560,590,720]@02.4:objeto' -> ('box:[...]', 'chico')
             'centro:grande' -> ('centro', 'grande')
             'izquierda'     -> ('izquierda', 'medio')
             'ninguno'       -> (None, 'medio')
    """
    if not obj_raw:
        return None, "medio"
    raw_str = str(obj_raw).strip()
    if "box:" in raw_str.lower() or "box:[" in raw_str.lower():
        from .config import parsear_directiva_circulo
        info_c = parsear_directiva_circulo(raw_str)
        if info_c.activo:
            return raw_str, info_c.tamanoPreset
        return None, "medio"

    raw = _quitar_acentos(raw_str.lower())
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
    tiene_col_altura = False
    for linea in contenido.splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith("#") or limpia.startswith("//"):
            continue
        if limpia.upper() in ("[GUION]", "[GUIÓN]", "[SCRIPT]", "[SEGMENTOS]"):
            en_guion = True
            continue

        if not en_guion:
            if ":" in limpia and "|" not in limpia:
                k, v = limpia.split(":", 1)
                k_up = _quitar_acentos(k.strip().upper())
                v_str = v.strip()
                if k_up in ("TITULO_SUPERIOR", "TITULO"):
                    config.titulo_superior = "" if v_str.lower() in ("ninguno", "none", "-", "vacio") else v_str
                elif k_up in ("TITULO_YOUTUBE", "YOUTUBE_TITULO"):
                    t_yt = v_str
                    tiene_emoji = any(ord(char) > 0x1F300 for char in t_yt)
                    if not tiene_emoji and t_yt:
                        if "#shorts" in t_yt.lower():
                            t_yt = re.sub(r"(?i)#shorts", "😱🔥 #shorts", t_yt).strip()
                        else:
                            t_yt = f"{t_yt} 😱🔥"
                    config.titulo_youtube = t_yt
                elif k_up in ("DESCRIPCION_YOUTUBE", "YOUTUBE_DESCRIPCION", "DESCRIPCION"):
                    config.descripcion_youtube = v_str
                elif k_up in ("ESTADO_PUBLICACION", "MODO_PUBLICACION", "PRIVACIDAD"):
                    config.estado_publicacion = v_str.lower()
                elif k_up in ("SCHEDULE", "PROGRAMAR", "PUBLICAR_EN"):
                    config.schedule = v_str
                elif k_up in ("PARA_NINOS", "KIDS", "MADE_FOR_KIDS", "ES_PARA_NINOS"):
                    v_clean = _quitar_acentos(v_str.lower())
                    config.para_ninos = v_clean in ("si", "true", "yes", "1", "kids")
                elif k_up in ("TAGS", "ETIQUETAS", "YOUTUBE_TAGS"):
                    config.tags_youtube = [t.strip().lstrip("#") for t in v_str.split(",") if t.strip()]
                elif k_up in ("MODO_ENCUADRE", "MODO_PANTALLA", "ENCUADRE"):
                    config.modo_encuadre = "blur" if "blur" in v_str.lower() or "borroso" in v_str.lower() else "full"
                elif k_up in ("VOZ", "VOZ_NARRADOR"):
                    for label_v, id_v in VOCES_DISPONIBLES.items():
                        if v_str.lower() in label_v.lower() or v_str.lower() == id_v.lower():
                            config.voz_narrador = id_v
                            break
                elif k_up in ("ARCHIVO_SALIDA", "SALIDA", "OUTPUT"):
                    config.archivo_salida = None if v_str.lower() in ("", "auto", "none", "-") else v_str
                elif k_up in ("TONO_VIDEO", "TONO", "MOOD", "EMOCION"):
                    config.tono_video = v_str.strip().lower()
                elif k_up in ("VOLUMEN_MUSICA", "VOLUMEN_FONDO", "VOLUMEN_BGM"):
                    try:
                        config.volumen_musica = float(v_str.replace(",", "."))
                    except ValueError:
                        pass
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
            if any("ALTURA" in p.upper() or "Y_TEXTO" in p.upper() for p in partes):
                tiene_col_altura = True
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
        altura_str = "70%"
        if len(partes) >= 8 and (tiene_col_altura or _es_campo_altura(partes[6])):
            # FORMATO DE 8 COLUMNAS (CON ALTURA DE SUBTÍTULOS):
            # TIEMPO | EFECTO | SFX | EMOJI | FLECHA | CIRCULO | ALTURA | TEXTO
            rango_t, efecto_str, sfx_str, emoji_str, flecha_str, circulo_str, altura_str = partes[:7]
            texto_voz = " | ".join(partes[7:]).strip()
            if "-" in rango_t and rango_t.lower() != "-":
                t1, t2 = rango_t.split("-", 1)
                t_ini = _parsear_tiempo_a_segundos(t1)
                t_fin = _parsear_tiempo_a_segundos(t2)
            efecto = _normalizar_efecto(efecto_str)
            sfx_lista = _normalizar_sfx_lista(sfx_str)
            emoji, pos_emoji = _normalizar_emoji(emoji_str)
            flecha, _ = _normalizar_objetivo(flecha_str)
            circulo, tam_circulo = _normalizar_objetivo(circulo_str)
            if circulo == "si" and not flecha:
                circulo = None
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

        y_sub_seg = parsear_altura_subtitulos(altura_str)
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
                    y_subtitulos=y_sub_seg,
                )
            )

    return config



