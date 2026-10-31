# -*- coding: utf-8 -*-
import re
import customtkinter as ctk
from typing import List, Dict, Callable, Optional, Any

# =====================================================================
# CATÁLOGO OFICIAL Y 9 CUADRANTES PRECISOS DEL MOTOR
# =====================================================================
LISTA_EFECTOS = [
    "ninguno", "zoom_impacto", "zoom_in", "zoom_out", "flash",
    "temblor", "alerta_roja", "brillo_epico", "blanco_negro", "spotlight"
]

LISTA_SFX = [
    "ninguno", "crowd_shocked", "whoosh", "riser_suction", "vine_boom",
    "metal_pipe", "heartbeat_fast", "record_scratch", "suspense_hit", "ding",
    "good_idea", "cash_ting", "punch", "boxing_bell", "camera_flash",
    "camera_shooter", "cartoon_laugh", "kids_yeyy", "party_horn",
    "awww", "error", "xp_Error", "fart", "click", "pop"
]

LISTA_EMOJIS = [
    "ninguno",
    "sorprendido:derecha", "sorprendido:izquierda", "sorprendido:centro",
    "risa:derecha", "risa:izquierda",
    "fiesta:derecha", "fiesta:izquierda",
    "diablo:derecha", "diablo:izquierda",
    "enojo:derecha", "enojo:izquierda",
    "lloro:derecha", "lloro:izquierda",
    "sueno:derecha", "sueno:izquierda",
    "calavera:derecha", "calavera:izquierda", "calavera:centro",
    "fuego:derecha", "fuego:izquierda",
    "ojos:derecha", "ojos:izquierda", "ojos:arriba_der", "ojos:arriba_izq",
    "cerebro:derecha", "cerebro:izquierda"
]

LISTA_FLECHAS = [
    "ninguna", "ninguno",
    "centro", "arriba", "abajo", "izquierda", "derecha",
    "arriba_izq", "arriba_der", "abajo_izq", "abajo_der",
    "auto"
]

LISTA_CIRCULOS = [
    "ninguno",
    "centro:medio", "centro:grande", "centro:chico",
    "arriba:medio", "arriba:grande", "arriba:chico",
    "abajo:medio", "abajo:grande", "abajo:chico",
    "izquierda:medio", "izquierda:grande", "izquierda:chico",
    "derecha:medio", "derecha:grande", "derecha:chico",
    "arriba_izq:medio", "arriba_der:medio",
    "abajo_izq:medio", "abajo_der:medio"
]


def seg_a_mmss(seg: float) -> str:
    seg = max(0.0, round(seg * 2) / 2)
    m = int(seg // 60)
    s = seg % 60
    if abs(s - round(s)) < 0.05:
        return f"{m:02d}:{int(round(s)):02d}"
    return f"{m:02d}:{s:04.1f}"


def mmss_a_seg(texto: str) -> float:
    try:
        p = str(texto).strip().split(":")
        if len(p) == 2:
            return int(p[0]) * 60 + float(p[1])
        elif len(p) == 1:
            return float(p[0])
        elif len(p) == 3:
            return int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2])
    except Exception:
        return 0.0
    return 0.0


def _quitar_acentos(texto: str) -> str:
    import unicodedata
    if not texto:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(texto))
        if unicodedata.category(c) != "Mn"
    )


def _extraer_frame_pil(ruta_video, t_seg: float, w: int = 270, h: int = 480):
    """Extrae un fotograma exacto del video a t_seg y lo devuelve redimensionado en PIL.Image."""
    if not ruta_video:
        return None
    try:
        from pathlib import Path
        import cv2
        from PIL import Image
        p = Path(ruta_video)
        if not p.exists():
            return None
        cap = cv2.VideoCapture(str(p))
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(t_seg) * 1000.0))
        ret, frame_bgr = cap.read()
        cap.release()
        if not ret or frame_bgr is None:
            return None
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        return Image.fromarray(frame_rgb).resize((w, h), Image.Resampling.LANCZOS)
    except Exception:
        return None


def abrir_dialogo_posicion_pantalla(
    parent_win,
    datos_bloque: Dict,
    on_aplicar: Callable,
    ruta_video: Optional[Any] = None,
    on_preview_live: Optional[Callable] = None,
):
    import tkinter as tk
    import re
    import math
    from PIL import Image, ImageTk
    from pathlib import Path

    win_p = ctk.CTkToplevel(parent_win)
    win_p.title("Editor de Flechas, Círculos y Emojis")
    win_p.geometry("380x820")
    win_p.minsize(360, 720)
    win_p.resizable(False, True)
    win_p.configure(fg_color="#0e111a")
    win_p.transient(parent_win)
    win_p.grab_set()

    t_ini = float(datos_bloque.get("t_ini", 0.0))
    t_fin = float(datos_bloque.get("t_fin", 4.0))
    if t_fin <= t_ini:
        t_fin = t_ini + 3.0
    t_actual = t_ini

    CW, CH = 270, 480

    frame_cache = {}

    def _obtener_frame(t: float):
        t_key = round(float(t), 1)
        if t_key not in frame_cache:
            img = _extraer_frame_pil(ruta_video, t_key, CW, CH)
            frame_cache[t_key] = ImageTk.PhotoImage(img) if img else None
        return frame_cache[t_key]

    frame_activo = [_obtener_frame(t_ini)]

    assets_pil = {}
    rutas_flecha = [Path("assets/fotos/flecha.png"), Path("assets/emojis/flecha.png")]
    for rf in rutas_flecha:
        if rf.exists():
            try:
                assets_pil["flecha"] = Image.open(rf).convert("RGBA")
                break
            except Exception:
                pass

    rutas_circulo = [Path("assets/fotos/circulo_rojo.png"), Path("assets/fotos/circulo.png"), Path("assets/emojis/circulo_rojo.png")]
    for rc in rutas_circulo:
        if rc.exists():
            try:
                assets_pil["circulo"] = Image.open(rc).convert("RGBA")
                break
            except Exception:
                pass

    EMOJIS_CATALOGO = [
        "calavera", "cerebro", "diablo", "enojo", "fiesta",
        "fuego", "lloro", "ojos", "risa", "sorprendido", "sueno"
    ]
    emojis_dir = Path("assets/emojis")
    for nom in EMOJIS_CATALOGO:
        p_em = emojis_dir / f"emoji_{nom}.png"
        if p_em.exists():
            try:
                assets_pil[nom] = Image.open(p_em).convert("RGBA")
            except Exception:
                pass

    class SpriteItem:
        def __init__(self, tipo: str, nombre: str, x: float, y: float, scale: float = 1.0, rot: float = 0.0, tracking: bool = True):
            self.tipo = str(tipo)
            self.nombre = str(nombre)
            self.x = max(5.0, min(95.0, float(x)))
            self.y = max(5.0, min(95.0, float(y)))
            self.scale = max(0.4, min(2.5, float(scale)))
            self.rot = float(rot) % 360.0
            self.tracking = bool(tracking)

    sprites: List[SpriteItem] = []
    selected_sprite: Optional[SpriteItem] = None

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

    # 1. Círculo existente
    c_raw = str(datos_bloque.get("circulo", "")).strip()
    if c_raw and c_raw.lower() not in ("ninguno", "ninguna", "none", "no"):
        is_track = "fijo:" not in c_raw.lower() and "static:" not in c_raw.lower()
        c_clean = c_raw.lower().replace("fijo:", "").replace("static:", "").strip()
        sc = 1.3 if ":grande" in c_clean else (0.7 if ":chico" in c_clean else 1.0)
        m_c = re.search(r"(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)", c_clean)
        if m_c:
            cx, cy = float(m_c.group(1)), float(m_c.group(2))
        else:
            k = c_clean.split(":")[0].strip()
            cx, cy = pos_keyword_map.get(k, (50.0, 45.0))
        sprites.append(SpriteItem("circulo", "circulo", cx, cy, scale=sc, rot=0.0, tracking=is_track))

    # 2. Flecha existente
    f_raw = str(datos_bloque.get("flecha", "")).strip()
    if f_raw and f_raw.lower() not in ("ninguno", "ninguna", "none", "no"):
        is_track = "fijo:" not in f_raw.lower() and "static:" not in f_raw.lower()
        f_clean = f_raw.lower().replace("fijo:", "").replace("static:", "").strip()
        m_rot = re.search(r"@(\d+(?:\.\d+)?)", f_clean)
        rot_val = float(m_rot.group(1)) if m_rot else 315.0
        m_f = re.search(r"(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)", f_clean)
        if m_f:
            fx, fy = float(m_f.group(1)), float(m_f.group(2))
        else:
            k = f_clean.split("@")[0].strip()
            fx, fy = pos_keyword_map.get(k, (50.0, 50.0))
        sprites.append(SpriteItem("flecha", "flecha", fx, fy, scale=1.0, rot=rot_val, tracking=is_track))

    # 3. Emojis existentes (múltiples con +)
    e_raw = str(datos_bloque.get("emoji", "")).strip()
    if e_raw and e_raw.lower() not in ("ninguno", "ninguna", "none", "no"):
        partes = e_raw.split("+") if "+" in e_raw else [e_raw]
        for p in partes:
            p = p.strip()
            if not p or p.lower() in ("ninguno", "ninguna", "none", "no"):
                continue
            is_track = "fijo:" not in p.lower() and "static:" not in p.lower()
            p_clean = p.replace("fijo:", "").replace("static:", "").strip()
            m_rot = re.search(r"@(\d+(?:\.\d+)?)", p_clean)
            rot_val = float(m_rot.group(1)) if m_rot else 0.0
            p_nom_pos = p_clean.split("@")[0].strip()
            if ":" in p_nom_pos:
                nom_e, pos_e = p_nom_pos.split(":", 1)
            else:
                nom_e, pos_e = p_nom_pos, "derecha"
            nom_clean = _quitar_acentos(nom_e.strip().lower())
            if nom_clean.startswith("emoji_"):
                nom_clean = nom_clean[6:]
            m_e = re.search(r"(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)", pos_e)
            if m_e:
                ex, ey = float(m_e.group(1)), float(m_e.group(2))
            else:
                ex, ey = pos_keyword_map.get(pos_e.strip().lower(), (78.0, 32.0))
            sprites.append(SpriteItem("emoji", nom_clean, ex, ey, scale=1.0, rot=rot_val, tracking=is_track))

    if sprites:
        selected_sprite = sprites[0]

    # Canvas vertical 9:16
    canvas = tk.Canvas(win_p, width=CW, height=CH, bg="#050811", highlightthickness=1, highlightbackground="#252B3D")
    canvas.pack(pady=(8, 2))

    cached_photos = []

    def _redibujar():
        canvas.delete("all")
        cached_photos.clear()

        # Fondo de video
        if frame_activo[0] is not None:
            canvas.create_image(0, 0, image=frame_activo[0], anchor="nw")
        else:
            canvas.create_rectangle(0, 0, CW, CH, fill="#050811", outline="")

        # Guías 3x3 sutiles
        dash_col = "#2a3754" if frame_activo[0] is None else "#334155"
        canvas.create_line(CW * 0.33, 0, CW * 0.33, CH, fill=dash_col, dash=(2, 3))
        canvas.create_line(CW * 0.66, 0, CW * 0.66, CH, fill=dash_col, dash=(2, 3))
        canvas.create_line(0, CH * 0.33, CW, CH * 0.33, fill=dash_col, dash=(2, 3))
        canvas.create_line(0, CH * 0.66, CW, CH * 0.66, fill=dash_col, dash=(2, 3))

        # Sprites
        for s in sprites:
            base_img = None
            base_sz = 62
            if s.tipo == "flecha":
                base_img = assets_pil.get("flecha")
                base_sz = 60
            elif s.tipo == "circulo":
                base_img = assets_pil.get("circulo")
                base_sz = 68
            elif s.tipo == "emoji":
                base_img = assets_pil.get(s.nombre, assets_pil.get("sorprendido"))
                base_sz = 62

            cx = int(round((s.x / 100.0) * CW))
            cy = int(round((s.y / 100.0) * CH))
            dim = max(24, int(round(base_sz * s.scale)))

            if base_img is not None:
                try:
                    img_scaled = base_img.resize((dim, dim), Image.Resampling.BILINEAR)
                    if abs(s.rot) > 0.5:
                        img_scaled = img_scaled.rotate(-s.rot, resample=Image.Resampling.BICUBIC, expand=True)
                    photo = ImageTk.PhotoImage(img_scaled)
                    cached_photos.append(photo)
                    canvas.create_image(cx, cy, image=photo, anchor="center")
                except Exception:
                    pass
            else:
                if s.tipo == "circulo":
                    r = dim // 2
                    canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#ef4444", width=3)
                elif s.tipo == "flecha":
                    rad = math.radians(s.rot)
                    fx = cx + 25 * math.cos(rad)
                    fy = cy + 25 * math.sin(rad)
                    canvas.create_line(fx, fy, cx, cy, fill="#f59e0b", width=3, arrow=tk.LAST)
                else:
                    canvas.create_rectangle(cx - 20, cy - 20, cx + 20, cy + 20, fill="#f59e0b", outline="")

            # Marco de selección estilo Word si está seleccionado
            if s == selected_sprite:
                hw = max(14, int(round(dim * 0.5)))
                hh = max(14, int(round(dim * 0.5)))
                bx0, by0 = cx - hw, cy - hh
                bx1, by1 = cx + hw, cy + hh

                canvas.create_rectangle(bx0, by0, bx1, by1, outline="#38bdf8", width=1.8, dash=(4, 3))

                for hx, hy in [(bx0, by0), (bx1, by0), (bx0, by1), (bx1, by1)]:
                    canvas.create_rectangle(hx - 4, hy - 4, hx + 4, hy + 4, fill="#ffffff", outline="#0284c7", width=1.5)

                stem_y = by0 - 22
                canvas.create_line(cx, by0, cx, stem_y, fill="#38bdf8", width=1.8)
                canvas.create_oval(cx - 6, stem_y - 6, cx + 6, stem_y + 6, fill="#10b981", outline="#ffffff", width=1.5)

    drag_mode = None
    drag_offset_x = 0.0
    drag_offset_y = 0.0
    drag_start_scale = 1.0
    drag_start_dist = 1.0
    drag_start_rot = 0.0
    drag_start_angle = 0.0

    def _on_canvas_press(event):
        nonlocal drag_mode, drag_offset_x, drag_offset_y
        nonlocal drag_start_scale, drag_start_dist, drag_start_rot, drag_start_angle
        nonlocal selected_sprite

        mx, my = event.x, event.y

        if selected_sprite is not None:
            cx = (selected_sprite.x / 100.0) * CW
            cy = (selected_sprite.y / 100.0) * CH
            base_sz = 68 if selected_sprite.tipo == "circulo" else 62
            dim = max(24, int(round(base_sz * selected_sprite.scale)))
            hw = max(14, int(round(dim * 0.5)))
            hh = max(14, int(round(dim * 0.5)))
            bx0, by0 = cx - hw, cy - hh
            bx1, by1 = cx + hw, cy + hh
            stem_y = by0 - 22

            # Mango de rotación
            if math.hypot(mx - cx, my - stem_y) <= 12:
                drag_mode = "rotate"
                drag_start_rot = selected_sprite.rot
                drag_start_angle = math.degrees(math.atan2(my - cy, mx - cx))
                return

            # 4 esquinas de escala
            for hx, hy in [(bx0, by0), (bx1, by0), (bx0, by1), (bx1, by1)]:
                if abs(mx - hx) <= 8 and abs(my - hy) <= 8:
                    drag_mode = "scale"
                    drag_start_scale = selected_sprite.scale
                    drag_start_dist = max(10.0, math.hypot(mx - cx, my - cy))
                    return

        # Clic dentro de cuerpo de sprite
        for s in reversed(sprites):
            scx = (s.x / 100.0) * CW
            scy = (s.y / 100.0) * CH
            base_sz = 68 if s.tipo == "circulo" else 62
            dim = max(24, int(round(base_sz * s.scale)))
            hw = max(14, int(round(dim * 0.5)))
            hh = max(14, int(round(dim * 0.5)))
            if abs(mx - scx) <= hw + 6 and abs(my - scy) <= hh + 6:
                selected_sprite = s
                drag_mode = "move"
                drag_offset_x = mx - scx
                drag_offset_y = my - scy
                _actualizar_panel_seleccion()
                _actualizar_cuadrillas()
                _redibujar()
                return

        # Clic en vacío
        selected_sprite = None
        drag_mode = None
        _actualizar_panel_seleccion()
        _actualizar_cuadrillas()
        _redibujar()

    def _on_canvas_drag(event):
        nonlocal selected_sprite
        if selected_sprite is None or drag_mode is None:
            return

        mx, my = event.x, event.y
        scx = (selected_sprite.x / 100.0) * CW
        scy = (selected_sprite.y / 100.0) * CH

        if drag_mode == "move":
            ncx = max(10, min(CW - 10, mx - drag_offset_x))
            ncy = max(10, min(CH - 10, my - drag_offset_y))
            selected_sprite.x = (ncx / float(CW)) * 100.0
            selected_sprite.y = (ncy / float(CH)) * 100.0
            _actualizar_panel_seleccion()
            _redibujar()

        elif drag_mode == "scale":
            curr_dist = math.hypot(mx - scx, my - scy)
            ratio = curr_dist / max(10.0, drag_start_dist)
            selected_sprite.scale = max(0.4, min(2.5, drag_start_scale * ratio))
            _actualizar_panel_seleccion()
            _redibujar()

        elif drag_mode == "rotate":
            curr_angle = math.degrees(math.atan2(my - scy, mx - scx))
            delta = curr_angle - drag_start_angle
            selected_sprite.rot = (drag_start_rot + delta) % 360.0
            _actualizar_panel_seleccion()
            _redibujar()

    def _on_canvas_release(event):
        nonlocal drag_mode
        drag_mode = None

    canvas.bind("<Button-1>", _on_canvas_press)
    canvas.bind("<B1-Motion>", _on_canvas_drag)
    canvas.bind("<ButtonRelease-1>", _on_canvas_release)

    # Scrubber de tiempo
    f_time = ctk.CTkFrame(win_p, fg_color="transparent")
    f_time.pack(fill="x", padx=16, pady=(3, 2))

    lbl_t_ini = ctk.CTkLabel(f_time, text=f"{t_ini:.1f}s", font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8")
    lbl_t_ini.pack(side="left")

    lbl_t_cur = ctk.CTkLabel(f_time, text=f"⏱ {t_actual:.1f}s", font=ctk.CTkFont(size=11, weight="bold"), text_color="#38bdf8")
    lbl_t_cur.pack(side="left", padx=8)

    lbl_t_fin = ctk.CTkLabel(f_time, text=f"{t_fin:.1f}s", font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8")
    lbl_t_fin.pack(side="right")

    def _on_time_slider(val):
        nonlocal t_actual
        t_actual = float(val)
        lbl_t_cur.configure(text=f"⏱ {t_actual:.1f}s")
        frame_activo[0] = _obtener_frame(t_actual)
        if on_preview_live is not None:
            try:
                on_preview_live("seek", t_actual, "", "", 0)
            except Exception:
                pass
        _redibujar()

    n_pasos = max(10, int(round((t_fin - t_ini) * 20)))
    slider_time = ctk.CTkSlider(
        f_time, from_=t_ini, to=max(t_ini + 0.1, t_fin), number_of_steps=n_pasos,
        command=_on_time_slider, height=14, progress_color="#38bdf8", button_color="#38bdf8"
    )
    slider_time.set(t_ini)
    slider_time.pack(side="left", fill="x", expand=True, padx=4)

    # Cuadrillas (Flecha y Círculo)
    f_cuad = ctk.CTkFrame(win_p, fg_color="transparent")
    f_cuad.pack(fill="x", padx=16, pady=(2, 2))

    def _toggle_flecha():
        nonlocal selected_sprite
        f_exist = next((s for s in sprites if s.tipo == "flecha"), None)
        if f_exist:
            sprites.remove(f_exist)
            if selected_sprite == f_exist:
                selected_sprite = None
        else:
            sp = SpriteItem("flecha", "flecha", 50.0, 50.0, scale=1.0, rot=315.0, tracking=True)
            sprites.append(sp)
            selected_sprite = sp
        _actualizar_panel_seleccion()
        _actualizar_cuadrillas()
        _redibujar()

    def _toggle_circulo():
        nonlocal selected_sprite
        c_exist = next((s for s in sprites if s.tipo == "circulo"), None)
        if c_exist:
            sprites.remove(c_exist)
            if selected_sprite == c_exist:
                selected_sprite = None
        else:
            sp = SpriteItem("circulo", "circulo", 50.0, 45.0, scale=1.0, rot=0.0, tracking=True)
            sprites.append(sp)
            selected_sprite = sp
        _actualizar_panel_seleccion()
        _actualizar_cuadrillas()
        _redibujar()

    btn_cuad_flecha = ctk.CTkButton(
        f_cuad, text="➔ Flecha", height=30, font=ctk.CTkFont(size=12, weight="bold"),
        fg_color="#181f33", hover_color="#27324f", command=_toggle_flecha
    )
    btn_cuad_flecha.pack(side="left", fill="x", expand=True, padx=(0, 4))

    btn_cuad_circulo = ctk.CTkButton(
        f_cuad, text="◯ Círculo", height=30, font=ctk.CTkFont(size=12, weight="bold"),
        fg_color="#181f33", hover_color="#27324f", command=_toggle_circulo
    )
    btn_cuad_circulo.pack(side="left", fill="x", expand=True, padx=(4, 0))

    def _actualizar_cuadrillas():
        tiene_f = any(s.tipo == "flecha" for s in sprites)
        tiene_c = any(s.tipo == "circulo" for s in sprites)
        btn_cuad_flecha.configure(
            fg_color="#1d4ed8" if tiene_f else "#181f33",
            text="✓ Flecha Activa" if tiene_f else "➔ Flecha"
        )
        btn_cuad_circulo.configure(
            fg_color="#b91c1c" if tiene_c else "#181f33",
            text="✓ Círculo Activo" if tiene_c else "◯ Círculo"
        )

    # Grilla estilo WhatsApp de Emojis
    f_em_box = ctk.CTkFrame(win_p, fg_color="#111624", corner_radius=8, border_width=1, border_color="#1f273b")
    f_em_box.pack(fill="x", padx=16, pady=(3, 3))

    lbl_em_title = ctk.CTkLabel(
        f_em_box, text="🎭 Emojis (Toca para agregar a la pantalla)",
        font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8"
    )
    lbl_em_title.pack(anchor="w", padx=8, pady=(4, 2))

    f_em_grid = ctk.CTkFrame(f_em_box, fg_color="transparent")
    f_em_grid.pack(padx=6, pady=(0, 6))

    emoji_thumbnails = {}
    for nom in EMOJIS_CATALOGO:
        p_em = emojis_dir / f"emoji_{nom}.png"
        if p_em.exists():
            try:
                im = Image.open(p_em).convert("RGBA")
                emoji_thumbnails[nom] = ctk.CTkImage(light_image=im, dark_image=im, size=(26, 26))
            except Exception:
                pass

    def _agregar_emoji(nom_em: str):
        nonlocal selected_sprite
        n_existentes = len([s for s in sprites if s.tipo == "emoji"])
        offset_x = (n_existentes % 4) * 8.0
        offset_y = (n_existentes % 4) * 6.0
        sp = SpriteItem("emoji", nom_em, 76.0 - offset_x, 30.0 + offset_y, scale=1.0, rot=0.0, tracking=True)
        sprites.append(sp)
        selected_sprite = sp
        _actualizar_panel_seleccion()
        _redibujar()

    for idx, nom in enumerate(EMOJIS_CATALOGO):
        r = 0 if idx < 6 else 1
        c = idx if idx < 6 else idx - 6
        thumb = emoji_thumbnails.get(nom)
        btn_e = ctk.CTkButton(
            f_em_grid,
            image=thumb,
            text="" if thumb else nom[:3],
            width=46,
            height=34,
            corner_radius=6,
            fg_color="#181f33",
            hover_color="#2b3658",
            command=lambda n=nom: _agregar_emoji(n),
        )
        btn_e.grid(row=r, column=c, padx=3, pady=2)

    # Panel de Sprite Seleccionado
    f_sel = ctk.CTkFrame(win_p, fg_color="#141824", corner_radius=8, border_width=1, border_color="#222b40")
    f_sel.pack(fill="x", padx=16, pady=(3, 3))

    lbl_sel_info = ctk.CTkLabel(
        f_sel, text="Toca un sprite en pantalla para moverlo o girarlo",
        font=ctk.CTkFont(size=11, weight="bold"), text_color="#64748b"
    )
    lbl_sel_info.pack(side="left", padx=(8, 4), pady=4)

    var_tracking = ctk.BooleanVar(value=True)

    def _on_toggle_tracking():
        if selected_sprite is not None:
            selected_sprite.tracking = var_tracking.get()

    chk_tracking = ctk.CTkCheckBox(
        f_sel, text="Tracking IA", variable=var_tracking, command=_on_toggle_tracking,
        font=ctk.CTkFont(size=11, weight="bold"), checkbox_width=18, checkbox_height=18, corner_radius=4
    )
    chk_tracking.pack(side="right", padx=(4, 8), pady=4)

    def _quitar_sprite_seleccionado():
        nonlocal selected_sprite
        if selected_sprite is not None and selected_sprite in sprites:
            sprites.remove(selected_sprite)
            selected_sprite = None
            _actualizar_panel_seleccion()
            _actualizar_cuadrillas()
            _redibujar()

    btn_quitar = ctk.CTkButton(
        f_sel, text="🗑 Quitar", fg_color="#45121b", hover_color="#881337",
        width=60, height=24, font=ctk.CTkFont(size=11, weight="bold"),
        command=_quitar_sprite_seleccionado
    )
    btn_quitar.pack(side="right", padx=4, pady=4)

    def _actualizar_panel_seleccion():
        if selected_sprite is not None:
            nom_dsp = selected_sprite.nombre.title()
            if selected_sprite.tipo == "flecha" or abs(selected_sprite.rot) > 1.0:
                texto_sel = f"🎯 {nom_dsp} | Giro: {selected_sprite.rot:.0f}°"
            else:
                texto_sel = f"🎯 {nom_dsp}"
            lbl_sel_info.configure(
                text=texto_sel,
                text_color="#38bdf8"
            )
            var_tracking.set(selected_sprite.tracking)
            chk_tracking.configure(state="normal")
            btn_quitar.configure(state="normal")
        else:
            lbl_sel_info.configure(
                text="Toca un elemento para mover o girar",
                text_color="#64748b"
            )
            chk_tracking.configure(state="disabled")
            btn_quitar.configure(state="disabled")

    _actualizar_cuadrillas()
    _actualizar_panel_seleccion()
    _redibujar()

    def _al_cerrar():
        if on_preview_live is not None:
            try:
                on_preview_live(None, None, "", "", 0, None)
            except Exception:
                pass
        win_p.destroy()

    def _guardar_y_cerrar():
        c_s = next((s for s in sprites if s.tipo == "circulo"), None)
        if c_s:
            tam = "chico" if c_s.scale < 0.8 else ("grande" if c_s.scale > 1.3 else "medio")
            pref = "" if c_s.tracking else "fijo:"
            res_circulo = f"{pref}{c_s.x:.1f},{c_s.y:.1f}:{tam}"
        else:
            res_circulo = "ninguno"

        f_s = next((s for s in sprites if s.tipo == "flecha"), None)
        if f_s:
            pref = "" if f_s.tracking else "fijo:"
            rot_int = int(round(f_s.rot)) % 360
            res_flecha = f"{pref}{f_s.x:.1f},{f_s.y:.1f}@{rot_int}"
        else:
            res_flecha = "ninguna"

        e_s_list = [s for s in sprites if s.tipo == "emoji"]
        if e_s_list:
            parts = []
            for s in e_s_list:
                pref = "" if s.tracking else "fijo:"
                rot_str = f"@{int(round(s.rot)) % 360}" if abs(s.rot) > 1 else ""
                parts.append(f"{pref}{s.nombre}:{s.x:.1f},{s.y:.1f}{rot_str}")
            res_emoji = "+".join(parts)
        else:
            res_emoji = "ninguno"

        on_aplicar(res_circulo, res_flecha, res_emoji)
        _al_cerrar()

    win_p.protocol("WM_DELETE_WINDOW", _al_cerrar)

    ctk.CTkButton(
        win_p, text="Guardar Cambios", command=_guardar_y_cerrar,
        corner_radius=10, height=34, fg_color="#10b981", hover_color="#059669",
        text_color="#052e16", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
    ).pack(fill="x", padx=16, pady=(6, 10))


class BloqueGuionCard(ctk.CTkFrame):
    """Tarjeta interactiva con edición de tiempos manual sincronizada y controles de reordenamiento."""

    def __init__(
        self,
        master,
        index: int,
        datos: Dict,
        on_change: Callable,
        on_time_edit: Callable,
        on_move: Callable,
        on_delete: Callable,
        mostrar_assets_inicial: bool = False,
        ruta_video: Optional[Any] = None,
        on_preview_live: Optional[Callable] = None,
    ):
        super().__init__(master, fg_color="#181B26", corner_radius=10, border_width=1, border_color="#2A3147")
        self.index = index
        self.datos = datos
        self.on_change = on_change
        self.on_time_edit = on_time_edit
        self.on_move = on_move
        self.on_delete = on_delete
        self.mostrar_assets = mostrar_assets_inicial
        self.ruta_video = ruta_video
        self.on_preview_live = on_preview_live
        self._assets_creados = False

        self.grid_columnconfigure(0, weight=1)
        self._build_ui()
        self._actualizar_semaforo_palabras()

    def _build_ui(self):
        # ---------------- FILA 1: TIEMPOS + SEMÁFORO + ACCIONES ----------------
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))

        badge = ctk.CTkLabel(
            top_frame, text=f"#{self.index + 1}",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#313952", corner_radius=6, width=28, height=24,
            text_color="#f8fafc"
        )
        badge.pack(side="left", padx=(0, 6))

        ctk.CTkLabel(top_frame, text="⏱", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 2))

        self.entry_t_ini = ctk.CTkEntry(
            top_frame, width=54, height=24, justify="center",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#101524", border_color="#2a3147"
        )
        self.entry_t_ini.insert(0, seg_a_mmss(self.datos["t_ini"]))
        self.entry_t_ini.pack(side="left", padx=2)
        self.entry_t_ini.bind("<FocusOut>", self._on_ini_edited)
        self.entry_t_ini.bind("<Return>", self._on_ini_edited)

        ctk.CTkLabel(top_frame, text="→", font=ctk.CTkFont(size=12, weight="bold"), text_color="#64748b").pack(side="left", padx=2)

        self.entry_t_fin = ctk.CTkEntry(
            top_frame, width=54, height=24, justify="center",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#101524", border_color="#2a3147"
        )
        self.entry_t_fin.insert(0, seg_a_mmss(self.datos["t_fin"]))
        self.entry_t_fin.pack(side="left", padx=2)
        self.entry_t_fin.bind("<FocusOut>", self._on_fin_edited)
        self.entry_t_fin.bind("<Return>", self._on_fin_edited)

        self.lbl_duracion = ctk.CTkLabel(
            top_frame, text="", font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8"
        )
        self.lbl_duracion.pack(side="left", padx=(6, 4))



        # Botones de acción a la derecha
        btn_del = ctk.CTkButton(
            top_frame, text="🗑", width=26, height=24, fg_color="#45121b", hover_color="#881337",
            font=ctk.CTkFont(size=11),
            command=lambda: self.on_delete(self.index)
        )
        btn_del.pack(side="right", padx=(3, 0))

        btn_down = ctk.CTkButton(
            top_frame, text="▼", width=24, height=24, fg_color="#1e2436", hover_color="#2d354d",
            font=ctk.CTkFont(size=10, weight="bold"),
            command=lambda: self.on_move(self.index, 1)
        )
        btn_down.pack(side="right", padx=2)

        btn_up = ctk.CTkButton(
            top_frame, text="▲", width=24, height=24, fg_color="#1e2436", hover_color="#2d354d",
            font=ctk.CTkFont(size=10, weight="bold"),
            command=lambda: self.on_move(self.index, -1)
        )
        btn_up.pack(side="right", padx=2)

        self.btn_toggle_card_assets = ctk.CTkButton(
            top_frame,
            text="▲ Ocultar" if self.mostrar_assets else "🎛️ Assets",
            width=76,
            height=24,
            fg_color="#3B4261" if self.mostrar_assets else "#22283A",
            hover_color="#333D59",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._toggle_assets_local
        )
        self.btn_toggle_card_assets.pack(side="right", padx=4)

        # ---------------- FILA 2: CONTENEDOR DE ASSETS (LAZY LOAD) ----------------
        if self.mostrar_assets:
            self._asegurar_assets_frame()

        # ---------------- FILA 3: VOICEOVER / TEXTO DE NARRACIÓN ----------------
        vo_frame = ctk.CTkFrame(self, fg_color="transparent")
        vo_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(4, 8))
        vo_frame.grid_columnconfigure(0, weight=1)

        self.entry_texto = ctk.CTkEntry(
            vo_frame, height=32, font=ctk.CTkFont(size=13),
            placeholder_text="Escribe aquí el texto del guion con signos ¡!..."
        )
        self.entry_texto.insert(0, str(self.datos.get("texto", "")))
        self.entry_texto.grid(row=0, column=0, sticky="ew")
        self.entry_texto.bind("<KeyRelease>", self._on_texto_edit)

    def refrescar_tiempos_ui(self):
        """Actualiza los entries de tiempo y el semáforo in-place sin destruir ni recrear la tarjeta."""
        self.entry_t_ini.delete(0, "end")
        self.entry_t_ini.insert(0, seg_a_mmss(self.datos["t_ini"]))
        self.entry_t_fin.delete(0, "end")
        self.entry_t_fin.insert(0, seg_a_mmss(self.datos["t_fin"]))
        self._actualizar_semaforo_palabras()

    def _on_fin_edited(self, _event=None):
        try:
            nuevo_fin = mmss_a_seg(self.entry_t_fin.get())
            if nuevo_fin <= self.datos["t_ini"]:
                nuevo_fin = self.datos["t_ini"] + 0.5
            self.datos["t_fin"] = nuevo_fin
            self.entry_t_fin.delete(0, "end")
            self.entry_t_fin.insert(0, seg_a_mmss(nuevo_fin))
            self._actualizar_semaforo_palabras()
            self.on_time_edit(self.index, "fin", nuevo_fin)
        except Exception:
            pass

    def _on_ini_edited(self, _event=None):
        try:
            nuevo_ini = mmss_a_seg(self.entry_t_ini.get())
            if nuevo_ini >= self.datos["t_fin"]:
                nuevo_ini = max(0.0, self.datos["t_fin"] - 0.5)
            self.datos["t_ini"] = nuevo_ini
            self.entry_t_ini.delete(0, "end")
            self.entry_t_ini.insert(0, seg_a_mmss(nuevo_ini))
            self._actualizar_semaforo_palabras()
            self.on_time_edit(self.index, "ini", nuevo_ini)
        except Exception:
            pass

    def _asegurar_assets_frame(self):
        """Instancia o muestra los selectores organizados en filas compactas sin recrear widgets."""
        if self._assets_creados:
            if hasattr(self, "assets_frame") and self.assets_frame.winfo_exists():
                self.assets_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=4)
            return
        self._assets_creados = True

        self.assets_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.assets_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=4)

        # Fila 1: Efecto, SFX 1, SFX 2, Flechas/Círculos y Altura Texto en una sola línea
        row_assets_1 = ctk.CTkFrame(self.assets_frame, fg_color="transparent")
        row_assets_1.pack(fill="x", pady=(0, 4))

        self.opt_efecto = self._crear_selector(
            row_assets_1, "🎥 Efecto", LISTA_EFECTOS, self.datos.get("efecto", "ninguno"), width=105
        )

        sfx_partes = [s.strip() for s in str(self.datos.get("sfx", "")).split("+") if s.strip()]
        sfx1_val = sfx_partes[0] if len(sfx_partes) >= 1 else "ninguno"
        sfx2_val = sfx_partes[1] if len(sfx_partes) >= 2 else "ninguno"

        self.opt_sfx1 = self._crear_selector(
            row_assets_1, "🔊 SFX 1", LISTA_SFX, sfx1_val, width=105
        )
        self.opt_sfx2 = self._crear_selector(
            row_assets_1, "🔊 SFX 2", LISTA_SFX, sfx2_val, width=105
        )

        # Botón Flechas/Círculos a la derecha en la misma línea
        f_btn_pos = ctk.CTkFrame(row_assets_1, fg_color="transparent")
        f_btn_pos.pack(side="left", padx=3, pady=2)
        ctk.CTkLabel(f_btn_pos, text="", font=ctk.CTkFont(size=10)).pack(anchor="w")
        btn_pos = ctk.CTkButton(
            f_btn_pos,
            text="Flechas/Círculos",
            command=self._abrir_selector_posicion,
            height=24,
            width=108,
            fg_color="#1d4ed8",
            hover_color="#1e40af",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        btn_pos.pack()

        # Botón Altura Texto a la derecha en la misma línea
        f_btn_alt = ctk.CTkFrame(row_assets_1, fg_color="transparent")
        f_btn_alt.pack(side="left", padx=3, pady=2)
        ctk.CTkLabel(f_btn_alt, text="", font=ctk.CTkFont(size=10)).pack(anchor="w")
        self.btn_alt_toggle = ctk.CTkButton(
            f_btn_alt,
            text="📏 Altura Texto",
            command=self._toggle_frame_altura,
            height=24,
            width=95,
            fg_color="#1e2436",
            hover_color="#2d354d",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.btn_alt_toggle.pack()

        # Fila de Altura de Texto (oculta por defecto, se despliega con '📏 Altura Texto')
        self.frame_altura = ctk.CTkFrame(self.assets_frame, fg_color="#121623", corner_radius=6)
        self._altura_visible = False

        alt_val_ini = 70.0
        m_a = re.search(r"(\d+(?:\.\d+)?)", str(self.datos.get("altura", "70%")))
        if m_a:
            v_a = float(m_a.group(1))
            alt_val_ini = (v_a / 1920.0 * 100.0) if v_a > 100.0 else v_a
        alt_val_ini = max(15.0, min(85.0, alt_val_ini))
        self.altura_card_var = ctk.DoubleVar(value=alt_val_ini)

        self.lbl_alt_card = ctk.CTkLabel(
            self.frame_altura,
            text=f"📏 Altura Texto: {alt_val_ini:.0f}%",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#ffffff",
        )
        self.lbl_alt_card.pack(side="left", padx=(8, 10), pady=4)

        def _on_slider_alt_change(val: float):
            alt_int = int(round(val))
            self.datos["altura"] = f"{alt_int}%"
            self.lbl_alt_card.configure(text=f"📏 Altura Texto: {alt_int}%")
            self.on_change()
            if self.on_preview_live is not None:
                try:
                    self.on_preview_live(None, None, "altura_only", None, None, alt_int)
                except Exception:
                    pass

        self.slider_alt_card = ctk.CTkSlider(
            self.frame_altura,
            from_=15.0, to=85.0, number_of_steps=70,
            variable=self.altura_card_var,
            command=_on_slider_alt_change,
            width=160, height=14,
            progress_color="#ffffff", button_color="#ffffff"
        )
        self.slider_alt_card.pack(side="left", padx=(0, 8), pady=4)

    def _toggle_frame_altura(self):
        if not hasattr(self, "frame_altura") or not self.frame_altura.winfo_exists():
            return
        if getattr(self, "_altura_visible", False):
            self.frame_altura.pack_forget()
            self._altura_visible = False
            if hasattr(self, "btn_alt_toggle") and self.btn_alt_toggle.winfo_exists():
                self.btn_alt_toggle.configure(fg_color="#1e2436")
        else:
            self.frame_altura.pack(fill="x", pady=(3, 2))
            self._altura_visible = True
            if hasattr(self, "btn_alt_toggle") and self.btn_alt_toggle.winfo_exists():
                self.btn_alt_toggle.configure(fg_color="#334155")

    def _abrir_selector_posicion(self):
        def _on_aplicar(c_val, f_val, e_val):
            self.datos["circulo"] = c_val
            self.datos["flecha"] = f_val
            self.datos["emoji"] = e_val
            self.on_change()

        abrir_dialogo_posicion_pantalla(
            self.winfo_toplevel(),
            self.datos,
            _on_aplicar,
            ruta_video=self.ruta_video,
            on_preview_live=self.on_preview_live,
        )

    def _destruir_assets_frame(self):
        """Oculta los assets in-place para máxima velocidad sin destruir widgets."""
        if not self._assets_creados:
            return
        try:
            self._guardar_valores_assets_a_datos()
            if hasattr(self, "assets_frame") and self.assets_frame.winfo_exists():
                self.assets_frame.grid_remove()
        except Exception:
            pass

    def _guardar_valores_assets_a_datos(self):
        if not self._assets_creados:
            return
        try:
            self.datos["efecto"] = self.opt_efecto.get()
            s1 = self.opt_sfx1.get()
            s2 = self.opt_sfx2.get()
            if s1 != "ninguno" and s2 != "ninguno" and s1 != s2:
                self.datos["sfx"] = f"{s1}+{s2}"
            elif s1 != "ninguno":
                self.datos["sfx"] = s1
            elif s2 != "ninguno":
                self.datos["sfx"] = s2
            else:
                self.datos["sfx"] = "ninguno"
        except Exception:
            pass

    def _toggle_assets_local(self):
        self.mostrar_assets = not self.mostrar_assets
        if self.mostrar_assets:
            self._asegurar_assets_frame()
            self.btn_toggle_card_assets.configure(text="▲ Ocultar", fg_color="#3B4261")
        else:
            self._sincronizar_estado()
            if hasattr(self, "assets_frame") and self.assets_frame.winfo_exists():
                self.assets_frame.grid_remove()
            self.btn_toggle_card_assets.configure(text="🎛️ Assets", fg_color="#22283A")
        self.on_change()

    def _crear_selector(self, parent, label: str, lista: List[str], val_actual: str, width: int = 120):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(side="left", padx=4, pady=2)
        ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=10, weight="bold"), text_color="#94a3b8").pack(anchor="w")

        val_clean = str(val_actual).strip()
        lista_final = list(lista)
        if val_clean and val_clean not in lista_final:
            lista_final.append(val_clean)

        opt = ctk.CTkOptionMenu(
            f, values=lista_final, width=width, height=24,
            corner_radius=6, font=ctk.CTkFont(size=10),
            command=lambda _: self._sincronizar_estado()
        )
        opt.set(val_clean if val_clean else lista_final[0])
        opt.pack()
        return opt

    def _on_texto_edit(self, _event=None):
        self.datos["texto"] = self.entry_texto.get()
        self._actualizar_semaforo_palabras()
        self.on_change()

    def _actualizar_semaforo_palabras(self):
        dur = max(0.5, self.datos["t_fin"] - self.datos["t_ini"])
        self.lbl_duracion.configure(text=f"({dur:.1f}s)")

    def _sincronizar_estado(self):
        self._guardar_valores_assets_a_datos()
        self.datos["texto"] = self.entry_texto.get().strip()
        self.on_change()


class VisualScriptEditor(ctk.CTkFrame):
    """
    Editor Visual Interactivo de Guiones:
    - Ripple Time bidireccional automático entre bloques.
    - Reordenamiento rápido de bloques con ▲ y ▼.
    - Edición del Título viral real de YouTube con sincronización limpia.
    - Modo Doble: Solo Voz ultra-rápido o Profundo con Assets.
    """

    def __init__(
        self,
        master,
        ruta_video: Optional[Any] = None,
        on_preview_live: Optional[Callable] = None,
        **kwargs
    ):
        self.ruta_video = ruta_video
        self.on_preview_live = on_preview_live
        frame_kwargs = {
            k: v for k, v in kwargs.items()
            if k in ("width", "height", "corner_radius", "border_width", "bg_color", "fg_color", "border_color")
        }
        if "fg_color" not in frame_kwargs:
            frame_kwargs["fg_color"] = "transparent"
        super().__init__(master, **frame_kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.metadatos_ocultos: Dict[str, str] = {
            "MODO_ENCUADRE": "full",
            "VOLUMEN_VIDEO_ORIGINAL": "0",
            "ARCHIVO_SALIDA": "auto"
        }
        self.bloques: List[Dict] = []
        self.cards: List[BloqueGuionCard] = []
        self._modo_raw = False
        self.modo_profundo = False

        self._build_header()
        self._build_body()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="#141824", corner_radius=10, border_width=1, border_color="#252B3D")
        header.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 6))
        header.grid_columnconfigure(0, weight=1)

        self.entry_titulo = ctk.CTkEntry(
            header, height=30, font=ctk.CTkFont(size=12, weight="bold"),
            placeholder_text="Título para YouTube (#shorts)..."
        )
        self.entry_titulo.grid(row=0, column=0, padx=(10, 6), pady=8, sticky="ew")
        self.entry_titulo.bind("<KeyRelease>", lambda _: self._actualizar_raw_interno())

        btn_add = ctk.CTkButton(
            header, text="＋ Nuevo Bloque", width=120, height=28,
            fg_color="#0284c7", hover_color="#0369a1",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._agregar_bloque_arriba
        )
        btn_add.grid(row=0, column=1, padx=4, pady=8)

        self.btn_toggle_raw = ctk.CTkButton(
            header, text="📝 Texto Crudo", width=105, height=28,
            fg_color="#22283A", hover_color="#333D59",
            font=ctk.CTkFont(size=11),
            command=self._toggle_vista
        )
        self.btn_toggle_raw.grid(row=0, column=2, padx=8, pady=8)

    def _build_body(self):
        self.scroll_cards = ctk.CTkScrollableFrame(self, fg_color="#0e111a", corner_radius=8)
        self.scroll_cards.grid(row=1, column=0, sticky="nsew", padx=4, pady=2)
        self.scroll_cards.grid_columnconfigure(0, weight=1)

        self.raw_textbox = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=12))
        self.raw_textbox.bind("<KeyRelease>", self._on_raw_edited_manually)

    def _toggle_modo_profundo(self):
        self.modo_profundo = not self.modo_profundo
        if self.modo_profundo:
            self.btn_toggle_modo.configure(text="🎛️ Ver Assets (Todos)", fg_color="#6d28d9")
        else:
            self.btn_toggle_modo.configure(text="🎙️ Solo Voz (Todos)", fg_color="#1e3a5f")

        for c in self.cards:
            c.mostrar_assets = self.modo_profundo
            if self.modo_profundo:
                c._asegurar_assets_frame()
                c.btn_toggle_card_assets.configure(text="▲ Ocultar", fg_color="#3B4261")
            else:
                c._sincronizar_estado()
                if hasattr(c, "assets_frame") and c.assets_frame.winfo_exists():
                    c.assets_frame.grid_remove()
                c.btn_toggle_card_assets.configure(text="🎛️ Assets", fg_color="#22283A")

    def _toggle_vista(self):
        self._modo_raw = not self._modo_raw
        if self._modo_raw:
            self._actualizar_raw_interno()
            self.scroll_cards.grid_remove()
            self.raw_textbox.grid(row=1, column=0, sticky="nsew", padx=4, pady=2)
            self.btn_toggle_raw.configure(text="🎛️ Vista Tarjetas")
        else:
            texto_actual = self.raw_textbox.get("1.0", "end").strip()
            self.cargar_desde_texto(texto_actual)
            self.raw_textbox.grid_remove()
            self.scroll_cards.grid(row=1, column=0, sticky="nsew", padx=4, pady=2)
            self.btn_toggle_raw.configure(text="📝 Texto Crudo")

    def _on_raw_edited_manually(self, _event=None):
        pass

    def cargar_desde_texto(self, raw_script: str):
        self.raw_textbox.delete("1.0", "end")
        self.raw_textbox.insert("1.0", raw_script)

        self.bloques.clear()
        titulo_yt = ""
        titulo_sup = ""
        en_guion = False

        for linea in raw_script.splitlines():
            l_strip = linea.strip()
            if not l_strip:
                continue
            if l_strip.startswith("[GUION]"):
                en_guion = True
                continue
            if not en_guion:
                if ":" in l_strip:
                    k, v = l_strip.split(":", 1)
                    k_clean = k.strip().upper()
                    v_clean = v.strip()
                    if k_clean == "TITULO_YOUTUBE":
                        titulo_yt = v_clean
                    elif k_clean == "TITULO_SUPERIOR":
                        titulo_sup = v_clean
                    else:
                        self.metadatos_ocultos[k_clean] = v_clean
                continue

            if l_strip.upper().startswith("TIEMPO") or "|" not in l_strip:
                continue

            partes = [p.strip() for p in l_strip.split("|")]
            # Soporta 8 columnas (con ALTURA) o 7 columnas (compatibilidad)
            def _es_alt(s: str) -> bool:
                s_c = s.strip().lower()
                return s_c in ("arriba", "medio", "centro", "abajo", "muy_abajo", "fondo") or bool(re.match(r"^(y:)?\d{1,4}%?$", s_c))

            if len(partes) >= 8 and _es_alt(partes[6]):
                rango_t = partes[0].split("-")
                t_ini = mmss_a_seg(rango_t[0]) if len(rango_t) > 0 else 0.0
                t_fin = mmss_a_seg(rango_t[1]) if len(rango_t) > 1 else t_ini + 4.0
                if t_fin <= t_ini:
                    t_fin = t_ini + 4.0
                self.bloques.append({
                    "t_ini": t_ini,
                    "t_fin": t_fin,
                    "efecto": partes[1],
                    "sfx": partes[2],
                    "emoji": partes[3],
                    "flecha": partes[4],
                    "circulo": partes[5],
                    "altura": partes[6],
                    "texto": " | ".join(partes[7:]).strip()
                })
            elif len(partes) >= 7:
                rango_t = partes[0].split("-")
                t_ini = mmss_a_seg(rango_t[0]) if len(rango_t) > 0 else 0.0
                t_fin = mmss_a_seg(rango_t[1]) if len(rango_t) > 1 else t_ini + 4.0
                if t_fin <= t_ini:
                    t_fin = t_ini + 4.0
                self.bloques.append({
                    "t_ini": t_ini,
                    "t_fin": t_fin,
                    "efecto": partes[1],
                    "sfx": partes[2],
                    "emoji": partes[3],
                    "flecha": partes[4],
                    "circulo": partes[5],
                    "altura": "70%",
                    "texto": " | ".join(partes[6:]).strip()
                })

        # Mostrar el título real viral de YouTube
        titulo_mostrar = titulo_yt or titulo_sup or "Short Viral"
        self.entry_titulo.delete(0, "end")
        self.entry_titulo.insert(0, titulo_mostrar)

        if not self.bloques:
            self.bloques.append({
                "t_ini": 0.0, "t_fin": 4.0,
                "efecto": "zoom_impacto", "sfx": "crowd_shocked",
                "emoji": "sorprendido:derecha", "flecha": "centro",
                "circulo": "ninguno", "texto": ""
            })

        self._renderizar_tarjetas()
        self._actualizar_raw_interno()

    def exportar_a_texto(self) -> str:
        if self._modo_raw:
            return self.raw_textbox.get("1.0", "end").strip()

        for c in self.cards:
            try:
                c.datos["t_ini"] = mmss_a_seg(c.entry_t_ini.get())
                c.datos["t_fin"] = max(c.datos["t_ini"] + 0.5, mmss_a_seg(c.entry_t_fin.get()))
                c.datos["texto"] = c.entry_texto.get().strip()
                if c._assets_creados:
                    c._guardar_valores_assets_a_datos()
            except Exception:
                pass

        titulo_editado = self.entry_titulo.get().strip() or "Short Viral"
        tit_sup_limpio = re.sub(r'[^A-Za-z0-9_ -]', '', titulo_editado).strip()[:40] or "Short_Viral"

        lineas = [
            f"TITULO_SUPERIOR: {tit_sup_limpio}",
            f"TITULO_YOUTUBE: {titulo_editado}"
        ]
        for k, v in self.metadatos_ocultos.items():
            if k not in ("TITULO_SUPERIOR", "TITULO_YOUTUBE"):
                lineas.append(f"{k}: {v}")

        lineas.append("")
        lineas.append("[GUION]")
        lineas.append("TIEMPO | EFECTO | SFX | EMOJI | FLECHA | CIRCULO | ALTURA | TEXTO")

        for b in self.bloques:
            t_str = f"{seg_a_mmss(b['t_ini'])} - {seg_a_mmss(b['t_fin'])}"
            alt_val = b.get("altura", "70%") or "70%"
            fila = (
                f"{t_str} | {b['efecto']} | {b['sfx']} | "
                f"{b['emoji']} | {b['flecha']} | {b['circulo']} | {alt_val} | {b['texto']}"
            )
            lineas.append(fila)

        return "\n".join(lineas)

    def _actualizar_raw_interno(self):
        if getattr(self, "_debounce_raw_id", None):
            try:
                self.after_cancel(self._debounce_raw_id)
            except Exception:
                pass
        self._debounce_raw_id = self.after(120, self._ejecutar_actualizacion_raw)

    def _ejecutar_actualizacion_raw(self):
        self._debounce_raw_id = None
        if getattr(self, "_actualizando_raw", False):
            return
        self._actualizando_raw = True
        try:
            if not self._modo_raw:
                texto = self.exportar_a_texto()
                self.raw_textbox.delete("1.0", "end")
                self.raw_textbox.insert("1.0", texto)
        finally:
            self._actualizando_raw = False

    def _renderizar_tarjetas(self):
        for c in self.cards:
            try:
                c.destroy()
            except Exception:
                pass
        self.cards.clear()

        for idx, b in enumerate(self.bloques):
            card = BloqueGuionCard(
                self.scroll_cards,
                index=idx,
                datos=b,
                on_change=self._actualizar_raw_interno,
                on_time_edit=self._on_block_time_edited,
                on_move=self._mover_bloque,
                on_delete=self._eliminar_bloque,
                mostrar_assets_inicial=self.modo_profundo,
                ruta_video=self.ruta_video,
                on_preview_live=self.on_preview_live,
            )
            card.grid(row=idx, column=0, sticky="ew", padx=4, pady=4)
            self.cards.append(card)

    def _on_block_time_edited(self, idx: int, campo: str, nuevo_seg: float):
        """Efecto dominó (Ripple Time): sincroniza el fin de un bloque con el inicio del siguiente in-place."""
        if 0 <= idx < len(self.bloques):
            if campo == "fin":
                self.bloques[idx]["t_fin"] = nuevo_seg
                if idx + 1 < len(self.bloques):
                    sig = self.bloques[idx + 1]
                    dur_sig = max(0.5, sig["t_fin"] - sig["t_ini"])
                    sig["t_ini"] = nuevo_seg
                    if sig["t_fin"] <= sig["t_ini"]:
                        sig["t_fin"] = sig["t_ini"] + dur_sig
                    for j in range(idx, len(self.cards)):
                        if j < len(self.bloques):
                            self.cards[j].datos = self.bloques[j]
                            self.cards[j].refrescar_tiempos_ui()
            elif campo == "ini":
                self.bloques[idx]["t_ini"] = nuevo_seg
                if idx > 0:
                    ant = self.bloques[idx - 1]
                    ant["t_fin"] = nuevo_seg
                    if idx - 1 < len(self.cards):
                        self.cards[idx - 1].datos = ant
                        self.cards[idx - 1].refrescar_tiempos_ui()
                if idx < len(self.cards):
                    self.cards[idx].datos = self.bloques[idx]
                    self.cards[idx].refrescar_tiempos_ui()

            self._actualizar_raw_interno()

    def _ajustar_tiempo_cascada(self, idx: int, delta_seg: float):
        """Ajusta tiempos en cascada in-place en 0ms sin destruir widgets."""
        if 0 <= idx < len(self.bloques):
            self.bloques[idx]["t_fin"] = max(self.bloques[idx]["t_ini"] + 0.5, self.bloques[idx]["t_fin"] + delta_seg)
            for j in range(idx + 1, len(self.bloques)):
                dur = max(0.5, self.bloques[j]["t_fin"] - self.bloques[j]["t_ini"])
                self.bloques[j]["t_ini"] = self.bloques[j - 1]["t_fin"]
                self.bloques[j]["t_fin"] = self.bloques[j]["t_ini"] + dur
            for j in range(idx, len(self.cards)):
                if j < len(self.bloques):
                    self.cards[j].datos = self.bloques[j]
                    self.cards[j].refrescar_tiempos_ui()
            self._actualizar_raw_interno()

    def _mover_bloque(self, idx: int, direccion: int):
        target = idx + direccion
        if 0 <= idx < len(self.bloques) and 0 <= target < len(self.bloques):
            self.bloques[idx], self.bloques[target] = self.bloques[target], self.bloques[idx]
            # Reencadenar tiempos desde 00:00 conservando la duración de cada bloque
            t_curr = 0.0
            for b in self.bloques:
                d = max(0.5, b["t_fin"] - b["t_ini"])
                b["t_ini"] = t_curr
                b["t_fin"] = t_curr + d
                t_curr += d

            self._renderizar_tarjetas()
            self._actualizar_raw_interno()

    def _agregar_bloque_arriba(self):
        t_base = self.bloques[-1]["t_fin"] if self.bloques else 0.0
        dur_nueva = 4.0
        nuevo = {
            "t_ini": t_base,
            "t_fin": t_base + dur_nueva,
            "efecto": "zoom_in",
            "sfx": "whoosh",
            "emoji": "sorprendido:derecha",
            "flecha": "centro",
            "circulo": "ninguno",
            "texto": "¡Escribe aquí la nueva narración sincronizada!"
        }
        self.bloques.append(nuevo)
        self._renderizar_tarjetas()
        self._actualizar_raw_interno()

    def _eliminar_bloque(self, idx: int):
        if len(self.bloques) <= 1:
            return
        if 0 <= idx < len(self.bloques):
            eliminado = self.bloques.pop(idx)
            dur = eliminado["t_fin"] - eliminado["t_ini"]
            for j in range(idx, len(self.bloques)):
                self.bloques[j]["t_ini"] = max(0.0, self.bloques[j]["t_ini"] - dur)
                self.bloques[j]["t_fin"] = max(self.bloques[j]["t_ini"] + 1.0, self.bloques[j]["t_fin"] - dur)

            self._renderizar_tarjetas()
            self._actualizar_raw_interno()

    def get(self, index1="1.0", index2="end") -> str:
        return self.exportar_a_texto()

    def insert(self, index, text: str):
        self.cargar_desde_texto(text)

    def delete(self, index1="1.0", index2=None):
        self.raw_textbox.delete("1.0", "end")
        self.bloques.clear()
        for c in self.cards:
            try:
                c.destroy()
            except Exception:
                pass
        self.cards.clear()
        try:
            self.entry_titulo.delete(0, "end")
        except Exception:
            pass
