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

import sys

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

import asyncio
import time
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys

WIN_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
WIN_STARTUPINFO = None
if sys.platform == "win32":
    WIN_STARTUPINFO = subprocess.STARTUPINFO()
    WIN_STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    WIN_STARTUPINFO.wShowWindow = subprocess.SW_HIDE
import unicodedata
import urllib.request
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False


# ==============================================================================
# MOTOR Y MÓDULOS MODULARES (shorts_engine)
# ==============================================================================
from shorts_engine import *
from motor_optimizado import (
    aplicar_alerta_roja_rapida,
    obtener_color_semantico,
    evaluar_ritmo_bloque,
    recortar_silencios_tts,
    realzar_frame_viral,
    generar_plantilla_guion_manual,
    comprobar_actualizacion_repo,
    ejecutar_actualizacion_repo,
)
from ui_editor_guion import VisualScriptEditor


def iniciar_aplicacion_gui() -> None:
    import calendar as _cal
    import datetime as _dt
    import json as _json
    import queue
    import random
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox
    import webbrowser
    import customtkinter as ctk

    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Mateo.ShortsStudio.App")
    except Exception:
        pass

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("Shorts Studio")
    root.minsize(840, 320)
    root.configure(fg_color="#0b0d13")

    def autoajustar_tamano_ventana() -> None:
        """
        Amolda dinámicamente la altura de la ventana para que calce exactamente
        con el contenido actual (sin dejar espacios vacíos abajo).
        """
        try:
            root.update_idletasks()
            req_h = root.winfo_reqheight() + 8
            cur_w = max(860, root.winfo_width())
            root.geometry(f"{cur_w}x{req_h}")
        except Exception:
            pass

    _ico_app = BASE_DIR / "icono_shorts_studio.ico"
    if not _ico_app.exists():
        _ico_app = BASE_DIR / "icono_ctk_azul.ico"

    _ico_cache: Dict[str, Any] = {"big": None, "small": None}

    def _obtener_iconos_nativos() -> Tuple[Any, Any]:
        if not _ico_app.exists():
            return None, None
        if _ico_cache["big"] is None:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                _ico_cache["big"] = user32.LoadImageW(None, str(_ico_app), 1, 32, 32, 0x10)
                _ico_cache["small"] = user32.LoadImageW(None, str(_ico_app), 1, 16, 16, 0x10)
            except Exception:
                pass
        return _ico_cache["big"], _ico_cache["small"]

    def configurar_icono_taskbar_hwnd(hwnd: int) -> None:
        """
        Configura el icono nativo de Shorts Studio en la barra de tareas de Windows
        y en el PropertyStore de Shell para la ventana toplevel.
        """
        if not _ico_app.exists() or not hwnd:
            return
        try:
            import ctypes
            from ctypes import wintypes
            import uuid

            user32 = ctypes.windll.user32
            h_big, h_small = _obtener_iconos_nativos()
            if h_big:
                user32.SendMessageW(hwnd, 0x80, 1, h_big)  # WM_SETICON ICON_BIG
            if h_small:
                user32.SendMessageW(hwnd, 0x80, 0, h_small)  # WM_SETICON ICON_SMALL

            # Asignar AppUserModelID y RelaunchIconResource en el IPropertyStore de la ventana
            IID_IPropertyStore = uuid.UUID("{886d8eeb-8cf2-4446-8d02-cdba1dbdcf99}")

            class PROPERTYKEY(ctypes.Structure):
                _fields_ = [("fmtid", ctypes.c_ubyte * 16), ("pid", wintypes.DWORD)]

            class PROPVARIANT(ctypes.Structure):
                _fields_ = [
                    ("vt", wintypes.USHORT),
                    ("wReserved1", wintypes.WORD),
                    ("wReserved2", wintypes.WORD),
                    ("wReserved3", wintypes.WORD),
                    ("pwszVal", wintypes.LPWSTR),
                    ("pad", ctypes.c_ubyte * 8),
                ]

            def _make_pkey(guid_str: str, pid: int) -> PROPERTYKEY:
                u = uuid.UUID(guid_str)
                pk = PROPERTYKEY()
                pk.pid = pid
                pk.fmtid = (ctypes.c_ubyte * 16)(*u.bytes_le)
                return pk

            PKEY_AUMID = _make_pkey("{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}", 5)
            PKEY_IconRes = _make_pkey("{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}", 2)
            PKEY_RelaunchCmd = _make_pkey("{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}", 4)

            class IPropertyStoreVtbl(ctypes.Structure):
                _fields_ = [
                    ("QueryInterface", ctypes.c_void_p),
                    ("AddRef", ctypes.c_void_p),
                    ("Release", ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)),
                    ("GetCount", ctypes.c_void_p),
                    ("GetAt", ctypes.c_void_p),
                    ("GetValue", ctypes.c_void_p),
                    ("SetValue", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))),
                    ("Commit", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)),
                ]

            class IPropertyStore(ctypes.Structure):
                _fields_ = [("lpVtbl", ctypes.POINTER(IPropertyStoreVtbl))]

            iid_bytes = (ctypes.c_ubyte * 16)(*IID_IPropertyStore.bytes_le)
            pps = ctypes.POINTER(IPropertyStore)()
            if hasattr(ctypes.windll, "propsys") and hasattr(ctypes.windll.propsys, "SHGetPropertyStoreForWindow"):
                hr = ctypes.windll.propsys.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(iid_bytes), ctypes.byref(pps))
                if hr == 0 and pps:
                    pv_aumid = PROPVARIANT()
                    pv_aumid.vt = 31  # VT_LPWSTR
                    pv_aumid.pwszVal = "Mateo.ShortsStudio.App"
                    pps.contents.lpVtbl.contents.SetValue(pps, ctypes.byref(PKEY_AUMID), ctypes.byref(pv_aumid))

                    pv_icon = PROPVARIANT()
                    pv_icon.vt = 31
                    pv_icon.pwszVal = str(_ico_app.resolve()) + ",0"
                    pps.contents.lpVtbl.contents.SetValue(pps, ctypes.byref(PKEY_IconRes), ctypes.byref(pv_icon))

                    exe_launcher = BASE_DIR / "Shorts Studio.exe"
                    if exe_launcher.exists():
                        pv_cmd = PROPVARIANT()
                        pv_cmd.vt = 31
                        pv_cmd.pwszVal = f'"{exe_launcher.resolve()}"'
                        pps.contents.lpVtbl.contents.SetValue(pps, ctypes.byref(PKEY_RelaunchCmd), ctypes.byref(pv_cmd))

                    pps.contents.lpVtbl.contents.Commit(pps)
                    pps.contents.lpVtbl.contents.Release(pps)
        except Exception:
            pass

    def aplicar_icono_ventana(win: tk.Misc) -> None:
        """Aplica el icono oficial de Shorts Studio a cualquier ventana toplevel."""
        if _ico_app.exists():
            try:
                win.iconbitmap(str(_ico_app))
            except Exception:
                pass
            try:
                import ctypes
                user32 = ctypes.windll.user32
                top_hwnd = user32.GetParent(win.winfo_id())
                if not top_hwnd:
                    top_hwnd = int(win.wm_frame(), 16) if win.wm_frame() else win.winfo_id()
                if top_hwnd:
                    configurar_icono_taskbar_hwnd(top_hwnd)
            except Exception:
                pass

    try:
        root.iconbitmap(str(_ico_app))
    except Exception:
        pass
    root.after(150, lambda: aplicar_icono_ventana(root))

    def formatear_subs(num: Any) -> str:
        try:
            n = int(num or 0)
        except Exception:
            return ""
        if n <= 0:
            return ""
        if n >= 1_000_000:
            val = f"{n / 1_000_000:.1f}M".replace(".0M", "M")
        elif n >= 1_000:
            val = f"{n / 1_000:.1f}K".replace(".0K", "K")
        else:
            val = f"{n:,}"
        return f"{val} subs"

    cola_logs: "queue.Queue[str]" = queue.Queue()
    editando_lock = threading.Lock()
    ultimo_video_generado: List[Optional[Path]] = [None]

    BG_DARK = "#0b0d13"
    CARD_BG = "#141824"
    CARD_BORDER = "#252b3d"
    INPUT_BG = "#0e111a"
    TEXT_MAIN = "#f8fafc"
    TEXT_MUTED = "#94a3b8"
    TEXT_DIM = "#64748b"
    PURPLE_MAIN = "#7c3aed"
    PURPLE_HOVER = "#6d28d9"
    CYAN_ACCENT = "#38bdf8"
    GREEN_ACCENT = "#10b981"

    SCHEDULE_MEM_FILE = BASE_DIR / "ultimo_schedule.json"
    MESES_ES = [
        "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]
    DIAS_CORTOS_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

    encuadre_map = {
        "Pantalla Completa Vertical (Crop 9:16)": "full",
        "Fondo Borroso para Horizontales (Blur 9:16)": "blur",
    }

    MAPA_MODELOS_IA = {
        "Gemini 3.5 Flash Lite · Recomendado (rápido, cuota amplia, ideal para video)": "gemini-3.5-flash-lite",
        "Gemini 3.6 Flash · Alta calidad (cuota diaria limitada a 20/día en Free Tier)": "gemini-3.6-flash",
        "Gemini 3.8 Flash · Razonamiento extra (sujeto a disponibilidad)": "gemini-3.8-flash",
        "Argon 4 · Máxima calidad (requiere facturación en AI Studio)": "gemini-4-argon",
    }

    def _cargar_memoria() -> Dict[str, object]:
        manana = _dt.date.today() + _dt.timedelta(days=1)
        def_data: Dict[str, object] = {
            "activar_schedule": True,
            "fecha": manana.strftime("%Y-%m-%d"),
            "hora": "13:00",
            "privacidad": "Privado",
            "voz": list(VOCES_DISPONIBLES.keys())[0],
            "encuadre": list(encuadre_map.keys())[0],
            "modo_fuente": "Canales Seleccionados",
            "modo_contenido": "IA Automática",
            "modo_subida": "Subida Automática",
            "accion_final": "Subir automáticamente",
            "modelo_ia": list(MAPA_MODELOS_IA.keys())[0],
            "orden_canales": "Rotación (En fila)",
            "min_views_millones": "1.0M+ vistas",
            "cantidad_total": "2 Shorts",
            "shorts_por_dia": "2 / día",
            "modo_horario": "Horarios Pico",
            "intervalo_horas": "Cada 8h",
            "cuenta_destino": "Canal Principal",
            "modo_cuentas": "una",
            "cuenta_activa_id": "",
            "grupo_cuentas_ids": [],
            "estrategia_multicuenta": "cross_posting",
            "canales_por_cuenta": {},
            "canales": [],
            "indice_rotacion": 0,
            "canal_fijo_seleccionado": "",
            "custom_reels": [],
            "modo_render": "Automático (GPU)",
        }
        if SCHEDULE_MEM_FILE.exists():
            try:
                leido = _json.loads(SCHEDULE_MEM_FILE.read_text(encoding="utf-8"))
                fecha_str = str(leido.get("fecha", def_data["fecha"]))
                f_parsed = _dt.date.fromisoformat(fecha_str)
                if f_parsed < _dt.date.today():
                    f_parsed = _dt.date.today()
                mf_leido = str(leido.get("modo_fuente", "Canales Seleccionados"))
                if "Editado" in mf_leido:
                    mf_val = "Subir Video Editado"
                elif "Link" in mf_leido:
                    mf_val = "Link de Video"
                else:
                    mf_val = "Canales Seleccionados"
                return {
                    "activar_schedule": True,
                    "fecha": f_parsed.strftime("%Y-%m-%d"),
                    "hora": str(leido.get("hora", "13:00")),
                    "privacidad": str(leido.get("privacidad", "Privado")),
                    "voz": str(leido.get("voz", def_data["voz"])),
                    "encuadre": str(leido.get("encuadre", def_data["encuadre"])),
                    "modo_fuente": mf_val,
                    "modo_contenido": "Personalizado" if "Personalizado" in str(leido.get("modo_contenido", "IA Automática")) else "IA Automática",
                    "modo_subida": "Edición Manual" if "Manual" in str(leido.get("modo_subida", "")) else ("Revisión Previa" if "Revisión" in str(leido.get("modo_subida", "")) or "Revision" in str(leido.get("modo_subida", "")) else "Subida Automática"),
                    "accion_final": "Subir automáticamente",
                    "modelo_ia": (str(leido.get("modelo_ia")) if str(leido.get("modelo_ia")) in MAPA_MODELOS_IA else def_data["modelo_ia"]),
                    "orden_canales": str(leido.get("orden_canales", "Rotación (En fila)")),
                    "min_views_millones": str(leido.get("min_views_millones", "1.0M+ vistas")),
                    "cantidad_total": str(leido.get("cantidad_total", "2 Shorts")),
                    "shorts_por_dia": str(leido.get("shorts_por_dia", "2 / día")),
                    "modo_horario": ("Horario Específico" if ("Específ" in str(leido.get("modo_horario", "")) or "especif" in str(leido.get("modo_horario", "")).lower()) else ("Cada X hs" if "Cada" in str(leido.get("modo_horario", "")) else "Horarios Pico")),
                    "hora_esp": str(leido.get("hora_esp", leido.get("hora", "13:00")) or "13:00"),
                    "hora_desde": str(leido.get("hora_desde", "13:00") or "13:00"),
                    "intervalo_horas": str(re.sub(r"\D", "", str(leido.get("intervalo_horas", "8"))) or "8"),
                    "cuenta_destino": str(leido.get("cuenta_destino", "Canal Principal")),
                    "modo_cuentas": str(leido.get("modo_cuentas", "una")),
                    "cuenta_activa_id": str(leido.get("cuenta_activa_id", "")),
                    "grupo_cuentas_ids": list(leido.get("grupo_cuentas_ids", [])),
                    "estrategia_multicuenta": str(leido.get("estrategia_multicuenta", "cross_posting")),
                    "canales_por_cuenta": dict(leido.get("canales_por_cuenta") or {}),
                    "canales": list(leido.get("canales", [])),
                    "indice_rotacion": int(leido.get("indice_rotacion", 0)),
                    "canal_fijo_seleccionado": str(leido.get("canal_fijo_seleccionado", "")),
                    "custom_reels": list(leido.get("custom_reels", [])),
                    "modo_render": str(leido.get("modo_render", "Automático (GPU)")),
                }
            except Exception:
                pass
        return def_data

    mem = _cargar_memoria()

    programar_var = tk.BooleanVar(value=bool(mem["activar_schedule"]))
    fecha_elegida_var = tk.StringVar(value=str(mem["fecha"]))
    hora_elegida_var = tk.StringVar(value=str(mem["hora"]))
    hora_esp_var = tk.StringVar(value=str(mem.get("hora_esp", mem["hora"]) or "13:00"))
    hora_desde_var = tk.StringVar(value=str(mem.get("hora_desde", "13:00") or "13:00"))
    privacidad_var = tk.StringVar(value=str(mem["privacidad"]))
    voz_var = tk.StringVar(value=str(mem["voz"]))
    encuadre_var = tk.StringVar(value=str(mem["encuadre"]))
    lista_videos_editados_locales: List[Path] = []
    if mem.get("videos_editados_guardados"):
        for _p_str in mem["videos_editados_guardados"]:
            _p = Path(_p_str)
            if _p.exists() and _p not in lista_videos_editados_locales:
                lista_videos_editados_locales.append(_p)
    modo_fuente_var = tk.StringVar(value=str(mem["modo_fuente"]))
    modo_contenido_var = tk.StringVar(value=str(mem["modo_contenido"]))
    modo_subida_var = tk.StringVar(value=str(mem.get("modo_subida", "Subida Automática")))
    accion_final_var = tk.StringVar(value=str(mem.get("accion_final", "Subir automáticamente")))
    modelo_ia_var = tk.StringVar(value=str(mem["modelo_ia"]))
    modo_render_var = tk.StringVar(value=str(mem.get("modo_render", "Automático (GPU)")))
    orden_canales_var = tk.StringVar(value=str(mem["orden_canales"]))
    canal_fijo_var = tk.StringVar(value=str(mem.get("canal_fijo_seleccionado", "")))
    min_views_var = tk.StringVar(value=str(mem["min_views_millones"]))
    cantidad_total_var = tk.StringVar(value=str(mem["cantidad_total"]))
    shorts_por_dia_var = tk.StringVar(value=str(mem["shorts_por_dia"]))
    modo_horario_var = tk.StringVar(value=str(mem["modo_horario"]))
    intervalo_horas_var = tk.StringVar(value=str(mem["intervalo_horas"]))
    cuenta_destino_var = tk.StringVar(value=str(mem.get("cuenta_destino", "Canal Principal")))
    lista_canales: List[str] = [str(c) for c in (mem.get("canales") or []) if str(c).strip()]
    estado_rotacion = {"idx": int(mem.get("indice_rotacion", 0))}
    mapa_cuentas_ui: Dict[str, str] = {}

    # Estado multi-cuenta y canales fuente guardados individualmente por cuenta de YouTube
    canales_por_cuenta: Dict[str, List[str]] = {}
    raw_cpc = mem.get("canales_por_cuenta")
    if isinstance(raw_cpc, dict):
        for k_cp, v_cp in raw_cpc.items():
            if isinstance(v_cp, list):
                canales_por_cuenta[str(k_cp)] = [str(x) for x in v_cp if str(x).strip()]

    cid_mem = str(mem.get("cuenta_activa_id") or "")
    if cid_mem and cid_mem in canales_por_cuenta and canales_por_cuenta[cid_mem]:
        lista_canales = list(canales_por_cuenta[cid_mem])
    elif not lista_canales and canales_por_cuenta:
        for _c_list in canales_por_cuenta.values():
            if _c_list:
                lista_canales = list(_c_list)
                break

    estado_seleccion_cuentas: Dict[str, object] = {
        "modo": str(mem.get("modo_cuentas") or "una"),  # "una" | "todas" | "grupo"
        "cuenta_id": cid_mem,
        "grupo_ids": [str(x) for x in (mem.get("grupo_cuentas_ids") or []) if str(x).strip()],
        "estrategia": str(mem.get("estrategia_multicuenta") or "cross_posting"),  # "cross_posting" | "rotacion"
    }
    cache_avatares_ctk: Dict[str, ctk.CTkImage] = {}
    row_botones_accion: Optional[ctk.CTkFrame] = None
    btn_auto_1clic: Optional[ctk.CTkButton] = None
    btn_guardar_carpeta: Optional[ctk.CTkButton] = None
    btn_ajustes: Optional[ctk.CTkButton] = None
    solo_guardar_actual = [False]

    # Lista de diccionarios para personalizar cada Reel individualmente (hasta 12 Shorts)
    datos_custom_reels: List[Dict[str, str]] = []
    raw_custom = mem.get("custom_reels")
    if isinstance(raw_custom, list):
        for item_c in raw_custom:
            if isinstance(item_c, dict):
                datos_custom_reels.append(
                    {
                        "titulo": str(item_c.get("titulo") or ""),
                        "descripcion": str(item_c.get("descripcion") or ""),
                        "guion": str(item_c.get("guion") or ""),
                    }
                )
    while len(datos_custom_reels) < 12:
        datos_custom_reels.append({"titulo": "", "descripcion": "", "guion": ""})
    estado_reel_custom = {"idx": 0, "cargando": False}

    MAPA_MIN_VIEWS = {
        "100K+ vistas": 100_000,
        "500K+ vistas": 500_000,
        "1.0M+ vistas": 1_000_000,
        "5.0M+ vistas": 5_000_000,
        "10M+ vistas": 10_000_000,
        "20M+ vistas": 20_000_000,
        "Sin mínimo": 0,
    }

    MAPA_CANTIDAD_TOTAL = {
        "1 Short": 1,
        "2 Shorts": 2,
        "3 Shorts": 3,
        "4 Shorts": 4,
        "5 Shorts": 5,
        "6 Shorts": 6,
        "8 Shorts": 8,
        "10 Shorts": 10,
        "12 Shorts": 12,
    }

    MAPA_POR_DIA = {
        "1 / día": 1,
        "2 / día": 2,
        "3 / día": 3,
        "4 / día": 4,
        "5 / día": 5,
        "6 / día": 6,
        "8 / día": 8,
        "10 / día": 10,
        "12 / día": 12,
    }

    MAPA_INTERVALO_HS = {
        "Cada 3h": 3,
        "Cada 4h": 4,
        "Cada 6h": 6,
        "Cada 8h": 8,
        "Cada 12h": 12,
    }

    def _guardar_memoria(*_args: object) -> None:
        try:
            cid_act = str(estado_seleccion_cuentas.get("cuenta_id") or "")
            if cid_act and str(estado_seleccion_cuentas.get("modo") or "una") == "una":
                if lista_canales or cid_act not in canales_por_cuenta or not canales_por_cuenta[cid_act]:
                    canales_por_cuenta[cid_act] = list(lista_canales)
            SCHEDULE_MEM_FILE.write_text(
                _json.dumps(
                    {
                        "activar_schedule": True,
                        "videos_editados_guardados": [str(p) for p in lista_videos_editados_locales],
                        "fecha": fecha_elegida_var.get(),
                        "hora": (hora_esp_var.get() if "Específ" in modo_horario_var.get() else hora_desde_var.get()),
                        "hora_esp": hora_esp_var.get(),
                        "hora_desde": hora_desde_var.get(),
                        "privacidad": privacidad_var.get(),
                        "voz": voz_var.get(),
                        "encuadre": encuadre_var.get(),
                        "modo_fuente": modo_fuente_var.get(),
                        "modo_contenido": modo_contenido_var.get(),
                        "modo_subida": modo_subida_var.get(),
                        "accion_final": accion_final_var.get(),
                        "modelo_ia": modelo_ia_var.get(),
                        "orden_canales": orden_canales_var.get(),
                        "min_views_millones": min_views_var.get(),
                        "cantidad_total": cantidad_total_var.get(),
                        "shorts_por_dia": shorts_por_dia_var.get(),
                        "modo_horario": modo_horario_var.get(),
                        "intervalo_horas": intervalo_horas_var.get(),
                        "cuenta_destino": cuenta_destino_var.get(),
                        "modo_cuentas": estado_seleccion_cuentas.get("modo", "una"),
                        "cuenta_activa_id": estado_seleccion_cuentas.get("cuenta_id", ""),
                        "grupo_cuentas_ids": estado_seleccion_cuentas.get("grupo_ids", []),
                        "estrategia_multicuenta": estado_seleccion_cuentas.get("estrategia", "cross_posting"),
                        "canales_por_cuenta": canales_por_cuenta,
                        "canales": lista_canales,
                        "indice_rotacion": estado_rotacion["idx"],
                        "canal_fijo_seleccionado": canal_fijo_var.get(),
                        "custom_reels": datos_custom_reels[:12],
                        "modo_render": modo_render_var.get(),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _formatear_boton_fecha(iso_str: str) -> str:
        try:
            d = _dt.date.fromisoformat(iso_str)
            return f"{d.day:02d}/{d.month:02d}"
        except Exception:
            return f"{iso_str}"


    # ==========================================================================
    # ENCABEZADO SUPERIOR + BARRA DE CUOTA DIARIA REAL DE GOOGLE + BOTÓN AJUSTES
    # ==========================================================================
    header = ctk.CTkFrame(root, fg_color="transparent")
    header.pack(fill="x", padx=28, pady=(16, 8))

    title_box = ctk.CTkFrame(header, fg_color="transparent")
    title_box.pack(side="left")

    ctk.CTkLabel(
        title_box,
        text="Shorts Studio",
        font=ctk.CTkFont(family="Segoe UI", size=25, weight="bold"),
        text_color=TEXT_MAIN,
    ).pack(anchor="w")

    # Contenedor superior derecho ordenado:
    # [quota_pill] -> [btn_cuenta_top] -> [btn_ajustes] (en la esquina superior derecha)
    header_right = ctk.CTkFrame(header, fg_color="transparent")
    header_right.pack(side="right")

    # Tarjeta Píldora Compacta de Shorts Restantes Hoy + Botón '+' para agregar API JSON (+6 Shorts/día)
    quota_pill = ctk.CTkFrame(header_right, fg_color=CARD_BG, corner_radius=16, border_width=1, border_color=CARD_BORDER)
    quota_pill.pack(side="left", padx=(0, 8), pady=4)

    quota_top = ctk.CTkFrame(quota_pill, fg_color="transparent")
    quota_top.pack(fill="both", expand=True, padx=(12, 6), pady=4)

    def agregar_api_json_gui(parent_win: Optional[tk.Misc] = None) -> None:
        from tkinter import filedialog
        import shutil as _shutil

        ruta_sel = filedialog.askopenfilename(
            parent=parent_win or root,
            title="Selecciona un archivo client_secrets.json de otro proyecto Google Cloud (+6 Shorts/día)",
            filetypes=[("Credenciales OAuth Google", "*.json"), ("Todos los archivos", "*.*")],
        )
        if not ruta_sel:
            return
        try:
            p_origen = Path(ruta_sel)
            raw_j = _json.loads(p_origen.read_text(encoding="utf-8"))
            info_j = raw_j.get("installed") or raw_j.get("web") or {}
            cid = str(info_j.get("client_id") or "").strip()
            if not cid:
                messagebox.showwarning(
                    "Archivo inválido",
                    "El archivo JSON seleccionado no parece ser un client_secrets.json OAuth válido de Google Cloud.",
                    parent=parent_win or root,
                )
                return
            dir_apis = BASE_DIR / "apis_google"
            dir_apis.mkdir(parents=True, exist_ok=True)
            pref_id = re.sub(r"[^a-zA-Z0-9]", "", cid[:12])
            destino = dir_apis / f"client_secrets_{pref_id}.json"
            _shutil.copy2(p_origen, destino)
            refrescar_barra_cuota()
            max_n, cant_n = obtener_max_shorts_pool_dia()
            messagebox.showinfo(
                "API Agregada (+6 Shorts/día)",
                f"¡Proyecto Google Cloud sumado al Pool!\n\nAhora tienes {cant_n} API(s) activas = hasta {max_n} Shorts por día.",
                parent=parent_win or root,
            )
        except Exception as e_ap:
            messagebox.showerror("Error", f"No se pudo importar el archivo JSON:\n{e_ap}", parent=parent_win or root)

    def abrir_dialogo_explicativo_api_json(parent_win: Optional[tk.Misc] = None) -> None:
        win_exp = ctk.CTkToplevel(parent_win or root)
        win_exp.title("Aumentar Cuota Diaria de Subida")
        win_exp.geometry("540x360")
        win_exp.resizable(False, False)
        win_exp.configure(fg_color=BG_DARK)
        win_exp.transient(parent_win or root)
        aplicar_icono_ventana(win_exp)
        win_exp.grab_set()

        card_e = ctk.CTkFrame(win_exp, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card_e.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            card_e,
            text="Aumentar Capacidad Diaria (+6 Shorts/día)",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w", padx=20, pady=(18, 8))

        msg_explicativo = (
            "YouTube limita la subida automática a aproximadamente 6 Shorts diarios "
            "por cada proyecto de Google Cloud (cuota de 10.000 unidades de YouTube Data API v3).\n\n"
            "Para aumentar tu límite y poder subir 12, 18, 24 o más Shorts por día, "
            "puedes sumar archivos 'client_secrets.json' de otros proyectos de Google Cloud Console.\n\n"
            "El sistema rotará automáticamente entre todas tus claves para no agotar la cuota de ninguna."
        )

        ctk.CTkLabel(
            card_e,
            text=msg_explicativo,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_MUTED,
            justify="left",
            wraplength=460,
        ).pack(anchor="w", padx=20, pady=(0, 16))

        btn_row = ctk.CTkFrame(card_e, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(8, 16))

        def _proceder_seleccion() -> None:
            win_exp.destroy()
            agregar_api_json_gui(parent_win or root)

        ctk.CTkButton(
            btn_row,
            text="Seleccionar client_secrets.json",
            command=_proceder_seleccion,
            height=34,
            corner_radius=12,
            fg_color=PURPLE_MAIN,
            hover_color=PURPLE_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_row,
            text="Cancelar",
            command=win_exp.destroy,
            height=34,
            corner_radius=12,
            fg_color=INPUT_BG,
            hover_color="#1d2334",
            border_width=1,
            border_color=CARD_BORDER,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).pack(side="right")

    lbl_cuota_info = ctk.CTkLabel(
        quota_top,
        text="6/6 Shorts disponibles",
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        text_color="#ffffff",
    )
    lbl_cuota_info.pack(side="left", padx=(6, 8), pady=2)

    def refrescar_barra_cuota() -> None:
        max_tot, n_apis = obtener_max_shorts_pool_dia()
        usados_h, disp_h, _pct = obtener_estado_cuota_diaria()
        lbl_cuota_info.configure(
            text=f"{disp_h}/{max_tot} Shorts disponibles",
            text_color="#ffffff",
        )

    def sincronizar_cuota_async() -> None:
        lbl_cuota_info.configure(text="Sincronizando...", text_color=CYAN_ACCENT)

        def _worker_sync() -> None:
            sincronizar_cuota_real_youtube()
            try:
                root.after(0, refrescar_barra_cuota)
            except Exception:
                pass

        threading.Thread(target=_worker_sync, daemon=True).start()

    refrescar_barra_cuota()
    root.after(400, sincronizar_cuota_async)

    def _comprobar_actualizacion_background() -> None:
        def _worker_bg():
            hay_upd, cant_upd, _msg = comprobar_actualizacion_repo(BASE_DIR)
            if hay_upd:
                def _notificar_header():
                    if btn_ajustes is not None:
                        btn_ajustes.configure(
                            text=f"Ajustes ({cant_upd})",
                            border_color="#facc15",
                            text_color="#facc15",
                        )
                try:
                    root.after(0, _notificar_header)
                except Exception:
                    pass

        threading.Thread(target=_worker_bg, daemon=True).start()

    root.after(1500, _comprobar_actualizacion_background)

    # Contenedor dinámico del Paso 1 (alterna entre Modo Canales y Modo Link según Ajustes)
    contenedor_paso1 = ctk.CTkFrame(root, fg_color="transparent")
    contenedor_paso1.pack(fill="x", padx=28, pady=(0, 10))

    # --- TARJETA MODO A: POOL DE CANALES FUENTE ---
    card_canales = ctk.CTkFrame(contenedor_paso1, fg_color=CARD_BG, corner_radius=22, border_width=1, border_color=CARD_BORDER)

    top_canales = ctk.CTkFrame(card_canales, fg_color="transparent")
    top_canales.pack(fill="x", padx=20, pady=(12, 6))

    lbl_titulo_canales = ctk.CTkLabel(
        top_canales,
        text="Canales Fuente",
        font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
        text_color=TEXT_MAIN,
    )
    lbl_titulo_canales.pack(side="left")

    cfg_canales_frame = ctk.CTkFrame(top_canales, fg_color="transparent")
    cfg_canales_frame.pack(side="right")

    ctk.CTkLabel(
        cfg_canales_frame,
        text="Selección de Canal:",
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        text_color=TEXT_MUTED,
    ).pack(side="left", padx=(0, 6))

    ctk.CTkOptionMenu(
        cfg_canales_frame,
        variable=orden_canales_var,
        values=["Rotación (En fila)", "Aleatorio", "Canal único (Clic para elegir)"],
        command=lambda _: (_guardar_memoria(), renderizar_chips_canales()),
        corner_radius=12,
        height=28,
        width=195,
        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        fg_color="#1e2436",
        button_color="#2d354d",
    ).pack(side="left", padx=(0, 14))

    ctk.CTkLabel(
        cfg_canales_frame,
        text="Filtro de Vistas Mínimas:",
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        text_color=TEXT_MUTED,
    ).pack(side="left", padx=(0, 6))

    ctk.CTkOptionMenu(
        cfg_canales_frame,
        variable=min_views_var,
        values=list(MAPA_MIN_VIEWS.keys()),
        command=lambda _: (_guardar_memoria(), renderizar_chips_canales()),
        corner_radius=12,
        height=28,
        width=128,
        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        fg_color="#1e2436",
        button_color="#2d354d",
    ).pack(side="left")

    canales_body_row = ctk.CTkFrame(card_canales, fg_color="transparent")
    canales_body_row.pack(fill="x", padx=20, pady=(0, 12))

    chips_container = ctk.CTkFrame(
        canales_body_row,
        corner_radius=14,
        fg_color=INPUT_BG,
        border_width=1,
        border_color="#1f2537",
    )
    chips_container.pack(side="left", fill="both", expand=True, padx=(0, 10))

    def agregar_canal_gui() -> None:
        dialog = ctk.CTkInputDialog(
            text="Ingresa el link o @nombre del canal de YouTube:\n(ejemplo: https://youtube.com/@canal o @canal)",
            title="Agregar Canal Fuente",
        )
        try:
            aplicar_icono_ventana(dialog)
        except Exception:
            pass
        raw = dialog.get_input()
        if not raw:
            return
        url_norm = normalizar_url_canal_shorts(raw.strip())
        if not url_norm:
            return
        if url_norm not in lista_canales:
            lista_canales.append(url_norm)
            _guardar_memoria()
        renderizar_chips_canales()

    btn_add_canal = ctk.CTkButton(
        canales_body_row,
        text="+ Agregar Canal",
        command=agregar_canal_gui,
        corner_radius=16,
        height=40,
        width=135,
        fg_color=INPUT_BG,
        hover_color="#1e2538",
        border_width=1,
        border_color="#2a3147",
        text_color="#ffffff",
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
    )
    btn_add_canal.pack(side="right", anchor="center")

    def renderizar_chips_canales() -> None:
        for w in chips_container.winfo_children():
            w.destroy()
        if not lista_canales:
            ctk.CTkLabel(
                chips_container,
                text="No hay canales fuente agregados. Toca '+ Agregar Canal' a la derecha para sumar canales.",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=TEXT_MUTED,
            ).pack(padx=12, pady=12)
            autoajustar_tamano_ventana()
            return

        row_frame = None
        MAX_POR_FILA = 3
        modo_ord = orden_canales_var.get()
        es_modo_fijo = ("Único" in modo_ord or "fijo" in modo_ord.lower())

        if es_modo_fijo and not canal_fijo_var.get() and lista_canales:
            canal_fijo_var.set(lista_canales[0])

        for idx_c, c_url in enumerate(lista_canales):
            if idx_c % MAX_POR_FILA == 0:
                row_frame = ctk.CTkFrame(chips_container, fg_color="transparent")
                row_frame.pack(fill="x", padx=8, pady=3)

            es_fijo = es_modo_fijo and (c_url == canal_fijo_var.get())
            es_turno = (not es_modo_fijo) and (idx_c == (estado_rotacion["idx"] % len(lista_canales))) and ("Rotación" in modo_ord)

            bg_chip = "#143828" if es_fijo else ("#251d42" if es_turno else "#1b2234")
            borde_chip = GREEN_ACCENT if es_fijo else (PURPLE_MAIN if es_turno else "#2c3652")
            borde_w = 2 if (es_fijo or es_turno) else 1

            chip = ctk.CTkFrame(
                row_frame,
                fg_color=bg_chip,
                corner_radius=14,
                border_width=borde_w,
                border_color=borde_chip,
                cursor="hand2",
            )
            chip.pack(side="left", padx=5, pady=2)

            pref_turno = "✔ " if es_fijo else ("▶ " if es_turno else "")
            lbl_c = ctk.CTkLabel(
                chip,
                text=f"{pref_turno}{idx_c + 1}. {etiqueta_corta_canal(c_url)}",
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color="#ffffff" if (es_fijo or es_turno) else TEXT_MAIN,
                cursor="hand2",
            )
            lbl_c.pack(side="left", padx=(12, 6), pady=4)

            def _click_seleccionar_este_canal(e=None, u=c_url) -> None:
                canal_fijo_var.set(u)
                orden_canales_var.set("Canal único (Clic para elegir)")
                _guardar_memoria()
                renderizar_chips_canales()

            chip.bind("<Button-1>", _click_seleccionar_este_canal)
            lbl_c.bind("<Button-1>", _click_seleccionar_este_canal)

            def _quitar_c(u: str = c_url) -> None:
                if u in lista_canales:
                    lista_canales.remove(u)
                    if canal_fijo_var.get() == u:
                        canal_fijo_var.set(lista_canales[0] if lista_canales else "")
                    _guardar_memoria()
                    renderizar_chips_canales()

            ctk.CTkButton(
                chip,
                text="X",
                width=22,
                height=22,
                corner_radius=11,
                fg_color="transparent",
                hover_color="#dc2626",
                text_color=TEXT_MUTED,
                command=_quitar_c,
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="right", padx=(0, 6), pady=4)
        autoajustar_tamano_ventana()

    # --- TARJETA MODO B: LINK DE VIDEO (INDIVIDUAL O MÚLTIPLES LINKS) ---
    card_link = ctk.CTkFrame(contenedor_paso1, fg_color=CARD_BG, corner_radius=22, border_width=1, border_color=CARD_BORDER)

    top_link_row = ctk.CTkFrame(card_link, fg_color="transparent")
    top_link_row.pack(fill="x", padx=22, pady=(14, 8))

    ctk.CTkLabel(
        top_link_row,
        text="Links de Videos de YouTube",
        font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
        text_color=TEXT_MAIN,
    ).pack(side="left")

    lbl_contador_links = ctk.CTkLabel(
        top_link_row,
        text="1 Video",
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        text_color=CYAN_ACCENT,
        fg_color="#0e2a3a",
        corner_radius=10,
        padx=10,
        pady=2,
    )
    lbl_contador_links.pack(side="right")

    filas_links_container = ctk.CTkFrame(card_link, fg_color="transparent")
    filas_links_container.pack(fill="x", padx=22, pady=(0, 14))

    lista_filas_links: List[Dict[str, object]] = []

    def obtener_links_ingresados() -> List[str]:
        links: List[str] = []
        for fd in lista_filas_links:
            ent = fd.get("entry")
            if ent and ent.winfo_exists():
                v = ent.get().strip().strip('"')
                if v:
                    links.append(v)
        return links

    def _actualizar_ui_filas_links() -> None:
        nonlocal entry_url
        tot = len(lista_filas_links)
        for fd in lista_filas_links:
            btn_d = fd.get("btn_del")
            if btn_d is not None and isinstance(btn_d, ctk.CTkButton):
                if tot > 1:
                    if not btn_d.winfo_ismapped():
                        btn_d.pack(side="left", padx=(4, 0))
                else:
                    btn_d.pack_forget()

        if lista_filas_links:
            entry_url = lista_filas_links[0]["entry"]

        cant = len(lista_filas_links)
        lbl_contador_links.configure(text=f"{cant} {'Video' if cant == 1 else 'Videos'}")
        try:
            refrescar_plan_ui()
        except (NameError, Exception):
            pass
        autoajustar_tamano_ventana()

    # --- TARJETA MODO C: SUBIR VIDEO YA EDITADO (DESDE CARPETA / DISCO) ---
    card_video_editado = ctk.CTkFrame(contenedor_paso1, fg_color=CARD_BG, corner_radius=22, border_width=1, border_color=CARD_BORDER)

    top_editado_row = ctk.CTkFrame(card_video_editado, fg_color="transparent")
    top_editado_row.pack(fill="x", padx=20, pady=(12, 6))

    ctk.CTkLabel(
        top_editado_row,
        text="Videos Editados para Subir",
        font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
        text_color=TEXT_MAIN,
    ).pack(side="left")

    editado_header_right = ctk.CTkFrame(top_editado_row, fg_color="transparent")
    editado_header_right.pack(side="right")

    lbl_contador_editados = ctk.CTkLabel(
        editado_header_right,
        text="0 Videos",
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        text_color=CYAN_ACCENT,
        fg_color="#0e2a3a",
        corner_radius=10,
        padx=10,
        pady=2,
    )
    lbl_contador_editados.pack(side="right", padx=(8, 0))



    def _renderizar_lista_videos_editados() -> None:
        for w in filas_editados_container.winfo_children():
            w.destroy()

        cant_e = len(lista_videos_editados_locales)
        lbl_contador_editados.configure(text=f"{cant_e} {'Video' if cant_e == 1 else 'Videos'}")

        if not lista_videos_editados_locales:
            empty_row = ctk.CTkFrame(filas_editados_container, fg_color="transparent")
            empty_row.pack(fill="x", pady=6)
            ctk.CTkLabel(
                empty_row,
                text="Ningún video seleccionado. Toca '+ Seleccionar Video(s) MP4' para elegir videos ya terminados de tu disco.",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=TEXT_MUTED,
            ).pack(anchor="w", padx=6)
            return

        for idx_ev, p_ev in enumerate(lista_videos_editados_locales):
            f_row = ctk.CTkFrame(filas_editados_container, fg_color="#101522", corner_radius=12, border_width=1, border_color="#1c2538")
            f_row.pack(fill="x", pady=2)

            t_mb = ""
            try:
                sz = p_ev.stat().st_size / (1024 * 1024)
                t_mb = f" · {sz:.1f} MB"
            except Exception:
                pass

            ctk.CTkLabel(
                f_row,
                text=f"{idx_ev + 1}.  {p_ev.name}{t_mb}",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color=TEXT_MAIN,
            ).pack(side="left", padx=12, pady=6)

            def _remover_video_editado(idx_borrar: int = idx_ev) -> None:
                if 0 <= idx_borrar < len(lista_videos_editados_locales):
                    lista_videos_editados_locales.pop(idx_borrar)
                    _guardar_memoria()
                    _renderizar_lista_videos_editados()
                    refrescar_plan_ui()
                    refrescar_texto_boton_accion()
                    autoajustar_tamano_ventana()

            ctk.CTkButton(
                f_row,
                text="X",
                command=_remover_video_editado,
                width=26,
                height=26,
                corner_radius=8,
                fg_color="transparent",
                hover_color="#ef4444",
                text_color="#ef4444",
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="right", padx=6, pady=4)

    def _seleccionar_videos_editados_dialog() -> None:
        try:
            from tkinter import filedialog
            archivos = filedialog.askopenfilenames(
                title="Seleccionar Video(s) ya Editados para Subir",
                initialdir=str(OUTPUT_DIR if OUTPUT_DIR.exists() else BASE_DIR),
                filetypes=[
                    ("Videos MP4", "*.mp4"),
                    ("Todos los Videos", "*.mp4 *.mov *.mkv *.webm"),
                    ("Todos los archivos", "*.*"),
                ],
                parent=root,
            )
            if archivos:
                for a_str in archivos:
                    p_obj = Path(a_str)
                    if p_obj.exists() and p_obj not in lista_videos_editados_locales:
                        lista_videos_editados_locales.append(p_obj)
                _guardar_memoria()
                _renderizar_lista_videos_editados()
                refrescar_plan_ui()
                refrescar_texto_boton_accion()
                autoajustar_tamano_ventana()
        except Exception as e_fd:
            messagebox.showerror("Error al seleccionar videos", str(e_fd), parent=root)

    btn_seleccionar_editados = ctk.CTkButton(
        editado_header_right,
        text="+ Seleccionar Video(s) MP4",
        command=_seleccionar_videos_editados_dialog,
        height=30,
        corner_radius=12,
        fg_color=PURPLE_MAIN,
        hover_color=PURPLE_HOVER,
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
    )
    btn_seleccionar_editados.pack(side="right")

    filas_editados_container = ctk.CTkFrame(card_video_editado, fg_color="transparent")
    filas_editados_container.pack(fill="x", padx=20, pady=(4, 12))

    def _agregar_fila_link(valor_inicial: str = "") -> None:
        if len(lista_filas_links) >= 12:
            messagebox.showinfo("Límite alcanzado", "Puedes agregar hasta 12 links simultáneos.", parent=root)
            return

        idx_f = len(lista_filas_links)
        row_f = ctk.CTkFrame(filas_links_container, fg_color="transparent")
        row_f.pack(fill="x", pady=(0, 8))

        ph = "https://www.youtube.com/shorts/..." if idx_f == 0 else f"Link #{idx_f + 1} (https://www.youtube.com/shorts/...)"
        ent = ctk.CTkEntry(
            row_f,
            placeholder_text=ph,
            corner_radius=18,
            height=42,
            fg_color=INPUT_BG,
            border_width=1,
            border_color="#2a3147",
            text_color="#ffffff",
            font=ctk.CTkFont(family="Consolas", size=14),
        )
        ent.pack(side="left", fill="x", expand=True, padx=(0, 8))
        if valor_inicial:
            ent.insert(0, valor_inicial)

        def _pegar_en_este(e=ent) -> None:
            try:
                clip = root.clipboard_get().strip()
                lineas = [l.strip().strip('"') for l in clip.splitlines() if l.strip()]
                if not lineas:
                    return
                e.delete(0, tk.END)
                e.insert(0, lineas[0])
                for l_extra in lineas[1:]:
                    if len(lista_filas_links) < 12:
                        _agregar_fila_link(l_extra)
                _actualizar_ui_filas_links()
            except Exception:
                pass

        btn_peg = ctk.CTkButton(
            row_f,
            text="Pegar",
            command=_pegar_en_este,
            corner_radius=18,
            height=42,
            width=90,
            fg_color="#1e2538",
            hover_color="#2b3550",
            text_color=TEXT_MAIN,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        )
        btn_peg.pack(side="left", padx=(0, 4))

        btn_add = ctk.CTkButton(
            row_f,
            text="+",
            command=lambda: _agregar_fila_link(),
            corner_radius=18,
            height=42,
            width=42,
            fg_color=INPUT_BG,
            hover_color="#1e2538",
            border_width=1,
            border_color="#2a3147",
            text_color="#ffffff",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        btn_add.pack(side="left")

        fila_record: Dict[str, object] = {
            "frame": row_f,
            "entry": ent,
            "btn_pegar": btn_peg,
            "btn_add": btn_add,
            "btn_del": None,
        }

        def _quitar_este(rf=row_f, fr=fila_record) -> None:
            try:
                rf.destroy()
            except Exception:
                pass
            if fr in lista_filas_links:
                lista_filas_links.remove(fr)
            _actualizar_ui_filas_links()

        btn_del = ctk.CTkButton(
            row_f,
            text="X",
            command=_quitar_este,
            corner_radius=18,
            height=42,
            width=42,
            fg_color="#261b23",
            hover_color="#dc2626",
            text_color="#f87171",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        fila_record["btn_del"] = btn_del

        lista_filas_links.append(fila_record)
        _actualizar_ui_filas_links()

    entry_url = None
    _agregar_fila_link()

    # ==========================================================================
    # PASO 2 UNIFICADO: PLAN DE SUBIDA, CANTIDAD POR DÍA Y HORARIOS INTELIGENTES
    # (Sin hueco vacío entre Canales/Link y Programación; la personalización manual
    #  se abre en una ventana emergente DESPUÉS de elegir los videos reales)
    # ==========================================================================
    card_pub = ctk.CTkFrame(root, fg_color=CARD_BG, corner_radius=22, border_width=1, border_color=CARD_BORDER)
    card_pub.pack(fill="x", padx=28, pady=(0, 12))

    pub_header = ctk.CTkFrame(card_pub, fg_color="transparent")
    pub_header.pack(fill="x", padx=20, pady=(12, 10))

    ctk.CTkLabel(
        pub_header,
        text="Plan de Subida y Programación",
        font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
        text_color=TEXT_MAIN,
    ).pack(side="left")

    # Controles fijos a la derecha (X Shorts y X/día) que NUNCA se mueven
    pub_fixed_controls = ctk.CTkFrame(pub_header, fg_color="transparent")
    pub_fixed_controls.pack(side="right")

    opt_cantidad_total = ctk.CTkOptionMenu(
        pub_fixed_controls,
        variable=cantidad_total_var,
        values=list(MAPA_CANTIDAD_TOTAL.keys()),
        corner_radius=12,
        height=30,
        width=110,
        fg_color=PURPLE_MAIN,
        button_color=PURPLE_HOVER,
        button_hover_color="#5b21b6",
        text_color="#ffffff",
        dropdown_hover_color=PURPLE_MAIN,
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
    )
    opt_cantidad_total.pack(side="left", padx=(0, 8))

    opt_por_dia = ctk.CTkOptionMenu(
        pub_fixed_controls,
        variable=shorts_por_dia_var,
        values=list(MAPA_POR_DIA.keys()),
        corner_radius=12,
        height=30,
        width=105,
        fg_color=INPUT_BG,
        button_color="#252d42",
        button_hover_color="#333e5a",
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
    )
    opt_por_dia.pack(side="left")

    # Controles extra según la estrategia (se insertan entre el título y las opciones fijas X Shorts / X día)
    frame_controles_estrategia_extra = ctk.CTkFrame(pub_header, fg_color="transparent")

    # Subframe para "Cada X hs" (Edición manual: Desde HH:MM, Cada N hs)
    frame_sub_cada_x_hs = ctk.CTkFrame(frame_controles_estrategia_extra, fg_color="transparent")

    lbl_desde = ctk.CTkLabel(
        frame_sub_cada_x_hs,
        text="Desde:",
        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        text_color=TEXT_MUTED,
    )
    lbl_desde.pack(side="left", padx=(0, 4))

    entry_hora_desde = ctk.CTkEntry(
        frame_sub_cada_x_hs,
        textvariable=hora_desde_var,
        placeholder_text="13:00",
        corner_radius=10,
        height=30,
        width=74,
        fg_color=INPUT_BG,
        border_color="#2a3147",
        text_color="#ffffff",
        justify="center",
        font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
    )
    entry_hora_desde.pack(side="left", padx=(0, 8))

    lbl_cada = ctk.CTkLabel(
        frame_sub_cada_x_hs,
        text="Cada:",
        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        text_color=TEXT_MUTED,
    )
    lbl_cada.pack(side="left", padx=(0, 4))

    entry_intervalo = ctk.CTkEntry(
        frame_sub_cada_x_hs,
        textvariable=intervalo_horas_var,
        placeholder_text="8",
        corner_radius=10,
        height=30,
        width=42,
        fg_color=INPUT_BG,
        border_color="#2a3147",
        text_color="#ffffff",
        justify="center",
        font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
    )
    entry_intervalo.pack(side="left", padx=(0, 4))

    lbl_hs = ctk.CTkLabel(
        frame_sub_cada_x_hs,
        text="hs",
        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        text_color=TEXT_MUTED,
    )
    lbl_hs.pack(side="left")

    # Subframe para "Horario Específico" (Edición manual con máscara HH:MM)
    frame_sub_horario_especifico = ctk.CTkFrame(frame_controles_estrategia_extra, fg_color="transparent")

    lbl_a_las = ctk.CTkLabel(
        frame_sub_horario_especifico,
        text="A las:",
        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        text_color=TEXT_MUTED,
    )
    lbl_a_las.pack(side="left", padx=(0, 4))

    entry_hora_esp = ctk.CTkEntry(
        frame_sub_horario_especifico,
        textvariable=hora_esp_var,
        placeholder_text="07:52",
        corner_radius=10,
        height=30,
        width=78,
        fg_color=INPUT_BG,
        border_color="#2a3147",
        text_color="#ffffff",
        justify="center",
        font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
    )
    entry_hora_esp.pack(side="left")

    def _cargar_imagen_avatar_ctk(avatar_path_str: str, size_px: int = 24) -> Optional[ctk.CTkImage]:
        if not avatar_path_str:
            return None
        key_c = f"{avatar_path_str}:{size_px}"
        if key_c in cache_avatares_ctk:
            return cache_avatares_ctk[key_c]
        try:
            p_av = Path(avatar_path_str)
            if p_av.exists():
                from PIL import Image
                pil_im = Image.open(p_av).convert("RGBA")
                ctk_im = ctk.CTkImage(light_image=pil_im, dark_image=pil_im, size=(size_px, size_px))
                cache_avatares_ctk[key_c] = ctk_im
                return ctk_im
        except Exception:
            pass
        return None

    def _sincronizar_canales_de_cuenta_activa(nuevo_cid: str, guardar_previo: bool = True) -> None:
        cid_prev = str(estado_seleccion_cuentas.get("cuenta_id") or "")
        if guardar_previo and cid_prev and str(estado_seleccion_cuentas.get("modo") or "una") == "una":
            canales_por_cuenta[cid_prev] = list(lista_canales)

        if nuevo_cid:
            estado_seleccion_cuentas["cuenta_id"] = nuevo_cid
            if nuevo_cid not in canales_por_cuenta:
                # Inicializar con los canales actuales la primera vez
                canales_por_cuenta[nuevo_cid] = list(lista_canales)
            else:
                lista_canales.clear()
                lista_canales.extend(canales_por_cuenta[nuevo_cid])
            estado_rotacion["idx"] = 0

    def refrescar_selector_cuentas_ui() -> None:
        try:
            from subir_a_youtube import listar_cuentas_vinculadas
            cuentas = listar_cuentas_vinculadas()
        except Exception:
            cuentas = [{"id": "principal", "nombre": "Canal Principal", "avatar_path": ""}]
        if not cuentas:
            cuentas = [{"id": "principal", "nombre": "Canal Principal", "avatar_path": ""}]

        mapa_cuentas_ui.clear()
        ids_validos = [str(c.get("id") or "principal") for c in cuentas]
        dict_por_id = {str(c.get("id") or "principal"): c for c in cuentas}
        for c_info in cuentas:
            cid = str(c_info.get("id") or "principal")
            cnom = str(c_info.get("nombre") or cid)
            mapa_cuentas_ui[cnom] = cid

        cid_act = str(estado_seleccion_cuentas.get("cuenta_id") or "")
        if not cid_act or cid_act not in dict_por_id:
            cid_act = ids_validos[0]
            _sincronizar_canales_de_cuenta_activa(cid_act, guardar_previo=False)
        else:
            if cid_act not in canales_por_cuenta:
                canales_por_cuenta[cid_act] = list(lista_canales)
            elif str(estado_seleccion_cuentas.get("modo") or "una") == "una":
                if canales_por_cuenta[cid_act]:
                    lista_canales.clear()
                    lista_canales.extend(canales_por_cuenta[cid_act])
                elif lista_canales:
                    canales_por_cuenta[cid_act] = list(lista_canales)

        modo_act = str(estado_seleccion_cuentas.get("modo") or "una")
        grupo_ids = [g for g in (estado_seleccion_cuentas.get("grupo_ids") or []) if g in dict_por_id]
        estado_seleccion_cuentas["grupo_ids"] = grupo_ids

        # Actualizar botón superior de Cuenta y etiqueta de Canales Fuente
        strat_ui = str(estado_seleccion_cuentas.get("estrategia") or "cross_posting")
        tag_strat = " · Cross-post" if strat_ui == "cross_posting" else " · Rotación"
        if modo_act == "todas" and len(cuentas) > 1:
            txt_btn = f"Todas ({len(cuentas)} cuentas{tag_strat}) ▾"
            img_btn = None
            lbl_titulo_canales.configure(text="Canales Fuente")
        elif modo_act == "grupo" and len(grupo_ids) >= 1:
            txt_btn = f"Grupo ({len(grupo_ids)} cuentas{tag_strat}) ▾"
            img_btn = None
            lbl_titulo_canales.configure(text="Canales Fuente")
        else:
            estado_seleccion_cuentas["modo"] = "una"
            info_c = dict_por_id.get(cid_act, cuentas[0])
            nom_c = str(info_c.get("nombre") or "Mi Canal")
            subs_val = int(info_c.get("subscribers") or 0)
            subs_tag = f" ({formatear_subs(subs_val)})" if subs_val > 0 else ""
            av_p = str(info_c.get("avatar_path") or "")
            img_btn = _cargar_imagen_avatar_ctk(av_p, size_px=24)
            txt_btn = f"{nom_c[:18]}{subs_tag} ▾"
            lbl_titulo_canales.configure(text="Canales Fuente")

        if "btn_cuenta_top" in locals() or "btn_cuenta_top" in globals():
            try:
                btn_cuenta_top.configure(text=txt_btn, image=img_btn)
            except Exception:
                pass
        renderizar_chips_canales()
        try:
            root.after(0, _actualizar_pildora_cola)
            root.after(0, _actualizar_pildora_rendimiento)
        except Exception:
            pass

    def vincular_nueva_cuenta_gui(parent_win: Optional[tk.Misc] = None) -> None:
        def _worker_vinc() -> None:
            try:
                from subir_a_youtube import vincular_nueva_cuenta_interactivo
                info_nueva = vincular_nueva_cuenta_interactivo()
                nom_c = str(info_nueva.get("nombre") or "Nueva Cuenta")
                nuevo_id = str(info_nueva.get("id") or "")

                def _ok_v() -> None:
                    if nuevo_id:
                        _sincronizar_canales_de_cuenta_activa(nuevo_id, guardar_previo=True)
                        # Una cuenta recién vinculada empieza con su propia lista de canales (copia o limpia)
                        estado_seleccion_cuentas["modo"] = "una"
                    refrescar_selector_cuentas_ui()
                    _guardar_memoria()
                    sincronizar_cuota_async()
                    messagebox.showinfo(
                        "Cuenta Vinculada",
                        f"¡Canal '{nom_c}' vinculado con éxito!\n\nAhora está seleccionado arriba a la derecha con sus propios canales guardados.",
                        parent=parent_win or root,
                    )

                root.after(0, _ok_v)
            except Exception as e_v:
                root.after(
                    0,
                    lambda msg=str(e_v): messagebox.showerror(
                        "Error al vincular cuenta",
                        f"No se pudo completar la vinculación:\n{msg}",
                        parent=parent_win or root,
                    ),
                )

        threading.Thread(target=_worker_vinc, daemon=True).start()

    # Programar está siempre activo (todos los Shorts se programan en sus horarios inteligentes)

    # FILA 2: Selector Unificado de Estrategia (a la izquierda) + Fecha Base (DD/MM blanco) + Previsualización de Salidas (blanco)
    row_plan2 = ctk.CTkFrame(card_pub, fg_color="transparent")
    row_plan2.pack(fill="x", padx=20, pady=(0, 12))

    opt_estrategia = ctk.CTkOptionMenu(
        row_plan2,
        values=["Horarios Pico", "Cada X hs", "Horario Específico"],
        variable=modo_horario_var,
        corner_radius=14,
        height=34,
        width=150,
        fg_color=INPUT_BG,
        button_color="#252d42",
        button_hover_color="#333e5a",
        text_color="#ffffff",
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
    )
    opt_estrategia.pack(side="left", padx=(0, 8))

    btn_calendario = ctk.CTkButton(
        row_plan2,
        text=_formatear_boton_fecha(fecha_elegida_var.get()),
        corner_radius=14,
        height=34,
        width=80,
        fg_color=INPUT_BG,
        hover_color="#1c2233",
        border_width=1,
        border_color="#2e3852",
        text_color="#ffffff",
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
    )
    btn_calendario.pack(side="left", padx=(0, 8))

    preview_box = ctk.CTkFrame(row_plan2, fg_color=INPUT_BG, corner_radius=14, border_width=1, border_color="#1f263a")
    preview_box.pack(side="left", fill="x", expand=True)

    lbl_preview_horarios = ctk.CTkLabel(
        preview_box,
        text="",
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        text_color="#ffffff",
        wraplength=540,
        justify="left",
    )
    lbl_preview_horarios.pack(anchor="w", padx=12, pady=6, fill="x")

    def calcular_lista_horarios_actual() -> List[Optional[str]]:
        mf = modo_fuente_var.get()
        if "Canales" in mf:
            cant_t = MAPA_CANTIDAD_TOTAL.get(cantidad_total_var.get(), 2)
        elif "Link" in mf:
            cant_ingresados = len(obtener_links_ingresados())
            cant_t = cant_ingresados if cant_ingresados > 0 else max(1, len(lista_filas_links))
        else:
            cant_t = len(lista_videos_editados_locales) if lista_videos_editados_locales else 1
        por_d = MAPA_POR_DIA.get(shorts_por_dia_var.get(), 2)
        if not programar_var.get():
            return [None] * cant_t
        raw_int = re.sub(r"\D", "", intervalo_horas_var.get())
        interv = max(1, min(24, int(raw_int))) if raw_int else 8
        est_act = modo_horario_var.get()
        if "Específ" in est_act or "especif" in est_act.lower():
            h_cand = hora_esp_var.get().strip()
        elif "Cada" in est_act:
            h_cand = hora_desde_var.get().strip()
        else:
            h_cand = "13:00"
        if ":" not in h_cand or len(h_cand) < 4:
            h_cand = "13:00"
        slots = calcular_horarios_inteligentes(
            cantidad_total=cant_t,
            por_dia=por_d,
            fecha_base_iso=fecha_elegida_var.get().strip(),
            modo_horario=est_act,
            hora_inicio=h_cand,
            intervalo_hs=interv,
        )
        return [s for s in slots]

    def refrescar_plan_ui(*_args: object) -> None:
        if _args and isinstance(_args[0], str) and _args[0] in ("Horarios Pico", "Cada X hs", "Horario Específico"):
            modo_horario_var.set(_args[0])
        _guardar_memoria()
        mf = modo_fuente_var.get()
        es_canales = "Canales" in mf
        es_editado = "Editado" in mf

        privacidad_var.set("Privado")

        if es_canales:
            opt_cantidad_total.configure(state="normal")
            opt_por_dia.configure(state="normal")
        else:
            opt_cantidad_total.configure(state="disabled")
            opt_por_dia.configure(state="disabled")

        est_act = modo_horario_var.get()
        frame_sub_cada_x_hs.pack_forget()
        frame_sub_horario_especifico.pack_forget()

        if "Cada X" in est_act:
            frame_controles_estrategia_extra.pack(side="right", padx=(0, 16))
            frame_sub_cada_x_hs.pack(side="left")
        elif "Específ" in est_act or "Fijo" in est_act:
            frame_controles_estrategia_extra.pack(side="right", padx=(0, 16))
            frame_sub_horario_especifico.pack(side="left")
        else:
            frame_controles_estrategia_extra.pack_forget()

        slots = calcular_lista_horarios_actual()
        partes_prev: List[str] = []
        modo_c_act = str(estado_seleccion_cuentas.get("modo") or "una")
        strat_c_act = str(estado_seleccion_cuentas.get("estrategia") or "cross_posting")

        from subir_a_youtube import listar_cuentas_vinculadas
        try:
            cuentas_v_plan = listar_cuentas_vinculadas() or [{"id": "principal", "nombre": "Canal Principal"}]
        except Exception:
            cuentas_v_plan = [{"id": "principal", "nombre": "Canal Principal"}]
        dict_cv = {str(c.get("id") or "principal"): c for c in cuentas_v_plan}

        if modo_c_act == "todas":
            c_plan_obj = list(cuentas_v_plan)
        elif modo_c_act == "grupo":
            g_ids_p = [g for g in (estado_seleccion_cuentas.get("grupo_ids") or []) if g in dict_cv]
            c_plan_obj = [dict_cv[g] for g in g_ids_p] if g_ids_p else [cuentas_v_plan[0]]
        else:
            cid_u = str(estado_seleccion_cuentas.get("cuenta_id") or cuentas_v_plan[0].get("id") or "principal")
            c_plan_obj = [dict_cv.get(cid_u, cuentas_v_plan[0])]

        for idx_s, s_str in enumerate(slots):
            if not s_str:
                continue
            try:
                f_part, h_part = s_str.split(" ")
                d_obj = _dt.date.fromisoformat(f_part)
                d_txt = f"{d_obj.day:02d}/{d_obj.month:02d}"
                tiempo_txt = f"{d_txt} {h_part}"
            except Exception:
                tiempo_txt = str(s_str)

            partes_prev.append(f"#{idx_s + 1} {tiempo_txt}")

        resumen_str = "  ·  ".join(partes_prev)
        if modo_c_act in ("todas", "grupo") and strat_c_act == "rotacion" and len(c_plan_obj) > 1 and len(slots) < len(c_plan_obj):
            resumen_str += f"  (Rotando: {len(c_plan_obj) - len(slots)} cuenta(s) sin video en este lote)"
        lbl_preview_horarios.configure(
            text=resumen_str,
            text_color="#ffffff",
            wraplength=540,
            justify="left",
        )
        autoajustar_tamano_ventana()
        refrescar_texto_boton_accion()

    opt_estrategia.configure(command=refrescar_plan_ui)
    opt_cantidad_total.configure(command=refrescar_plan_ui)
    opt_por_dia.configure(command=refrescar_plan_ui)

    def _filtrar_tecla_no_digito(event: tk.Event) -> Optional[str]:
        if event.keysym in ("BackSpace", "Delete", "Left", "Right", "Tab", "Home", "End", "Return"):
            return None
        if event.state & 4:  # Ctrl+C, Ctrl+V, etc.
            return None
        if event.char and not event.char.isdigit():
            return "break"
        return None

    try:
        entry_hora_desde._entry.bind("<KeyPress>", _filtrar_tecla_no_digito)
        entry_hora_esp._entry.bind("<KeyPress>", _filtrar_tecla_no_digito)
        entry_intervalo._entry.bind("<KeyPress>", _filtrar_tecla_no_digito)
    except Exception:
        pass

    def _crear_formateador_hora(var_hora: tk.StringVar, entry_ref: Any) -> Callable[..., None]:
        en_formato = [False]
        prev_h = [var_hora.get()]

        def _on_escribir(*_args: object) -> None:
            if en_formato[0]:
                return
            w_foc = root.focus_get()
            pos_antes = 0
            ent_inner = getattr(entry_ref, "_entry", None)
            if w_foc == ent_inner:
                try:
                    pos_antes = w_foc.index(tk.INSERT)
                except Exception:
                    pos_antes = len(var_hora.get())

            val = var_hora.get()
            prev = prev_h[0]
            is_backspace = len(val) < len(prev)
            digitos = [c for c in val if c.isdigit()][:4]

            pos_nueva = pos_antes
            if not digitos:
                nuevo = ""
                pos_nueva = 0
            elif is_backspace:
                nuevo = val if all(c.isdigit() or c == ":" for c in val) else "".join(digitos)
            elif len(digitos) <= 2:
                nuevo = "".join(digitos)
                if len(digitos) == 2:
                    nuevo = "".join(digitos) + ":"
                    if pos_antes == 2:
                        pos_nueva = 3
            else:
                h = min(23, int("".join(digitos[:2])))
                m_raw = "".join(digitos[2:])
                if len(m_raw) == 2:
                    m_raw = f"{min(59, int(m_raw)):02d}"
                nuevo = f"{h:02d}:{m_raw}"
                if pos_antes == 2:
                    pos_nueva = 3

            if nuevo != val:
                en_formato[0] = True
                var_hora.set(nuevo)
                en_formato[0] = False
                if w_foc == ent_inner:
                    root.after_idle(lambda w=w_foc, p=pos_nueva, n=nuevo: (w.icursor(min(len(n), p)) if (hasattr(w, "winfo_exists") and w.winfo_exists()) else None))

            prev_h[0] = nuevo
            refrescar_plan_ui()

        return _on_escribir

    _en_formato_interv = [False]

    def _on_intervalo_escribir(*_args: object) -> None:
        if _en_formato_interv[0]:
            return
        val = intervalo_horas_var.get()
        digitos = [c for c in val if c.isdigit()][:2]
        nuevo = "".join(digitos)
        if nuevo != val:
            _en_formato_interv[0] = True
            intervalo_horas_var.set(nuevo)
            _en_formato_interv[0] = False
        refrescar_plan_ui()

    hora_esp_var.trace_add("write", _crear_formateador_hora(hora_esp_var, entry_hora_esp))
    hora_desde_var.trace_add("write", _crear_formateador_hora(hora_desde_var, entry_hora_desde))
    intervalo_horas_var.trace_add("write", _on_intervalo_escribir)

    def refrescar_texto_boton_accion() -> None:
        """Actualiza el texto y estilo de los botones de acción para todas las combinaciones de Fuente, Contenido y Subida/Guardado."""
        try:
            mf = modo_fuente_var.get()
            es_editado = "Editado" in mf
            es_canales = "Canales" in mf
            es_link = not es_editado and not es_canales
            es_manual = "Manual" in modo_subida_var.get()

            # 1. TEXTO PARA EL BOTÓN PRINCIPAL (SUBIR A YOUTUBE)
            if es_manual:
                txt_subir = "ELEGIR VIDEO Y EDITAR GUION" if not es_editado else "IMPORTAR Y EDITAR GUION"
            elif es_editado:
                txt_subir = "IMPORTAR Y SUBIR A YOUTUBE"
            elif es_canales:
                txt_subir = "CREAR Y SUBIR EN 1 CLIC"
            else:
                txt_subir = "CREAR Y SUBIR DESDE LINK"

            if btn_auto_1clic is not None:
                btn_auto_1clic.configure(
                    text=txt_subir,
                    fg_color=PURPLE_MAIN,
                    hover_color=PURPLE_HOVER,
                    text_color="#ffffff",
                )

            # 2. TEXTO PARA EL BOTÓN SECUNDARIO (GUARDAR EN CARPETA DIRECTAMENTE)
            if not es_editado:
                txt_guardar = "EDITAR Y GUARDAR EN CARPETA" if es_manual else "CREAR Y GUARDAR EN CARPETA"

                if btn_guardar_carpeta is not None:
                    btn_guardar_carpeta.configure(
                        text=txt_guardar,
                        fg_color="#182235",
                        hover_color="#23324f",
                        text_color="#ffffff",
                    )
        except Exception:
            pass

    def actualizar_modo_vista(*_args: object) -> None:
        _guardar_memoria()
        renderizar_chips_canales()
        _renderizar_lista_videos_editados()
        card_canales.pack_forget()
        card_link.pack_forget()
        card_video_editado.pack_forget()

        mf = modo_fuente_var.get()
        es_editado = "Editado" in mf
        if "Canales" in mf:
            card_canales.pack(fill="x")
        elif "Link" in mf:
            card_link.pack(fill="x")
        else:
            card_video_editado.pack(fill="x")

        if btn_guardar_carpeta is not None and row_botones_accion is not None and btn_auto_1clic is not None:
            if es_editado:
                btn_guardar_carpeta.grid_remove()
                row_botones_accion.grid_columnconfigure(1, weight=0)
                btn_auto_1clic.grid_configure(padx=0)
            else:
                row_botones_accion.grid_columnconfigure(0, weight=8)
                row_botones_accion.grid_columnconfigure(1, weight=2)
                btn_auto_1clic.grid_configure(padx=(0, 8))
                btn_guardar_carpeta.grid(row=0, column=1, sticky="nsew")

        refrescar_plan_ui()
        refrescar_texto_boton_accion()
        autoajustar_tamano_ventana()

    # ==========================================================================
    # VENTANA DE AJUSTES (CON TOGGLE DE MODO, CONTENIDO IA/MANUAL Y MODELO ARGON 4)
    # ==========================================================================
    def abrir_ventana_ajustes() -> None:
        win = ctk.CTkToplevel(root)
        win.withdraw()
        win.title("Ajustes y Herramientas")
        win.geometry("600x750")
        win.resizable(False, False)
        win.configure(fg_color=BG_DARK)
        win.transient(root)

        # 1. Modos de Trabajo principales
        card_modo = ctk.CTkFrame(win, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card_modo.pack(fill="x", padx=24, pady=(18, 10))

        ctk.CTkLabel(
            card_modo,
            text="Modo de Obtención de Videos",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w", padx=18, pady=(10, 4))

        ctk.CTkSegmentedButton(
            card_modo,
            values=["Canales Seleccionados", "Link de Video", "Subir Video Editado"],
            variable=modo_fuente_var,
            command=actualizar_modo_vista,
            corner_radius=14,
            height=32,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            selected_color=PURPLE_MAIN,
        ).pack(fill="x", padx=18, pady=(0, 12))

        ctk.CTkLabel(
            card_modo,
            text="Modo de Publicación",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w", padx=18, pady=(2, 4))

        def _al_cambiar_modo_subida(_val=None):
            _guardar_memoria()
            refrescar_texto_boton_accion()

        ctk.CTkSegmentedButton(
            card_modo,
            values=["Subida Automática", "Revisión Previa", "Edición Manual"],
            variable=modo_subida_var,
            command=_al_cambiar_modo_subida,
            corner_radius=14,
            height=32,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            selected_color=PURPLE_MAIN,
        ).pack(fill="x", padx=18, pady=(0, 14))

        # 2. Tarjeta de APIs, Cuotas y Límites (YouTube y Gemini / Argon 4)
        card_api = ctk.CTkFrame(win, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card_api.pack(fill="x", padx=24, pady=(0, 10))

        # Fila de Cuota Diaria de YouTube dentro de card_api
        row_cuota_ajustes = ctk.CTkFrame(card_api, fg_color="#101524", corner_radius=14, border_width=1, border_color="#222b42")
        row_cuota_ajustes.pack(fill="x", padx=18, pady=(14, 10))

        top_cuota_aj = ctk.CTkFrame(row_cuota_ajustes, fg_color="transparent")
        top_cuota_aj.pack(fill="x", padx=14, pady=(8, 8))

        lbl_cuota_ajustes_txt = ctk.CTkLabel(
            top_cuota_aj,
            text="Cuota Diaria de YouTube",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_MAIN,
        )
        lbl_cuota_ajustes_txt.pack(side="left")

        def _mostrar_ayuda_cuota_yt():
            win_h = ctk.CTkToplevel(win)
            win_h.withdraw()
            win_h.title("Guía de Cuota de YouTube")
            win_h.resizable(False, False)
            win_h.configure(fg_color=BG_DARK)
            aplicar_icono_ventana(win_h)
            win_h.transient(win)
            win_h.grab_set()

            f_c = ctk.CTkFrame(win_h, fg_color="#101524", corner_radius=16, border_width=1, border_color="#222b42")
            f_c.pack(fill="both", expand=True, padx=14, pady=14)

            ctk.CTkLabel(
                f_c,
                text="¿Cómo funciona la cuota de subida?",
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                text_color=TEXT_MAIN,
            ).pack(anchor="w", padx=16, pady=(12, 8))

            ctk.CTkLabel(
                f_c,
                text="• Cada proyecto de Google Cloud otorga 10.000 unidades diarias (~6 Shorts por día).\n\n• Podés agregar más archivos client_secrets.json de otros proyectos gratuitos para sumar +6 Shorts por día por cada proyecto.\n\n• La cuota se reinicia automáticamente todos los días a las 04:00 AM (Argentina / UTC-3).",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="#cbd5e1",
                justify="left",
                anchor="w",
                wraplength=480,
            ).pack(fill="x", padx=16, pady=(0, 14))

            ctk.CTkButton(
                f_c,
                text="Entendido",
                command=win_h.destroy,
                corner_radius=10,
                height=28,
                width=100,
                fg_color=PURPLE_MAIN,
                hover_color=PURPLE_HOVER,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            ).pack(pady=(0, 6))

            win_h.update_idletasks()
            w_req = max(520, win_h.winfo_reqwidth())
            h_req = win_h.winfo_reqheight() + 10
            try:
                x = win.winfo_x() + (win.winfo_width() // 2) - (w_req // 2)
                y = win.winfo_y() + (win.winfo_height() // 2) - (h_req // 2)
                win_h.geometry(f"{w_req}x{h_req}+{max(0, x)}+{max(0, y)}")
            except Exception:
                win_h.geometry(f"{w_req}x{h_req}")
            win_h.deiconify()

        btn_ayuda_cuota_yt = ctk.CTkButton(
            top_cuota_aj,
            text="?",
            command=_mostrar_ayuda_cuota_yt,
            corner_radius=11,
            width=22,
            height=22,
            fg_color="#1e293b",
            hover_color="#334155",
            border_width=1,
            border_color="#334155",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=CYAN_ACCENT,
        )
        btn_ayuda_cuota_yt.pack(side="left", padx=(8, 0))

        ctk.CTkButton(
            top_cuota_aj,
            text="+ Agregar API (+6 Shorts/día)",
            command=lambda: abrir_dialogo_explicativo_api_json(win),
            corner_radius=12,
            height=28,
            fg_color="#1e293b",
            hover_color="#334155",
            text_color=CYAN_ACCENT,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        ).pack(side="right")

        # Monitor de cuotas y estado en vivo de Gemini / Argon
        frame_probe = ctk.CTkFrame(card_api, fg_color="#101524", corner_radius=14, border_width=1, border_color="#222b42")
        frame_probe.pack(fill="x", padx=18, pady=(0, 10))

        row_probe_top = ctk.CTkFrame(frame_probe, fg_color="transparent")
        row_probe_top.pack(fill="x", padx=14, pady=(10, 8))

        ctk.CTkLabel(
            row_probe_top,
            text="Estado actual de modelos y cuotas",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(side="left")

        def _mostrar_ayuda_cuotas():
            win_h = ctk.CTkToplevel(win)
            win_h.withdraw()
            win_h.title("Guía de Colores y Cuotas")
            win_h.resizable(False, False)
            win_h.configure(fg_color=BG_DARK)
            aplicar_icono_ventana(win_h)
            win_h.transient(win)
            win_h.grab_set()

            f_c = ctk.CTkFrame(win_h, fg_color="#101524", corner_radius=16, border_width=1, border_color="#222b42")
            f_c.pack(fill="both", expand=True, padx=14, pady=14)

            ctk.CTkLabel(
                f_c,
                text="Significado de Colores y Cuotas",
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                text_color=TEXT_MAIN,
            ).pack(anchor="w", padx=16, pady=(12, 10))

            items = [
                ("🟢 Borde Verde (Disponible):", "Cuentas listas con cuota activa. Si consumiste alguna cuenta por cuota diaria (429), muestra ej. 3/4 en verde porque las restantes están listas para trabajar.", "#34d399"),
                ("🟠 Borde Naranja (Tráfico):", "La cuenta que se perdió falló por congestión, saturación temporal o timeout de Google (503 / >1.6s), no por falta de cuota.", "#fbbf24"),
                ("🔴 Borde Rojo (Agotado):", "Todas las cuentas del pool agotaron el cupo diario de solicitudes (0/4 con 429).", "#f87171"),
                ("🟣 Borde Púrpura (Plan Pago):", "Modelo que requiere plan con facturación en Google AI Studio (sin cuota gratuita).", "#a5b4fc"),
            ]
            for tit, desc, col in items:
                r = ctk.CTkFrame(f_c, fg_color="transparent")
                r.pack(fill="x", padx=16, pady=4)
                ctk.CTkLabel(r, text=tit, font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=col, width=175, anchor="w").pack(side="left", anchor="n")
                ctk.CTkLabel(r, text=desc, font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#cbd5e1", anchor="w", justify="left", wraplength=420).pack(side="left", fill="x", expand=True)

            f_info = ctk.CTkFrame(f_c, fg_color="#151b2e", corner_radius=10, border_width=1, border_color="#2a3350")
            f_info.pack(fill="x", padx=16, pady=(12, 12))

            ctk.CTkLabel(
                f_info,
                text="⏰ Reinicio diario: Google reinicia las cuotas a las 00:00 Pacífico (04:00 AM hora de Argentina / UTC-3).\n👥 Multi-cuenta: Comprueba todas las cuentas vinculadas en paralelo. Si todas están sanas muestra solo el nombre (ej: 3.8); si consumiste cuota o hay fallas, indica las cuentas activas (ej: 3/4).",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color="#94a3b8",
                justify="left",
                anchor="w",
                wraplength=560,
            ).pack(fill="x", padx=10, pady=8)

            ctk.CTkButton(
                f_c,
                text="Entendido",
                command=win_h.destroy,
                corner_radius=10,
                height=28,
                width=100,
                fg_color=PURPLE_MAIN,
                hover_color=PURPLE_HOVER,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            ).pack(pady=(0, 6))

            win_h.update_idletasks()
            w_req = max(630, win_h.winfo_reqwidth())
            h_req = win_h.winfo_reqheight() + 10
            try:
                x = win.winfo_x() + (win.winfo_width() // 2) - (w_req // 2)
                y = win.winfo_y() + (win.winfo_height() // 2) - (h_req // 2)
                win_h.geometry(f"{w_req}x{h_req}+{max(0, x)}+{max(0, y)}")
            except Exception:
                win_h.geometry(f"{w_req}x{h_req}")
            win_h.deiconify()

        btn_ayuda = ctk.CTkButton(
            row_probe_top,
            text="?",
            command=_mostrar_ayuda_cuotas,
            corner_radius=11,
            width=22,
            height=22,
            fg_color="#1e293b",
            hover_color="#334155",
            border_width=1,
            border_color="#334155",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=CYAN_ACCENT,
        )
        btn_ayuda.pack(side="left", padx=(8, 0))

        frame_filas_modelos = ctk.CTkFrame(frame_probe, fg_color="transparent")
        frame_filas_modelos.pack(fill="x", padx=10, pady=(0, 12))
        frame_filas_modelos.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="model_box")

        def _render_resultado_modelos(lista_res: List[Dict[str, Any]]):
            for w in frame_filas_modelos.winfo_children():
                try:
                    w.destroy()
                except Exception:
                    pass

            for idx, item in enumerate(lista_res):
                c_box = ctk.CTkFrame(
                    frame_filas_modelos,
                    fg_color=item.get("color_bg", "#151a2d"),
                    border_color=item.get("color_borde", "#334155"),
                    border_width=2,
                    corner_radius=12,
                    height=42,
                )
                c_box.grid(row=0, column=idx, padx=4, pady=2, sticky="nsew")
                c_box.pack_propagate(False)

                ctk.CTkLabel(
                    c_box,
                    text=item.get("nombre_corto", item.get("nombre", "")),
                    font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                    text_color="#ffffff",
                ).pack(expand=True, fill="both")

        def _ejecutar_diagnostico_ia():
            btn_probe_ia.configure(state="disabled", text="Verificando...")
            for w in frame_filas_modelos.winfo_children():
                try:
                    w.destroy()
                except Exception:
                    pass
            lbl_cargando = ctk.CTkLabel(
                frame_filas_modelos,
                text="Comprobando disponibilidad en tiempo real con Google...",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=CYAN_ACCENT,
            )
            lbl_cargando.grid(row=0, column=0, columnspan=4, pady=10)

            def _worker():
                from shorts_engine.gemini_ia import auditar_estado_pool_en_vivo
                res = auditar_estado_pool_en_vivo()
                def _ui():
                    btn_probe_ia.configure(state="normal", text="Refrescar")
                    _render_resultado_modelos(res)
                win.after(0, _ui)

            threading.Thread(target=_worker, daemon=True).start()

        btn_probe_ia = ctk.CTkButton(
            row_probe_top,
            text="Refrescar",
            command=_ejecutar_diagnostico_ia,
            corner_radius=10,
            height=28,
            width=90,
            fg_color="#1e293b",
            hover_color="#334155",
            border_width=1,
            border_color="#334155",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#e2e8f0",
        )
        btn_probe_ia.pack(side="right")

        # Cargar plantilla inicial de cajas
        from shorts_engine.gemini_ia import obtener_modelos_plantilla
        _render_resultado_modelos(obtener_modelos_plantilla())

        # Contenedor de Claves API dentro de card_api (encuadre propio)
        frame_claves = ctk.CTkFrame(card_api, fg_color="#101524", corner_radius=14, border_width=1, border_color="#222b42")
        frame_claves.pack(fill="x", padx=18, pady=(0, 14))

        top_api = ctk.CTkFrame(frame_claves, fg_color="transparent")
        top_api.pack(fill="x", padx=14, pady=(10, 8))

        ctk.CTkLabel(
            top_api,
            text="Claves API",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(side="left")

        def _mostrar_ayuda_api():
            win_h = ctk.CTkToplevel(win)
            win_h.withdraw()
            win_h.title("Guía de Claves API")
            win_h.resizable(False, False)
            win_h.configure(fg_color=BG_DARK)
            aplicar_icono_ventana(win_h)
            win_h.transient(win)
            win_h.grab_set()

            f_c = ctk.CTkFrame(win_h, fg_color="#101524", corner_radius=16, border_width=1, border_color="#222b42")
            f_c.pack(fill="both", expand=True, padx=14, pady=14)

            ctk.CTkLabel(
                f_c,
                text="Claves API de Gemini / Argon 4",
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                text_color=TEXT_MAIN,
            ).pack(anchor="w", padx=16, pady=(12, 8))

            ctk.CTkLabel(
                f_c,
                text="• Podés ingresar 1 o varias claves (una por línea o separadas por coma).\n\n• La app rota automáticamente entre cuentas si alguna agota su cuota diaria (429).\n\n• Podés obtener claves gratuitas en Google AI Studio con cualquier cuenta de Google.",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="#cbd5e1",
                justify="left",
                anchor="w",
                wraplength=480,
            ).pack(fill="x", padx=16, pady=(0, 14))

            ctk.CTkButton(
                f_c,
                text="Entendido",
                command=win_h.destroy,
                corner_radius=10,
                height=28,
                width=100,
                fg_color=PURPLE_MAIN,
                hover_color=PURPLE_HOVER,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            ).pack(pady=(0, 6))

            win_h.update_idletasks()
            w_req = max(520, win_h.winfo_reqwidth())
            h_req = win_h.winfo_reqheight() + 10
            try:
                x = win.winfo_x() + (win.winfo_width() // 2) - (w_req // 2)
                y = win.winfo_y() + (win.winfo_height() // 2) - (h_req // 2)
                win_h.geometry(f"{w_req}x{h_req}+{max(0, x)}+{max(0, y)}")
            except Exception:
                win_h.geometry(f"{w_req}x{h_req}")
            win_h.deiconify()

        btn_ayuda_api = ctk.CTkButton(
            top_api,
            text="?",
            command=_mostrar_ayuda_api,
            corner_radius=11,
            width=22,
            height=22,
            fg_color="#1e293b",
            hover_color="#334155",
            border_width=1,
            border_color="#334155",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=CYAN_ACCENT,
        )
        btn_ayuda_api.pack(side="left", padx=(8, 0))

        ctk.CTkButton(
            top_api,
            text="Obtener Clave Gratis",
            command=lambda: webbrowser.open("https://aistudio.google.com/apikey"),
            corner_radius=14,
            height=28,
            width=140,
            fg_color="#1e293b",
            hover_color="#334155",
            text_color=CYAN_ACCENT,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).pack(side="right")

        keys_existentes = obtener_gemini_api_keys()

        row_k_bottom = ctk.CTkFrame(frame_claves, fg_color="transparent")
        row_k_bottom.pack(fill="x", padx=14, pady=(0, 10))

        n_ini = len(keys_existentes)
        lbl_status_k = ctk.CTkLabel(
            row_k_bottom,
            text=f"Pool activo: {n_ini} cuenta{'s' if n_ini != 1 else ''} vinculada{'s' if n_ini != 1 else ''}" if n_ini else "Sin claves cargadas",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#ffffff",
        )
        lbl_status_k.pack(side="left")

        def _actualizar_status_pool(n_k: int) -> None:
            lbl_status_k.configure(
                text=f"Pool activo: {n_k} cuenta{'s' if n_k != 1 else ''} vinculada{'s' if n_k != 1 else ''}" if n_k else "Sin claves cargadas",
                text_color="#ffffff" if n_k else "#f59e0b",
            )

        def _abrir_dialogo_editar_claves() -> None:
            win_e = ctk.CTkToplevel(win)
            win_e.title("Editar Lista de Claves API")
            win_e.geometry("520x400")
            win_e.resizable(False, False)
            aplicar_icono_ventana(win_e)
            win_e.transient(win)
            win_e.grab_set()

            try:
                win_e.update_idletasks()
                x = win.winfo_x() + (win.winfo_width() // 2) - 260
                y = win.winfo_y() + (win.winfo_height() // 2) - 200
                win_e.geometry(f"+{max(0, x)}+{max(0, y)}")
            except Exception:
                pass

            f_c = ctk.CTkFrame(win_e, fg_color="#101524", corner_radius=16, border_width=1, border_color="#222b42")
            f_c.pack(fill="both", expand=True, padx=14, pady=14)

            ctk.CTkLabel(
                f_c,
                text="Lista de Claves API de Gemini / Argon 4",
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                text_color=TEXT_MAIN,
            ).pack(anchor="w", padx=16, pady=(12, 4))

            ctk.CTkLabel(
                f_c,
                text="Ingresá una clave por línea. Podés agregar, editar o eliminar claves del pool.",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="#94a3b8",
                anchor="w",
            ).pack(anchor="w", padx=16, pady=(0, 10))

            txt_edit = ctk.CTkTextbox(
                f_c,
                corner_radius=12,
                fg_color=INPUT_BG,
                border_color="#2e364f",
                border_width=1,
                font=ctk.CTkFont(family="Consolas", size=12),
            )
            txt_edit.pack(fill="both", expand=True, padx=16, pady=(0, 14))

            claves_actuales = obtener_gemini_api_keys()
            if claves_actuales:
                txt_edit.insert("1.0", "\n".join(claves_actuales))

            row_btns = ctk.CTkFrame(f_c, fg_color="transparent")
            row_btns.pack(fill="x", padx=16, pady=(0, 6))

            def _guardar_desde_editor() -> None:
                k_raw = txt_edit.get("1.0", "end").strip()
                keys_lista = extraer_gemini_api_keys(k_raw)
                guardar_gemini_api_key("\n".join(keys_lista))
                _actualizar_status_pool(len(keys_lista))
                win_e.destroy()
                if keys_lista:
                    messagebox.showinfo("Claves Guardadas", f"Se guardaron {len(keys_lista)} clave(s) en el pool.", parent=win)
                else:
                    messagebox.showwarning("Atención", "No se detectó ninguna clave válida. El pool quedó vacío.", parent=win)

            ctk.CTkButton(
                row_btns,
                text="Cancelar",
                command=win_e.destroy,
                corner_radius=10,
                height=30,
                width=100,
                fg_color="#1e293b",
                hover_color="#334155",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#e2e8f0",
            ).pack(side="left")

            ctk.CTkButton(
                row_btns,
                text="Guardar Cambios",
                command=_guardar_desde_editor,
                corner_radius=10,
                height=30,
                width=130,
                fg_color=GREEN_ACCENT,
                hover_color="#059669",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#052e16",
            ).pack(side="right")

        ctk.CTkButton(
            top_api,
            text="Editar Lista",
            command=_abrir_dialogo_editar_claves,
            corner_radius=14,
            height=28,
            width=105,
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#e2e8f0",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).pack(side="right", padx=(0, 8))

        def _pegar_desde_portapapeles() -> None:
            try:
                clip_raw = win.clipboard_get()
            except Exception:
                clip_raw = ""

            if not clip_raw or not clip_raw.strip():
                messagebox.showwarning(
                    "Portapapeles Vacío",
                    "No se encontró texto en el portapapeles.\nCopiá una API Key de Google AI Studio e intentá de nuevo.",
                    parent=win,
                )
                return

            candidatas = extraer_gemini_api_keys(clip_raw)
            if not candidatas:
                messagebox.showwarning(
                    "Clave No Válida",
                    "El texto del portapapeles no coincide con una API Key válida de Gemini (debe tener al menos 20 caracteres).",
                    parent=win,
                )
                return

            actuales = obtener_gemini_api_keys()
            nuevas = [k for k in candidatas if k not in actuales]

            if not nuevas:
                messagebox.showinfo(
                    "Ya Registrada",
                    "La clave copiada ya está registrada en el pool.",
                    parent=win,
                )
                return

            totales = actuales + nuevas
            guardar_gemini_api_key("\n".join(totales))
            _actualizar_status_pool(len(totales))

            cant_nuevas = len(nuevas)
            msg = f"Se agregó {cant_nuevas} clave nueva al pool." if cant_nuevas == 1 else f"Se agregaron {cant_nuevas} claves nuevas al pool."
            messagebox.showinfo("Clave Agregada", f"{msg}\nTotal en el pool: {len(totales)} cuenta{'s' if len(totales) != 1 else ''}.", parent=win)

        ctk.CTkButton(
            row_k_bottom,
            text="Pegar desde Portapapeles",
            command=_pegar_desde_portapapeles,
            corner_radius=14,
            height=30,
            width=180,
            fg_color=GREEN_ACCENT,
            hover_color="#059669",
            text_color="#052e16",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).pack(side="right")
        # 4. Carpetas Output y Assets (estilo píldoras inferiores lado a lado)
        row_pildoras_carpetas = ctk.CTkFrame(win, fg_color="transparent")
        row_pildoras_carpetas.pack(fill="x", padx=24, pady=(0, 14))

        ctk.CTkButton(
            row_pildoras_carpetas,
            text="Carpeta Assets",
            command=abrir_carpeta_assets,
            corner_radius=14,
            height=38,
            fg_color=INPUT_BG,
            hover_color="#1e2538",
            border_width=1,
            border_color="#2a3147",
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        ).pack(side="left", fill="both", expand=True, padx=(0, 6))

        ctk.CTkButton(
            row_pildoras_carpetas,
            text="Carpeta Output",
            command=abrir_carpeta_salida,
            corner_radius=14,
            height=38,
            fg_color=INPUT_BG,
            hover_color="#1e2538",
            border_width=1,
            border_color="#2a3147",
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        ).pack(side="right", fill="both", expand=True, padx=(6, 0))

        # 5. Tarjeta de Actualizaciones de GitHub / Repositorio
        card_actualizacion = ctk.CTkFrame(win, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card_actualizacion.pack(fill="x", padx=24, pady=(0, 14))

        row_act_inner = ctk.CTkFrame(card_actualizacion, fg_color="transparent")
        row_act_inner.pack(fill="x", padx=18, pady=12)

        f_txt_act = ctk.CTkFrame(row_act_inner, fg_color="transparent")
        f_txt_act.pack(side="left", fill="both", expand=True)

        lbl_tit_act = ctk.CTkLabel(
            f_txt_act,
            text="Actualizaciones de la Aplicación",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_MAIN,
            anchor="w",
        )
        lbl_tit_act.pack(anchor="w")

        lbl_estado_act = ctk.CTkLabel(
            f_txt_act,
            text="Comprobando repositorio...",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
            anchor="w",
        )
        lbl_estado_act.pack(anchor="w")

        def _reiniciar_app_local():
            try:
                import subprocess as _subp, sys as _sys, os as _os
                win.destroy()
                _subp.Popen([_sys.executable, _sys.argv[0]], cwd=str(BASE_DIR))
                _os._exit(0)
            except Exception as e_rst:
                messagebox.showerror("Error al reiniciar", f"Por favor cerrá y volvé a abrir la app manualmente:\n{e_rst}")

        def _ejecutar_pull_actualizacion():
            btn_accion_act.configure(text="Descargando...", state="disabled")
            lbl_estado_act.configure(text="Descargando última versión desde GitHub...", text_color=CYAN_ACCENT)

            def _worker_pull():
                ok_pull, msg_pull = ejecutar_actualizacion_repo(BASE_DIR)
                def _ui_fin_pull():
                    if ok_pull:
                        lbl_estado_act.configure(text="Actualización descargada con éxito.", text_color=GREEN_ACCENT)
                        btn_accion_act.configure(
                            text="Reiniciar App",
                            state="normal",
                            fg_color=GREEN_ACCENT,
                            hover_color="#059669",
                            text_color="#052e16",
                            command=_reiniciar_app_local,
                        )
                        if btn_ajustes is not None:
                            btn_ajustes.configure(text="Ajustes", border_color=CARD_BORDER, text_color=TEXT_MAIN)

                        resp = messagebox.askyesno(
                            "Actualización Completada",
                            "¡Shorts Studio se actualizó correctamente a la última versión!\n\n¿Deseas reiniciar la aplicación ahora para aplicar los cambios?",
                            parent=win,
                        )
                        if resp:
                            _reiniciar_app_local()
                    else:
                        lbl_estado_act.configure(text=f"Error: {msg_pull[:60]}", text_color="#f87171")
                        btn_accion_act.configure(
                            text="Reintentar",
                            state="normal",
                            fg_color=PURPLE_MAIN,
                            command=_ejecutar_pull_actualizacion,
                        )
                        messagebox.showwarning("Fallo al actualizar", f"No se pudo completar la actualización automática:\n\n{msg_pull}", parent=win)

                try:
                    root.after(0, _ui_fin_pull)
                except Exception:
                    pass

            threading.Thread(target=_worker_pull, daemon=True).start()

        def _verificar_en_ajustes(forzar: bool = False):
            if forzar:
                lbl_estado_act.configure(text="Conectando con GitHub...", text_color=TEXT_MUTED)
                btn_accion_act.configure(text="Buscando...", state="disabled")

            def _worker_chk():
                hay_upd, cant_upd, msg_upd = comprobar_actualizacion_repo(BASE_DIR)
                def _ui_fin_chk():
                    try:
                        if hay_upd:
                            lbl_estado_act.configure(
                                text=f"Hay {cant_upd} mejora{'s' if cant_upd != 1 else ''} nueva{'s' if cant_upd != 1 else ''} disponible{'s' if cant_upd != 1 else ''} en GitHub",
                                text_color="#facc15",
                            )
                            btn_accion_act.configure(
                                text="Actualizar Ahora",
                                state="normal",
                                fg_color=GREEN_ACCENT,
                                hover_color="#059669",
                                text_color="#052e16",
                                command=_ejecutar_pull_actualizacion,
                            )
                            if btn_ajustes is not None:
                                btn_ajustes.configure(
                                    text=f"Ajustes ({cant_upd})",
                                    border_color="#facc15",
                                    text_color="#facc15",
                                )
                        else:
                            lbl_estado_act.configure(
                                text="La app está al día con la última versión de GitHub.",
                                text_color="#94a3b8",
                            )
                            btn_accion_act.configure(
                                text="Buscar Actualizaciones",
                                state="normal",
                                fg_color=INPUT_BG,
                                hover_color="#1e2538",
                                text_color="#ffffff",
                                command=lambda: _verificar_en_ajustes(forzar=True),
                            )
                            if btn_ajustes is not None:
                                btn_ajustes.configure(text="Ajustes", border_color=CARD_BORDER, text_color=TEXT_MAIN)
                    except Exception:
                        pass

                try:
                    root.after(0, _ui_fin_chk)
                except Exception:
                    pass

            threading.Thread(target=_worker_chk, daemon=True).start()

        btn_accion_act = ctk.CTkButton(
            row_act_inner,
            text="Buscar Actualizaciones",
            corner_radius=12,
            height=32,
            fg_color=INPUT_BG,
            hover_color="#1e2538",
            border_width=1,
            border_color="#2a3147",
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=lambda: _verificar_en_ajustes(forzar=True),
        )
        btn_accion_act.pack(side="right")

        _verificar_en_ajustes(forzar=False)

        aplicar_icono_ventana(win)
        win.update_idletasks()
        req_h = win.winfo_reqheight() + 8
        try:
            rx = root.winfo_x() + (root.winfo_width() // 2) - 300
            ry = root.winfo_y() + (root.winfo_height() // 2) - (req_h // 2)
            win.geometry(f"600x{req_h}+{max(0, rx)}+{max(0, ry)}")
        except Exception:
            win.geometry(f"600x{req_h}")
        win.deiconify()
        win.lift()
        win.focus_force()
        win.grab_set()

    def finalizar_app_completamente() -> None:
        try:
            root.destroy()
        except Exception:
            pass
        os._exit(0)

    def al_cerrar_ventana_x() -> None:
        # Si está editando/subiendo Reels, al tocar la X pasa a segundo plano sin cortar nada;
        # al volver a abrir el icono del Escritorio/Inicio, la ventana reaparece con el progreso actual.
        if editando_lock.locked():
            root.withdraw()
        else:
            finalizar_app_completamente()

    root.protocol("WM_DELETE_WINDOW", al_cerrar_ventana_x)

    def _vigilar_senal_mostrar_ventana() -> None:
        sig_file = BASE_DIR / "temp_build" / "mostrar_ventana.signal"
        if sig_file.exists():
            try:
                sig_file.unlink()
            except Exception:
                pass
            try:
                root.deiconify()
                root.state("normal")
                root.attributes("-topmost", True)
                root.update()
                root.attributes("-topmost", False)
                root.lift()
                root.focus_force()
            except Exception:
                pass
        root.after(400, _vigilar_senal_mostrar_ventana)

    root.after(400, _vigilar_senal_mostrar_ventana)

    def abrir_selector_cuentas_popup() -> None:
        pop = ctk.CTkToplevel(root)
        pop.title("Elegir Cuenta o Grupo de Subida")
        pop.geometry("490x560")
        pop.resizable(False, False)
        pop.configure(fg_color=BG_DARK)
        pop.transient(root)
        aplicar_icono_ventana(pop)
        pop.grab_set()

        pop.grid_columnconfigure(0, weight=1)
        pop.grid_rowconfigure(3, weight=1)

        top_header_pop = ctk.CTkFrame(pop, fg_color="transparent")
        top_header_pop.grid(row=0, column=0, sticky="ew", padx=22, pady=(16, 10))

        lbl_tit_pop = ctk.CTkLabel(
            top_header_pop,
            text="Elegir Cuenta de Subida",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=TEXT_MAIN,
        )
        lbl_tit_pop.pack(side="left")

        ctk.CTkButton(
            top_header_pop,
            text="+ Vincular Nueva Cuenta",
            command=lambda: (pop.destroy(), vincular_nueva_cuenta_gui(root)),
            corner_radius=12,
            height=30,
            fg_color="#1e293b",
            hover_color="#334155",
            text_color=CYAN_ACCENT,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        ).pack(side="right")

        try:
            from subir_a_youtube import listar_cuentas_vinculadas
            cuentas_disp = listar_cuentas_vinculadas()
        except Exception:
            cuentas_disp = [{"id": "principal", "nombre": "Canal Principal", "avatar_path": ""}]
        if not cuentas_disp:
            cuentas_disp = [{"id": "principal", "nombre": "Canal Principal", "avatar_path": ""}]

        modo_actual = str(estado_seleccion_cuentas.get("modo") or "una")
        cid_actual = str(estado_seleccion_cuentas.get("cuenta_id") or "")
        if not cid_actual and cuentas_disp:
            cid_actual = str(cuentas_disp[0].get("id") or "principal")
        grupo_actual = set(estado_seleccion_cuentas.get("grupo_ids") or [])

        # Variable temporal para no alterar nada hasta tocar "Aplicar Selección"
        cid_temp = tk.StringVar(value=cid_actual)

        # Selector superior de modo: 1 Cuenta | Todas las Cuentas | Grupo Seleccionado
        mapa_modo_seg = {
            "1 Cuenta": "una",
            "Grupo": "grupo",
            "Todas": "todas",
        }
        inv_modo_seg = {v: k for k, v in mapa_modo_seg.items()}
        seg_modo_var = tk.StringVar(value=inv_modo_seg.get(modo_actual, "1 Cuenta"))

        strat_actual = str(estado_seleccion_cuentas.get("estrategia") or "cross_posting")
        mapa_strat_seg = {
            "Mismo Video (Cross-posting)": "cross_posting",
            "Rotar Videos (1 por cuenta)": "rotacion",
        }
        inv_strat_seg = {v: k for k, v in mapa_strat_seg.items()}
        seg_strat_var = tk.StringVar(value=inv_strat_seg.get(strat_actual, "Mismo Video (Cross-posting)"))

        frame_strat = ctk.CTkFrame(
            pop,
            corner_radius=12,
            fg_color="#182032",
            border_width=1,
            border_color="#26334d",
        )
        ctk.CTkLabel(
            frame_strat,
            text="Estrategia al publicar en varias cuentas:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=CYAN_ACCENT,
        ).pack(anchor="w", padx=12, pady=(8, 4))

        lbl_strat_desc = ctk.CTkLabel(
            frame_strat,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
            justify="left",
            wraplength=440,
        )

        def _actualizar_desc_strat(*_args: object) -> None:
            if "Cross-posting" in seg_strat_var.get():
                lbl_strat_desc.configure(
                    text="El mismo Short se subirá a todas las cuentas marcadas simultáneamente."
                )
            else:
                lbl_strat_desc.configure(
                    text="Cada Short se asignará a una cuenta distinta por turno (1 video diferente por cuenta)."
                )

        seg_strat_widget = ctk.CTkSegmentedButton(
            frame_strat,
            values=["Mismo Video (Cross-posting)", "Rotar Videos (1 por cuenta)"],
            variable=seg_strat_var,
            command=_actualizar_desc_strat,
            corner_radius=10,
            height=30,
            selected_color="#2563eb",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        )
        seg_strat_widget.pack(fill="x", padx=12, pady=(0, 4))
        lbl_strat_desc.pack(anchor="w", padx=12, pady=(0, 8))
        _actualizar_desc_strat()
        frame_strat.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 10))

        lista_scroll = ctk.CTkScrollableFrame(
            pop,
            corner_radius=16,
            fg_color=CARD_BG,
            border_width=1,
            border_color=CARD_BORDER,
        )
        lista_scroll.grid(row=3, column=0, sticky="nsew", padx=22, pady=(0, 10))

        vars_checks_grupo: Dict[str, tk.BooleanVar] = {}
        bot_bar: Optional[ctk.CTkFrame] = None

        def _render_lista_popup(*_args: object) -> None:
            for w in lista_scroll.winfo_children():
                w.destroy()
            m_txt = _args[0] if _args and isinstance(_args[0], str) else seg_modo_var.get()
            m_sel = mapa_modo_seg.get(m_txt, "una")
            if m_sel in ("todas", "grupo"):
                frame_strat.grid()
                if bot_bar is not None:
                    bot_bar.grid()
            else:
                frame_strat.grid_remove()
                if bot_bar is not None:
                    bot_bar.grid_remove()

            if m_sel == "todas":
                f_todas = ctk.CTkFrame(lista_scroll, fg_color="#182032", corner_radius=14, border_width=1, border_color="#26334d")
                f_todas.pack(fill="both", expand=True, padx=12, pady=24)
                ctk.CTkLabel(
                    f_todas,
                    text="🌐 Modo Todas las Cuentas Activo",
                    font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                    text_color=CYAN_ACCENT,
                ).pack(pady=(20, 6))
                ctk.CTkLabel(
                    f_todas,
                    text=f"Se publicará automáticamente en todas tus cuentas vinculadas ({len(cuentas_disp)} canales).\nConfigura la estrategia deseada arriba y presiona Listo.",
                    font=ctk.CTkFont(family="Segoe UI", size=12),
                    text_color=TEXT_MUTED,
                    justify="center",
                    wraplength=380,
                ).pack(padx=16, pady=(0, 20))
                return

            elif m_sel == "grupo":
                ctk.CTkLabel(
                    lista_scroll,
                    text="Marca las cuentas que quieres incluir en el grupo de subida:",
                    font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                    text_color=CYAN_ACCENT,
                ).pack(anchor="w", padx=12, pady=(6, 8))

            for c_it in cuentas_disp:
                c_id = str(c_it.get("id") or "principal")
                c_nom = str(c_it.get("nombre") or c_id)
                c_av = str(c_it.get("avatar_path") or "")
                n_can = len(canales_por_cuenta.get(c_id, lista_canales if c_id == cid_actual else []))
                es_activa = (m_sel == "una" and c_id == cid_temp.get())

                item_f = ctk.CTkFrame(
                    lista_scroll,
                    fg_color="#1f273d" if es_activa else INPUT_BG,
                    corner_radius=14,
                    border_width=1,
                    border_color=PURPLE_MAIN if es_activa else "#242c42",
                )
                item_f.pack(fill="x", padx=8, pady=4)

                lbl_av = None
                av_img = _cargar_imagen_avatar_ctk(c_av, size_px=34)
                if av_img:
                    lbl_av = ctk.CTkLabel(item_f, text="", image=av_img)
                    lbl_av.pack(side="left", padx=(10, 8), pady=8)
                else:
                    lbl_av = ctk.CTkLabel(
                        item_f,
                        text="Canal",
                        font=ctk.CTkFont(size=18),
                    )
                    lbl_av.pack(side="left", padx=(12, 8), pady=8)

                info_col = ctk.CTkFrame(item_f, fg_color="transparent")
                info_col.pack(side="left", fill="x", expand=True, pady=6)

                s_val = int(c_it.get("subscribers") or 0)
                s_txt = f"  ·  {formatear_subs(s_val)}" if s_val > 0 else ""

                lbl_nom = ctk.CTkLabel(
                    info_col,
                    text=f"{c_nom}{s_txt}",
                    font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                    text_color="#ffffff" if es_activa else TEXT_MAIN,
                )
                lbl_nom.pack(anchor="w")

                lbl_can = ctk.CTkLabel(
                    info_col,
                    text=f"{n_can} canal(es) fuente guardados",
                    font=ctk.CTkFont(family="Segoe UI", size=12),
                    text_color=CYAN_ACCENT if es_activa else TEXT_MUTED,
                )
                lbl_can.pack(anchor="w")

                def _aplicar_cambios_inmediatos() -> None:
                    m_f = mapa_modo_seg.get(seg_modo_var.get(), "una")
                    estr_f = mapa_strat_seg.get(seg_strat_var.get(), "cross_posting")
                    estado_seleccion_cuentas["estrategia"] = estr_f
                    if m_f == "todas":
                        cid_prev = str(estado_seleccion_cuentas.get("cuenta_id") or "")
                        if cid_prev:
                            canales_por_cuenta[cid_prev] = list(lista_canales)
                        estado_seleccion_cuentas["modo"] = "todas"
                    elif m_f == "grupo":
                        elegidos_g = [k for k, v in vars_checks_grupo.items() if v.get()]
                        if not elegidos_g and cuentas_disp:
                            elegidos_g = [str(cuentas_disp[0].get("id") or "principal")]
                        cid_prev = str(estado_seleccion_cuentas.get("cuenta_id") or "")
                        if cid_prev:
                            canales_por_cuenta[cid_prev] = list(lista_canales)
                        estado_seleccion_cuentas["modo"] = "grupo"
                        estado_seleccion_cuentas["grupo_ids"] = elegidos_g
                    else:
                        nuevo_cid = cid_temp.get() or (str(cuentas_disp[0].get("id") or "principal") if cuentas_disp else "principal")
                        _sincronizar_canales_de_cuenta_activa(nuevo_cid, guardar_previo=True)
                        estado_seleccion_cuentas["modo"] = "una"
                        estado_seleccion_cuentas["cuenta_id"] = nuevo_cid

                    refrescar_selector_cuentas_ui()
                    refrescar_plan_ui()
                    _guardar_memoria()

                if m_sel == "una":
                    def _marcar_esta(_e=None, cid_x=c_id):
                        cid_temp.set(cid_x)
                        estado_seleccion_cuentas["modo"] = "una"
                        estado_seleccion_cuentas["cuenta_id"] = cid_x
                        _sincronizar_canales_de_cuenta_activa(cid_x, guardar_previo=True)
                        _aplicar_cambios_inmediatos()
                        pop.destroy()

                    partes_clic = [item_f, info_col, lbl_nom, lbl_can]
                    if lbl_av is not None:
                        partes_clic.append(lbl_av)
                    for w_part in partes_clic:
                        w_part.bind("<Button-1>", lambda _e, cx=c_id: _marcar_esta(_e, cx))
                        try:
                            w_part.configure(cursor="hand2")
                        except Exception:
                            pass

                    if es_activa:
                        ctk.CTkLabel(
                            item_f,
                            text="✓ Activa",
                            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                            text_color=GREEN_ACCENT,
                        ).pack(side="right", padx=16)
                elif m_sel == "grupo":
                    if c_id not in vars_checks_grupo:
                        vars_checks_grupo[c_id] = tk.BooleanVar(
                            value=(c_id in grupo_actual) or (not grupo_actual and c_id == cid_actual)
                        )

                    def _al_cambiar_check_grupo():
                        _aplicar_cambios_inmediatos()

                    def _toggle_click_fila(_e=None, cid_x=c_id):
                        if cid_x in vars_checks_grupo:
                            vars_checks_grupo[cid_x].set(not vars_checks_grupo[cid_x].get())
                            _aplicar_cambios_inmediatos()

                    partes_clic = [item_f, info_col, lbl_nom, lbl_can]
                    if lbl_av is not None:
                        partes_clic.append(lbl_av)
                    for w_part in partes_clic:
                        w_part.bind("<Button-1>", lambda _e, cx=c_id: _toggle_click_fila(_e, cx))
                        try:
                            w_part.configure(cursor="hand2")
                        except Exception:
                            pass

                    ctk.CTkCheckBox(
                        item_f,
                        text="",
                        variable=vars_checks_grupo[c_id],
                        command=_al_cambiar_check_grupo,
                        width=24,
                        checkbox_width=22,
                        checkbox_height=22,
                        corner_radius=6,
                        fg_color=PURPLE_MAIN,
                        hover_color=PURPLE_HOVER,
                    ).pack(side="right", padx=10)
                elif m_sel == "todas":
                    ctk.CTkLabel(
                        item_f,
                        text="Incluida",
                        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                        text_color=GREEN_ACCENT,
                    ).pack(side="right", padx=14)

        def _al_cambiar_modo_toggle(val_modo: str) -> None:
            m_f = mapa_modo_seg.get(val_modo, "una")
            estado_seleccion_cuentas["modo"] = m_f
            if m_f == "todas":
                cid_prev = str(estado_seleccion_cuentas.get("cuenta_id") or "")
                if cid_prev:
                    canales_por_cuenta[cid_prev] = list(lista_canales)
            elif m_f == "grupo":
                cid_prev = str(estado_seleccion_cuentas.get("cuenta_id") or "")
                if cid_prev:
                    canales_por_cuenta[cid_prev] = list(lista_canales)
                elegidos_g = [k for k, v in vars_checks_grupo.items() if v.get()]
                if not elegidos_g and cuentas_disp:
                    elegidos_g = [str(cuentas_disp[0].get("id") or "principal")]
                estado_seleccion_cuentas["grupo_ids"] = elegidos_g
            else:
                nuevo_cid = cid_temp.get() or (str(cuentas_disp[0].get("id") or "principal") if cuentas_disp else "principal")
                _sincronizar_canales_de_cuenta_activa(nuevo_cid, guardar_previo=True)
                estado_seleccion_cuentas["cuenta_id"] = nuevo_cid

            refrescar_selector_cuentas_ui()
            refrescar_plan_ui()
            _guardar_memoria()
            _render_lista_popup(val_modo)

        seg_modo = ctk.CTkSegmentedButton(
            pop,
            values=["1 Cuenta", "Grupo", "Todas"],
            variable=seg_modo_var,
            command=_al_cambiar_modo_toggle,
            corner_radius=14,
            height=34,
            selected_color=PURPLE_MAIN,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        )
        seg_modo.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 10))

        bot_bar = ctk.CTkFrame(pop, fg_color="transparent")
        bot_bar.grid(row=4, column=0, sticky="ew", padx=22, pady=(0, 14))

        ctk.CTkButton(
            bot_bar,
            text="Listo",
            command=pop.destroy,
            corner_radius=14,
            height=36,
            fg_color="#1e2436",
            hover_color="#2d354d",
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        ).pack(fill="x")

        _render_lista_popup()

    _CACHE_SHORTS_PROGRAMADOS: List[Dict[str, Any]] = []

    def _obtener_programados_filtrados() -> Tuple[List[Dict[str, Any]], str, str]:
        """
        Retorna (items_filtrados, etiqueta_contexto, nombre_canal).
        Filtra _CACHE_SHORTS_PROGRAMADOS según estado_seleccion_cuentas ('una', 'grupo', 'todas').
        """
        modo_act = str(estado_seleccion_cuentas.get("modo") or "una")
        cid_act = str(estado_seleccion_cuentas.get("cuenta_id") or "principal")
        g_ids = set(str(g) for g in (estado_seleccion_cuentas.get("grupo_ids") or []))

        try:
            from subir_a_youtube import listar_cuentas_vinculadas
            cuentas = listar_cuentas_vinculadas()
        except Exception:
            cuentas = []
        mapa_nombres = {str(c.get("id") or "principal"): str(c.get("nombre") or c.get("id") or "Canal") for c in cuentas}
        mapa_subs = {str(c.get("id") or "principal"): int(c.get("subscribers") or 0) for c in cuentas}

        if modo_act == "una":
            nom_c = mapa_nombres.get(cid_act, cid_act)
            s_val = mapa_subs.get(cid_act, 0)
            s_tag = f" ({formatear_subs(s_val)})" if s_val > 0 else ""
            nom_con_subs = f"{nom_c}{s_tag}"
            filtrados = [x for x in _CACHE_SHORTS_PROGRAMADOS if str(x.get("cuenta_id")) == cid_act]
            return filtrados, f"en {nom_con_subs}", nom_con_subs
        elif modo_act == "grupo":
            filtrados = [x for x in _CACHE_SHORTS_PROGRAMADOS if str(x.get("cuenta_id")) in g_ids]
            return filtrados, f"en grupo ({len(g_ids)} canales)", f"Grupo ({len(g_ids)})"
        else:
            filtrados = list(_CACHE_SHORTS_PROGRAMADOS)
            return filtrados, "en todas las cuentas", "Todas las cuentas"

    _CACHE_VIDEOS_PUBLICADOS: List[Dict[str, Any]] = []
    _TS_ACTUALIZACION_METRICAS: float = 0.0
    _TS_ACTUALIZACION_COLA: float = 0.0

    def _datos_pubs_iguales(lista1: List[Dict[str, Any]], lista2: List[Dict[str, Any]]) -> bool:
        if len(lista1) != len(lista2):
            return False
        for a, b in zip(lista1, lista2):
            if (str(a.get("url") or "") != str(b.get("url") or "") or
                str(a.get("titulo") or "") != str(b.get("titulo") or "") or
                int(a.get("vistas") or 0) != int(b.get("vistas") or 0) or
                int(a.get("likes") or 0) != int(b.get("likes") or 0) or
                int(a.get("comentarios") or 0) != int(b.get("comentarios") or 0) or
                str(a.get("fecha_dia") or "") != str(b.get("fecha_dia") or "") or
                str(a.get("hora_local") or "") != str(b.get("hora_local") or "")):
                return False
        return True

    def _prog_son_iguales(lista1: List[Dict[str, Any]], lista2: List[Dict[str, Any]]) -> bool:
        if len(lista1) != len(lista2):
            return False
        for a, b in zip(lista1, lista2):
            if (str(a.get("id") or a.get("url") or "") != str(b.get("id") or b.get("url") or "") or
                str(a.get("titulo") or "") != str(b.get("titulo") or "") or
                str(a.get("fecha_dia") or "") != str(b.get("fecha_dia") or "") or
                str(a.get("hora_local") or "") != str(b.get("hora_local") or "")):
                return False
        return True

    def _obtener_publicados_filtrados() -> Tuple[List[Dict[str, Any]], str, str]:
        """
        Retorna (items_filtrados, etiqueta_contexto, nombre_canal).
        Filtra _CACHE_VIDEOS_PUBLICADOS según estado_seleccion_cuentas ('una', 'grupo', 'todas').
        """
        modo_act = str(estado_seleccion_cuentas.get("modo") or "una")
        cid_act = str(estado_seleccion_cuentas.get("cuenta_id") or "principal")
        g_ids = set(str(g) for g in (estado_seleccion_cuentas.get("grupo_ids") or []))

        try:
            from subir_a_youtube import listar_cuentas_vinculadas
            cuentas = listar_cuentas_vinculadas()
        except Exception:
            cuentas = []
        mapa_nombres = {str(c.get("id") or "principal"): str(c.get("nombre") or c.get("id") or "Canal") for c in cuentas}
        mapa_subs = {str(c.get("id") or "principal"): int(c.get("subscribers") or 0) for c in cuentas}

        if modo_act == "una":
            nom_c = mapa_nombres.get(cid_act, cid_act)
            s_val = mapa_subs.get(cid_act, 0)
            s_tag = f" ({formatear_subs(s_val)})" if s_val > 0 else ""
            nom_con_subs = f"{nom_c}{s_tag}"
            filtrados = [x for x in _CACHE_VIDEOS_PUBLICADOS if str(x.get("cuenta_id")) == cid_act]
            return filtrados, f"en {nom_con_subs}", nom_con_subs
        elif modo_act == "grupo":
            filtrados = [x for x in _CACHE_VIDEOS_PUBLICADOS if str(x.get("cuenta_id")) in g_ids]
            return filtrados, f"en grupo ({len(g_ids)} canales)", f"Grupo ({len(g_ids)})"
        else:
            filtrados = list(_CACHE_VIDEOS_PUBLICADOS)
            return filtrados, "en todas las cuentas", "Todas las cuentas"

    def _actualizar_pildora_cola() -> None:
        if "btn_cola_programados" not in locals() and "btn_cola_programados" not in globals():
            return
        items_f, _, _ = _obtener_programados_filtrados()
        c = len(items_f)

        if c == 1:
            texto = "1 Short programado  ·  Ver cola ▾"
        elif c > 1:
            texto = f"{c} Shorts programados  ·  Ver cola ▾"
        else:
            texto = "Sin Shorts programados  ·  Ver cola de subidas ▾"

        color_txt = "#ffffff"
        color_bd = "#2a3147"
        color_bg = INPUT_BG

        try:
            btn_cola_programados.configure(
                text=texto,
                text_color=color_txt,
                border_color=color_bd,
                fg_color=color_bg,
            )
        except Exception:
            pass

    def _actualizar_pildora_rendimiento() -> None:
        if "btn_rendimiento_videos" not in locals() and "btn_rendimiento_videos" not in globals():
            return
        pubs_f, _, _ = _obtener_publicados_filtrados()
        c_pubs = len(pubs_f)

        if c_pubs > 0:
            texto = f"{c_pubs} Short{'s' if c_pubs != 1 else ''} reciente{'s' if c_pubs != 1 else ''}  ·  Ver métricas ▾"
        else:
            texto = "Shorts Publicados  ·  Ver métricas ▾"

        color_txt = "#ffffff"
        color_bd = "#2a3147"
        color_bg = INPUT_BG

        try:
            btn_rendimiento_videos.configure(
                text=texto,
                text_color=color_txt,
                border_color=color_bd,
                fg_color=color_bg,
            )
        except Exception:
            pass

    def sincronizar_cola_programados_async() -> None:
        def _worker_cola() -> None:
            nonlocal _TS_ACTUALIZACION_COLA, _TS_ACTUALIZACION_METRICAS
            try:
                from subir_a_youtube import obtener_shorts_programados, obtener_metricas_ultimos_videos
                prog = obtener_shorts_programados()
                pubs = obtener_metricas_ultimos_videos(total_max=30)
                _CACHE_SHORTS_PROGRAMADOS.clear()
                _CACHE_SHORTS_PROGRAMADOS.extend(prog)
                _CACHE_VIDEOS_PUBLICADOS.clear()
                _CACHE_VIDEOS_PUBLICADOS.extend(pubs)
                _TS_ACTUALIZACION_COLA = time.time()
                _TS_ACTUALIZACION_METRICAS = time.time()
            except Exception as e_c:
                print(f"[!] Error al sincronizar cola y métricas: {e_c}")
            try:
                root.after(0, _actualizar_pildora_cola)
                root.after(0, _actualizar_pildora_rendimiento)
                root.after(0, refrescar_selector_cuentas_ui)
                # No refrescar ventanas secundarias automáticamente para evitar parpadeos
            except Exception:
                pass

        threading.Thread(target=_worker_cola, daemon=True).start()

    _ventana_programados_ref: Optional[ctk.CTkToplevel] = None
    _ventana_overview_ref: Optional[ctk.CTkToplevel] = None

    def abrir_ventana_shorts_programados() -> None:
        nonlocal _ventana_programados_ref
        if _ventana_programados_ref and _ventana_programados_ref.winfo_exists():
            _ventana_programados_ref.lift()
            _ventana_programados_ref.focus_force()
            return

        win_p = ctk.CTkToplevel(root)
        _ventana_programados_ref = win_p
        win_p.title("Shorts Programados en Cola")
        win_p.geometry("740x630")
        win_p.minsize(660, 520)
        win_p.configure(fg_color=BG_DARK)
        win_p.transient(root)
        aplicar_icono_ventana(win_p)
        win_p.grab_set()

        scroll_f = ctk.CTkScrollableFrame(
            win_p,
            fg_color=INPUT_BG,
            corner_radius=18,
            border_width=1,
            border_color=CARD_BORDER,
        )
        scroll_f.pack(fill="both", expand=True, padx=24, pady=(16, 16))

        def _render_vista() -> None:
            for widget in scroll_f.winfo_children():
                widget.destroy()

            items_a_mostrar, _, _ = _obtener_programados_filtrados()

            sec_prog_header = ctk.CTkFrame(scroll_f, fg_color="transparent")
            sec_prog_header.pack(fill="x", padx=10, pady=(4, 6))

            ctk.CTkLabel(
                sec_prog_header,
                text="Shorts en Cola de Publicación",
                font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                text_color=TEXT_MAIN,
            ).pack(side="left")

            btn_refrescar_cola = ctk.CTkButton(
                sec_prog_header,
                text="Refrescar",
                command=_refrescar_manual_cola,
                width=85,
                height=26,
                corner_radius=8,
                fg_color="#1e2436",
                hover_color="#2b354f",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#ffffff",
            )
            btn_refrescar_cola.pack(side="right", padx=(8, 0))

            ctk.CTkLabel(
                sec_prog_header,
                text=f"{len(items_a_mostrar)} en cola",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color="#ffffff",
                fg_color="#101524",
                corner_radius=8,
                padx=8,
                pady=2,
            ).pack(side="right")

            if not items_a_mostrar:
                empty_card = ctk.CTkFrame(scroll_f, fg_color=CARD_BG, corner_radius=14, border_width=1, border_color=CARD_BORDER)
                empty_card.pack(fill="x", padx=10, pady=(20, 10))
                ctk.CTkLabel(
                    empty_card,
                    text="No tienes Shorts programados.",
                    font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                    text_color=TEXT_MAIN,
                ).pack(pady=(16, 2))
                ctk.CTkLabel(
                    empty_card,
                    text="Todos tus videos ya se encuentran publicados o listos para programar.",
                    font=ctk.CTkFont(family="Segoe UI", size=12),
                    text_color=TEXT_MUTED,
                ).pack(pady=(0, 14))
            else:
                for it in items_a_mostrar:
                    item_card = ctk.CTkFrame(scroll_f, fg_color=CARD_BG, corner_radius=14, border_width=1, border_color=CARD_BORDER)
                    item_card.pack(fill="x", padx=10, pady=4)

                    # Línea 1: Título a la izquierda, Fecha y hora a la derecha
                    row_line1 = ctk.CTkFrame(item_card, fg_color="transparent")
                    row_line1.pack(fill="x", padx=14, pady=(10, 6))

                    f_dia_str = str(it.get("fecha_dia") or "")
                    hora_str = str(it.get("hora_local") or "")
                    try:
                        d_p = _dt.date.fromisoformat(f_dia_str)
                        y_short = d_p.year % 100
                        txt_fecha_prog = f"{d_p.day:02d}/{d_p.month:02d}/{y_short:02d} {hora_str[:5]}"
                    except Exception:
                        txt_fecha_prog = f"{f_dia_str} {hora_str}".strip()

                    if txt_fecha_prog:
                        ctk.CTkLabel(
                            row_line1,
                            text=txt_fecha_prog,
                            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
                            text_color="#ffffff",
                            fg_color="#182030",
                            corner_radius=8,
                            padx=10,
                            pady=2,
                        ).pack(side="right", padx=(8, 0))

                    lbl_tit = ctk.CTkLabel(
                        row_line1,
                        text=str(it.get("titulo") or "Short sin título"),
                        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                        text_color=TEXT_MAIN,
                        anchor="w",
                        justify="left",
                        wraplength=520,
                    )
                    lbl_tit.pack(side="left", fill="x", expand=True)

                    # Línea 2: Estado/Canal a la izquierda, botón Ver en YouTube por debajo de la fecha/hora
                    row_line2 = ctk.CTkFrame(item_card, fg_color="transparent")
                    row_line2.pack(fill="x", padx=14, pady=(0, 10))

                    nom_cuenta = str(it.get("cuenta_nombre") or "")
                    if nom_cuenta:
                        ctk.CTkLabel(
                            row_line2,
                            text=nom_cuenta[:20],
                            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                            text_color="#ffffff",
                            fg_color="#101524",
                            corner_radius=8,
                            padx=10,
                            pady=2,
                        ).pack(side="left", padx=(0, 8))

                    ctk.CTkLabel(
                        row_line2,
                        text="Programado",
                        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                        text_color="#ffffff",
                        fg_color="#101524",
                        corner_radius=8,
                        padx=10,
                        pady=2,
                    ).pack(side="left")

                    url_v = it.get("url") or ""
                    if url_v:
                        ctk.CTkButton(
                            row_line2,
                            text="Ver en YouTube",
                            command=lambda u=url_v: webbrowser.open(u),
                            width=120,
                            height=26,
                            corner_radius=10,
                            fg_color="#cc0000",
                            hover_color="#990000",
                            text_color="#ffffff",
                            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                        ).pack(side="right", padx=(8, 0))

        def _refrescar_manual_cola() -> None:
            def _worker_fetch() -> None:
                nonlocal _TS_ACTUALIZACION_COLA
                try:
                    from subir_a_youtube import obtener_shorts_programados
                    items_prog = obtener_shorts_programados()
                    _CACHE_SHORTS_PROGRAMADOS.clear()
                    _CACHE_SHORTS_PROGRAMADOS.extend(items_prog)
                    _TS_ACTUALIZACION_COLA = time.time()
                except Exception as e_f:
                    print(f"[!] Error refrescando programados: {e_f}")

                def _ui_update() -> None:
                    try:
                        if win_p.winfo_exists():
                            _render_vista()
                        _actualizar_pildora_cola()
                    except Exception:
                        pass

                try:
                    root.after(0, _ui_update)
                except Exception:
                    pass

            threading.Thread(target=_worker_fetch, daemon=True).start()

        def _cerrar_win_p() -> None:
            nonlocal _ventana_programados_ref
            _ventana_programados_ref = None
            try:
                win_p.destroy()
            except Exception:
                pass
            sincronizar_cola_programados_async()

        win_p.protocol("WM_DELETE_WINDOW", _cerrar_win_p)

        def _sync_silencioso_programados(forzar_render: bool = False) -> None:
            def _worker_fetch() -> None:
                nonlocal _TS_ACTUALIZACION_COLA
                hubo_cambios = False
                try:
                    from subir_a_youtube import obtener_shorts_programados
                    items_prog = obtener_shorts_programados()
                    if not _prog_son_iguales(_CACHE_SHORTS_PROGRAMADOS, items_prog):
                        hubo_cambios = True
                        _CACHE_SHORTS_PROGRAMADOS.clear()
                        _CACHE_SHORTS_PROGRAMADOS.extend(items_prog)
                    _TS_ACTUALIZACION_COLA = time.time()
                except Exception as e_f:
                    print(f"[!] Error refrescando programados: {e_f}")

                def _ui_update() -> None:
                    try:
                        if win_p.winfo_exists():
                            if hubo_cambios or forzar_render:
                                _render_vista()
                        _actualizar_pildora_cola()
                    except Exception:
                        pass

                try:
                    root.after(0, _ui_update)
                except Exception:
                    pass

            threading.Thread(target=_worker_fetch, daemon=True).start()

        if _CACHE_SHORTS_PROGRAMADOS:
            _render_vista()
        else:
            loading_card = ctk.CTkFrame(scroll_f, fg_color=CARD_BG, corner_radius=14, border_width=1, border_color=CARD_BORDER)
            loading_card.pack(fill="x", padx=10, pady=(20, 10))
            ctk.CTkLabel(
                loading_card,
                text="Consultando Shorts programados...",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=TEXT_MUTED,
            ).pack(pady=16)
            _sync_silencioso_programados(forzar_render=True)

    def abrir_ventana_overview_rendimiento() -> None:
        nonlocal _ventana_overview_ref
        if _ventana_overview_ref and _ventana_overview_ref.winfo_exists():
            _ventana_overview_ref.lift()
            _ventana_overview_ref.focus_force()
            return

        win_o = ctk.CTkToplevel(root)
        _ventana_overview_ref = win_o
        win_o.title("Overview de Rendimiento")
        win_o.geometry("820x680")
        win_o.minsize(760, 520)
        win_o.configure(fg_color=BG_DARK)
        win_o.transient(root)
        aplicar_icono_ventana(win_o)
        win_o.grab_set()

        # Barra de ordenamiento superior
        sort_bar = ctk.CTkFrame(win_o, fg_color="transparent")
        sort_bar.pack(fill="x", padx=24, pady=(16, 10))

        orden_var = tk.StringVar(value="Nuevo")

        ctk.CTkLabel(
            sort_bar,
            text="Ordenar por:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=(0, 8))

        seg_orden = ctk.CTkSegmentedButton(
            sort_bar,
            values=["Nuevo", "Vistas", "Likes", "Comentarios"],
            variable=orden_var,
            command=lambda _: _render_vista(),
            corner_radius=12,
            height=30,
            selected_color=PURPLE_MAIN,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        )
        seg_orden.pack(side="left")

        btn_refrescar_overview = ctk.CTkButton(
            sort_bar,
            text="Refrescar",
            command=lambda: _refrescar_manual_overview(),
            width=90,
            height=30,
            corner_radius=12,
            fg_color="#1e2436",
            hover_color="#2b354f",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#ffffff",
        )
        btn_refrescar_overview.pack(side="right")

        scroll_f = ctk.CTkScrollableFrame(
            win_o,
            fg_color=INPUT_BG,
            corner_radius=18,
            border_width=1,
            border_color=CARD_BORDER,
        )
        scroll_f.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        def _render_vista() -> None:
            for widget in scroll_f.winfo_children():
                widget.destroy()

            pubs_f, _, _ = _obtener_publicados_filtrados()
            candidatos = list(pubs_f)

            criterio = orden_var.get()
            if "Vistas" in criterio:
                candidatos.sort(key=lambda x: int(x.get("vistas") or 0), reverse=True)
            elif "Likes" in criterio:
                candidatos.sort(key=lambda x: int(x.get("likes") or 0), reverse=True)
            elif "Comentarios" in criterio:
                candidatos.sort(key=lambda x: int(x.get("comentarios") or 0), reverse=True)
            else:
                def _sort_fecha(it_x: Dict[str, Any]) -> float:
                    dt_u = it_x.get("dt_utc")
                    if hasattr(dt_u, "timestamp"):
                        try:
                            return float(dt_u.timestamp())
                        except Exception:
                            pass
                    return 0.0

                candidatos.sort(key=_sort_fecha, reverse=True)

            pubs_a_mostrar = candidatos[:10]

            if not pubs_a_mostrar:
                empty_pub_card = ctk.CTkFrame(scroll_f, fg_color=CARD_BG, corner_radius=14, border_width=1, border_color=CARD_BORDER)
                empty_pub_card.pack(fill="x", padx=10, pady=(20, 10))
                ctk.CTkLabel(
                    empty_pub_card,
                    text="No se encontraron videos publicados en esta vista.",
                    font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                    text_color=TEXT_MAIN,
                ).pack(pady=(16, 4))
                ctk.CTkLabel(
                    empty_pub_card,
                    text="Las estadísticas se actualizarán automáticamente cuando publiques tus primeros videos.",
                    font=ctk.CTkFont(family="Segoe UI", size=12),
                    text_color=TEXT_MUTED,
                ).pack(pady=(0, 16))
            else:
                for it_pub in pubs_a_mostrar:
                    card_pub_v = ctk.CTkFrame(scroll_f, fg_color=CARD_BG, corner_radius=14, border_width=1, border_color=CARD_BORDER)
                    card_pub_v.pack(fill="x", padx=10, pady=4)

                    # Línea 1: Título a la izquierda, Fecha y hora a la derecha
                    row_line1 = ctk.CTkFrame(card_pub_v, fg_color="transparent")
                    row_line1.pack(fill="x", padx=14, pady=(10, 6))

                    fecha_str = it_pub.get("fecha_dia", "")
                    hora_str = it_pub.get("hora_local", "")
                    try:
                        d_pub = _dt.date.fromisoformat(fecha_str)
                        y_pub = d_pub.year % 100
                        txt_fh = f"{d_pub.day:02d}/{d_pub.month:02d}/{y_pub:02d} {hora_str[:5]}"
                    except Exception:
                        txt_fh = f"{fecha_str} {hora_str}".strip() if (fecha_str or hora_str) else ""

                    if txt_fh:
                        ctk.CTkLabel(
                            row_line1,
                            text=txt_fh,
                            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
                            text_color="#ffffff",
                            fg_color="#182030",
                            corner_radius=8,
                            padx=10,
                            pady=2,
                        ).pack(side="right", padx=(8, 0))

                    lbl_tit_pub = ctk.CTkLabel(
                        row_line1,
                        text=str(it_pub.get("titulo") or "Video sin título"),
                        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                        text_color=TEXT_MAIN,
                        anchor="w",
                        justify="left",
                        wraplength=560,
                    )
                    lbl_tit_pub.pack(side="left", fill="x", expand=True)

                    # Línea 2: Vistas, Likes, Comentarios a la izquierda, botón Ver en YouTube por debajo de fecha/hora
                    row_line2 = ctk.CTkFrame(card_pub_v, fg_color="transparent")
                    row_line2.pack(fill="x", padx=14, pady=(0, 10))

                    v_num = int(it_pub.get("vistas") or 0)
                    l_num = int(it_pub.get("likes") or 0)
                    c_num = int(it_pub.get("comentarios") or 0)

                    # Badge Vistas
                    ctk.CTkLabel(
                        row_line2,
                        text=f"{v_num:,} vistas",
                        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                        text_color="#ffffff",
                        fg_color="#101524",
                        corner_radius=8,
                        padx=10,
                        pady=2,
                    ).pack(side="left", padx=(0, 8))

                    # Badge Likes
                    ctk.CTkLabel(
                        row_line2,
                        text=f"{l_num:,} likes",
                        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                        text_color="#ffffff",
                        fg_color="#101524",
                        corner_radius=8,
                        padx=10,
                        pady=2,
                    ).pack(side="left", padx=(0, 8))

                    # Badge Comentarios
                    ctk.CTkLabel(
                        row_line2,
                        text=f"{c_num:,} comentarios",
                        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                        text_color="#ffffff",
                        fg_color="#101524",
                        corner_radius=8,
                        padx=10,
                        pady=2,
                    ).pack(side="left")

                    u_pub = it_pub.get("url") or ""
                    if u_pub:
                        ctk.CTkButton(
                            row_line2,
                            text="Ver en YouTube",
                            command=lambda u=u_pub: webbrowser.open(u),
                            width=120,
                            height=26,
                            corner_radius=10,
                            fg_color="#cc0000",
                            hover_color="#990000",
                            text_color="#ffffff",
                            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                        ).pack(side="right", padx=(8, 0))

        def _refrescar_manual_overview() -> None:
            def _worker_fetch() -> None:
                nonlocal _TS_ACTUALIZACION_METRICAS
                try:
                    from subir_a_youtube import obtener_metricas_ultimos_videos
                    items_pubs = obtener_metricas_ultimos_videos(total_max=30)
                    _CACHE_VIDEOS_PUBLICADOS.clear()
                    _CACHE_VIDEOS_PUBLICADOS.extend(items_pubs)
                    _TS_ACTUALIZACION_METRICAS = time.time()
                except Exception as e_f:
                    print(f"[!] Error refrescando métricas: {e_f}")

                def _ui_update() -> None:
                    try:
                        if win_o.winfo_exists():
                            _render_vista()
                        _actualizar_pildora_rendimiento()
                    except Exception:
                        pass

                try:
                    root.after(0, _ui_update)
                except Exception:
                    pass

            threading.Thread(target=_worker_fetch, daemon=True).start()

        def _cerrar_win_o() -> None:
            nonlocal _ventana_overview_ref
            _ventana_overview_ref = None
            try:
                win_o.destroy()
            except Exception:
                pass
            sincronizar_cola_programados_async()

        win_o.protocol("WM_DELETE_WINDOW", _cerrar_win_o)

        def _sync_silencioso_overview(forzar_render: bool = False) -> None:
            def _worker_fetch() -> None:
                nonlocal _TS_ACTUALIZACION_METRICAS
                hubo_cambios = False
                try:
                    from subir_a_youtube import obtener_metricas_ultimos_videos
                    items_pubs = obtener_metricas_ultimos_videos(total_max=30)
                    if not _datos_pubs_iguales(_CACHE_VIDEOS_PUBLICADOS, items_pubs):
                        hubo_cambios = True
                        _CACHE_VIDEOS_PUBLICADOS.clear()
                        _CACHE_VIDEOS_PUBLICADOS.extend(items_pubs)
                    _TS_ACTUALIZACION_METRICAS = time.time()
                except Exception as e_f:
                    print(f"[!] Error refrescando métricas de videos: {e_f}")

                def _ui_update() -> None:
                    try:
                        if win_o.winfo_exists():
                            if hubo_cambios or forzar_render:
                                _render_vista()
                        _actualizar_pildora_rendimiento()
                    except Exception:
                        pass

                try:
                    root.after(0, _ui_update)
                except Exception:
                    pass

            threading.Thread(target=_worker_fetch, daemon=True).start()

        if _CACHE_VIDEOS_PUBLICADOS:
            _render_vista()
        else:
            loading_card = ctk.CTkFrame(scroll_f, fg_color=CARD_BG, corner_radius=14, border_width=1, border_color=CARD_BORDER)
            loading_card.pack(fill="x", padx=10, pady=(20, 10))
            ctk.CTkLabel(
                loading_card,
                text="Obteniendo métricas en vivo de YouTube...",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=TEXT_MUTED,
            ).pack(pady=16)
            _sync_silencioso_overview(forzar_render=True)

    def _ciclo_auto_refresco_silencioso() -> None:
        if not editando_lock.locked():
            def _worker_bg() -> None:
                nonlocal _TS_ACTUALIZACION_COLA, _TS_ACTUALIZACION_METRICAS
                if editando_lock.locked():
                    return
                try:
                    from subir_a_youtube import (
                        obtener_shorts_programados,
                        obtener_metricas_ultimos_videos,
                        sincronizar_cuota_real_youtube,
                    )
                    sincronizar_cuota_real_youtube()
                    if editando_lock.locked():
                        return
                    prog = obtener_shorts_programados()
                    if editando_lock.locked():
                        return
                    pubs = obtener_metricas_ultimos_videos(total_max=30)
                    if editando_lock.locked():
                        return

                    prog_cambio = not _prog_son_iguales(_CACHE_SHORTS_PROGRAMADOS, prog)
                    pubs_cambio = not _datos_pubs_iguales(_CACHE_VIDEOS_PUBLICADOS, pubs)

                    if prog_cambio:
                        _CACHE_SHORTS_PROGRAMADOS.clear()
                        _CACHE_SHORTS_PROGRAMADOS.extend(prog)
                        _TS_ACTUALIZACION_COLA = time.time()
                    if pubs_cambio:
                        _CACHE_VIDEOS_PUBLICADOS.clear()
                        _CACHE_VIDEOS_PUBLICADOS.extend(pubs)
                        _TS_ACTUALIZACION_METRICAS = time.time()

                    def _ui_update_silencioso() -> None:
                        if editando_lock.locked():
                            return
                        try:
                            refrescar_barra_cuota()
                            refrescar_selector_cuentas_ui()
                            _actualizar_pildora_cola()
                            _actualizar_pildora_rendimiento()
                            # Ventanas secundarias se mantienen estables sin refrescos automáticos
                        except Exception:
                            pass

                    root.after(0, _ui_update_silencioso)
                except Exception:
                    pass

            threading.Thread(target=_worker_bg, daemon=True).start()

        root.after(60000, _ciclo_auto_refresco_silencioso)

    root.after(60000, _ciclo_auto_refresco_silencioso)

    btn_cuenta_top = ctk.CTkButton(
        header_right,
        text="Mi Cuenta ▾",
        command=abrir_selector_cuentas_popup,
        compound="left",
        corner_radius=20,
        height=40,
        fg_color=CARD_BG,
        hover_color="#1f2637",
        border_width=1,
        border_color=PURPLE_MAIN,
        text_color=TEXT_MAIN,
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
    )
    btn_cuenta_top.pack(side="left", padx=(0, 8), pady=4)

    refrescar_selector_cuentas_ui()

    btn_ajustes = ctk.CTkButton(
        header_right,
        text="Ajustes",
        command=abrir_ventana_ajustes,
        corner_radius=20,
        height=40,
        width=115,
        fg_color=CARD_BG,
        hover_color="#1f2637",
        border_width=1,
        border_color=CARD_BORDER,
        text_color=TEXT_MAIN,
        font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
    )
    btn_ajustes.pack(side="left", pady=4)

    actualizar_modo_vista()

    def abrir_calendario_popup() -> None:
        hoy = _dt.date.today()
        try:
            f_actual = _dt.date.fromisoformat(fecha_elegida_var.get())
        except Exception:
            f_actual = hoy
        if f_actual < hoy:
            f_actual = hoy

        estado_cal = {"year": f_actual.year, "month": f_actual.month}

        pop = ctk.CTkToplevel(root)
        pop.title("Elegir Fecha")
        pop.configure(fg_color=BG_DARK)
        pop.resizable(False, False)
        pop.transient(root)
        aplicar_icono_ventana(pop)
        pop.grab_set()

        bx = max(40, btn_calendario.winfo_rootx() - 40)
        by = btn_calendario.winfo_rooty() + btn_calendario.winfo_height() + 6
        pop.geometry(f"330x280+{bx}+{by}")

        wrap = ctk.CTkFrame(pop, fg_color=CARD_BG, corner_radius=20, border_width=1, border_color=CARD_BORDER)
        wrap.pack(fill="both", expand=True, padx=10, pady=10)

        nav_row = ctk.CTkFrame(wrap, fg_color="transparent")
        nav_row.pack(fill="x", padx=12, pady=(10, 6))

        btn_prev = ctk.CTkButton(
            nav_row, text="◀", width=34, height=30, corner_radius=12,
            fg_color="#1e2538", hover_color="#2d3753",
        )
        btn_prev.pack(side="left")

        lbl_mes = ctk.CTkLabel(
            nav_row, text="", font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=TEXT_MAIN,
        )
        lbl_mes.pack(side="left", expand=True)

        btn_next = ctk.CTkButton(
            nav_row, text="▶", width=34, height=30, corner_radius=12,
            fg_color="#1e2538", hover_color="#2d3753",
        )
        btn_next.pack(side="right")

        grid_frame = ctk.CTkFrame(wrap, fg_color="transparent")
        grid_frame.pack(padx=10, pady=(2, 10))

        def _elegir_fecha(d_sel: _dt.date) -> None:
            iso = d_sel.strftime("%Y-%m-%d")
            fecha_elegida_var.set(iso)
            programar_var.set(True)
            btn_calendario.configure(text=_formatear_boton_fecha(iso))
            refrescar_plan_ui()
            pop.destroy()

        def _dibujar_mes() -> None:
            for w in grid_frame.winfo_children():
                w.destroy()

            y = estado_cal["year"]
            m = estado_cal["month"]
            lbl_mes.configure(text=f"{MESES_ES[m]} {y}")

            if (y, m) <= (hoy.year, hoy.month):
                btn_prev.configure(state="disabled", fg_color="#10131c")
            else:
                btn_prev.configure(state="normal", fg_color="#1e2538")

            for col_i, nombre_d in enumerate(DIAS_CORTOS_ES):
                ctk.CTkLabel(
                    grid_frame, text=nombre_d, width=36,
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                    text_color=TEXT_MUTED,
                ).grid(row=0, column=col_i, pady=(0, 4))

            cal_matrix = _cal.monthcalendar(y, m)
            for r_i, semana in enumerate(cal_matrix, start=1):
                for c_i, dia_num in enumerate(semana):
                    if dia_num == 0:
                        ctk.CTkLabel(grid_frame, text="", width=36, height=30).grid(row=r_i, column=c_i)
                        continue

                    fecha_celda = _dt.date(y, m, dia_num)
                    es_pasado = fecha_celda < hoy
                    es_sel = fecha_celda == f_actual
                    es_hoy = fecha_celda == hoy

                    if es_pasado:
                        ctk.CTkButton(
                            grid_frame, text=str(dia_num), width=36, height=30, corner_radius=10,
                            fg_color="transparent", text_color="#334155", state="disabled",
                        ).grid(row=r_i, column=c_i, padx=2, pady=2)
                    else:
                        bg_c = PURPLE_MAIN if es_sel else ("#0284c7" if es_hoy else "#1b2234")
                        ctk.CTkButton(
                            grid_frame,
                            text=str(dia_num),
                            command=lambda fc=fecha_celda: _elegir_fecha(fc),
                            width=36,
                            height=30,
                            corner_radius=10,
                            fg_color=bg_c,
                            hover_color=GREEN_ACCENT,
                            text_color="#ffffff",
                            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold" if (es_sel or es_hoy) else "normal"),
                        ).grid(row=r_i, column=c_i, padx=2, pady=2)

        def _mes_anterior() -> None:
            if (estado_cal["year"], estado_cal["month"]) <= (hoy.year, hoy.month):
                return
            if estado_cal["month"] == 1:
                estado_cal["month"] = 12
                estado_cal["year"] -= 1
            else:
                estado_cal["month"] -= 1
            _dibujar_mes()

        def _mes_siguiente() -> None:
            if estado_cal["month"] == 12:
                estado_cal["month"] = 1
                estado_cal["year"] += 1
            else:
                estado_cal["month"] += 1
            _dibujar_mes()

        btn_prev.configure(command=_mes_anterior)
        btn_next.configure(command=_mes_siguiente)
        _dibujar_mes()

    btn_calendario.configure(command=abrir_calendario_popup)

    def obtener_schedule_seleccionado() -> Optional[str]:
        _guardar_memoria()
        if not programar_var.get():
            return None
        return f"{fecha_elegida_var.get().strip()} {hora_elegida_var.get().strip()}"

    # ==========================================================================
    # PASO 3 Y 4 UNIFICADOS: BOTÓN DE INICIO QUE SE REEMPLAZA POR LA BARRA DE CARGA
    # ==========================================================================
    contenedor_accion_y_progreso = ctk.CTkFrame(root, fg_color="transparent")
    contenedor_accion_y_progreso.pack(fill="x", padx=28, pady=(2, 20))

    solo_guardar_actual = [False]

    row_botones_accion = ctk.CTkFrame(contenedor_accion_y_progreso, fg_color="transparent")
    row_botones_accion.pack(fill="x")
    row_botones_accion.grid_columnconfigure(0, weight=8)
    row_botones_accion.grid_columnconfigure(1, weight=2)

    btn_auto_1clic = ctk.CTkButton(
        row_botones_accion,
        text="CREAR Y SUBIR SHORT EN 1 CLIC",
        corner_radius=24,
        height=58,
        fg_color=PURPLE_MAIN,
        hover_color=PURPLE_HOVER,
        text_color="#ffffff",
        font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
        command=lambda: ejecutar_flujo_1_clic(solo_guardar_override=False),
    )
    btn_auto_1clic.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

    btn_guardar_carpeta = ctk.CTkButton(
        row_botones_accion,
        text="GUARDAR EN CARPETA",
        corner_radius=24,
        height=58,
        fg_color="#182235",
        hover_color="#23324f",
        border_width=1,
        border_color="#334668",
        text_color="#ffffff",
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        command=lambda: ejecutar_flujo_1_clic(solo_guardar_override=True),
    )
    btn_guardar_carpeta.grid(row=0, column=1, sticky="nsew")

    refrescar_texto_boton_accion()

    row_pildoras_inferiores = ctk.CTkFrame(contenedor_accion_y_progreso, fg_color="transparent")
    row_pildoras_inferiores.pack(fill="x", pady=(10, 0))

    btn_cola_programados = ctk.CTkButton(
        row_pildoras_inferiores,
        text="Consultando cola de Shorts...",
        command=lambda: abrir_ventana_shorts_programados(),
        corner_radius=14,
        height=38,
        fg_color=INPUT_BG,
        hover_color="#1e2538",
        border_width=1,
        border_color="#2a3147",
        text_color="#ffffff",
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
    )
    btn_cola_programados.pack(side="left", fill="both", expand=True, padx=(0, 6))
    _actualizar_pildora_cola()

    btn_rendimiento_videos = ctk.CTkButton(
        row_pildoras_inferiores,
        text="Consultando métricas de Shorts...",
        command=lambda: abrir_ventana_overview_rendimiento(),
        corner_radius=14,
        height=38,
        fg_color=INPUT_BG,
        hover_color="#1e2538",
        border_width=1,
        border_color="#2a3147",
        text_color="#ffffff",
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
    )
    btn_rendimiento_videos.pack(side="right", fill="both", expand=True, padx=(6, 0))
    _actualizar_pildora_rendimiento()

    progress_card = ctk.CTkFrame(
        contenedor_accion_y_progreso,
        fg_color=CARD_BG,
        corner_radius=22,
        border_width=1,
        border_color=CARD_BORDER,
    )
    # Oculto inicialmente; al tocar el botón de acción, el botón desaparece
    # y aparece esta tarjeta de progreso en su lugar.

    def _mostrar_modo_progreso_activo(activo: bool) -> None:
        if activo:
            row_botones_accion.pack_forget()
            row_pildoras_inferiores.pack_forget()
            evento_cancelar.clear()
            txt_frenar = "Frenar Proceso" if solo_guardar_actual[0] else "Frenar Subida"
            btn_frenar_proceso.configure(state="normal", text=txt_frenar, fg_color="#3b151e")
            progress_card.pack(fill="x")
            row_pildoras_inferiores.pack(fill="x", pady=(10, 0))
        else:
            progress_card.pack_forget()
            row_pildoras_inferiores.pack_forget()
            btn_auto_1clic.configure(state="normal")
            btn_guardar_carpeta.configure(state="normal")
            refrescar_texto_boton_accion()
            row_botones_accion.pack(fill="x")
            row_pildoras_inferiores.pack(fill="x", pady=(10, 0))
        autoajustar_tamano_ventana()

    prog_top_row = ctk.CTkFrame(progress_card, fg_color="transparent")
    prog_top_row.pack(fill="x", padx=20, pady=(14, 6))

    lbl_estado = ctk.CTkLabel(
        prog_top_row,
        text="Listo — Elige tus canales o link arriba y dale a Crear y Subir",
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        text_color="#ffffff",
    )
    lbl_estado.pack(side="left")

    lbl_porcentaje_proceso = ctk.CTkLabel(
        prog_top_row,
        text="0%",
        font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        text_color="#ffffff",
    )
    lbl_porcentaje_proceso.pack(side="right")

    barra_progreso_proceso = ctk.CTkProgressBar(
        progress_card,
        height=14,
        corner_radius=8,
        fg_color="#181e2e",
        progress_color=PURPLE_MAIN,
    )
    barra_progreso_proceso.pack(fill="x", padx=20, pady=(2, 10))
    barra_progreso_proceso.set(0.0)

    frame_milestones = ctk.CTkFrame(progress_card, fg_color="transparent", height=0)

    row_frenar_proceso = ctk.CTkFrame(progress_card, fg_color="transparent")
    row_frenar_proceso.pack(fill="x", padx=18, pady=(0, 10))

    evento_cancelar = threading.Event()

    def solicitar_frenar_proceso() -> None:
        if not evento_cancelar.is_set():
            evento_cancelar.set()
            try:
                btn_frenar_proceso.configure(state="disabled", text="Frenando...", fg_color="#220e14")
                lbl_estado.configure(text="Frenando proceso... Asegurando archivos...", text_color="#f87171")
            except Exception:
                pass

    btn_frenar_proceso = ctk.CTkButton(
        row_frenar_proceso,
        text="Frenar Subida",
        command=solicitar_frenar_proceso,
        height=28,
        width=135,
        corner_radius=10,
        fg_color="#3b151e",
        hover_color="#5f1d2b",
        border_width=1,
        border_color="#ef4444",
        text_color="#fca5a5",
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
    )
    btn_frenar_proceso.pack(side="right")

    _max_pct_proceso = [0.0]

    def _actualizar_progreso_ui(
        pct_total: float,
        texto_estado: Optional[str] = None,
        color_estado: str = "#ffffff",
        color_barra: str = PURPLE_MAIN,
        forzar_reinicio: bool = False,
    ) -> None:
        pct_num = float(pct_total)
        if forzar_reinicio or pct_num <= 0.01:
            _max_pct_proceso[0] = max(0.0, min(100.0, pct_num))
        else:
            _max_pct_proceso[0] = max(_max_pct_proceso[0], max(0.0, min(100.0, pct_num)))
        pct_clamp = _max_pct_proceso[0]
        barra_progreso_proceso.set(pct_clamp / 100.0)
        barra_progreso_proceso.configure(progress_color=color_barra)
        lbl_porcentaje_proceso.configure(text=f"{int(round(pct_clamp))}%")
        if texto_estado is not None:
            # Todos los textos que indican el avance de la edición/subida se muestran en color blanco puro (#ffffff)
            color_final = "#ffffff" if color_estado not in ("#ef4444", "#f87171") else color_estado
            lbl_estado.configure(text=texto_estado, text_color=color_final)

    def _renderizar_milestones_ui(estados_reels: List[Dict[str, str]]) -> None:
        for w in frame_milestones.winfo_children():
            w.destroy()
        if len(estados_reels) <= 1:
            frame_milestones.pack_forget()
            autoajustar_tamano_ventana()
            return
        frame_milestones.pack(fill="x", padx=18, pady=(0, 6), before=row_frenar_proceso)
        for item_m in estados_reels:
            est_tipo = item_m.get("tipo", "pendiente")
            txt_m = item_m.get("texto", "")
            if est_tipo == "subido":
                bg_m = "#0f291e"
                bd_m = GREEN_ACCENT
                tc_m = "#4ade80"
            elif est_tipo == "activo":
                bg_m = "#231c38"
                bd_m = PURPLE_MAIN
                tc_m = "#e9d5ff"
            else:
                bg_m = "#151a28"
                bd_m = "#262f45"
                tc_m = TEXT_DIM
            pill_m = ctk.CTkFrame(
                frame_milestones,
                fg_color=bg_m,
                corner_radius=12,
                border_width=1,
                border_color=bd_m,
            )
            pill_m.pack(side="left", padx=(0, 8), pady=2)
            ctk.CTkLabel(
                pill_m,
                text=txt_m,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=tc_m,
            ).pack(padx=10, pady=3)

    _renderizar_milestones_ui([])

    class RedireccionadorSilencioso:
        def __init__(self, q: "queue.Queue[str]"):
            self.q = q

        def write(self, texto: str) -> None:
            if texto:
                self.q.put(texto)

        def flush(self) -> None:
            pass

    def vaciar_cola_logs() -> None:
        while not cola_logs.empty():
            try:
                cola_logs.get_nowait()
            except Exception:
                break
        root.after(200, vaciar_cola_logs)

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

    def abrir_carpeta_assets() -> None:
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(ASSETS_DIR))
        except Exception:
            pass

    def abrir_carpeta_musica() -> None:
        abrir_carpeta_assets()

    def verificar_canal_gui() -> None:
        try:
            from subir_a_youtube import obtener_servicio_youtube
            youtube = obtener_servicio_youtube()
            resp = youtube.channels().list(mine=True, part="snippet").execute()
            items = resp.get("items", [])
            if items:
                nombre_canal = items[0]["snippet"]["title"]
                messagebox.showinfo(
                    "Canal de YouTube Vinculado",
                    f"¡Conexión Activa!\n\nCanal: {nombre_canal}\n\n"
                    f"Tus credenciales están listas para subir videos directamente.",
                )
            else:
                messagebox.showinfo("Canal de YouTube", "Conectado a la API de YouTube correctamente.")
        except Exception as e:
            messagebox.showerror("Error de Vinculación", f"No se pudo conectar con YouTube:\n{e}")

    def _aplicar_custom_a_guion_txt(
        idx_reel: int,
        ruta_video: Path,
        custom_tit: str,
        custom_desc: str,
        custom_guion: str,
        sched_str: str,
        modo_priv: str,
    ) -> bool:
        """
        Si el usuario escribió un guión personalizado completo (y opcionalmente título/descripción),
        puede construir o sobreescribir `DEFAULT_GUION_TXT`.
        Retorna True si YA construyó el archivo completo sin necesitar llamar a la IA,
        o False si primero debe ejecutarse la IA y luego sobreescribir los campos personalizados.
        """
        if not custom_guion:
            return False

        dur_v = max(10.0, min(60.0, obtener_duracion_video_ffprobe(ruta_video)))
        lineas_guion_formateadas: List[str] = []

        # Detectar si el usuario ya pegó formato con '|' o texto libre
        lineas_raw = [ln.strip() for ln in custom_guion.replace(";", "\n").splitlines() if ln.strip()]
        if any("|" in ln for ln in lineas_raw):
            for ln in lineas_raw:
                if "|" in ln:
                    lineas_guion_formateadas.append(ln)
        else:
            # Dividir el texto libre del usuario en bloques de ~5 segundos cubriendo todo el video
            oraciones = [
                s.strip()
                for s in re.split(r"(?<=[\.\!\?])\s+", custom_guion.strip())
                if s.strip()
            ]
            if not oraciones:
                oraciones = [custom_guion.strip()]
            num_bloques = max(1, len(oraciones))
            paso = dur_v / num_bloques
            emojis_ciclo = ["sorprendido", "fuego", "impacto", "risa", "ojo", "trofeo", "estrella"]
            sfx_ciclo = ["whoosh", "pop", "impact", "ding", "riser", "bell"]
            for i_b, orac in enumerate(oraciones):
                t_ini = round(i_b * paso, 1)
                t_fin = round(min(dur_v, (i_b + 1) * paso), 1)
                if i_b == num_bloques - 1:
                    t_fin = round(dur_v, 1)
                emj = emojis_ciclo[i_b % len(emojis_ciclo)]
                sfx = sfx_ciclo[i_b % len(sfx_ciclo)]
                zoom_v = "1.12" if i_b % 2 == 0 else "1.06"
                lineas_guion_formateadas.append(
                    f"{t_ini:04.1f}-{t_fin:04.1f} | {orac} | {emj} | {sfx} | zoom={zoom_v}"
                )

        tit_yt = custom_tit if custom_tit else "Mira lo que ocurre en este video increíble #shorts"
        if "#shorts" not in tit_yt.lower():
            tit_yt = f"{tit_yt.strip()} #shorts"
        palabras_sup = [w for w in re.sub(r"#\S+", "", custom_tit or "MIRA ESTO").strip().split() if w][:5]
        tit_sup = " ".join(palabras_sup).upper()
        desc_yt = custom_desc if custom_desc else "No vas a creer este momento hasta el final. ¡Suscríbete para más! #shorts #viral #increible"

        contenido_txt = (
            "[CONFIGURACION]\n"
            f"VOZ = { VOCES_DISPONIBLES.get(voz_var.get(), EDGE_VOICE_DEFAULT) }\n"
            "VELOCIDAD_VOZ = +12%\n"
            "VOLUMEN_VIDEO_ORIGINAL = 0.28\n"
            f"MODO_ENCUADRE = { encuadre_map.get(encuadre_var.get(), 'full') }\n"
            f"TITULO_SUPERIOR = {tit_sup}\n"
            "SUBTITULO_SUPERIOR = ¡MIRA HASTA EL FINAL!\n"
            f"TITULO_YOUTUBE = {tit_yt}\n"
            f"DESCRIPCION_YOUTUBE = {desc_yt}\n"
            "TAGS_YOUTUBE = shorts, viral, increible, español, tendencias, entretenimiento, curioso\n"
            f"PRIVACIDAD_YOUTUBE = {modo_priv}\n"
            f"PROGRAMAR_SUBIDA = {sched_str}\n\n"
            "[GUION]\n"
            + "\n".join(lineas_guion_formateadas)
            + "\n"
        )
        DEFAULT_GUION_TXT.write_text(contenido_txt, encoding="utf-8")
        return True

    def _sobreescribir_campos_custom_en_guion_txt(custom_tit: str, custom_desc: str) -> None:
        if not DEFAULT_GUION_TXT.exists():
            return
        texto = DEFAULT_GUION_TXT.read_text(encoding="utf-8", errors="ignore")
        lineas = texto.splitlines()
        nuevas: List[str] = []
        for ln in lineas:
            if custom_tit and ln.strip().upper().startswith("TITULO_YOUTUBE"):
                t_val = custom_tit.strip()
                if "#shorts" not in t_val.lower():
                    t_val = f"{t_val} #shorts"
                nuevas.append(f"TITULO_YOUTUBE = {t_val}")
            elif custom_tit and ln.strip().upper().startswith("TITULO_SUPERIOR"):
                palabras_sup = [w for w in re.sub(r"#\S+", "", custom_tit).strip().split() if w][:5]
                t_sup = (" ".join(palabras_sup).upper()) if palabras_sup else "MIRA ESTO"
                nuevas.append(f"TITULO_SUPERIOR = {t_sup}")
            elif custom_desc and ln.strip().upper().startswith("DESCRIPCION_YOUTUBE"):
                nuevas.append(f"DESCRIPCION_YOUTUBE = {custom_desc.strip()}")
            else:
                nuevas.append(ln)
        DEFAULT_GUION_TXT.write_text("\n".join(nuevas) + "\n", encoding="utf-8")

    def _abrir_ventana_personalizar_lote(
        videos_elegidos: List[Dict[str, object]],
        evento_listo: threading.Event,
        resultado_modal: Dict[str, bool],
    ) -> None:
        win_c = ctk.CTkToplevel(root)
        win_c.title("Personalizar Reels Seleccionados")
        win_c.geometry("720x570")
        win_c.resizable(False, False)
        win_c.configure(fg_color=BG_DARK)
        win_c.transient(root)
        aplicar_icono_ventana(win_c)
        win_c.grab_set()

        total_v = len(videos_elegidos)
        estado_nav = {"idx": 0}

        top_bar = ctk.CTkFrame(win_c, fg_color="transparent")
        top_bar.pack(fill="x", padx=24, pady=(16, 6))

        ctk.CTkLabel(
            top_bar,
            text="Videos Elegidos — Personaliza Título, Descripción y Guión",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(side="left")

        nav_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        nav_box.pack(side="right")

        btn_p = ctk.CTkButton(
            nav_box,
            text="◀",
            width=34,
            height=28,
            corner_radius=10,
            fg_color="#1e2538",
            hover_color=PURPLE_MAIN,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        btn_p.pack(side="left", padx=(0, 6))

        lbl_nav_r = ctk.CTkLabel(
            nav_box,
            text=f"Reel 1 de {total_v}",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=CYAN_ACCENT,
            width=95,
        )
        lbl_nav_r.pack(side="left")

        btn_n = ctk.CTkButton(
            nav_box,
            text="▶",
            width=34,
            height=28,
            corner_radius=10,
            fg_color="#1e2538",
            hover_color=PURPLE_MAIN,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        btn_n.pack(side="left", padx=(6, 0))

        # Tarjeta con la info del video elegido y su link clickeable
        info_card = ctk.CTkFrame(win_c, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        info_card.pack(fill="x", padx=24, pady=(4, 10))

        lbl_info_vid = ctk.CTkLabel(
            info_card,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#facc15",
            anchor="w",
        )
        lbl_info_vid.pack(fill="x", padx=16, pady=(10, 2))

        row_lnk = ctk.CTkFrame(info_card, fg_color="transparent")
        row_lnk.pack(fill="x", padx=16, pady=(0, 10))

        ent_link_elegido = ctk.CTkEntry(
            row_lnk,
            corner_radius=12,
            height=30,
            fg_color=INPUT_BG,
            border_color="#2a3147",
            text_color=CYAN_ACCENT,
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        ent_link_elegido.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def _abrir_link_navegador() -> None:
            u = str(videos_elegidos[estado_nav["idx"]].get("url") or "")
            if u.startswith("http"):
                webbrowser.open(u)

        ctk.CTkButton(
            row_lnk,
            text="Ver Video en YouTube",
            command=_abrir_link_navegador,
            corner_radius=12,
            height=30,
            width=175,
            fg_color="#1e293b",
            hover_color=PURPLE_MAIN,
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).pack(side="right")

        # Tarjeta de Campos de Personalización
        form_card = ctk.CTkFrame(win_c, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        form_card.pack(fill="both", expand=True, padx=24, pady=(0, 10))

        # Título Row con Switch IA
        row_h_tit = ctk.CTkFrame(form_card, fg_color="transparent")
        row_h_tit.pack(fill="x", padx=16, pady=(10, 2))

        ctk.CTkLabel(
            row_h_tit,
            text="Título de YouTube Shorts:",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(side="left")

        sw_ia_tit = ctk.CTkSwitch(
            row_h_tit,
            text="Crear con IA",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#c084fc",
            progress_color=PURPLE_MAIN,
            button_color="#ffffff",
            button_hover_color="#e2e8f0",
            height=18,
            width=38,
            command=lambda: _actualizar_estados_campos_ia(),
        )
        sw_ia_tit.pack(side="right")

        ent_m_tit = ctk.CTkEntry(
            form_card,
            placeholder_text="Escribe un título viral o activa 'Crear con IA'...",
            corner_radius=12,
            height=34,
            fg_color=INPUT_BG,
            border_color="#2a3147",
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        ent_m_tit.pack(fill="x", padx=16, pady=(0, 8))

        # Descripción Row con Switch IA
        row_h_desc = ctk.CTkFrame(form_card, fg_color="transparent")
        row_h_desc.pack(fill="x", padx=16, pady=(0, 2))

        ctk.CTkLabel(
            row_h_desc,
            text="Descripción y Hashtags:",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(side="left")

        sw_ia_desc = ctk.CTkSwitch(
            row_h_desc,
            text="Crear con IA",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#c084fc",
            progress_color=PURPLE_MAIN,
            button_color="#ffffff",
            button_hover_color="#e2e8f0",
            height=18,
            width=38,
            command=lambda: _actualizar_estados_campos_ia(),
        )
        sw_ia_desc.pack(side="right")

        ent_m_desc = ctk.CTkEntry(
            form_card,
            placeholder_text="Escribe descripción y hashtags o activa 'Crear con IA'...",
            corner_radius=12,
            height=34,
            fg_color=INPUT_BG,
            border_color="#2a3147",
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        ent_m_desc.pack(fill="x", padx=16, pady=(0, 8))

        # Guión Row con Switch IA
        row_h_guion = ctk.CTkFrame(form_card, fg_color="transparent")
        row_h_guion.pack(fill="x", padx=16, pady=(0, 2))

        ctk.CTkLabel(
            row_h_guion,
            text="Guión / Narración del Reel:",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(side="left")

        sw_ia_guion = ctk.CTkSwitch(
            row_h_guion,
            text="Crear con IA",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#c084fc",
            progress_color=PURPLE_MAIN,
            button_color="#ffffff",
            button_hover_color="#e2e8f0",
            height=18,
            width=38,
            command=lambda: _actualizar_estados_campos_ia(),
        )
        sw_ia_guion.pack(side="right")

        txt_m_guion = ctk.CTkTextbox(
            form_card,
            height=90,
            corner_radius=12,
            fg_color=INPUT_BG,
            border_width=1,
            border_color="#2a3147",
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        txt_m_guion.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        def _actualizar_estados_campos_ia() -> None:
            if sw_ia_tit.get():
                ent_m_tit.configure(state="disabled", fg_color="#101522")
            else:
                ent_m_tit.configure(state="normal", fg_color=INPUT_BG)

            if sw_ia_desc.get():
                ent_m_desc.configure(state="disabled", fg_color="#101522")
            else:
                ent_m_desc.configure(state="normal", fg_color=INPUT_BG)

            if sw_ia_guion.get():
                txt_m_guion.configure(state="disabled", fg_color="#101522")
            else:
                txt_m_guion.configure(state="normal", fg_color=INPUT_BG)

        def _guardar_actual_en_mem() -> None:
            i_c = estado_nav["idx"]
            datos_custom_reels[i_c]["usar_ia_tit"] = bool(sw_ia_tit.get())
            datos_custom_reels[i_c]["usar_ia_desc"] = bool(sw_ia_desc.get())
            datos_custom_reels[i_c]["usar_ia_guion"] = bool(sw_ia_guion.get())
            datos_custom_reels[i_c]["titulo"] = ent_m_tit.get().strip() if not sw_ia_tit.get() else ""
            datos_custom_reels[i_c]["descripcion"] = ent_m_desc.get().strip() if not sw_ia_desc.get() else ""
            datos_custom_reels[i_c]["guion"] = txt_m_guion.get("1.0", "end").strip() if not sw_ia_guion.get() else ""
            _guardar_memoria()

        def _mostrar_reel_idx() -> None:
            i_c = estado_nav["idx"]
            v_item = videos_elegidos[i_c]
            canal_str = str(v_item.get("canal") or "Link directo")
            tit_orig = str(v_item.get("titulo_orig") or "Video seleccionado")
            vistas_v = int(v_item.get("vistas") or 0)
            vistas_txt = f" · {vistas_v:,} vistas" if vistas_v > 0 else ""
            lbl_info_vid.configure(text=f"Reel #{i_c + 1} ({canal_str}{vistas_txt}): {tit_orig[:58]}")

            ent_link_elegido.configure(state="normal")
            ent_link_elegido.delete(0, tk.END)
            ent_link_elegido.insert(0, str(v_item.get("url") or ""))
            ent_link_elegido.configure(state="readonly")

            d_c = datos_custom_reels[i_c]
            ia_tit = d_c.get("usar_ia_tit", not bool(d_c.get("titulo")))
            ia_desc = d_c.get("usar_ia_desc", not bool(d_c.get("descripcion")))
            ia_guion = d_c.get("usar_ia_guion", not bool(d_c.get("guion")))

            if ia_tit:
                sw_ia_tit.select()
            else:
                sw_ia_tit.deselect()

            if ia_desc:
                sw_ia_desc.select()
            else:
                sw_ia_desc.deselect()

            if ia_guion:
                sw_ia_guion.select()
            else:
                sw_ia_guion.deselect()

            ent_m_tit.configure(state="normal")
            ent_m_tit.delete(0, tk.END)
            if d_c.get("titulo"):
                ent_m_tit.insert(0, d_c["titulo"])

            ent_m_desc.configure(state="normal")
            ent_m_desc.delete(0, tk.END)
            if d_c.get("descripcion"):
                ent_m_desc.insert(0, d_c["descripcion"])

            txt_m_guion.configure(state="normal")
            txt_m_guion.delete("1.0", "end")
            if d_c.get("guion"):
                txt_m_guion.insert("1.0", d_c["guion"])

            _actualizar_estados_campos_ia()

            lbl_nav_r.configure(text=f"Reel {i_c + 1} de {total_v}")
            btn_p.configure(state="normal" if i_c > 0 else "disabled")
            btn_n.configure(state="normal" if i_c < total_v - 1 else "disabled")

        def _prev_m() -> None:
            _guardar_actual_en_mem()
            if estado_nav["idx"] > 0:
                estado_nav["idx"] -= 1
                _mostrar_reel_idx()

        def _next_m() -> None:
            _guardar_actual_en_mem()
            if estado_nav["idx"] < total_v - 1:
                estado_nav["idx"] += 1
                _mostrar_reel_idx()

        btn_p.configure(command=_prev_m)
        btn_n.configure(command=_next_m)

        bot_row = ctk.CTkFrame(win_c, fg_color="transparent")
        bot_row.pack(fill="x", padx=24, pady=(0, 16))

        def _cancelar_m() -> None:
            resultado_modal["confirmado"] = False
            try:
                win_c.destroy()
            except Exception:
                pass
            evento_listo.set()

        def _confirmar_m() -> None:
            _guardar_actual_en_mem()
            resultado_modal["confirmado"] = True
            try:
                win_c.destroy()
            except Exception:
                pass
            evento_listo.set()

        win_c.protocol("WM_DELETE_WINDOW", _cancelar_m)

        ctk.CTkButton(
            bot_row,
            text="Cancelar",
            command=_cancelar_m,
            corner_radius=18,
            height=42,
            width=130,
            fg_color="#1e2436",
            hover_color="#334155",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        ).pack(side="left")

        txt_confirmar = (
            "COMENZAR EDICIÓN Y GUARDAR AHORA"
            if solo_guardar_actual[0]
            else "COMENZAR EDICIÓN Y SUBIDA AHORA"
        )
        ctk.CTkButton(
            bot_row,
            text=txt_confirmar,
            command=_confirmar_m,
            corner_radius=18,
            height=42,
            fg_color=GREEN_ACCENT,
            hover_color="#059669",
            text_color="#052e16",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
        ).pack(side="right", fill="x", expand=True, padx=(12, 0))

        _mostrar_reel_idx()

    def abrir_dialogo_revision_short(
        ruta_video: Path,
        titulo: str,
        ruta_guion: Path,
        on_decision: Callable[[str, str], None],
        es_modo_editado: bool = False,
        url_video_orig: str = "",
        es_modo_manual_inicial: bool = False,
        solo_guardar: bool = False,
    ) -> None:
        win_r = ctk.CTkToplevel(root)
        win_r.title("Shorts Studio · Edición Manual" if es_modo_manual_inicial else "Shorts Studio · Revisión Previa")
        win_r.geometry("1080x700")
        win_r.minsize(980, 640)
        win_r.resizable(True, True)
        win_r.configure(fg_color=BG_DARK)
        win_r.transient(root)
        aplicar_icono_ventana(win_r)
        win_r.lift()
        win_r.focus_force()
        win_r.grab_set()

        player = None
        reproduciendo = False
        duracion_total = 1.0
        arrastrando_slider = False
        cancelado_reproductor = False
        txt_guion_box: Optional[Any] = None

        def _limpiar() -> None:
            nonlocal cancelado_reproductor
            cancelado_reproductor = True
            if player is not None:
                try:
                    player.close_player()
                except Exception:
                    pass

        def _al_cerrar_x() -> None:
            _limpiar()
            win_r.destroy()
            on_decision("descartar", "")

        win_r.protocol("WM_DELETE_WINDOW", _al_cerrar_x)

        def _responder(acc: str) -> None:
            fb = txt_guion_box.get("1.0", "end").strip() if txt_guion_box is not None else ""
            _limpiar()
            win_r.destroy()
            on_decision(acc, fb)

        # ── Layout principal ──────────────────────────────────────────────────
        panel_principal = ctk.CTkFrame(win_r, fg_color="transparent")
        panel_principal.pack(fill="both", expand=True, padx=20, pady=16)
        panel_principal.grid_columnconfigure(0, weight=0)
        panel_principal.grid_columnconfigure(1, weight=1)
        panel_principal.grid_rowconfigure(0, weight=1)

        # ── Columna izquierda: reproductor 9:16 ───────────────────────────
        col_izq = ctk.CTkFrame(
            panel_principal,
            fg_color=CARD_BG,
            corner_radius=18,
            border_width=1,
            border_color=CARD_BORDER,
            width=308,
        )
        col_izq.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        col_izq.grid_propagate(False)

        canvas_video = tk.Canvas(
            col_izq,
            width=270,
            height=480,
            bg="#000000",
            highlightthickness=0,
        )
        canvas_video.pack(padx=18, pady=(16, 8))

        slider_seek = ctk.CTkSlider(
            col_izq,
            from_=0.0,
            to=1.0,
            height=12,
            progress_color=PURPLE_MAIN,
            button_color=CYAN_ACCENT,
            button_hover_color="#38bdf8",
        )
        slider_seek.set(0.0)
        slider_seek.pack(fill="x", padx=18, pady=(0, 6))

        def _fmt_tiempo(s: float) -> str:
            s_int = max(0, int(s))
            return f"{s_int // 60:02d}:{s_int % 60:02d}"

        def _seek_press(event: Any) -> None:
            nonlocal arrastrando_slider
            arrastrando_slider = True

        def _seek_release(event: Any) -> None:
            nonlocal arrastrando_slider
            arrastrando_slider = False
            if player is not None and duracion_total > 0:
                try:
                    player.seek(slider_seek.get() * duracion_total, relative=False)
                    win_r.after(10, _loop_reproductor)
                except Exception:
                    pass

        def _on_slider_change(val: float) -> None:
            if arrastrando_slider and duracion_total > 0 and player is not None:
                try:
                    target_pts = float(val) * duracion_total
                    player.seek(target_pts, relative=False)
                    lbl_tiempo.configure(text=f"{_fmt_tiempo(target_pts)} / {_fmt_tiempo(duracion_total)}")
                except Exception:
                    pass

        slider_seek.bind("<Button-1>", _seek_press)
        slider_seek.bind("<ButtonRelease-1>", _seek_release)
        slider_seek.configure(command=_on_slider_change)

        row_ctrl = ctk.CTkFrame(col_izq, fg_color="transparent")
        row_ctrl.pack(fill="x", padx=18, pady=(0, 10))

        btn_play = ctk.CTkButton(
            row_ctrl, text="▶", width=36, height=30, corner_radius=8,
            fg_color=INPUT_BG, hover_color="#2a3147",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        lbl_tiempo = ctk.CTkLabel(
            row_ctrl, text="00:00 / 00:00",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=TEXT_MUTED,
        )
        btn_play.pack(side="left", padx=(0, 8))
        lbl_tiempo.pack(side="left")

        slider_vol = ctk.CTkSlider(
            row_ctrl, from_=0.0, to=1.0, width=54, height=12,
            number_of_steps=20, progress_color=CYAN_ACCENT, button_color=CYAN_ACCENT,
        )
        slider_vol.set(1.0)
        lbl_vol = ctk.CTkLabel(row_ctrl, text="Vol", font=ctk.CTkFont(family="Segoe UI", size=10), text_color=TEXT_DIM)
        slider_vol.pack(side="right")
        lbl_vol.pack(side="right", padx=(0, 4))

        def _on_vol_change(val: float) -> None:
            if player is not None:
                try:
                    player.set_volume(float(val))
                except Exception:
                    pass

        slider_vol.configure(command=_on_vol_change)

        def _toggle_play() -> None:
            nonlocal reproduciendo
            if player is not None:
                try:
                    reproduciendo = not reproduciendo
                    player.set_pause(not reproduciendo)
                    btn_play.configure(text="■" if reproduciendo else "▶")
                    if reproduciendo:
                        win_r.after(10, _loop_reproductor)
                except Exception:
                    pass

        btn_play.configure(command=_toggle_play)

        # Enlace original por debajo del reproductor de video
        if url_video_orig and url_video_orig.strip():
            row_url = ctk.CTkFrame(col_izq, fg_color="#101524", corner_radius=10, border_width=1, border_color="#1e2538")
            row_url.pack(fill="x", padx=16, pady=(0, 10))

            ent_url_disp = ctk.CTkEntry(
                row_url, height=24,
                font=ctk.CTkFont(family="Segoe UI", size=10),
                fg_color="transparent", border_width=0,
                text_color=CYAN_ACCENT,
            )
            ent_url_disp.insert(0, url_video_orig.strip())
            ent_url_disp.configure(state="readonly")
            ent_url_disp.pack(side="left", fill="x", expand=True, padx=(8, 2), pady=3)

            def _abrir_url_navegador() -> None:
                import webbrowser
                try:
                    webbrowser.open(url_video_orig.strip())
                except Exception:
                    pass

            def _copiar_url_clip() -> None:
                try:
                    root.clipboard_clear()
                    root.clipboard_append(url_video_orig.strip())
                    btn_copiar_url.configure(text="OK!")
                    root.after(1400, lambda: btn_copiar_url.configure(text="Copiar"))
                except Exception:
                    pass

            ctk.CTkButton(
                row_url, text="Abrir", width=42, height=22, corner_radius=6,
                fg_color="#1e2538", hover_color="#2d3752",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                command=_abrir_url_navegador,
            ).pack(side="right", padx=(2, 4), pady=3)

            btn_copiar_url = ctk.CTkButton(
                row_url, text="Copiar", width=46, height=22, corner_radius=6,
                fg_color="#1e2538", hover_color="#2d3752",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                command=_copiar_url_clip,
            )
            btn_copiar_url.pack(side="right", padx=(2, 0), pady=3)

            def _descartar_para_siempre() -> None:
                try:
                    from shorts_engine.youtube_manager import descartar_video_para_siempre
                    descartar_video_para_siempre(url_video_orig.strip())
                except Exception:
                    pass
                _responder("descartar")

            btn_descartar_perm = ctk.CTkButton(
                col_izq,
                text="🗑 Descartar short para siempre",
                command=_descartar_para_siempre,
                height=28, corner_radius=8,
                fg_color="#1f1418", hover_color="#7f1d1d",
                border_width=1, border_color="#451a22",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#f87171",
            )
            btn_descartar_perm.pack(fill="x", padx=16, pady=(0, 10))

        # ── Columna derecha ────────────────────────────────────────────────
        col_der = ctk.CTkFrame(panel_principal, fg_color="transparent")
        col_der.grid(row=0, column=1, sticky="nsew")
        col_der.grid_rowconfigure(1, weight=1)
        col_der.grid_columnconfigure(0, weight=1)

        # Header compacto
        hdr = ctk.CTkFrame(col_der, fg_color=CARD_BG, corner_radius=14, border_width=1, border_color=CARD_BORDER)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        hdr_inner = ctk.CTkFrame(hdr, fg_color="transparent")
        hdr_inner.pack(fill="x", padx=16, pady=8)

        lbl_texto_estado = ""
        if es_modo_manual_inicial:
            lbl_texto_estado = "Edición Manual · Redactá el Guion y Efectos"
        elif es_modo_editado:
            lbl_texto_estado = "Video editado listo"

        if lbl_texto_estado:
            lbl_estado = ctk.CTkLabel(
                hdr_inner,
                text=lbl_texto_estado,
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                text_color=TEXT_MAIN,
            )
            lbl_estado.pack(side="left")



        # Selectores interactivos de Voz del Narrador y Canción de Fondo
        f_top_ctrls = ctk.CTkFrame(hdr_inner, fg_color="transparent")
        f_top_ctrls.pack(side="right", padx=(0, 12))

        # 1. Selector interactivo de Voz del Narrador
        f_voz = ctk.CTkFrame(f_top_ctrls, fg_color="transparent")
        f_voz.pack(side="left", padx=(0, 12))

        lbl_voz = ctk.CTkLabel(
            f_voz,
            text="🗣️ Voz:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=TEXT_MUTED,
        )
        lbl_voz.pack(side="left", padx=(0, 5))

        def _al_cambiar_voz(nueva_voz: str):
            voz_var.set(nueva_voz)
            _guardar_memoria()
            if txt_guion_box is not None:
                txt_guion_box.metadatos_ocultos["VOZ_NARRADOR"] = nueva_voz

        opt_voz = ctk.CTkOptionMenu(
            f_voz,
            values=list(VOCES_DISPONIBLES.keys()),
            command=_al_cambiar_voz,
            width=135,
            height=26,
            fg_color="#182032",
            button_color="#25304a",
            button_hover_color="#334166",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=11),
        )
        opt_voz.set(voz_var.get())
        opt_voz.pack(side="left")

        # 2. Selector interactivo de Canción / Música de Fondo
        pistas_disponibles = ["Auto", "Sin Música"]
        try:
            from shorts_engine.config import MUSICA_DIR
            pistas_disco = [p.stem for p in sorted(MUSICA_DIR.glob("*")) if p.is_file() and p.suffix.lower() in (".mp3", ".wav", ".m4a", ".aac")]
            if pistas_disco:
                pistas_disponibles = ["Auto", *pistas_disco, "Sin Música"]
        except Exception:
            pass

        def _al_cambiar_musica(nueva_cancion: str):
            if txt_guion_box is not None:
                if nueva_cancion == "Auto":
                    txt_guion_box.metadatos_ocultos["TONO_VIDEO"] = "auto"
                elif nueva_cancion == "Sin Música":
                    txt_guion_box.metadatos_ocultos["TONO_VIDEO"] = "sin_musica"
                else:
                    txt_guion_box.metadatos_ocultos["TONO_VIDEO"] = nueva_cancion

        f_musica = ctk.CTkFrame(f_top_ctrls, fg_color="transparent")
        f_musica.pack(side="left")

        lbl_musica = ctk.CTkLabel(
            f_musica,
            text="🎵 Canción:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=TEXT_MUTED,
        )
        lbl_musica.pack(side="left", padx=(0, 5))

        opt_musica = ctk.CTkOptionMenu(
            f_musica,
            values=pistas_disponibles,
            command=_al_cambiar_musica,
            width=125,
            height=26,
            fg_color="#182032",
            button_color="#25304a",
            button_hover_color="#334166",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=11),
        )
        opt_musica.set("Auto")
        opt_musica.pack(side="left")

        # Tarjeta guion (ocupa todo el espacio disponible)
        card_guion = ctk.CTkFrame(
            col_der, fg_color=CARD_BG, corner_radius=18,
            border_width=1, border_color=CARD_BORDER,
        )
        card_guion.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        card_guion.grid_rowconfigure(1, weight=1)
        card_guion.grid_columnconfigure(0, weight=1)

        lbl_guion_tit = ctk.CTkLabel(
            card_guion,
            text="Guion editable" if not es_modo_editado else "Metadatos",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_MAIN,
            anchor="w",
        )
        lbl_guion_tit.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))

        def _seek_en_reproductor(t_seg: float) -> None:
            if player is not None and duracion_total > 0:
                try:
                    player.seek(max(0.0, float(t_seg)), relative=False)
                    slider_seek.set(max(0.0, min(1.0, float(t_seg) / duracion_total)))
                    lbl_tiempo.configure(text=f"{_fmt_tiempo(t_seg)} / {_fmt_tiempo(duracion_total)}")
                    win_r.after(10, _loop_reproductor)
                except Exception:
                    pass

        def _overlay_pos_en_reproductor(x_pct, y_pct, tipo, tam, rot, alt_pct=None) -> None:
            if x_pct == "seek":
                try:
                    _seek_en_reproductor(float(y_pct))
                except Exception:
                    pass
                return
            canvas_video.delete("overlay_pos")
            if (x_pct is None and alt_pct is None) or (not tipo and alt_pct is None):
                return
            try:
                # 1. Indicador en vivo de altura de texto / subtítulos
                if alt_pct is not None:
                    try:
                        v_alt = float(alt_pct)
                        sub_y = (v_alt / 100.0) * 480.0
                        canvas_video.create_line(0, sub_y, 270, sub_y, fill="#10b981", dash=(4, 3), width=1.5, tags="overlay_pos")
                        bw, bh = 190, 22
                        bx0 = (270 - bw) // 2
                        by0 = sub_y - (bh // 2)
                        canvas_video.create_rectangle(bx0 - 1, by0 - 1, bx0 + bw + 1, by0 + bh + 1, fill="#000000", outline="#10b981", width=1.5, tags="overlay_pos")
                        canvas_video.create_rectangle(bx0, by0, bx0 + bw, by0 + bh, fill="#071824", outline="", tags="overlay_pos")
                        canvas_video.create_text(135, sub_y, text=f"💬 Subtítulos ({v_alt:.0f}%)", fill="#38bdf8", font=("Segoe UI", 8, "bold"), tags="overlay_pos")
                    except Exception:
                        pass

                if x_pct is not None and y_pct is not None and tipo not in (None, "", "ninguno", "altura_only"):
                    px = (float(x_pct) / 100.0) * 270.0
                    py = (float(y_pct) / 100.0) * 480.0
                    r_px = 22 if tam == "chico" else (32 if tam == "medio" else 44)

                    if tipo in ("circulo", "ambos"):
                        canvas_video.create_oval(px - r_px - 2, py - r_px - 2, px + r_px + 2, py + r_px + 2, outline="#000000", width=5, tags="overlay_pos")
                        canvas_video.create_oval(px - r_px, py - r_px, px + r_px, py + r_px, outline="#ef4444", width=3, tags="overlay_pos")
                        canvas_video.create_line(px - 8, py, px + 8, py, fill="#000000", width=3, tags="overlay_pos")
                        canvas_video.create_line(px - 8, py, px + 8, py, fill="#38bdf8", width=1.5, tags="overlay_pos")
                        canvas_video.create_line(px, py - 8, px, py + 8, fill="#000000", width=3, tags="overlay_pos")
                        canvas_video.create_line(px, py - 8, px, py + 8, fill="#38bdf8", width=1.5, tags="overlay_pos")
                        canvas_video.create_oval(px - 3, py - 3, px + 3, py + 3, fill="#38bdf8", outline="#000000", width=1, tags="overlay_pos")

                    if tipo in ("flecha", "ambos"):
                        rad = math.radians(float(rot))
                        dist_flecha = 60
                        fx0 = px + dist_flecha * math.cos(rad)
                        fy0 = py + dist_flecha * math.sin(rad)
                        gap_c = (r_px + 4) if tipo == "ambos" else 0
                        tip_x = px + gap_c * math.cos(rad)
                        tip_y = py + gap_c * math.sin(rad)

                        canvas_video.create_line(fx0, fy0, tip_x, tip_y, fill="#000000", width=7, arrow=tk.LAST, arrowshape=(18, 20, 8), tags="overlay_pos")
                        canvas_video.create_line(fx0, fy0, tip_x, tip_y, fill="#f59e0b", width=3.5, arrow=tk.LAST, arrowshape=(15, 17, 6), tags="overlay_pos")
                        canvas_video.create_oval(tip_x - 5, tip_y - 5, tip_x + 5, tip_y + 5, outline="#000000", width=3, tags="overlay_pos")
                        canvas_video.create_oval(tip_x - 5, tip_y - 5, tip_x + 5, tip_y + 5, outline="#38bdf8", width=1.5, tags="overlay_pos")
                        canvas_video.create_oval(tip_x - 2, tip_y - 2, tip_x + 2, tip_y + 2, fill="#38bdf8", outline="", tags="overlay_pos")

                canvas_video.tag_raise("overlay_pos")
            except Exception:
                pass

        txt_guion_box = VisualScriptEditor(
            card_guion,
            ruta_video=ruta_video,
            on_preview_live=_overlay_pos_en_reproductor,
        )
        txt_guion_box.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))

        if ruta_guion.exists():
            try:
                txt_guion_raw = ruta_guion.read_text(encoding="utf-8", errors="replace")
                txt_guion_box.insert("1.0", txt_guion_raw)

                tono_leido = txt_guion_box.metadatos_ocultos.get("TONO_VIDEO", "").strip()
                if tono_leido:
                    if tono_leido.lower() in ("sin_musica", "sin musica", "ninguna", "ninguno", "none"):
                        opt_musica.set("Sin Música")
                    elif tono_leido.lower() in ("auto", "fondo", "neutral"):
                        opt_musica.set("Auto")
                    else:
                        for p_nom in pistas_disponibles:
                            if tono_leido.lower() == p_nom.lower() or tono_leido.lower() in p_nom.lower():
                                opt_musica.set(p_nom)
                                break

                voz_leida = txt_guion_box.metadatos_ocultos.get("VOZ_NARRADOR", "").strip()
                if voz_leida and voz_leida in VOCES_DISPONIBLES:
                    opt_voz.set(voz_leida)
                    voz_var.set(voz_leida)
            except Exception:
                pass

        if not es_modo_editado and not es_modo_manual_inicial:
            ctk.CTkButton(
                card_guion,
                text="Re-renderizar con guion editado",
                command=lambda: _responder("reeditar"),
                height=34, corner_radius=10,
                fg_color=PURPLE_MAIN, hover_color=PURPLE_HOVER,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color="#ffffff",
            ).grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        else:
            tam_mb = ""
            try:
                tam_mb = f" · {ruta_video.stat().st_size / (1024 * 1024):.1f} MB"
            except Exception:
                pass
            ctk.CTkLabel(
                card_guion,
                text=f"{ruta_video.name}{tam_mb}",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=TEXT_DIM, anchor="w",
            ).grid(row=2, column=0, sticky="w", padx=16, pady=(0, 10))

        # Tarjeta de acciones (fija abajo)
        card_acciones = ctk.CTkFrame(
            col_der, fg_color=CARD_BG, corner_radius=18,
            border_width=1, border_color=CARD_BORDER,
        )
        card_acciones.grid(row=2, column=0, sticky="ew")

        if es_modo_manual_inicial:
            btn_subir = ctk.CTkButton(
                card_acciones,
                text="🎬 Renderizar Short con este Guion",
                command=lambda: _responder("reeditar"),
                height=40, corner_radius=12,
                fg_color=PURPLE_MAIN, hover_color=PURPLE_HOVER,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color="#ffffff",
            )
            btn_subir.pack(fill="x", padx=16, pady=(12, 8))
        else:
            btn_subir = ctk.CTkButton(
                card_acciones,
                text="Guardar en Carpeta" if solo_guardar else "Subir a YouTube",
                command=lambda: _responder("subir"),
                height=40, corner_radius=12,
                fg_color=GREEN_ACCENT, hover_color="#059669",
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color="#ffffff",
            )
            btn_subir.pack(fill="x", padx=16, pady=(12, 8))

        row_sec = ctk.CTkFrame(card_acciones, fg_color="transparent")
        row_sec.pack(fill="x", padx=16, pady=(0, 12))
        row_sec.grid_columnconfigure((0, 1), weight=1, uniform="sec_btn")

        ctk.CTkButton(
            row_sec,
            text="Siguiente Video" if es_modo_editado else "Buscar Otro Video",
            command=lambda: _responder("buscar_otro"),
            height=32, corner_radius=10,
            fg_color=INPUT_BG, hover_color="#1e2538",
            border_width=1, border_color="#2a3147",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#ffffff",
        ).grid(row=0, column=0, padx=(0, 4), sticky="ew")

        ctk.CTkButton(
            row_sec,
            text="Cancelar Proceso",
            command=lambda: _responder("descartar"),
            height=32, corner_radius=10,
            fg_color="#1c2030", hover_color="#7f1d1d",
            border_width=1, border_color="#3b4252",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#f87171",
        ).grid(row=0, column=1, padx=(4, 0), sticky="ew")

        # Inicialización del reproductor ffpyplayer (inicia pausado)
        try:
            from ffpyplayer.player import MediaPlayer
            from PIL import Image, ImageTk

            player = MediaPlayer(str(ruta_video), ff_opts={"autoexit": False, "paused": True})
            player.set_size(270, 480)
            player.set_pause(True)
        except Exception as e_init:
            player = None
            canvas_video.create_text(
                135,
                240,
                text=f"No se pudo inicializar\nel reproductor interno:\n{e_init}",
                fill="#ef4444",
                font=("Segoe UI", 10),
                justify="center",
            )

        def _loop_reproductor() -> None:
            nonlocal duracion_total, reproduciendo
            if cancelado_reproductor:
                return

            if player is not None:
                if duracion_total <= 1.0:
                    try:
                        meta = player.get_metadata()
                        if meta and meta.get("duration"):
                            duracion_total = float(meta["duration"])
                    except Exception:
                        pass

                frame, val = player.get_frame()
                if val == "eof":
                    try:
                        player.seek(0.0, relative=False)
                        player.set_pause(True)
                        reproduciendo = False
                        btn_play.configure(text="▶")
                    except Exception:
                        pass
                    if not arrastrando_slider:
                        slider_seek.set(0.0)
                        lbl_tiempo.configure(text=f"00:00 / {_fmt_tiempo(duracion_total)}")
                    delay_ms = 30
                elif frame is not None:
                    img, pts = frame
                    w, h = img.get_size()
                    try:
                        pil_img = Image.frombytes("RGB", (w, h), bytes(img.to_bytearray()[0]))
                        photo = ImageTk.PhotoImage(pil_img)
                        canvas_video.delete("frame_video")
                        canvas_video.create_image(0, 0, image=photo, anchor="nw", tags="frame_video")
                        canvas_video.image = photo
                        canvas_video.tag_lower("frame_video")
                        canvas_video.tag_raise("overlay_pos")
                    except Exception:
                        pass

                    if not arrastrando_slider and duracion_total > 0:
                        progreso = max(0.0, min(1.0, pts / duracion_total))
                        slider_seek.set(progreso)
                        lbl_tiempo.configure(text=f"{_fmt_tiempo(pts)} / {_fmt_tiempo(duracion_total)}")

                    delay_ms = max(5, int(val * 1000)) if isinstance(val, (int, float)) and val > 0 else 10
                else:
                    delay_ms = max(5, int(val * 1000)) if isinstance(val, (int, float)) and val > 0 else 12

                if not reproduciendo:
                    delay_ms = max(delay_ms, 120)

                win_r.after(delay_ms, _loop_reproductor)

        if player is not None:
            win_r.after(10, _loop_reproductor)
    def abrir_dialogo_frenado(datos_frenado: Dict[str, Any]) -> None:
        subidos = datos_frenado.get("subidos", [])
        editados = datos_frenado.get("editados", [])
        cant_cola_total = datos_frenado.get("cant_total", 1)

        win_f = ctk.CTkToplevel(root)
        win_f.title("Subida Detenida · Estado del Proceso")
        win_f.geometry("640x480")
        win_f.resizable(False, False)
        win_f.configure(fg_color=BG_DARK)
        win_f.transient(root)
        aplicar_icono_ventana(win_f)
        win_f.grab_set()

        if not subidos and not editados:
            color_badge = "#ef4444"
            bg_badge = "#38161c"
            txt_badge = "PROCESO CANCELADO A TIEMPO"
            tit_header = "No se editó ni se subió ningún video"
            sub_header = "Detectamos que frenaste la operación a tiempo por clic accidental.\nTu canal de YouTube, tus archivos y tu cuota diaria están 100% intactos."
        elif editados and not subidos:
            color_badge = "#facc15"
            bg_badge = "#342813"
            txt_badge = "SUBIDA A YOUTUBE DETENIDA"
            tit_header = f"Se guardaron {len(editados)} video(s) en tu equipo"
            sub_header = "La subida a YouTube fue detenida. Los videos que ya terminaron de procesarse\nquedaron a salvo en tu carpeta 'output_shorts' sin publicarse en YouTube."
        else:
            color_badge = "#a855f7"
            bg_badge = "#2c153d"
            txt_badge = "PROCESO DETENIDO CON ENTREGAS PARCIALES"
            tit_header = f"{len(subidos)} Short(s) subido(s) y {len(editados)} guardado(s)"
            sub_header = "Se frenó la operación. A continuación puedes ver qué videos ya quedaron\npublicados/programados en YouTube y cuáles quedaron guardados localmente."

        top_f = ctk.CTkFrame(win_f, fg_color="transparent")
        top_f.pack(fill="x", padx=24, pady=(20, 10))

        badge = ctk.CTkFrame(top_f, fg_color=bg_badge, corner_radius=10, border_width=1, border_color=color_badge)
        badge.pack(anchor="w", pady=(0, 6))
        ctk.CTkLabel(
            badge,
            text=txt_badge,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=color_badge,
        ).pack(padx=10, pady=3)

        ctk.CTkLabel(
            top_f,
            text=tit_header,
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            text_color=TEXT_MAIN,
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            top_f,
            text=sub_header,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_MUTED,
            anchor="w",
            justify="left",
        ).pack(fill="x")

        scroll_detalles = ctk.CTkScrollableFrame(win_f, fg_color="#101522", corner_radius=14, border_width=1, border_color=CARD_BORDER)
        scroll_detalles.pack(fill="both", expand=True, padx=24, pady=(6, 14))

        if not subidos and not editados:
            card_info = ctk.CTkFrame(scroll_detalles, fg_color=CARD_BG, corner_radius=12, border_width=1, border_color=CARD_BORDER)
            card_info.pack(fill="x", padx=10, pady=10)
            ctk.CTkLabel(
                card_info,
                text="Estado del Sistema:",
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color=TEXT_MAIN,
                anchor="w",
            ).pack(fill="x", padx=14, pady=(12, 4))
            ctk.CTkLabel(
                card_info,
                text="• Videos subidos a YouTube: 0\n• Videos generados en disco: 0\n• Cuota de YouTube API consumida: 0\n• Estado: Detenido inmediatamente sin modificaciones.",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=TEXT_MUTED,
                anchor="w",
                justify="left",
            ).pack(fill="x", padx=14, pady=(0, 12))
        else:
            if subidos:
                ctk.CTkLabel(
                    scroll_detalles,
                    text=f"Videos Subidos por Completo a YouTube ({len(subidos)}):",
                    font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                    text_color="#4ade80",
                    anchor="w",
                ).pack(fill="x", padx=8, pady=(8, 4))
                for s_item in subidos:
                    s_card = ctk.CTkFrame(scroll_detalles, fg_color=CARD_BG, corner_radius=10, border_width=1, border_color="#1a3b2b")
                    s_card.pack(fill="x", padx=8, pady=3)
                    row_s = ctk.CTkFrame(s_card, fg_color="transparent")
                    row_s.pack(fill="x", padx=12, pady=8)
                    u_s = s_item.get("url") or ""
                    if u_s:
                        ctk.CTkButton(
                            row_s,
                            text="Ver en YouTube",
                            command=lambda u=u_s: webbrowser.open(u),
                            width=110,
                            height=26,
                            corner_radius=8,
                            fg_color="#1e2436",
                            hover_color="#2b354f",
                            text_color=CYAN_ACCENT,
                            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                        ).pack(side="right", padx=(8, 0))
                    ctk.CTkLabel(
                        row_s,
                        text=f"Reel #{s_item.get('reel_num', 1)}: {str(s_item.get('titulo', 'Short'))[:50]}",
                        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                        text_color=TEXT_MAIN,
                        anchor="w",
                    ).pack(side="left", fill="x", expand=True)

            if editados:
                ctk.CTkLabel(
                    scroll_detalles,
                    text=f"Videos Editados y Guardados en Carpeta (No Subidos) ({len(editados)}):",
                    font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                    text_color="#38bdf8",
                    anchor="w",
                ).pack(fill="x", padx=8, pady=(12, 4))
                for e_item in editados:
                    e_card = ctk.CTkFrame(scroll_detalles, fg_color=CARD_BG, corner_radius=10, border_width=1, border_color="#1e2e42")
                    e_card.pack(fill="x", padx=8, pady=3)
                    row_e = ctk.CTkFrame(e_card, fg_color="transparent")
                    row_e.pack(fill="x", padx=12, pady=8)
                    ctk.CTkLabel(
                        row_e,
                        text=f"Reel #{e_item.get('reel_num', 1)}: {str(e_item.get('archivo', 'video.mp4'))[:45]}",
                        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                        text_color="#f8fafc",
                        anchor="w",
                    ).pack(side="left", fill="x", expand=True)
                    ctk.CTkLabel(
                        row_e,
                        text="Guardado en output_shorts",
                        font=ctk.CTkFont(family="Segoe UI", size=11),
                        text_color="#94a3b8",
                    ).pack(side="right")

        bot_row = ctk.CTkFrame(win_f, fg_color="transparent")
        bot_row.pack(fill="x", padx=24, pady=(0, 20))

        if editados or subidos:
            ctk.CTkButton(
                bot_row,
                text="Abrir Carpeta 'output_shorts'",
                command=abrir_carpeta_salida,
                height=38,
                corner_radius=12,
                fg_color="#1e2436",
                hover_color="#2e3852",
                border_width=1,
                border_color=CARD_BORDER,
                text_color=CYAN_ACCENT,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            ).pack(side="left")

        ctk.CTkButton(
            bot_row,
            text="Entendido",
            command=lambda: win_f.destroy(),
            height=38,
            width=120,
            corner_radius=12,
            fg_color=PURPLE_MAIN,
            hover_color=PURPLE_HOVER,
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        ).pack(side="right")

    def ejecutar_flujo_1_clic(solo_guardar_override: Optional[bool] = None) -> None:
        es_modo_manual_cfg = "Manual" in modo_subida_var.get()
        api_k = "\n".join(obtener_gemini_api_keys()) or obtener_gemini_api_key()
        if not api_k and not es_modo_manual_cfg and not ("Editado" in modo_fuente_var.get()):
            messagebox.showinfo(
                "Configura tu API Key Gratuita (1 vez)",
                "Primero ingresa tu clave gratuita de Google AI Studio en Ajustes.",
            )
            abrir_ventana_ajustes()
            return

        mf_act = modo_fuente_var.get()
        es_modo_canales = "Canales" in mf_act
        es_modo_editado = "Editado" in mf_act

        if es_modo_canales and not lista_canales:
            messagebox.showwarning(
                "Sin canales cargados",
                "Agrega al menos un canal de YouTube arriba (pegando su link o @nombre y tocando '+ Agregar Canal').",
            )
            return

        if es_modo_editado and not lista_videos_editados_locales:
            messagebox.showwarning(
                "Sin videos seleccionados",
                "Toca '+ Seleccionar Video(s) MP4' para elegir tus videos editados antes de importar y subir.",
            )
            return

        links_a_procesar: List[str] = []
        if not es_modo_canales and not es_modo_editado:
            links_a_procesar = obtener_links_ingresados()
            if not links_a_procesar:
                if DEFAULT_VIDEO_INPUT.exists():
                    links_a_procesar = [str(DEFAULT_VIDEO_INPUT)]
                else:
                    messagebox.showwarning(
                        "Sin links ingresados",
                        "Pega al menos un link de video de YouTube antes de comenzar.",
                    )
                    return

        if not editando_lock.acquire(blocking=False):
            return

        voz_elegida = VOCES_DISPONIBLES.get(voz_var.get(), EDGE_VOICE_DEFAULT)
        encuadre_elegido = encuadre_map.get(encuadre_var.get(), "full")
        min_v = MAPA_MIN_VIEWS.get(min_views_var.get(), 1_000_000)
        if es_modo_canales:
            cant_cola = MAPA_CANTIDAD_TOTAL.get(cantidad_total_var.get(), 2)
        elif es_modo_editado:
            cant_cola = len(lista_videos_editados_locales)
        else:
            cant_cola = len(links_a_procesar)
        horarios_lote_plan = calcular_lista_horarios_actual()
        es_custom_activo = "Personalizado" in modo_contenido_var.get()
        pref_modelo_ia = "gemini-3.8-flash" 
        if solo_guardar_override is not None:
            solo_guardar = bool(solo_guardar_override)
        else:
            solo_guardar = False
        solo_guardar_actual[0] = solo_guardar

        modo_priv = "private"
        if "público" in privacidad_var.get().lower() or "publico" in privacidad_var.get().lower():
            modo_priv = "public"
        elif "oculto" in privacidad_var.get().lower():
            modo_priv = "unlisted"

        _mostrar_modo_progreso_activo(True)

        estados_milestones: List[Dict[str, str]] = [
            {"tipo": "pendiente", "texto": f"Reel {i + 1}: En cola"}
            for i in range(cant_cola)
        ]
        _renderizar_milestones_ui(estados_milestones)
        _actualizar_progreso_ui(1.0, "Buscando y seleccionando videos...", "#facc15", PURPLE_MAIN)

        def tarea_auto_total() -> None:
            nonlocal voz_elegida
            voz_elegida = VOCES_DISPONIBLES.get(voz_var.get(), EDGE_VOICE_DEFAULT)
            stdout_orig = sys.stdout
            stderr_orig = sys.stderr
            sys.stdout = RedireccionadorSilencioso(cola_logs)
            sys.stderr = RedireccionadorSilencioso(cola_logs)
            links_subidos: List[str] = []
            shorts_subidos: List[Dict[str, Any]] = []
            shorts_guardados_disco: List[Dict[str, Any]] = []
            try:
                from subir_a_youtube import subir_video

                horarios_lote = list(horarios_lote_plan)
                while len(horarios_lote) < cant_cola:
                    horarios_lote.append(None)

                # ==================================================================
                # FASE 1: ELEGIR TODOS LOS VIDEOS DEL LOTE PRIMERO
                # (Si se sube a Todas o Grupo, cada Reel elige video de los canales
                #  guardados en la cuenta a la que va dirigido ese Reel)
                # ==================================================================
                from subir_a_youtube import listar_cuentas_vinculadas
                todas_cuentas_v = listar_cuentas_vinculadas()
                if not todas_cuentas_v:
                    todas_cuentas_v = [{"id": "principal", "nombre": "Canal Principal"}]
                dict_cuentas_v = {str(c.get("id") or "principal"): c for c in todas_cuentas_v}

                modo_c_lote = str(estado_seleccion_cuentas.get("modo") or "una")
                cid_unica = str(estado_seleccion_cuentas.get("cuenta_id") or todas_cuentas_v[0]["id"])
                if modo_c_lote == "todas":
                    cuentas_objetivo_lote = list(todas_cuentas_v)
                elif modo_c_lote == "grupo":
                    g_ids = [g for g in (estado_seleccion_cuentas.get("grupo_ids") or []) if g in dict_cuentas_v]
                    cuentas_objetivo_lote = [dict_cuentas_v[g] for g in g_ids] if g_ids else [dict_cuentas_v.get(cid_unica, todas_cuentas_v[0])]
                else:
                    cuentas_objetivo_lote = [dict_cuentas_v.get(cid_unica, todas_cuentas_v[0])]

                strat_lote = str(estado_seleccion_cuentas.get("estrategia") or "cross_posting")
                es_cross_post_lote = (modo_c_lote in ("todas", "grupo") and strat_lote == "cross_posting" and len(cuentas_objetivo_lote) > 1)

                videos_seleccionados: List[Dict[str, object]] = []
                ids_reservados_sesion: List[str] = []

                if es_modo_canales:
                    es_rotacion = "Rotación" in orden_canales_var.get()
                    for idx_sel in range(cant_cola):
                        num_s = idx_sel + 1
                        pref_s = f"[Reel {num_s}/{cant_cola}] " if cant_cola > 1 else ""
                        if es_cross_post_lote:
                            cuenta_reel_info = cuentas_objetivo_lote[0]
                            cid_reel = str(cuenta_reel_info.get("id") or "principal")
                            cnom_reel = " + ".join(str(c.get("nombre") or c.get("id"))[:10] for c in cuentas_objetivo_lote)
                            cuentas_este_reel = list(cuentas_objetivo_lote)
                            canales_de_esta_cuenta = []
                            for c_o in cuentas_objetivo_lote:
                                c_o_id = str(c_o.get("id") or "")
                                for can in (canales_por_cuenta.get(c_o_id) or []):
                                    if can not in canales_de_esta_cuenta:
                                        canales_de_esta_cuenta.append(can)
                            if not canales_de_esta_cuenta:
                                canales_de_esta_cuenta = list(lista_canales)
                        else:
                            cuenta_reel_info = cuentas_objetivo_lote[idx_sel % len(cuentas_objetivo_lote)]
                            cid_reel = str(cuenta_reel_info.get("id") or "principal")
                            cnom_reel = str(cuenta_reel_info.get("nombre") or cid_reel)
                            cuentas_este_reel = [cuenta_reel_info]
                            canales_de_esta_cuenta = list(canales_por_cuenta.get(cid_reel) or lista_canales)
                            if not canales_de_esta_cuenta:
                                canales_de_esta_cuenta = list(lista_canales)

                        estados_milestones[idx_sel] = {"tipo": "activo", "texto": f"Reel {num_s}: Eligiendo video..."}
                        copia_ms = [dict(x) for x in estados_milestones]
                        root.after(0, lambda cm=copia_ms: _renderizar_milestones_ui(cm))

                        canales_intentar: List[str] = []
                        es_modo_fijo = ("Único" in orden_canales_var.get() or "fijo" in orden_canales_var.get().lower())
                        if es_modo_fijo and canal_fijo_var.get():
                            c_fijo = canal_fijo_var.get()
                            canales_intentar = [c_fijo] if c_fijo in canales_de_esta_cuenta else ([c_fijo] + canales_de_esta_cuenta)
                        elif es_rotacion and canales_de_esta_cuenta:
                            for offset in range(len(canales_de_esta_cuenta)):
                                pos = (estado_rotacion["idx"] + offset) % len(canales_de_esta_cuenta)
                                canales_intentar.append(canales_de_esta_cuenta[pos])
                        else:
                            canales_intentar = list(canales_de_esta_cuenta)
                            random.shuffle(canales_intentar)

                        elegido_info: Optional[Tuple[str, str, int]] = None
                        canal_usado = ""
                        for c_cand in canales_intentar:
                            if evento_cancelar.is_set():
                                raise InterruptedError("Operación detenida por el usuario antes de procesar videos.")
                            c_lbl = etiqueta_corta_canal(c_cand)
                            pct_busq = 1.0 + (idx_sel / cant_cola) * 6.0
                            root.after(
                                0,
                                lambda pg=pct_busq, cl=c_lbl, p=pref_s: (
                                    btn_auto_1clic.configure(text=f"{p}ELIGIENDO SHORT EN {cl.upper()}..."),
                                    _actualizar_progreso_ui(
                                        pg,
                                        f"{p}Escaneando {cl} buscando Short viral ({min_views_var.get()})...",
                                        "#facc15",
                                        PURPLE_MAIN,
                                    ),
                                ),
                            )
                            res_viral = buscar_short_viral_en_canal(
                                c_cand,
                                min_views=min_v,
                                estricto_min_views=True,
                                cuenta_id=cid_reel,
                                ids_excluir=ids_reservados_sesion,
                                cancelar_check=lambda: evento_cancelar.is_set(),
                            )
                            if res_viral:
                                elegido_info = res_viral
                                canal_usado = c_cand
                                ids_reservados_sesion.append(res_viral[0])
                                if es_rotacion and c_cand in lista_canales:
                                    estado_rotacion["idx"] = (lista_canales.index(c_cand) + 1) % len(lista_canales)
                                    root.after(0, _guardar_memoria)
                                    root.after(0, renderizar_chips_canales)
                                break
                            else:
                                print(f"[*] Ningún Short con >= {min_v:,} vistas en {c_lbl}. Buscando en el siguiente canal...")

                        if not elegido_info:
                            raise RuntimeError(
                                f"No se encontró ningún Short con al menos {min_views_var.get()} sin usar en ninguno de los "
                                f"canales configurados ({len(canales_intentar)} revisados para '{cnom_reel}').\n\n"
                                f"Sugerencias:\n"
                                f"• Baja el filtro en Ajustes > Filtro de Vistas Mínimas (ej. 500K+ o 100K+).\n"
                                f"• Agrega más canales con Shorts virales a tu lista."
                            )

                        u_vid, t_vid, v_vid = elegido_info
                        videos_seleccionados.append(
                            {
                                "url": u_vid,
                                "titulo_orig": t_vid,
                                "vistas": v_vid,
                                "canal": etiqueta_corta_canal(canal_usado),
                                "cuenta_id": cid_reel,
                                "cuenta_nombre": cnom_reel,
                                "cuentas_destino": list(cuentas_este_reel),
                            }
                        )
                        estados_milestones[idx_sel] = {"tipo": "pendiente", "texto": f"Reel {num_s}: Elegido"}
                        copia_ms2 = [dict(x) for x in estados_milestones]
                        root.after(0, lambda cm=copia_ms2: _renderizar_milestones_ui(cm))
                elif es_modo_editado:
                    for idx_ed, p_ed in enumerate(lista_videos_editados_locales):
                        if es_cross_post_lote:
                            c_reel = cuentas_objetivo_lote[0]
                            cid_reel = str(c_reel.get("id") or "principal")
                            cnom_reel = " + ".join(str(c.get("nombre") or c.get("id"))[:10] for c in cuentas_objetivo_lote)
                            cuentas_este_reel = list(cuentas_objetivo_lote)
                        else:
                            c_idx = idx_ed % len(cuentas_objetivo_lote)
                            c_reel = cuentas_objetivo_lote[c_idx]
                            cid_reel = str(c_reel.get("id") or "principal")
                            cnom_reel = str(c_reel.get("nombre") or cid_reel)
                            cuentas_este_reel = [c_reel]
                        nombre_limpio = p_ed.stem.replace("_", " ").replace("-", " ").title()
                        videos_seleccionados.append(
                            {
                                "url": str(p_ed),
                                "ruta_archivo_local": str(p_ed),
                                "titulo_orig": nombre_limpio,
                                "vistas": 0,
                                "canal": "Video Editado Local",
                                "cuenta_id": cid_reel,
                                "cuenta_nombre": cnom_reel,
                                "cuentas_destino": list(cuentas_este_reel),
                            }
                        )
                        estados_milestones[idx_ed] = {"tipo": "pendiente", "texto": f"Reel {idx_ed + 1}: Video Listo"}
                    copia_ms2 = [dict(x) for x in estados_milestones]
                    root.after(0, lambda cm=copia_ms2: _renderizar_milestones_ui(cm))
                else:
                    for idx_u, u_link in enumerate(links_a_procesar):
                        if es_cross_post_lote:
                            c_reel = cuentas_objetivo_lote[0]
                            cid_reel = str(c_reel.get("id") or "principal")
                            cnom_reel = " + ".join(str(c.get("nombre") or c.get("id"))[:10] for c in cuentas_objetivo_lote)
                            cuentas_este_reel = list(cuentas_objetivo_lote)
                        else:
                            c_idx = idx_u % len(cuentas_objetivo_lote)
                            c_reel = cuentas_objetivo_lote[c_idx]
                            cid_reel = str(c_reel.get("id") or "principal")
                            cnom_reel = str(c_reel.get("nombre") or cid_reel)
                            cuentas_este_reel = [c_reel]
                        videos_seleccionados.append(
                            {
                                "url": u_link,
                                "titulo_orig": f"Video Link #{idx_u + 1}",
                                "vistas": 0,
                                "canal": "Link de Video",
                                "cuenta_id": cid_reel,
                                "cuenta_nombre": cnom_reel,
                                "cuentas_destino": list(cuentas_este_reel),
                            }
                        )
                        estados_milestones[idx_u] = {"tipo": "pendiente", "texto": f"Reel {idx_u + 1}: Listo"}
                    copia_ms2 = [dict(x) for x in estados_milestones]
                    root.after(0, lambda cm=copia_ms2: _renderizar_milestones_ui(cm))

                # ==================================================================
                # FASE 1.5 (SOLO SI ESTÁ EN MODO PERSONALIZADO):
                # Mostrar ventana con los links elegidos para escribir Título/Desc/Guión
                # y darle a "Comenzar Edición y Subida Ahora"
                # ==================================================================
                if es_custom_activo:
                    for i_limpiar in range(len(videos_seleccionados)):
                        if i_limpiar not in datos_custom_reels:
                            datos_custom_reels[i_limpiar] = {
                                "titulo": "", "descripcion": "", "guion": "",
                                "usar_ia_tit": True, "usar_ia_desc": True, "usar_ia_guion": True
                            }
                    ev_modal = threading.Event()
                    res_modal = {"confirmado": False}
                    root.after(
                        0,
                        lambda: (
                            btn_auto_1clic.configure(text="PERSONALIZA TUS REELS EN LA VENTANA..."),
                            _actualizar_progreso_ui(
                                8.0,
                                "Videos elegidos: revisa los links y personaliza Título/Descripción/Guión...",
                                CYAN_ACCENT,
                                PURPLE_MAIN,
                            ),
                            _abrir_ventana_personalizar_lote(videos_seleccionados, ev_modal, res_modal),
                        ),
                    )
                    ev_modal.wait()
                    if not res_modal.get("confirmado"):
                        def _on_cancel() -> None:
                            _actualizar_progreso_ui(0.0, "Operación cancelada antes de editar.", TEXT_MUTED, PURPLE_MAIN)
                            _mostrar_modo_progreso_activo(False)

                        root.after(0, _on_cancel)
                        return

                # ==================================================================
                # FASE 2: DESCARGAR, CREAR GUIÓN (IA O CUSTOM), RENDERIZAR Y SUBIR
                # ==================================================================
                for idx_lote, info_sel in enumerate(videos_seleccionados):
                    if evento_cancelar.is_set():
                        raise InterruptedError("Operación detenida por el usuario.")
                    num_actual = idx_lote + 1
                    pref_lote = f"[Reel {num_actual}/{cant_cola}] " if cant_cola > 1 else ""
                    sched_actual = horarios_lote[idx_lote] if idx_lote < len(horarios_lote) else None
                    sched_str = sched_actual if sched_actual else "no"
                    url_descargar = str(info_sel.get("url") or "")
                    titulo_orig = str(info_sel.get("titulo_orig") or "")
                    vistas_orig = int(info_sel.get("vistas") or 0)

                    base_pct_reel = (idx_lote / cant_cola) * 100.0
                    ancho_pct_reel = 100.0 / cant_cola

                    def _set_subprogreso(frac_interna: float, msg_est: str, col_est: str = "#ffffff") -> None:
                        pct_g = base_pct_reel + (max(0.0, min(1.0, frac_interna)) * ancho_pct_reel)
                        root.after(
                            0,
                            lambda pg=pct_g, m=msg_est, c=col_est: _actualizar_progreso_ui(pg, m, "#ffffff", PURPLE_MAIN),
                        )

                    def _actualizar_milestone_actual(tipo_m: str, texto_corto: str) -> None:
                        estados_milestones[idx_lote] = {"tipo": tipo_m, "texto": texto_corto}
                        copia_m = [dict(x) for x in estados_milestones]
                        root.after(0, lambda cm=copia_m: _renderizar_milestones_ui(cm))

                    posible_local = Path(url_descargar)
                    if posible_local.exists() and posible_local.is_file():
                        ruta_video_usar = posible_local
                    else:
                        _actualizar_milestone_actual("activo", f"Reel {num_actual}: Descargando...")
                        _set_subprogreso(
                            0.12,
                            f"{pref_lote}Descargando '{titulo_orig[:38]}...' ({vistas_orig:,} vistas)"
                            if vistas_orig > 0
                            else f"{pref_lote}Descargando video de YouTube en máxima calidad...",
                        )
                        ruta_video_usar = descargar_video_youtube(
                            url_descargar,
                            cancelar_check=lambda: evento_cancelar.is_set(),
                        )
                        if evento_cancelar.is_set():
                            raise InterruptedError("Operación detenida por el usuario tras descargar el video.")
                        if ULTIMA_INFO_YTDLP.get("titulo"):
                            titulo_orig = ULTIMA_INFO_YTDLP["titulo"]

                    if es_modo_editado:
                        # Modo Subir Video Editado: asegurar formato vertical 9:16 y <=59.9s para YouTube Shorts
                        ruta_final = asegurar_formato_short(ruta_video_usar)
                        ultimo_video_generado[0] = ruta_final
                        _actualizar_milestone_actual("activo", f"Reel {num_actual}: Video Listo")
                        _set_subprogreso(0.35, f"{pref_lote}Procesando video editado ({ruta_final.name})...", CYAN_ACCENT)

                        custom_data = datos_custom_reels[idx_lote] if idx_lote < len(datos_custom_reels) else {}
                        usar_ia_tit = custom_data.get("usar_ia_tit", True) if es_custom_activo else True
                        usar_ia_desc = custom_data.get("usar_ia_desc", True) if es_custom_activo else True
                        c_tit = custom_data.get("titulo", "").strip() if (es_custom_activo and not usar_ia_tit) else ""
                        c_desc = custom_data.get("descripcion", "").strip() if (es_custom_activo and not usar_ia_desc) else ""

                        if es_custom_activo and c_tit:
                            tit_yt = f"{c_tit} #shorts" if "#shorts" not in c_tit.lower() else c_tit
                            d_final = c_desc or f"{c_tit} #shorts"
                            if "#shorts" not in d_final.lower():
                                d_final = f"{d_final}\n\n#shorts"
                            DEFAULT_GUION_TXT.write_text(f"TITULO_SUPERIOR: {c_tit}\nTITULO_YOUTUBE: {tit_yt}\nDESCRIPCION_YOUTUBE: {d_final}\nSCHEDULE: {sched_str}\n\n[GUION]\n", encoding="utf-8")
                            _set_subprogreso(0.65, f"{pref_lote}Título personalizado asignado...", CYAN_ACCENT)
                        else:
                            _actualizar_milestone_actual("activo", f"Reel {num_actual}: Título con IA...")
                            root.after(0, lambda p=pref_lote: btn_auto_1clic.configure(text=f"{p}GENERANDO TÍTULO CON IA..."))
                            _set_subprogreso(0.45, f"{pref_lote}Analizando video para título viral con IA...", CYAN_ACCENT)
                            try:
                                def _cb_tit_solo(sub_frac: float, msg_ia: str) -> None:
                                    _set_subprogreso(0.45 + max(0.0, min(1.0, sub_frac)) * 0.20, f"{pref_lote}{msg_ia}", CYAN_ACCENT)

                                generar_guion_con_gemini_flash(
                                    ruta_video=ruta_final,
                                    api_key=api_k,
                                    schedule_str=sched_str,
                                    modo_privacidad="privado" if modo_priv == "private" else modo_priv,
                                    contexto_titulo_orig=titulo_orig,
                                    modelo_preferido=pref_modelo_ia,
                                    progreso_cb=_cb_tit_solo,
                                    cancelar_check=lambda: evento_cancelar.is_set(),
                                )
                                if evento_cancelar.is_set():
                                    raise InterruptedError("Operación detenida por el usuario tras generar el título.")
                            except InterruptedError:
                                raise
                            except Exception as e_ia:
                                print(f"[!] Aviso al generar título IA: {e_ia}. Usando nombre de archivo.")
                                tit_fall = titulo_orig or ruta_final.stem
                                DEFAULT_GUION_TXT.write_text(f"TITULO_SUPERIOR: {tit_fall}\nTITULO_YOUTUBE: {tit_fall} #shorts\nSCHEDULE: {sched_str}\n\n[GUION]\n", encoding="utf-8")
                            _set_subprogreso(0.65, f"{pref_lote}Título listo...", CYAN_ACCENT)
                    else:
                        custom_data = datos_custom_reels[idx_lote] if idx_lote < len(datos_custom_reels) else {}
                        usar_ia_tit = custom_data.get("usar_ia_tit", True) if es_custom_activo else True
                        usar_ia_desc = custom_data.get("usar_ia_desc", True) if es_custom_activo else True
                        usar_ia_guion = custom_data.get("usar_ia_guion", True) if es_custom_activo else True

                        c_tit = custom_data.get("titulo", "").strip() if (es_custom_activo and not usar_ia_tit) else ""
                        c_desc = custom_data.get("descripcion", "").strip() if (es_custom_activo and not usar_ia_desc) else ""
                        c_guion = custom_data.get("guion", "").strip() if (es_custom_activo and not usar_ia_guion) else ""

                        es_modo_manual = ("Manual" in modo_subida_var.get())
                        es_modo_manual_inicial = False

                        if es_modo_manual:
                            _actualizar_milestone_actual("activo", f"Reel {num_actual}: Abriendo editor manual...")
                            _set_subprogreso(0.30, f"{pref_lote}Preparando video y plantilla de guion manual...", PURPLE_MAIN)
                            root.after(0, lambda p=pref_lote: btn_auto_1clic.configure(text=f"{p}LISTO PARA EDITAR GUION..."))

                            tit_base = c_tit or titulo_orig or ruta_video_usar.stem
                            plantilla_raw = generar_plantilla_guion_manual(
                                ruta_video=ruta_video_usar,
                                titulo_sugerido=tit_base,
                                sched_str=sched_str,
                                modo_priv="privado" if modo_priv == "private" else modo_priv,
                                modo_encuadre=encuadre_elegido,
                                descripcion_custom=c_desc,
                            )
                            DEFAULT_GUION_TXT.write_text(plantilla_raw, encoding="utf-8")
                            ruta_final = ruta_video_usar
                            ultimo_video_generado[0] = ruta_final
                            es_modo_manual_inicial = True
                        else:
                            guion_ya_listo = False
                            if es_custom_activo and c_guion:
                                _actualizar_milestone_actual("activo", f"Reel {num_actual}: Guión propio...")
                                _set_subprogreso(0.26, f"{pref_lote}Aplicando tu guión y título personalizados...")
                                guion_ya_listo = _aplicar_custom_a_guion_txt(
                                    idx_reel=idx_lote,
                                    ruta_video=ruta_video_usar,
                                    custom_tit=c_tit,
                                    custom_desc=c_desc,
                                    custom_guion=c_guion,
                                    sched_str=sched_str,
                                    modo_priv="privado" if modo_priv == "private" else modo_priv,
                                )

                            if not guion_ya_listo:
                                _actualizar_milestone_actual("activo", f"Reel {num_actual}: Creando guión IA...")
                                root.after(
                                    0,
                                    lambda p=pref_lote: btn_auto_1clic.configure(
                                        text=f"{p}CREANDO GUIÓN VIRAL CON IA..."
                                    ),
                                )
                                def _cb_guion(sub_frac: float, msg_ia: str) -> None:
                                    frac_ia = 0.12 + max(0.0, min(1.0, sub_frac)) * 0.16
                                    _set_subprogreso(frac_ia, f"{pref_lote}{msg_ia}", "#facc15")
                                    if "Auto-Auditoría" in msg_ia or "Auditoría" in msg_ia:
                                        root.after(0, lambda p=pref_lote: btn_auto_1clic.configure(text=f"{p}AUDITANDO COHERENCIA CON IA..."))

                                # Auto-auditoría retrospectiva de 3 rondas SIEMPRE activa al generar guion nuevo
                                # (tanto en Subida Automática como en Revisión Previa manual)
                                es_auto_auditoria = not es_modo_editado

                                generar_guion_con_gemini_flash(
                                    ruta_video=ruta_video_usar,
                                    api_key=api_k,
                                    schedule_str=sched_str,
                                    modo_privacidad="privado" if modo_priv == "private" else modo_priv,
                                    contexto_titulo_orig=titulo_orig,
                                    modelo_preferido=pref_modelo_ia,
                                    progreso_cb=_cb_guion,
                                    auto_auditoria_retrospectiva=es_auto_auditoria,
                                    cancelar_check=lambda: evento_cancelar.is_set(),
                                )
                                if evento_cancelar.is_set():
                                    raise InterruptedError("Operación detenida por el usuario tras generar el guion.")
                                if es_custom_activo and (c_tit or c_desc):
                                    _sobreescribir_campos_custom_en_guion_txt(c_tit, c_desc)

                            _actualizar_milestone_actual("activo", f"Reel {num_actual}: Editando 60 FPS...")
                            root.after(
                                0,
                                lambda p=pref_lote: btn_auto_1clic.configure(
                                    text=f"{p}RENDERIZANDO SHORT CON GPU..."
                                ),
                            )

                            def _cb_edicion(pct_edit: float, txt_edit: str) -> None:
                                # Soporta tanto fracción 0.0..1.0 como porcentaje 0.0..100.0 sin saltos
                                f_val = pct_edit if pct_edit <= 1.0 else (pct_edit / 100.0)
                                frac_interna = 0.30 + max(0.0, min(1.0, f_val)) * 0.58
                                _set_subprogreso(frac_interna, f"{pref_lote}{txt_edit}", CYAN_ACCENT)

                            modo_render_elegido = "cpu" if "CPU" in modo_render_var.get() else "auto"
                            ruta_final = asyncio.run(
                                editar_video_con_guion(
                                    ruta_video=ruta_video_usar,
                                    ruta_guion=DEFAULT_GUION_TXT,
                                    voz_override=voz_elegida,
                                    modo_encuadre_override=encuadre_elegido,
                                    progreso_cb=_cb_edicion,
                                    cancelar_check=lambda: evento_cancelar.is_set(),
                                    encoder_override=modo_render_elegido,
                                )
                            )
                    ultimo_video_generado[0] = ruta_final
                    shorts_guardados_disco.append({
                        "titulo": (c_tit if (es_custom_activo and c_tit) else titulo_orig) or ruta_final.stem,
                        "archivo": ruta_final.name,
                        "ruta": str(ruta_final),
                        "reel_num": num_actual,
                    })

                    if evento_cancelar.is_set():
                        raise InterruptedError("Operación detenida por el usuario tras guardar la edición.")

                    es_modo_manual = ("Manual" in modo_subida_var.get())
                    if solo_guardar and not es_modo_manual:
                        _actualizar_milestone_actual("subido", f"Reel {num_actual}: ✓ Guardado")
                        _set_subprogreso(
                            1.0,
                            f"{pref_lote}Reel guardado en output_shorts ({ruta_final.name})",
                            GREEN_ACCENT,
                        )
                    else:
                        # Si está activo el Modo Revisión Previa o Edición Manual, esperar la decisión del usuario
                        if "Revisión" in modo_subida_var.get() or "Revision" in modo_subida_var.get() or es_modo_manual:
                            _actualizar_milestone_actual("activo", f"Reel {num_actual}: {'Editando guion manual...' if es_modo_manual_inicial else 'Esperando tu revisión...'}")
                            root.after(0, lambda: btn_auto_1clic.configure(text="EDITANDO GUION MANUAL..." if es_modo_manual_inicial else "ESPERANDO TU REVISIÓN DEL SHORT..."))

                            descartar_video_actual = False
                            while True:
                                ev_decision = threading.Event()
                                datos_dec: Dict[str, str] = {}

                                def _mostrar_rev(
                                    rf=ruta_final,
                                    tit=(c_tit if (es_custom_activo and c_tit) else titulo_orig) or ruta_final.stem,
                                    url_v=str(info_sel.get("url") or info_sel.get("link") or link_directo_var.get().strip() or ""),
                                    es_man_ini=es_modo_manual_inicial,
                                    sg=solo_guardar,
                                ):
                                    try:
                                        abrir_dialogo_revision_short(
                                            ruta_video=rf,
                                            titulo=tit,
                                            ruta_guion=DEFAULT_GUION_TXT,
                                            on_decision=lambda acc, fb: (
                                                datos_dec.update({"accion": acc, "feedback": fb}),
                                                ev_decision.set(),
                                            ),
                                            es_modo_editado=es_modo_editado,
                                            url_video_orig=url_v,
                                            es_modo_manual_inicial=es_man_ini,
                                            solo_guardar=sg,
                                        )
                                    except Exception:
                                        datos_dec.update({"accion": "subir", "feedback": ""})
                                        ev_decision.set()

                                root.after(0, lambda rf=ruta_final, tit=(c_tit if (es_custom_activo and c_tit) else titulo_orig) or ruta_final.stem, url_v=str(info_sel.get("url") or info_sel.get("link") or link_directo_var.get().strip() or ""), es_m=es_modo_manual_inicial, sg=solo_guardar: _mostrar_rev(rf, tit, url_v, es_m, sg))
                                ev_decision.wait()

                                accion = datos_dec.get("accion", "subir")
                                feedback_usr = datos_dec.get("feedback", "")

                                if accion == "descartar":
                                    raise InterruptedError("Video descartado por el usuario en revisión.")
                                elif accion == "buscar_otro":
                                    _actualizar_milestone_actual("activo", f"Reel {num_actual}: Buscando otro video...")
                                    _set_subprogreso(0.04, f"{pref_lote}Buscando otro Short viral en los canales...", "#facc15")
                                    root.after(0, lambda p=pref_lote: btn_auto_1clic.configure(text=f"{p}BUSCANDO OTRO SHORT..."))

                                    nuevo_elegido = None
                                    if es_modo_canales:
                                        cid_actual = str(info_sel.get("cuenta_id") or "principal")
                                        canales_para_este = list(canales_por_cuenta.get(cid_actual) or lista_canales)
                                        if not canales_para_este:
                                            canales_para_este = list(lista_canales)
                                        es_modo_fijo_otro = ("Único" in orden_canales_var.get() or "fijo" in orden_canales_var.get().lower())
                                        if es_modo_fijo_otro and canal_fijo_var.get():
                                            canales_para_este = [canal_fijo_var.get()]
                                        elif not ("Rotación" in orden_canales_var.get()):
                                            random.shuffle(canales_para_este)
                                        for c_cand in canales_para_este:
                                            if evento_cancelar.is_set():
                                                raise InterruptedError("Operación detenida por el usuario.")
                                            c_lbl = etiqueta_corta_canal(c_cand)
                                            _set_subprogreso(0.06, f"{pref_lote}Buscando en {c_lbl}...", "#facc15")
                                            res_viral = buscar_short_viral_en_canal(
                                                c_cand,
                                                min_views=min_v,
                                                estricto_min_views=True,
                                                cuenta_id=cid_actual,
                                                ids_excluir=ids_reservados_sesion,
                                                cancelar_check=lambda: evento_cancelar.is_set(),
                                            )
                                            if res_viral:
                                                nuevo_elegido = res_viral
                                                ids_reservados_sesion.append(res_viral[0])
                                                break
                                    elif es_modo_editado:
                                        subidos_o_guardados = {Path(s.get("ruta", "")).resolve() for s in shorts_guardados_disco}
                                        for p_cand in lista_videos_editados_locales:
                                            if p_cand.resolve() not in subidos_o_guardados and p_cand.resolve() != ruta_video_usar.resolve():
                                                nuevo_elegido = (str(p_cand), p_cand.stem.replace("_", " ").title(), 0)
                                                break
                                    else:
                                        for u_cand in links_a_procesar:
                                            if u_cand != url_descargar:
                                                nuevo_elegido = (u_cand, "Video Link", 0)
                                                break

                                    if not nuevo_elegido:
                                        def _aviso_no_mas() -> None:
                                            messagebox.showwarning(
                                                "Sin Videos Disponibles",
                                                "No se encontró otro Short viral con los filtros actuales en los canales.\n\n"
                                                "Podés bajar el filtro de vistas mínimas o agregar más canales en Ajustes.",
                                            )
                                        root.after(0, _aviso_no_mas)
                                        continue

                                    u_nuevo, t_nuevo, v_nuevo = nuevo_elegido
                                    url_descargar = u_nuevo
                                    titulo_orig = t_nuevo
                                    vistas_orig = v_nuevo
                                    info_sel["url"] = u_nuevo
                                    info_sel["titulo_orig"] = t_nuevo
                                    info_sel["vistas"] = v_nuevo

                                    posible_local_n = Path(url_descargar)
                                    if posible_local_n.exists() and posible_local_n.is_file():
                                        ruta_video_usar = posible_local_n
                                    else:
                                        _actualizar_milestone_actual("activo", f"Reel {num_actual}: Descargando...")
                                        _set_subprogreso(0.10, f"{pref_lote}Descargando nuevo Short: '{titulo_orig[:36]}...'")
                                        root.after(0, lambda p=pref_lote: btn_auto_1clic.configure(text=f"{p}DESCARGANDO NUEVO SHORT..."))
                                        ruta_video_usar = descargar_video_youtube(
                                            url_descargar,
                                            cancelar_check=lambda: evento_cancelar.is_set(),
                                        )
                                        if evento_cancelar.is_set():
                                            raise InterruptedError("Operación detenida por el usuario tras descargar el video.")
                                        if ULTIMA_INFO_YTDLP.get("titulo"):
                                            titulo_orig = ULTIMA_INFO_YTDLP["titulo"]

                                    if es_modo_editado:
                                        ruta_final = ruta_video_usar
                                        ultimo_video_generado[0] = ruta_final
                                    elif es_modo_manual:
                                        _actualizar_milestone_actual("activo", f"Reel {num_actual}: Abriendo editor manual...")
                                        _set_subprogreso(0.30, f"{pref_lote}Preparando nuevo video en editor manual...", PURPLE_MAIN)
                                        root.after(0, lambda p=pref_lote: btn_auto_1clic.configure(text=f"{p}LISTO PARA EDITAR GUION..."))

                                        plantilla_raw = generar_plantilla_guion_manual(
                                            ruta_video=ruta_video_usar,
                                            titulo_sugerido=titulo_orig or ruta_video_usar.stem,
                                            sched_str=sched_actual or "auto",
                                            modo_priv="privado" if modo_priv == "private" else modo_priv,
                                            modo_encuadre=encuadre_elegido,
                                        )
                                        DEFAULT_GUION_TXT.write_text(plantilla_raw, encoding="utf-8")
                                        ruta_final = ruta_video_usar
                                        ultimo_video_generado[0] = ruta_final
                                        es_modo_manual_inicial = True
                                    else:
                                        _actualizar_milestone_actual("activo", f"Reel {num_actual}: Creando guión IA...")
                                        _set_subprogreso(0.20, f"{pref_lote}Generando guión con IA...", PURPLE_MAIN)
                                        root.after(0, lambda p=pref_lote: btn_auto_1clic.configure(text=f"{p}CREANDO GUIÓN CON IA..."))

                                        def _cb_guion_otro(sub_frac: float, msg_ia: str) -> None:
                                            frac_ia = 0.20 + max(0.0, min(1.0, sub_frac)) * 0.15
                                            _set_subprogreso(frac_ia, f"{pref_lote}{msg_ia}", "#facc15")

                                        generar_guion_con_gemini_flash(
                                            ruta_video=ruta_video_usar,
                                            api_key=api_k,
                                            schedule_str=sched_actual or "auto",
                                            modo_privacidad="privado" if modo_priv == "private" else modo_priv,
                                            contexto_titulo_orig=titulo_orig,
                                            modelo_preferido=pref_modelo_ia,
                                            progreso_cb=_cb_guion_otro,
                                            auto_auditoria_retrospectiva=True,
                                            cancelar_check=lambda: evento_cancelar.is_set(),
                                        )
                                        if evento_cancelar.is_set():
                                            raise InterruptedError("Operación detenida por el usuario tras generar el guion.")

                                        _actualizar_milestone_actual("activo", f"Reel {num_actual}: Editando 60 FPS...")
                                        root.after(0, lambda p=pref_lote: btn_auto_1clic.configure(text=f"{p}RENDERIZANDO SHORT GPU..."))

                                        def _cb_edit_otro(pct_edit: float, txt_edit: str) -> None:
                                            f_val = pct_edit if pct_edit <= 1.0 else (pct_edit / 100.0)
                                            frac_interna = 0.38 + max(0.0, min(1.0, f_val)) * 0.52
                                            _set_subprogreso(frac_interna, f"{pref_lote}{txt_edit}", CYAN_ACCENT)

                                        modo_render_elegido = "cpu" if "CPU" in modo_render_var.get() else "auto"
                                        ruta_final = asyncio.run(
                                            editar_video_con_guion(
                                                ruta_video=ruta_video_usar,
                                                ruta_guion=DEFAULT_GUION_TXT,
                                                voz_override=voz_elegida,
                                                modo_encuadre_override=encuadre_elegido,
                                                progreso_cb=_cb_edit_otro,
                                                cancelar_check=lambda: evento_cancelar.is_set(),
                                                encoder_override=modo_render_elegido,
                                            )
                                        )
                                        ultimo_video_generado[0] = ruta_final

                                    continue
                                elif accion == "reeditar":
                                    _actualizar_milestone_actual("activo", f"Reel {num_actual}: Renderizando Short con tu guion...")
                                    _set_subprogreso(0.25, f"{pref_lote}Guardando guion...", PURPLE_MAIN)
                                    root.after(0, lambda p=pref_lote: btn_auto_1clic.configure(text=f"{p}RENDERIZANDO CON TU GUION..."))

                                    if feedback_usr and feedback_usr.strip():
                                        DEFAULT_GUION_TXT.write_text(feedback_usr.strip() + "\n", encoding="utf-8")

                                    voz_elegida = VOCES_DISPONIBLES.get(voz_var.get(), EDGE_VOICE_DEFAULT)
                                    _set_subprogreso(0.35, f"{pref_lote}Renderizando video a 60 FPS con GPU...", CYAN_ACCENT)
                                    root.after(0, lambda p=pref_lote: btn_auto_1clic.configure(text=f"{p}RENDERIZANDO SHORT GPU..."))

                                    def _cb_reedit_e(pct_edit: float, txt_edit: str) -> None:
                                        f_val = pct_edit if pct_edit <= 1.0 else (pct_edit / 100.0)
                                        _set_subprogreso(0.35 + max(0.0, min(1.0, f_val)) * 0.55, f"{pref_lote}{txt_edit}", CYAN_ACCENT)

                                    modo_render_elegido = "cpu" if "CPU" in modo_render_var.get() else "auto"
                                    ruta_final = asyncio.run(
                                        editar_video_con_guion(
                                            ruta_video=ruta_video_usar,
                                            ruta_guion=DEFAULT_GUION_TXT,
                                            voz_override=voz_elegida,
                                            modo_encuadre_override=encuadre_elegido,
                                            progreso_cb=_cb_reedit_e,
                                            cancelar_check=lambda: evento_cancelar.is_set(),
                                            encoder_override=modo_render_elegido,
                                        )
                                    )
                                    ultimo_video_generado[0] = ruta_final
                                    es_modo_manual_inicial = False
                                    continue
                                else:
                                    if feedback_usr and feedback_usr.strip() and not es_modo_editado:
                                        try:
                                            DEFAULT_GUION_TXT.write_text(feedback_usr.strip() + "\n", encoding="utf-8")
                                        except Exception:
                                            pass
                                    if solo_guardar:
                                        _actualizar_milestone_actual("subido", f"Reel {num_actual}: ✓ Guardado")
                                        _set_subprogreso(
                                            1.0,
                                            f"{pref_lote}Reel guardado en output_shorts ({ruta_final.name})",
                                            GREEN_ACCENT,
                                        )
                                        break
                                    break

                        if solo_guardar:
                            continue

                        # Cuentas de YouTube asignadas a este Reel (una o varias si es cross-posting)
                        cuentas_dest_video: List[Dict[str, Any]] = list(info_sel.get("cuentas_destino") or [])
                        if not cuentas_dest_video:
                            id_c_def = str(info_sel.get("cuenta_id") or estado_seleccion_cuentas.get("cuenta_id") or "principal")
                            nom_c_def = str(info_sel.get("cuenta_nombre") or id_c_def)
                            cuentas_dest_video = [{"id": id_c_def, "nombre": nom_c_def}]

                        total_cdest = len(cuentas_dest_video)
                        for idx_cd, c_dest in enumerate(cuentas_dest_video):
                            if evento_cancelar.is_set():
                                raise InterruptedError("Operación detenida por el usuario antes de completar las subidas.")

                            id_cuenta_usar = str(c_dest.get("id") or "principal")
                            nombre_cuenta_subida = str(c_dest.get("nombre") or id_cuenta_usar)
                            tag_multi = f" ({idx_cd + 1}/{total_cdest})" if total_cdest > 1 else ""

                            _actualizar_milestone_actual("activo", f"Reel {num_actual}: Subiendo a {nombre_cuenta_subida[:14]}{tag_multi}...")
                            root.after(
                                0,
                                lambda p=pref_lote, nc=nombre_cuenta_subida[:16], tm=tag_multi: btn_auto_1clic.configure(
                                    text=f"{p}SUBIENDO A {nc.upper()}{tm}..."
                                ),
                            )
                            _set_subprogreso(
                                0.92 + (idx_cd / max(1, total_cdest)) * 0.06,
                                f"{pref_lote}Subiendo Short a '{nombre_cuenta_subida}'{tag_multi}...",
                                "#c084fc",
                            )

                            vid_id = subir_video(
                                ruta_video=ruta_final,
                                titulo=c_tit if (es_custom_activo and c_tit) else None,
                                descripcion=c_desc if (es_custom_activo and c_desc) else None,
                                estado_privacidad=modo_priv,
                                publish_at=sched_actual,
                                ruta_guion=DEFAULT_GUION_TXT,
                                cuenta_id=id_cuenta_usar,
                                callback_cancelar=lambda: evento_cancelar.is_set(),
                            )
                            registrar_video_usado(url_descargar, cuenta_id=id_cuenta_usar)
                            shorts_subidos.append({
                                "titulo": (c_tit if (es_custom_activo and c_tit) else titulo_orig) or ruta_final.stem,
                                "url": f"https://youtube.com/shorts/{vid_id}",
                                "cuenta": nombre_cuenta_subida,
                                "reel_num": num_actual,
                            })
                            incrementar_cuota_diaria(video_id=vid_id)
                            links_subidos.append(f"https://youtube.com/shorts/{vid_id}")

                        root.after(0, refrescar_barra_cuota)
                        root.after(1500, sincronizar_cola_programados_async)

                        txt_milestone_fin = f"Reel {num_actual}: ✓ Subido" + (f" ({total_cdest} cuentas)" if total_cdest > 1 else "")
                        _actualizar_milestone_actual("subido", txt_milestone_fin)
                        _set_subprogreso(
                            1.0,
                            f"{pref_lote}Reel {num_actual} subido con éxito a {total_cdest} cuenta(s) ({sched_actual or modo_priv.upper()})",
                            GREEN_ACCENT,
                        )

                # Si se programaron varios días, actualizar la fecha recordada al último día usado
                if not solo_guardar and horarios_lote and horarios_lote[-1]:
                    ultima_f = str(horarios_lote[-1]).split(" ")[0]
                    fecha_elegida_var.set(ultima_f)
                    root.after(
                        0,
                        lambda uf=ultima_f: (
                            btn_calendario.configure(text=_formatear_boton_fecha(uf)),
                            refrescar_plan_ui(),
                        ),
                    )

                def _on_ok() -> None:
                    try:
                        import winsound
                        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
                    except Exception:
                        pass
                    if solo_guardar:
                        txt_fin = (
                            f"100% — ¡Se crearon y guardaron todos los Reels ({len(videos_seleccionados)}) en output_shorts!"
                            if cant_cola > 1
                            else "100% — ¡Se creó y guardó el Reel en output_shorts!"
                        )
                        root.after(800, abrir_carpeta_salida)
                        _actualizar_progreso_ui(100.0, txt_fin, GREEN_ACCENT, GREEN_ACCENT)
                    else:
                        if len(links_subidos) > 0:
                            if es_cross_post_lote and len(cuentas_objetivo_lote) > 1:
                                txt_fin = f"100% — ¡Se publicaron {len(links_subidos)} Shorts en {len(cuentas_objetivo_lote)} cuentas con éxito!"
                            else:
                                txt_fin = (
                                    f"100% — ¡Se subieron todos los Reels ({len(links_subidos)}/{cant_cola}) con éxito!"
                                    if cant_cola > 1
                                    else "100% — ¡Se subió el Reel a YouTube con éxito!"
                                )
                            _actualizar_progreso_ui(100.0, txt_fin, GREEN_ACCENT, GREEN_ACCENT)
                        else:
                            txt_fin = "Proceso finalizado. No se subió ningún video."
                            _actualizar_progreso_ui(0.0, txt_fin, TEXT_MUTED, PURPLE_MAIN)
                    root.after(2800, lambda: _mostrar_modo_progreso_activo(False) if not editando_lock.locked() else None)
                root.after(0, _on_ok)
            except InterruptedError as exc_int:
                def _on_cancelado() -> None:
                    subidos_nums = {u.get("reel_num") for u in shorts_subidos}
                    editados_sin_subir = [e for e in shorts_guardados_disco if e.get("reel_num") not in subidos_nums]
                    datos_resumen = {
                        "subidos": shorts_subidos,
                        "editados": editados_sin_subir,
                        "cant_total": cant_cola,
                    }
                    if not shorts_subidos and not editados_sin_subir:
                        _actualizar_progreso_ui(0.0, "Operación frenada a tiempo. Sin cambios.", "#94a3b8", "#ef4444")
                    elif editados_sin_subir and not shorts_subidos:
                        pct_actual = barra_progreso_proceso.get() * 100.0
                        _actualizar_progreso_ui(
                            pct_actual,
                            f"Subida detenida: {len(editados_sin_subir)} video(s) guardado(s) en disco.",
                            "#facc15",
                            "#eab308",
                        )
                    else:
                        pct_actual = barra_progreso_proceso.get() * 100.0
                        _actualizar_progreso_ui(
                            pct_actual,
                            f"Proceso detenido: {len(shorts_subidos)} subido(s), {len(editados_sin_subir)} guardado(s).",
                            "#facc15",
                            PURPLE_MAIN,
                        )
                    abrir_dialogo_frenado(datos_resumen)
                    root.after(1500, lambda: _mostrar_modo_progreso_activo(False) if not editando_lock.locked() else None)

                root.after(0, _on_cancelado)
            except Exception as exc:
                err_completo = str(exc)
                def _on_err(err_msg: str = err_completo) -> None:
                    primer_linea = err_msg.splitlines()[0] if err_msg else "Error desconocido"
                    lbl_estado.configure(text=f"Error: {primer_linea}", text_color="#ef4444")
                    barra_progreso_proceso.configure(progress_color="#ef4444")
                    try:
                        messagebox.showerror("Error al buscar o procesar videos", err_msg)
                    except Exception:
                        pass
                    root.after(4500, lambda: _mostrar_modo_progreso_activo(False) if not editando_lock.locked() else None)

                root.after(0, _on_err)
            finally:
                sys.stdout = stdout_orig
                sys.stderr = stderr_orig
                editando_lock.release()

        threading.Thread(target=tarea_auto_total, daemon=True).start()

    btn_auto_1clic.configure(command=ejecutar_flujo_1_clic)
    root.after(10, actualizar_modo_vista)
    root.after(200, vaciar_cola_logs)
    root.after(700, sincronizar_cola_programados_async)
    root.after(60, autoajustar_tamano_ventana)
    root.after(300, autoajustar_tamano_ventana)
    root.deiconify()
    root.lift()
    root.focus_force()
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg1 = sys.argv[1].strip()
        if arg1.lower() == "--auto" and len(sys.argv) > 2:
            url_auto = sys.argv[2].strip()
            sched_auto = sys.argv[3].strip() if len(sys.argv) > 3 else "auto"
            priv_auto = sys.argv[4].strip() if len(sys.argv) > 4 else "private"
            v_desc = descargar_video_youtube(url_auto)
            generar_guion_con_gemini_flash(v_desc, obtener_gemini_api_key(), schedule_str=sched_auto, modo_privacidad=priv_auto)
            r_out = asyncio.run(editar_video_con_guion(v_desc, DEFAULT_GUION_TXT))
            from subir_a_youtube import subir_video
            subir_video(r_out, estado_privacidad=priv_auto, publish_at=sched_auto if sched_auto != "auto" else None, ruta_guion=DEFAULT_GUION_TXT)
        else:
            guion_arg = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else DEFAULT_GUION_TXT
            if arg1.startswith("http://") or arg1.startswith("https://") or "youtube.com" in arg1 or "youtu.be" in arg1:
                video_descargado = descargar_video_youtube(arg1)
                asyncio.run(editar_video_con_guion(video_descargado, guion_arg))
            else:
                video_arg = Path(arg1).resolve()
                asyncio.run(editar_video_con_guion(video_arg, guion_arg))
    else:
        # Instancia única con Mutex de Windows: si la app ya está corriendo en segundo plano
        # (por haberla cerrado con la X mientras editaba), le envía la señal para volver a
        # mostrar esa misma ventana con su barra de progreso intacta en lugar de abrir otra vacía.
        _mutex_handle = None
        try:
            import ctypes
            _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\MateoEditorShortsStudioSingleInstance")
            if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                sig_f = TEMP_DIR / "mostrar_ventana.signal"
                TEMP_DIR.mkdir(parents=True, exist_ok=True)
                sig_f.write_text("1", encoding="utf-8")
                import time
                for _ in range(6):
                    time.sleep(0.2)
                    if not sig_f.exists():
                        sys.exit(0)
                try:
                    sig_f.unlink()
                except Exception:
                    pass
        except SystemExit:
            raise
        except Exception:
            pass
        try:
            iniciar_aplicacion_gui()
        except Exception:
            import traceback
            import tkinter.messagebox as mb
            err = traceback.format_exc()
            with open("error_inicio.log", "w", encoding="utf-8") as ef:
                ef.write(err)
            try:
                mb.showerror("Error al Iniciar", "No se pudo iniciar la aplicación:\n\n" + err)
            except Exception:
                pass
            raise
