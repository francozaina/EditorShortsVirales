#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
SUBIDOR AUTOMÁTICO DE SHORTS A YOUTUBE (YouTube Data API v3)
================================================================================
Sube videos generados directamente a tu canal de YouTube de forma 100% segura
mediante OAuth 2.0 y la API oficial de Google.
================================================================================
"""

import os
import sys
import json
import time
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

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

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Scopes requeridos para subir videos
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output_shorts"
TOKEN_FILE = BASE_DIR / "token_youtube.json"
CUENTAS_DIR = BASE_DIR / "cuentas_youtube"
APIS_DIR = BASE_DIR / "apis_google"

CLIENT_SECRETS_CANDIDATES = [
    BASE_DIR / "client_secrets.json",
    BASE_DIR / "client_secrets.json.json",
    BASE_DIR / "client_secret.json",
    BASE_DIR / "credentials.json",
]


def listar_archivos_credenciales_pool() -> List[Path]:
    """
    Devuelve todos los archivos `client_secrets*.json` disponibles en el Pool
    (tanto el principal en `BASE_DIR` como los adicionales en `apis_google/*.json`),
    sin duplicar el mismo `client_id`. Cada proyecto de Google Cloud aporta 6 Shorts/día.
    """
    APIS_DIR.mkdir(parents=True, exist_ok=True)
    candidatos: List[Path] = []
    for p in CLIENT_SECRETS_CANDIDATES:
        if p.exists() and p.is_file():
            candidatos.append(p)
    for p in sorted(BASE_DIR.glob("client_secret*.json")):
        if p not in candidatos and p.is_file():
            candidatos.append(p)
    for p in sorted(APIS_DIR.glob("*.json")):
        if p not in candidatos and p.is_file():
            candidatos.append(p)

    unicos: List[Path] = []
    client_ids_vistos = set()
    for p in candidatos:
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            info = data.get("installed") or data.get("web") or {}
            cid = str(info.get("client_id") or p.resolve()).strip()
            if cid not in client_ids_vistos:
                client_ids_vistos.add(cid)
                unicos.append(p)
        except Exception:
            continue
    return unicos


def encontrar_archivo_credenciales() -> Optional[Path]:
    pool = listar_archivos_credenciales_pool()
    return pool[0] if pool else None


def obtener_client_id_corto(secret_path: Path) -> str:
    try:
        data = json.loads(secret_path.read_text(encoding="utf-8-sig"))
        info = data.get("installed") or data.get("web") or {}
        cid = str(info.get("client_id") or "").strip()
        if cid:
            return re.sub(r"[^a-zA-Z0-9_-]", "", cid[:18])
    except Exception:
        pass
    return re.sub(r"[^a-zA-Z0-9_-]", "", secret_path.stem[:18]) or "default"


def _sanitizar_id_cuenta(texto: str) -> str:
    limpio = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    limpio = re.sub(r"[^a-zA-Z0-9_-]+", "_", limpio).strip("_")
    return limpio[:40] or "Canal_YouTube"


def _descargar_avatar_circular(url_avatar: str, destino_png: Path) -> bool:
    if not url_avatar:
        return False
    try:
        import urllib.request
        from io import BytesIO
        from PIL import Image, ImageDraw

        req = urllib.request.Request(url_avatar, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            raw_bytes = r.read()
        img = Image.open(BytesIO(raw_bytes)).convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
        mask = Image.new("L", (64, 64), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, 63, 63), fill=255)
        out = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        out.paste(img, (0, 0), mask=mask)
        out.save(str(destino_png), "PNG")
        return True
    except Exception:
        return False


_CACHE_SUBSCRIBERS_CANAL: Dict[str, int] = {}


def obtener_subscribers_canal(cuenta_id: str = "principal") -> int:
    """Retorna la cantidad de suscriptores actuales del canal (de caché o índice)."""
    return int(_CACHE_SUBSCRIBERS_CANAL.get(str(cuenta_id), 0))


def obtener_todos_subscribers() -> Dict[str, int]:
    """Retorna mapa {cuenta_id: suscriptores} de todos los canales vinculados."""
    return dict(_CACHE_SUBSCRIBERS_CANAL)


def _guardar_suscriptores_en_indice(cid: str, sub_count: int) -> None:
    try:
        idx_p = CUENTAS_DIR / "indice_cuentas.json"
        if idx_p.exists() and sub_count > 0:
            raw_c = json.loads(idx_p.read_text(encoding="utf-8"))
            cambio = False
            for entry in raw_c:
                if str(entry.get("id")) == str(cid) and entry.get("subscribers") != sub_count:
                    entry["subscribers"] = sub_count
                    cambio = True
            if cambio:
                idx_p.write_text(json.dumps(raw_c, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def listar_cuentas_vinculadas() -> List[Dict[str, Any]]:
    """
    Lista todas las cuentas/canales de YouTube vinculados.
    Si existe el `token_youtube.json` clásico y aún no está en `cuentas_youtube/indice_cuentas.json`,
    lo migra automáticamente.
    Retorna lista de dicts: `[{'id': '...', 'nombre': '...', 'channel_id': '...', 'avatar_path': '...'}, ...]`.
    """
    CUENTAS_DIR.mkdir(parents=True, exist_ok=True)
    idx_file = CUENTAS_DIR / "indice_cuentas.json"
    cuentas: List[Dict[str, str]] = []
    if idx_file.exists():
        try:
            leido = json.loads(idx_file.read_text(encoding="utf-8"))
            if isinstance(leido, list):
                cuentas = [c for c in leido if isinstance(c, dict) and c.get("id")]
        except Exception:
            cuentas = []

    # Migrar token_youtube.json legacy si no hay cuentas registradas
    if not cuentas and TOKEN_FILE.exists():
        nombre_canal = "Canal Principal"
        ch_id = ""
        thumb_url = ""
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            yt = build("youtube", "v3", credentials=creds)
            resp = yt.channels().list(mine=True, part="snippet").execute()
            items = resp.get("items", [])
            if items:
                sn = items[0].get("snippet", {})
                nombre_canal = sn.get("title") or nombre_canal
                ch_id = items[0].get("id") or ""
                thumbs = sn.get("thumbnails") or {}
                thumb_url = (
                    (thumbs.get("default") or {}).get("url")
                    or (thumbs.get("medium") or {}).get("url")
                    or ""
                )
        except Exception:
            pass
        cid_slug = _sanitizar_id_cuenta(nombre_canal)
        dest_tok = CUENTAS_DIR / f"token_{cid_slug}_api0.json"
        avatar_file = CUENTAS_DIR / f"avatar_{cid_slug}.png"
        try:
            if not dest_tok.exists():
                dest_tok.write_text(TOKEN_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
        if thumb_url:
            _descargar_avatar_circular(thumb_url, avatar_file)
        cuentas.append(
            {
                "id": cid_slug,
                "nombre": nombre_canal,
                "channel_id": ch_id,
                "avatar_path": str(avatar_file) if avatar_file.exists() else "",
            }
        )
        try:
            idx_file.write_text(json.dumps(cuentas, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    # Si alguna cuenta existente no tiene avatar_path pero tiene token, intentar obtenerlo 1 vez sin bloquear si ya existe
    modificado = False
    for c in cuentas:
        cid_s = str(c.get("id") or "")
        av_p = Path(c["avatar_path"]) if c.get("avatar_path") else (CUENTAS_DIR / f"avatar_{cid_s}.png")
        if av_p.exists() and not c.get("avatar_path"):
            c["avatar_path"] = str(av_p)
            modificado = True
        elif not av_p.exists() and not c.get("avatar_intentado"):
            c["avatar_intentado"] = "1"
            modificado = True
            tok_c = CUENTAS_DIR / f"token_{cid_s}_api0.json"
            if not tok_c.exists() and TOKEN_FILE.exists():
                tok_c = TOKEN_FILE
            if tok_c.exists():
                try:
                    creds = Credentials.from_authorized_user_file(str(tok_c), SCOPES)
                    if creds and creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                    yt = build("youtube", "v3", credentials=creds)
                    resp = yt.channels().list(mine=True, part="snippet").execute()
                    items = resp.get("items", [])
                    if items:
                        sn = items[0].get("snippet", {})
                        if sn.get("title"):
                            c["nombre"] = sn["title"]
                        thumbs = sn.get("thumbnails") or {}
                        t_url = (thumbs.get("default") or {}).get("url") or (thumbs.get("medium") or {}).get("url") or ""
                        if t_url and _descargar_avatar_circular(t_url, av_p):
                            c["avatar_path"] = str(av_p)
                except Exception:
                    pass

    if modificado:
        try:
            idx_file.write_text(json.dumps(cuentas, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    for c in cuentas:
        cid_s = str(c.get("id") or "")
        try:
            subs_val = int(c.get("subscribers") or 0)
        except Exception:
            subs_val = 0
        c["subscribers"] = subs_val
        if subs_val > 0:
            _CACHE_SUBSCRIBERS_CANAL[cid_s] = subs_val

    return cuentas


def vincular_nueva_cuenta_interactivo(secret_path: Optional[Path] = None) -> Dict[str, str]:
    """
    Abre el navegador OAuth2 para vincular un nuevo canal/cuenta de YouTube,
    detecta su título real y foto de perfil, y lo guarda en `cuentas_youtube/indice_cuentas.json`.
    """
    CUENTAS_DIR.mkdir(parents=True, exist_ok=True)
    if secret_path is None:
        secret_path = encontrar_archivo_credenciales()
    if not secret_path or not secret_path.exists():
        raise FileNotFoundError("No se encontró 'client_secrets.json'. Agrega un proyecto API primero.")

    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
    creds = flow.run_local_server(port=0, prompt="select_account")
    yt = build("youtube", "v3", credentials=creds)
    resp = yt.channels().list(mine=True, part="snippet").execute()
    items = resp.get("items", [])
    thumb_url = ""
    if items:
        sn = items[0].get("snippet", {})
        nombre_canal = sn.get("title") or f"Cuenta YouTube {int(time.time()) % 1000}"
        ch_id = items[0].get("id") or ""
        thumbs = sn.get("thumbnails") or {}
        thumb_url = (thumbs.get("default") or {}).get("url") or (thumbs.get("medium") or {}).get("url") or ""
    else:
        nombre_canal = f"Cuenta YouTube {int(time.time()) % 1000}"
        ch_id = ""

    cid_slug = _sanitizar_id_cuenta(nombre_canal)
    api_tag = obtener_client_id_corto(secret_path)

    # Guardar token tanto para esta API específica como token base de la cuenta
    tok_api_file = CUENTAS_DIR / f"token_{cid_slug}_{api_tag}.json"
    tok_base_file = CUENTAS_DIR / f"token_{cid_slug}_api0.json"
    tok_json = creds.to_json()
    tok_api_file.write_text(tok_json, encoding="utf-8")
    tok_base_file.write_text(tok_json, encoding="utf-8")
    TOKEN_FILE.write_text(tok_json, encoding="utf-8")

    avatar_file = CUENTAS_DIR / f"avatar_{cid_slug}.png"
    if thumb_url:
        _descargar_avatar_circular(thumb_url, avatar_file)
    av_str = str(avatar_file) if avatar_file.exists() else ""

    cuentas = listar_cuentas_vinculadas()
    existente = False
    for c in cuentas:
        if (ch_id and c.get("channel_id") == ch_id) or c.get("id") == cid_slug:
            c["nombre"] = nombre_canal
            c["channel_id"] = ch_id
            c["id"] = cid_slug
            if av_str:
                c["avatar_path"] = av_str
            existente = True
            break
    if not existente:
        cuentas.append({"id": cid_slug, "nombre": nombre_canal, "channel_id": ch_id, "avatar_path": av_str})

    idx_file = CUENTAS_DIR / "indice_cuentas.json"
    idx_file.write_text(json.dumps(cuentas, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"id": cid_slug, "nombre": nombre_canal, "channel_id": ch_id, "avatar_path": av_str}


def desvincular_cuenta(cuenta_id: str) -> bool:
    """
    Elimina una cuenta vinculada de 'indice_cuentas.json' y borra sus archivos de token asociados.
    """
    if not cuenta_id:
        return False
    cid_s = _sanitizar_id_cuenta(str(cuenta_id).strip())
    CUENTAS_DIR.mkdir(parents=True, exist_ok=True)
    idx_file = CUENTAS_DIR / "indice_cuentas.json"
    eliminado = False
    if idx_file.exists():
        try:
            cuentas = json.loads(idx_file.read_text(encoding="utf-8"))
            if isinstance(cuentas, list):
                nuevas = []
                for c in cuentas:
                    if str(c.get("id")) == cid_s or str(c.get("id")) == str(cuenta_id) or str(c.get("channel_id")) == str(cuenta_id):
                        eliminado = True
                    else:
                        nuevas.append(c)
                if eliminado:
                    idx_file.write_text(json.dumps(nuevas, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    # Eliminar tokens asociados a esta cuenta
    candidatos_del = list(CUENTAS_DIR.glob(f"token_{cid_s}_*.json"))
    if cid_s != str(cuenta_id):
        candidatos_del.extend(list(CUENTAS_DIR.glob(f"token_{cuenta_id}_*.json")))
    for tok_file in candidatos_del:
        try:
            if tok_file.exists():
                tok_file.unlink()
        except Exception:
            pass

    # Eliminar avatar si existe
    for av_f in [CUENTAS_DIR / f"avatar_{cid_s}.png", CUENTAS_DIR / f"avatar_{cuenta_id}.png"]:
        try:
            if av_f.exists():
                av_f.unlink()
        except Exception:
            pass

    # Limpiar caché de suscriptores
    _CACHE_SUBSCRIBERS_CANAL.pop(cid_s, None)
    _CACHE_SUBSCRIBERS_CANAL.pop(str(cuenta_id), None)
    return eliminado


def mostrar_guia_configuracion() -> None:
    print("=" * 80)
    print("CONFIGURACION DE YOUTUBE DATA API v3 (Solo se hace 1 vez)")
    print("=" * 80)
    print("Para que este script pueda subir tus videos a YouTube automáticamente:")
    print()
    print("1. Entra a Google Cloud Console con la cuenta de tu canal:")
    print("   -> https://console.cloud.google.com/")
    print()
    print("2. Crea un proyecto nuevo (ej. 'Shorts Uploader').")
    print()
    print("3. En el menú lateral ve a 'APIs y servicios' > 'Biblioteca':")
    print("   - Busca 'YouTube Data API v3' y haz clic en 'Habilitar'.")
    print()
    print("4. Ve a 'APIs y servicios' > 'Pantalla de consentimiento OAuth':")
    print("   - Elige 'Externo' y dale a 'Crear'.")
    print("   - Completa el nombre de la app (ej. 'Mi Editor Shorts') y tu correo.")
    print("   - En 'Usuarios de prueba' (Test users), AGREGA TU PROPIO CORREO de Google.")
    print("   - Guarda los cambios.")
    print()
    print("5. Ve a 'APIs y servicios' > 'Credenciales':")
    print("   - Clic en '+ CREAR CREDENCIALES' > 'ID de cliente de OAuth'.")
    print("   - Tipo de aplicación: 'App de escritorio' (Desktop application).")
    print("   - Nombre: 'Editor Shorts PC'.")
    print("   - Haz clic en 'Crear'.")
    print()
    print("6. Descarga el archivo JSON generado, renómbralo a:")
    print(f"   -> client_secrets.json")
    print(f"   y pégalo en esta carpeta: {BASE_DIR}")
    print()
    print("=" * 80)


def obtener_servicio_youtube(
    cuenta_id: Optional[str] = None,
    secret_path_override: Optional[Path] = None,
) -> Any:
    """
    Obtiene el cliente autenticado de YouTube Data API v3 para la `cuenta_id` elegida
    y el proyecto API (`secret_path_override`) indicado.
    """
    CUENTAS_DIR.mkdir(parents=True, exist_ok=True)
    secret_path = secret_path_override or encontrar_archivo_credenciales()
    api_tag = obtener_client_id_corto(secret_path) if secret_path else "api0"

    # Resolver qué archivo de token corresponde a la cuenta + API seleccionada
    candidatos_token: List[Path] = []
    if cuenta_id and cuenta_id.strip():
        cid = _sanitizar_id_cuenta(cuenta_id.strip())
        candidatos_token.append(CUENTAS_DIR / f"token_{cid}_{api_tag}.json")
        if secret_path_override is None:
            candidatos_token.append(CUENTAS_DIR / f"token_{cid}_api0.json")
        for f_extra in sorted(CUENTAS_DIR.glob(f"token_{cid}_*.json")):
            if f_extra not in candidatos_token:
                candidatos_token.append(f_extra)
    else:
        cuentas = listar_cuentas_vinculadas()
        if cuentas:
            cid0 = cuentas[0]["id"]
            candidatos_token.append(CUENTAS_DIR / f"token_{cid0}_{api_tag}.json")
            if secret_path_override is None:
                candidatos_token.append(CUENTAS_DIR / f"token_{cid0}_api0.json")
        if secret_path_override is None:
            candidatos_token.append(TOKEN_FILE)

    creds: Optional[Credentials] = None
    token_cargado: Optional[Path] = None
    for t_cand in candidatos_token:
        if t_cand.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(t_cand), SCOPES)
                token_cargado = t_cand
                break
            except Exception:
                creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds:
            if not secret_path or not secret_path.exists():
                mostrar_guia_configuracion()
                raise FileNotFoundError(
                    "No se encontró 'client_secrets.json' en la carpeta. "
                    "Sigue los pasos mostrados arriba para descargarlo desde Google Cloud Console."
                )

            print("[*] Abriendo ventana de autorización en tu navegador web...")
            print("    (Selecciona tu cuenta/canal de YouTube y dale en 'Continuar' / 'Permitir')")
            flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
            creds = flow.run_local_server(port=0, prompt="select_account")

        # Guardar token en la ruta específica de esta cuenta + proyecto API
        destino_guardar = candidatos_token[0] if candidatos_token else TOKEN_FILE
        with open(destino_guardar, "w", encoding="utf-8") as token_out:
            token_out.write(creds.to_json())
        if token_cargado and token_cargado != destino_guardar:
            try:
                token_cargado.write_text(creds.to_json(), encoding="utf-8")
            except Exception:
                pass
        if secret_path_override is None:
            try:
                TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
            except Exception:
                pass

    return build("youtube", "v3", credentials=creds)


def encontrar_ultimo_video() -> Optional[Path]:
    if not OUTPUT_DIR.exists():
        return None
    videos = sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    return videos[0] if videos else None


def _quitar_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def parsear_schedule_fecha(texto: Optional[str]) -> Optional[str]:
    """
    Parsea una fecha/hora de publicación y la convierte al formato ISO 8601 UTC ('YYYY-MM-DDTHH:MM:SSZ')
    requerido por YouTube Data API v3.
    Soporta:
    - ISO 8601: '2026-10-28T13:00:00Z', '2026-10-28 13:00:00'
    - Relativos en español/inglés: 'manana 10:00', 'mañana a las 10:00', 'tomorrow 10:00', 'hoy 18:00', '10:00'
    """
    if not texto:
        return None
    t = _quitar_acentos(str(texto).strip().lower())
    if t in ("", "auto", "no", "none", "null", "ninguno", "ninguna", "privado", "publico"):
        return None

    # Formato ISO 8601 directo
    iso_match = re.match(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?$", texto.strip(), re.IGNORECASE)
    if iso_match:
        try:
            cand = texto.strip().replace(" ", "T")
            if cand.endswith("Z"):
                dt = datetime.fromisoformat(cand.replace("Z", "+00:00"))
                return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            elif "+" in cand or ("-" in cand[10:]):
                dt = datetime.fromisoformat(cand)
                return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                # Sin zona horaria especificada -> se asume hora local del usuario
                dt_local = datetime.fromisoformat(cand).astimezone()
                return dt_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass

    # Expresiones relativas en lenguaje natural (ej: "manana 10:00", "hoy 18:00", "10:00")
    ahora_local = datetime.now().astimezone()
    hora_match = re.search(r"(\d{1,2}):(\d{2})", t)
    if hora_match:
        hora = int(hora_match.group(1))
        minuto = int(hora_match.group(2))

        dias_sumar = 0
        if "manana" in t or "tomorrow" in t:
            dias_sumar = 1
        elif "hoy" in t or "today" in t:
            dias_sumar = 0
        else:
            # Si solo se indicó la hora y ya pasó hoy, se programa para mañana
            if ahora_local.hour > hora or (ahora_local.hour == hora and ahora_local.minute >= minuto):
                dias_sumar = 1

        target_local = ahora_local.replace(hour=hora, minute=minuto, second=0, microsecond=0) + timedelta(days=dias_sumar)
        target_utc = target_local.astimezone(timezone.utc)
        return target_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    return None


def extraer_metadatos_guion(ruta_guion: Optional[Path] = None) -> Dict[str, Any]:
    """
    Extrae los metadatos de YouTube definidos en el encabezado del guion:
    TITULO_YOUTUBE, DESCRIPCION_YOUTUBE, ESTADO_PUBLICACION, SCHEDULE, PARA_NINOS, TAGS.
    """
    if ruta_guion is None:
        ruta_guion = BASE_DIR / "guion_video.txt"

    res: Dict[str, Any] = {
        "titulo_youtube": None,
        "descripcion_youtube": None,
        "estado_publicacion": "private",
        "schedule": None,
        "para_ninos": False,
        "tags": [],
    }

    if not ruta_guion.exists():
        return res

    try:
        contenido = ruta_guion.read_text(encoding="utf-8-sig")
    except Exception:
        return res

    en_guion = False
    for linea in contenido.splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith(("#", "//")):
            continue
        if limpia.upper() in ("[GUION]", "[GUIÓN]", "[SCRIPT]", "[SEGMENTOS]"):
            en_guion = True
            continue
        if en_guion:
            continue

        if ":" in limpia and "|" not in limpia:
            k, v = limpia.split(":", 1)
            k_clean = _quitar_acentos(k.strip().upper())
            v_val = v.strip()

            if k_clean in ("TITULO_YOUTUBE", "YOUTUBE_TITULO"):
                if v_val and v_val.lower() not in ("auto", "none", "ninguno", "-"):
                    res["titulo_youtube"] = v_val
            elif k_clean in ("TITULO_SUPERIOR", "TITULO") and not res["titulo_youtube"]:
                if v_val and v_val.lower() not in ("auto", "none", "ninguno", "-"):
                    res["titulo_youtube"] = f"¡{v_val}! #shorts"
            elif k_clean in ("DESCRIPCION_YOUTUBE", "YOUTUBE_DESCRIPCION", "DESCRIPCION"):
                if v_val and v_val.lower() not in ("auto", "none", "ninguno", "-"):
                    res["descripcion_youtube"] = v_val
            elif k_clean in ("ESTADO_PUBLICACION", "MODO_PUBLICACION", "PRIVACIDAD"):
                v_low = v_val.lower()
                if "public" in v_low:
                    res["estado_publicacion"] = "public"
                elif "unlisted" in v_low or "oculto" in v_low:
                    res["estado_publicacion"] = "unlisted"
                elif "private" in v_low or "privado" in v_low:
                    res["estado_publicacion"] = "private"
            elif k_clean in ("SCHEDULE", "PROGRAMAR", "PUBLICAR_EN"):
                res["schedule"] = parsear_schedule_fecha(v_val)
            elif k_clean in ("PARA_NINOS", "KIDS", "MADE_FOR_KIDS", "ES_PARA_NINOS"):
                v_clean = _quitar_acentos(v_val.lower())
                res["para_ninos"] = v_clean in ("si", "true", "yes", "1", "kids")
            elif k_clean in ("TAGS", "ETIQUETAS", "YOUTUBE_TAGS"):
                res["tags"] = [t.strip().lstrip("#") for t in v_val.split(",") if t.strip()]

    return res


def subir_video(
    ruta_video: Path,
    titulo: Optional[str] = None,
    descripcion: Optional[str] = None,
    tags: Optional[List[str]] = None,
    privacidad: Optional[str] = None,
    publish_at: Optional[str] = None,
    para_ninos: Optional[bool] = None,
    estado_privacidad: Optional[str] = None,
    ruta_guion: Optional[Path] = None,
    cuenta_id: Optional[str] = None,
    callback_cancelar: Optional[Callable[[], bool]] = None,
) -> str:
    """
    Sube el archivo de video especificado a YouTube con metadatos completos.
    - Soporta elegir a qué cuenta vinculada subir (`cuenta_id`).
    - Soporta el Pool de Proyectos API (`listar_archivos_credenciales_pool()`): si el
      Proyecto #1 agotó su cuota de 6 Shorts/día (`quotaExceeded`), salta automáticamente
      al Proyecto #2, #3, etc., permitiendo subir 12, 18, 24+ Shorts por día.
    """
    if not ruta_video.exists():
        raise FileNotFoundError(f"No existe el archivo de video: {ruta_video}")

    # Garantizar que el video sea estrictamente vertical 9:16 y <=59.9s para que YouTube lo clasifique como Short
    try:
        from shorts_engine.video_render import asegurar_formato_short
        ruta_video = asegurar_formato_short(ruta_video)
    except Exception as e_short_fmt:
        print(f"[!] Aviso al asegurar formato short: {e_short_fmt}")

    # Si faltan metadatos, extraerlos automáticamente de guion_video.txt
    meta = extraer_metadatos_guion(ruta_guion)

    nombre_limpio = ruta_video.stem.replace("_", " ").strip()

    titulo_final = (titulo or meta.get("titulo_youtube") or f"¡{nombre_limpio}! #shorts").strip()
    if "#shorts" not in titulo_final.lower():
        if len(titulo_final) <= 91:
            titulo_final = f"{titulo_final} #shorts"
        else:
            titulo_final = f"{titulo_final[:91].strip()} #shorts"

    descripcion_final = (descripcion or meta.get("descripcion_youtube") or (
        f"¡Mira lo que ocurrió en este video! ¿Qué hubieras hecho tú? Déjamelo en los comentarios:\n\n"
        f"Suscríbete para más momentos virales diarios.\n\n"
        f"#shorts #viral #humor #comedia #shortsfeed"
    )).strip()
    if "#shorts" not in descripcion_final.lower():
        descripcion_final = f"{descripcion_final}\n\n#shorts"

    tags_final = tags or meta.get("tags") or ["shorts", "humor", "viral", "comedia", "bromas"]

    # Schedule: Si se pasa texto amigable o ISO, normalizarlo. Si se indica explícitamente sin schedule ("no", "sin schedule", etc.), omitir
    if publish_at is not None and str(publish_at).strip().lower() in ("", "no", "none", "null", "ninguno", "ninguna", "sin schedule", "directo", "privado"):
        publish_at_final = None
    else:
        publish_at_final = parsear_schedule_fecha(publish_at) or meta.get("schedule")

    # Declaración para niños: Por defecto False (audiencia general / comentarios y monetización activa)
    kids_final = para_ninos if para_ninos is not None else meta.get("para_ninos", False)

    # Privacidad base
    if estado_privacidad:
        priv_base = estado_privacidad
    elif privacidad:
        priv_base = privacidad
    else:
        priv_base = meta.get("estado_publicacion", "private")

    # Si se programa para fecha futura, YouTube exige que privacyStatus sea 'private'
    status_priv = "private" if publish_at_final else priv_base

    cuerpo = {
        "snippet": {
            "title": titulo_final[:100],  # Máximo 100 caracteres permitido por YouTube
            "description": descripcion_final[:5000],
            "tags": tags_final,
            "categoryId": "23",  # 23 = Comedy / Comedia
        },
        "status": {
            "privacyStatus": status_priv,
            "selfDeclaredMadeForKids": bool(kids_final),
        },
    }

    if publish_at_final:
        # Validar si publish_at_final quedó en el pasado (por ej. si la app quedó abierta muchas horas)
        try:
            dt_pub = datetime.fromisoformat(publish_at_final.replace("Z", "+00:00"))
            ahora_utc = datetime.now(timezone.utc)
            # YouTube requiere al menos 10 minutos en el futuro para programar
            if dt_pub <= ahora_utc + timedelta(minutes=10):
                dias_sumar = 1
                while dt_pub + timedelta(days=dias_sumar) <= ahora_utc + timedelta(minutes=10):
                    dias_sumar += 1
                dt_nueva = dt_pub + timedelta(days=dias_sumar)
                publish_at_final = dt_nueva.strftime("%Y-%m-%dT%H:%M:%SZ")
                print(f"[!] AVISO: El horario de programación ({dt_pub.strftime('%Y-%m-%d %H:%M')} UTC) ya había pasado o estaba muy cerca. Se reprogramó automáticamente a horario futuro: {publish_at_final}")
        except Exception:
            pass
        cuerpo["status"]["publishAt"] = publish_at_final

    tam_mb = ruta_video.stat().st_size / (1024 * 1024)
    print("=" * 80)
    print(f"SUBIENDO VIDEO A YOUTUBE:")
    print(f"   Archivo:    {ruta_video.name} ({tam_mb:.2f} MB)")
    print(f"   Título:     {titulo_final}")
    print(f"   Para Niños: {'SÍ (Contenido para niños)' if kids_final else 'NO (Audiencia general / Monetización y comentarios activos)'}")
    if publish_at_final:
        print(f"   Estado:     PROGRAMADO (Schedule)")
        print(f"   Publica en: {publish_at_final} (UTC)")
    else:
        print(f"   Estado:     {status_priv.upper()} (Sin programar)")
    print("=" * 80)

    pool_secrets = listar_archivos_credenciales_pool()
    if not pool_secrets:
        pool_secrets = [None]  # type: ignore[list-item]

    ultimo_error_subida: Optional[Exception] = None
    respuesta = None

    if callback_cancelar and callback_cancelar():
        raise InterruptedError("Subida cancelada por el usuario antes de iniciar el envío.")

    for idx_api, secret_cand in enumerate(pool_secrets):
        try:
            if len(pool_secrets) > 1 and secret_cand is not None:
                print(f"[*] Usando Proyecto API #{idx_api + 1}/{len(pool_secrets)} ({secret_cand.name})...")
            youtube = obtener_servicio_youtube(cuenta_id=cuenta_id, secret_path_override=secret_cand)

            media = MediaFileUpload(
                str(ruta_video),
                mimetype="video/mp4",
                chunksize=5 * 1024 * 1024,
                resumable=True,
            )

            request = youtube.videos().insert(
                part="snippet,status",
                body=cuerpo,
                media_body=media,
            )

            respuesta = None
            ultimo_progreso = -1
            while respuesta is None:
                if callback_cancelar and callback_cancelar():
                    raise InterruptedError("Subida cancelada por el usuario durante el envío.")
                estado, respuesta = request.next_chunk()
                if estado:
                    progreso = int(estado.progress() * 100)
                    if progreso != ultimo_progreso:
                        barra = "█" * (progreso // 5) + "-" * (20 - (progreso // 5))
                        print(f"[*] Progreso de subida: [{barra}] {progreso}%", end="\r", flush=True)
                        ultimo_progreso = progreso
            if respuesta is not None:
                break
        except HttpError as err_http:
            ultimo_error_subida = err_http
            err_txt = str(err_http)
            if ("quotaExceeded" in err_txt or "dailyLimitExceeded" in err_txt or err_http.resp.status in (403, 429)) and idx_api < len(pool_secrets) - 1:
                print(f"\n[!] Proyecto API #{idx_api + 1} alcanzó el límite diario de 6 Shorts. Saltando automáticamente al Proyecto API #{idx_api + 2}...")
                continue
            raise
        except Exception as err_gen:
            ultimo_error_subida = err_gen
            if idx_api < len(pool_secrets) - 1:
                print(f"\n[!] Fallo en Proyecto API #{idx_api + 1} ({err_gen}). Probando siguiente Proyecto API...")
                continue
            raise

    if respuesta is None:
        raise RuntimeError(f"No se pudo completar la subida con ningún proyecto API del Pool: {ultimo_error_subida}")

    print("\n[+] ¡Subida completada con éxito!")
    video_id = respuesta.get("id")
    url_short = f"https://youtube.com/shorts/{video_id}"
    url_normal = f"https://youtu.be/{video_id}"

    # Subir automáticamente la portada de alto impacto como miniatura oficial
    dir_salida = Path(__file__).resolve().parent / "output_shorts"
    candidatos_portada = [
        ruta_video.parent / f"portada_{ruta_video.stem}.jpg",
        ruta_video.parent / f"portada_{ruta_video.stem}.png",
        dir_salida / f"portada_{ruta_video.stem}.jpg",
    ]
    for p_cand in candidatos_portada:
        if p_cand.exists():
            try:
                print(f"[*] Vinculando miniatura oficial a YouTube ({p_cand.name})...")
                media_thumb = MediaFileUpload(str(p_cand), mimetype="image/jpeg")
                youtube.thumbnails().set(videoId=video_id, media_body=media_thumb).execute()
                print(f"[+] ¡Miniatura de portada vinculada exitosamente a tu video en YouTube!")
                break
            except Exception as e_th:
                # Si el canal requiere verificación por SMS para miniaturas personalizadas, no rompe la subida
                print(f"[*] Nota miniatura en YouTube: {e_th}")
                break

    print("=" * 80)
    print(f"TU SHORT YA ESTÁ EN YOUTUBE:")
    print(f"   -> Link Short: {url_short}")
    print(f"   -> Link Video: {url_normal}")
    print("=" * 80)
    return video_id


def actualizar_video_existente(
    video_id: str,
    titulo: Optional[str] = None,
    descripcion: Optional[str] = None,
    tags: Optional[List[str]] = None,
    privacidad: Optional[str] = None,
    publish_at: Optional[str] = None,
    para_ninos: Optional[bool] = None,
    ruta_guion: Optional[Path] = None,
) -> None:
    """
    Actualiza título, descripción, schedule, privacidad y audiencia para niños
    de un video que ya se encuentra subido en el canal de YouTube.
    """
    youtube = obtener_servicio_youtube()
    meta = extraer_metadatos_guion(ruta_guion)

    titulo_final = titulo or meta.get("titulo_youtube")
    desc_final = descripcion or meta.get("descripcion_youtube")
    tags_final = tags or meta.get("tags")
    pub_final = parsear_schedule_fecha(publish_at) or meta.get("schedule")
    kids_final = para_ninos if para_ninos is not None else meta.get("para_ninos", False)
    priv_final = privacidad or meta.get("estado_publicacion", "private")

    print("=" * 80)
    print(f"ACTUALIZANDO METADATOS EN YOUTUBE (Video ID: {video_id}):")
    if titulo_final:
        print(f"   Título:     {titulo_final}")
    print(f"   Para Niños: {'SÍ (Kids)' if kids_final else 'NO (Audiencia general)'}")
    if pub_final:
        print(f"   Schedule:   PROGRAMADO ({pub_final} UTC)")
    else:
        print(f"   Privacidad: {priv_final.upper()}")
    print("=" * 80)

    resp = youtube.videos().list(part="snippet,status", id=video_id).execute()
    items = resp.get("items", [])
    if not items:
        raise ValueError(f"No se encontró ningún video con ID '{video_id}' en tu canal.")

    video = items[0]
    snippet = video["snippet"]
    status = video["status"]

    if titulo_final:
        snippet["title"] = titulo_final[:100]
    if desc_final:
        snippet["description"] = desc_final[:5000]
    if tags_final:
        snippet["tags"] = tags_final

    status["selfDeclaredMadeForKids"] = bool(kids_final)
    if pub_final:
        status["privacyStatus"] = "private"
        status["publishAt"] = pub_final
    elif priv_final:
        status["privacyStatus"] = priv_final

    cuerpo = {
        "id": video_id,
        "snippet": snippet,
        "status": status,
    }

    try:
        youtube.videos().update(part="snippet,status", body=cuerpo).execute()
        print(f"[+] ¡Video {video_id} actualizado exitosamente en YouTube!")
        print(f"-> Link: https://youtube.com/shorts/{video_id}")
    except HttpError as err:
        print(f"[!] Error al actualizar video en YouTube: {err}")
        raise


def verificar_canal_youtube() -> None:
    print("[*] Conectando con la API de YouTube...")
    youtube = obtener_servicio_youtube()
    try:
        resp = youtube.channels().list(mine=True, part="snippet").execute()
        items = resp.get("items", [])
        if items:
            canal = items[0]["snippet"]["title"]
            print("=" * 80)
            print(f"[+] ¡CONEXIÓN EXITOSA! Canal vinculado: {canal}")
            print("=" * 80)
            print("Tu token de sesión quedó guardado. A partir de ahora, cada vez que")
            print("generes un video nuevo, puedes publicarlo con 'Subir_Short_YouTube.bat'.")
        else:
            print("[+] Conectado a la API de YouTube correctamente.")
    except Exception as e:
        print(f"[!] Error al consultar información del canal: {e}")


def obtener_shorts_programados() -> List[Dict[str, Any]]:
    """
    Consulta en la API de YouTube todos los Shorts programados (con status.publishAt en el futuro)
    en todas las cuentas vinculadas. Devuelve una lista ordenada por fecha de publicación.
    """
    import datetime as _dt
    cuentas = listar_cuentas_vinculadas()
    if not cuentas:
        cuentas = [{"id": "principal", "nombre": "Canal Principal"}]

    tz_local = _dt.datetime.now().astimezone().tzinfo
    now_utc = _dt.datetime.now(_dt.timezone.utc)
    todos: List[Dict[str, Any]] = []

    for c in cuentas:
        cid = str(c.get("id") or "principal")
        cname = str(c.get("nombre") or cid)
        try:
            yt = obtener_servicio_youtube(cuenta_id=cid)
            ch_resp = yt.channels().list(mine=True, part="contentDetails,snippet,statistics").execute()
            items_ch = ch_resp.get("items", [])
            if not items_ch:
                continue
            sub_count = int(items_ch[0].get("statistics", {}).get("subscriberCount") or 0)
            if sub_count > 0:
                _CACHE_SUBSCRIBERS_CANAL[cid] = sub_count
                _guardar_suscriptores_en_indice(cid, sub_count)

            uploads_id = items_ch[0]["contentDetails"]["relatedPlaylists"]["uploads"]
            pl_resp = yt.playlistItems().list(
                playlistId=uploads_id,
                part="snippet,contentDetails",
                maxResults=40,
            ).execute()
            vids = [
                it["contentDetails"]["videoId"]
                for it in pl_resp.get("items", [])
                if it.get("contentDetails", {}).get("videoId")
            ]
            if not vids:
                continue
            for i_b in range(0, len(vids), 50):
                sub_vids = vids[i_b : i_b + 50]
                v_resp = yt.videos().list(
                    id=",".join(sub_vids),
                    part="snippet,status",
                ).execute()
                for it in v_resp.get("items", []):
                    st = it.get("status", {})
                    pub_str = st.get("publishAt")
                    if not pub_str:
                        continue
                    try:
                        dt_utc = _dt.datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                    except Exception:
                        continue
                    if dt_utc < now_utc:
                        continue
                    dt_local = dt_utc.astimezone(tz_local)
                    vid_id = str(it.get("id") or "")
                    tit = str(it.get("snippet", {}).get("title") or "Short sin título")
                    todos.append({
                        "id": vid_id,
                        "titulo": tit,
                        "cuenta_id": cid,
                        "cuenta_nombre": cname,
                        "subscribers": sub_count,
                        "dt_utc": dt_utc,
                        "dt_local": dt_local,
                        "fecha_dia": dt_local.strftime("%Y-%m-%d"),
                        "hora_local": dt_local.strftime("%H:%M"),
                        "url": f"https://youtube.com/shorts/{vid_id}",
                    })
        except Exception as e_ch:
            print(f"[!] No se pudieron leer programados de '{cname}': {e_ch}")
            continue

    todos.sort(key=lambda x: x["dt_utc"])
    return todos


def obtener_metricas_ultimos_videos(limite_por_cuenta: int = 20, total_max: int = 30) -> List[Dict[str, Any]]:
    """
    Consulta en la API de YouTube los videos más recientes ya subidos/publicados
    en todas las cuentas vinculadas, obteniendo sus métricas reales:
    - Título
    - Vistas (viewCount)
    - Likes (likeCount)
    - Comentarios (commentCount)
    - Porcentaje de Engagement ((likes + comments) / views * 100)
    - Fecha y hora de publicación
    - Link directo al Short/Video
    Devuelve la lista ordenada por fecha de publicación descendente (los más recientes primero).
    """
    import datetime as _dt
    cuentas = listar_cuentas_vinculadas()
    if not cuentas:
        cuentas = [{"id": "principal", "nombre": "Canal Principal"}]

    tz_local = _dt.datetime.now().astimezone().tzinfo
    now_utc = _dt.datetime.now(_dt.timezone.utc)
    todos_publicados: List[Dict[str, Any]] = []

    for c in cuentas:
        cid = str(c.get("id") or "principal")
        cname = str(c.get("nombre") or cid)
        try:
            yt = obtener_servicio_youtube(cuenta_id=cid)
            ch_resp = yt.channels().list(mine=True, part="contentDetails,snippet,statistics").execute()
            items_ch = ch_resp.get("items", [])
            if not items_ch:
                continue
            sub_count = int(items_ch[0].get("statistics", {}).get("subscriberCount") or 0)
            if sub_count > 0:
                _CACHE_SUBSCRIBERS_CANAL[cid] = sub_count
                _guardar_suscriptores_en_indice(cid, sub_count)

            uploads_id = items_ch[0]["contentDetails"]["relatedPlaylists"]["uploads"]
            pl_resp = yt.playlistItems().list(
                playlistId=uploads_id,
                part="snippet,contentDetails",
                maxResults=min(50, limite_por_cuenta + 5),
            ).execute()
            vids = [
                it["contentDetails"]["videoId"]
                for it in pl_resp.get("items", [])
                if it.get("contentDetails", {}).get("videoId")
            ]
            if not vids:
                continue

            v_resp = yt.videos().list(
                id=",".join(vids),
                part="snippet,status,statistics",
            ).execute()

            for it in v_resp.get("items", []):
                st = it.get("status", {})
                pub_sched = st.get("publishAt")
                if pub_sched:
                    # Si tiene fecha de publicación en el futuro, es programado, no publicado aún
                    try:
                        dt_s = _dt.datetime.fromisoformat(pub_sched.replace("Z", "+00:00"))
                        if dt_s > now_utc:
                            continue
                    except Exception:
                        pass

                snip = it.get("snippet", {})
                raw_pub = snip.get("publishedAt") or pub_sched or ""
                try:
                    dt_pub_utc = _dt.datetime.fromisoformat(raw_pub.replace("Z", "+00:00"))
                except Exception:
                    dt_pub_utc = now_utc

                dt_pub_local = dt_pub_utc.astimezone(tz_local)

                stats = it.get("statistics", {})
                vistas = int(stats.get("viewCount", 0))
                likes = int(stats.get("likeCount", 0))
                comentarios = int(stats.get("commentCount", 0))

                # Ratios de engagement:
                ratio_likes = round((likes / vistas) * 100, 1) if vistas > 0 else 0.0
                ratio_interaccion = round(((likes + comentarios) / vistas) * 100, 1) if vistas > 0 else 0.0

                vid_id = str(it.get("id") or "")
                tit = str(snip.get("title") or "Short sin título")

                todos_publicados.append({
                    "id": vid_id,
                    "titulo": tit,
                    "cuenta_id": cid,
                    "cuenta_nombre": cname,
                    "subscribers": sub_count,
                    "vistas": vistas,
                    "likes": likes,
                    "comentarios": comentarios,
                    "engagement_pct": ratio_interaccion,
                    "ratio_likes": ratio_likes,
                    "ratio_interaccion": ratio_interaccion,
                    "dt_utc": dt_pub_utc,
                    "dt_local": dt_pub_local,
                    "fecha_dia": dt_pub_local.strftime("%Y-%m-%d"),
                    "hora_local": dt_pub_local.strftime("%H:%M"),
                    "url": f"https://youtube.com/shorts/{vid_id}",
                })
        except Exception as e_pub:
            print(f"[!] No se pudieron leer métricas de videos de '{cname}': {e_pub}")
            continue

    todos_publicados.sort(key=lambda x: x["dt_utc"], reverse=True)
    return todos_publicados[:total_max]


if __name__ == "__main__":
    print("==============================================================================")
    print(" SUBIDOR AUTOMÁTICO DE SHORTS A YOUTUBE")
    print("==============================================================================")

    import argparse

    parser = argparse.ArgumentParser(description="Subidor automático de Shorts a YouTube")
    parser.add_argument("video", nargs="?", help="Ruta al video MP4 (opcional)")
    parser.add_argument("--verificar", action="store_true", help="Solo verificar vinculación con el canal")
    parser.add_argument("--test", action="store_true", help="Alias de --verificar")
    parser.add_argument("--titulo", type=str, help="Título del Short")
    parser.add_argument("--descripcion", type=str, help="Descripción del Short")
    parser.add_argument("--schedule", type=str, help="Fecha/hora ISO 8601 o texto para programar (ej: '2026-10-28T13:00:00Z' o 'manana 10:00')")
    parser.add_argument("--privado", "--private", action="store_true", help="Subir en modo privado")
    parser.add_argument("--oculto", "--unlisted", action="store_true", help="Subir en modo oculto")
    parser.add_argument("--para-ninos", dest="para_ninos", action="store_true", default=None, help="Marcar como contenido para niños")
    parser.add_argument("--no-para-ninos", dest="para_ninos", action="store_false", help="Marcar como NO apto exclusivamente para niños (permite monetización y comentarios)")
    parser.add_argument("--guion", type=str, help="Ruta al archivo guion_video.txt con los metadatos")
    parser.add_argument("--actualizar", type=str, metavar="VIDEO_ID", help="ID de un video ya subido en YouTube para actualizar su título, descripción, schedule o kids")

    args = parser.parse_args()

    # Modo solo verificación / vinculación de canal
    if args.verificar or args.test:
        try:
            verificar_canal_youtube()
        except Exception as e:
            print(f"\n[ERROR] No se pudo verificar la conexión: {e}")
            sys.exit(1)
        sys.exit(0)

    # Modo actualizar video existente
    if args.actualizar:
        ruta_g = Path(args.guion).resolve() if args.guion else None
        priv = "private" if args.privado else ("unlisted" if args.oculto else None)
        try:
            actualizar_video_existente(
                video_id=args.actualizar.strip(),
                titulo=args.titulo,
                descripcion=args.descripcion,
                publish_at=args.schedule,
                para_ninos=args.para_ninos,
                privacidad=priv,
                ruta_guion=ruta_g,
            )
        except Exception as e:
            print(f"\n[ERROR] No se pudo actualizar el video: {e}")
            sys.exit(1)
        sys.exit(0)

    # Verificar si client_secrets.json existe antes de continuar
    if not encontrar_archivo_credenciales() and not TOKEN_FILE.exists():
        mostrar_guia_configuracion()
        print("\n[!] Presiona Enter cuando hayas copiado 'client_secrets.json' en esta carpeta...")
        try:
            input()
        except Exception:
            pass

        if not encontrar_archivo_credenciales():
            print("[x] No se encontró el archivo. Crea las credenciales en Google Cloud y vuelve a intentarlo.")
            sys.exit(1)

    # Detectar archivo de video
    if args.video:
        ruta_mp4 = Path(args.video).resolve()
    else:
        ruta_mp4 = encontrar_ultimo_video()

    if not ruta_mp4 or not ruta_mp4.exists():
        print(f"[!] No se encontró ningún video en {OUTPUT_DIR}. Renderiza uno primero.")
        sys.exit(1)

    # Estado de privacidad
    privacidad = None
    if args.privado:
        privacidad = "private"
    elif args.oculto:
        privacidad = "unlisted"

    ruta_guion_usar = Path(args.guion).resolve() if args.guion else None

    try:
        subir_video(
            ruta_video=ruta_mp4,
            titulo=args.titulo,
            descripcion=args.descripcion,
            privacidad=privacidad,
            publish_at=args.schedule if args.schedule else ("no" if args.privado else None),
            para_ninos=args.para_ninos,
            ruta_guion=ruta_guion_usar,
        )
    except Exception as e:
        print(f"\n[ERROR] Ocurrió un fallo al subir el video: {e}")
        sys.exit(1)
