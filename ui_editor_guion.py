# -*- coding: utf-8 -*-
import re
import customtkinter as ctk
from typing import List, Dict, Callable, Optional, Any
from motor_optimizado import (
    recortar_frame_916_pil,
    parsear_directiva_asset_manual,
    formatear_directiva_asset_manual,
)

# =====================================================================
# CATÁLOGO OFICIAL Y 9 CUADRANTES PRECISOS DEL MOTOR
# =====================================================================
LISTA_EFECTOS = [
    "ninguno", "zoom_impacto", "zoom_in", "zoom_out", "flash",
    "temblor", "alerta_roja", "brillo_epico", "blanco_negro", "spotlight"
]

LISTA_SFX = [
    "ninguno", "crowd_shocked", "whoosh", "riser_suction", "vine_boom",
    "metal_pipe", "heartbeat_fast", "record_scratch", "ding",
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
        return recortar_frame_916_pil(frame_rgb, w, h)
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
    win_p.title("Editor de Assets")
    win_p.geometry("380x865")
    win_p.minsize(360, 760)
    win_p.resizable(False, True)
    win_p.configure(fg_color="#0e111a")
    win_p.transient(parent_win)
    win_p.grab_set()

    t_ini = float(datos_bloque.get("t_ini", 0.0))
    t_fin = float(datos_bloque.get("t_fin", 4.0))
    if t_fin <= t_ini:
        t_fin = t_ini + 3.0
    dur_bloque = max(0.2, round(t_fin - t_ini, 2))
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
        def __init__(
            self,
            tipo: str,
            nombre: str,
            x: float,
            y: float,
            scale: float = 1.0,
            rot: float = 0.0,
            tracking: bool = False,
            t_ini_rel: float = 0.0,
            t_fin_rel: Optional[float] = None,
        ):
            self.tipo = str(tipo)
            self.nombre = str(nombre)
            self.x = max(3.0, min(97.0, float(x)))
            self.y = max(3.0, min(97.0, float(y)))
            self.scale = max(0.35, min(2.8, float(scale)))
            self.rot = float(rot) % 360.0
            self.tracking = bool(tracking)
            t_ini_val = 0.0 if t_ini_rel is None else float(t_ini_rel)
            self.t_ini_rel = max(0.0, min(dur_bloque - 0.1, t_ini_val))
            fin_def = dur_bloque if t_fin_rel is None else float(t_fin_rel)
            self.t_fin_rel = max(self.t_ini_rel + 0.1, min(dur_bloque, fin_def))

    sprites: List[SpriteItem] = []
    selected_sprite: Optional[SpriteItem] = None

    # 1. Círculo existente
    c_raw = str(datos_bloque.get("circulo", "")).strip()
    meta_c = parsear_directiva_asset_manual(c_raw, "circulo", 0.0, dur_bloque)
    if meta_c["activo"]:
        sprites.append(
            SpriteItem(
                "circulo", "circulo",
                meta_c["x"], meta_c["y"],
                scale=meta_c["scale"], rot=0.0,
                tracking=meta_c["tracking"],
                t_ini_rel=meta_c["t_ini_rel"], t_fin_rel=meta_c["t_fin_rel"],
            )
        )

    # 2. Flecha existente
    f_raw = str(datos_bloque.get("flecha", "")).strip()
    meta_f = parsear_directiva_asset_manual(f_raw, "flecha", 0.0, dur_bloque)
    if meta_f["activo"]:
        sprites.append(
            SpriteItem(
                "flecha", "flecha",
                meta_f["x"], meta_f["y"],
                scale=meta_f["scale"], rot=meta_f["rot"],
                tracking=meta_f["tracking"],
                t_ini_rel=meta_f["t_ini_rel"], t_fin_rel=meta_f["t_fin_rel"],
            )
        )

    # 3. Emojis existentes (múltiples con +)
    e_raw = str(datos_bloque.get("emoji", "")).strip()
    if e_raw and e_raw.lower() not in ("ninguno", "ninguna", "none", "no"):
        partes = e_raw.split("+") if "+" in e_raw else [e_raw]
        for p in partes:
            p = p.strip()
            if not p or p.lower() in ("ninguno", "ninguna", "none", "no"):
                continue
            meta_e = parsear_directiva_asset_manual(p, "emoji", 0.0, dur_bloque)
            if meta_e["activo"]:
                nom_clean = _quitar_acentos(meta_e["nombre"].strip().lower())
                if nom_clean.startswith("emoji_"):
                    nom_clean = nom_clean[6:]
                sprites.append(
                    SpriteItem(
                        "emoji", nom_clean,
                        meta_e["x"], meta_e["y"],
                        scale=meta_e["scale"], rot=meta_e["rot"],
                        tracking=meta_e["tracking"],
                        t_ini_rel=meta_e["t_ini_rel"], t_fin_rel=meta_e["t_fin_rel"],
                    )
                )

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
        t_rel_actual = max(0.0, t_actual - t_ini)
        for s in sprites:
            base_img = None
            base_sz = 50
            if s.tipo == "flecha":
                base_img = assets_pil.get("flecha")
                base_sz = 72
            elif s.tipo == "circulo":
                base_img = assets_pil.get("circulo")
                base_sz = 88
            elif s.tipo == "emoji":
                base_img = assets_pil.get(s.nombre, assets_pil.get("sorprendido"))
                base_sz = 50

            cx = int(round((s.x / 100.0) * CW))
            cy = int(round((s.y / 100.0) * CH))
            dim = max(24, int(round(base_sz * s.scale)))
            visible_en_t = (s.t_ini_rel - 0.05) <= t_rel_actual <= (s.t_fin_rel + 0.05)

            if base_img is not None:
                try:
                    img_scaled = base_img.resize((dim, dim), Image.Resampling.BILINEAR)
                    if abs(s.rot) > 0.5:
                        img_scaled = img_scaled.rotate(-s.rot, resample=Image.Resampling.BICUBIC, expand=False)
                    if not visible_en_t:
                        r_c, g_c, b_c, a_c = img_scaled.split()
                        a_c = a_c.point(lambda p: int(p * 0.35))
                        img_scaled = Image.merge("RGBA", (r_c, g_c, b_c, a_c))
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
            base_sz = 88 if selected_sprite.tipo == "circulo" else (72 if selected_sprite.tipo == "flecha" else 50)
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
            base_sz = 88 if s.tipo == "circulo" else (72 if s.tipo == "flecha" else 50)
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
                selected_sprite = sprites[0] if sprites else None
        else:
            t_ini_r = round(max(0.0, min(dur_bloque - 0.3, t_actual - t_ini)), 2) if (t_actual - t_ini) > 0.15 else 0.0
            sp = SpriteItem(
                "flecha", "flecha", 50.0, 50.0,
                scale=1.0, rot=315.0, tracking=False,
                t_ini_rel=t_ini_r, t_fin_rel=dur_bloque,
            )
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
                selected_sprite = sprites[0] if sprites else None
        else:
            t_ini_r = round(max(0.0, min(dur_bloque - 0.3, t_actual - t_ini)), 2) if (t_actual - t_ini) > 0.15 else 0.0
            sp = SpriteItem(
                "circulo", "circulo", 50.0, 45.0,
                scale=1.0, rot=0.0, tracking=False,
                t_ini_rel=t_ini_r, t_fin_rel=dur_bloque,
            )
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
        if selected_sprite is not None and selected_sprite.tipo == "emoji":
            selected_sprite.nombre = nom_em
            _actualizar_panel_seleccion()
            _redibujar()
            return
        n_existentes = len([s for s in sprites if s.tipo == "emoji"])
        offset_x = (n_existentes % 4) * 8.0
        offset_y = (n_existentes % 4) * 6.0
        t_ini_r = round(max(0.0, min(dur_bloque - 0.3, t_actual - t_ini)), 2) if (t_actual - t_ini) > 0.15 else 0.0
        sp = SpriteItem(
            "emoji", nom_em, 76.0 - offset_x, 30.0 + offset_y,
            scale=1.0, rot=0.0, tracking=False,
            t_ini_rel=t_ini_r, t_fin_rel=dur_bloque,
        )
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

    # Barra limpia de Tiempo del Asset seleccionado (Aparece / Duración / Desaparece)
    f_timing = ctk.CTkFrame(win_p, fg_color="#121623", corner_radius=8, border_width=1, border_color="#1f273b")
    f_timing.pack(fill="x", padx=16, pady=(1, 3))

    ctk.CTkLabel(
        f_timing, text="⏱", font=ctk.CTkFont(size=11, weight="bold"), text_color="#38bdf8"
    ).pack(side="left", padx=(7, 3), pady=4)

    ctk.CTkLabel(
        f_timing, text="Ini:", font=ctk.CTkFont(size=10, weight="bold"), text_color="#94a3b8"
    ).pack(side="left", padx=(2, 2))
    ent_ap = ctk.CTkEntry(
        f_timing, width=44, height=23, justify="center",
        font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
        fg_color="#0e111a", border_color="#2a344c"
    )
    ent_ap.pack(side="left", padx=(0, 4), pady=4)

    ctk.CTkLabel(
        f_timing, text="Fin:", font=ctk.CTkFont(size=10, weight="bold"), text_color="#94a3b8"
    ).pack(side="left", padx=(2, 2))
    ent_des = ctk.CTkEntry(
        f_timing, width=44, height=23, justify="center",
        font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
        fg_color="#0e111a", border_color="#2a344c"
    )
    ent_des.pack(side="left", padx=(0, 4), pady=4)

    def _fijar_ini_actual():
        if selected_sprite is None:
            return
        rel_cur = max(0.0, min(dur_bloque - 0.1, round(t_actual - t_ini, 2)))
        dur_prev = max(0.2, selected_sprite.t_fin_rel - selected_sprite.t_ini_rel)
        selected_sprite.t_ini_rel = rel_cur
        selected_sprite.t_fin_rel = min(dur_bloque, round(rel_cur + dur_prev, 2))
        _actualizar_panel_seleccion()
        _redibujar()

    btn_t_now = ctk.CTkButton(
        f_timing, text="Actual", width=48, height=22, corner_radius=5,
        fg_color="#1e293b", hover_color="#334155", text_color="#38bdf8",
        font=ctk.CTkFont(size=10, weight="bold"), command=_fijar_ini_actual
    )
    btn_t_now.pack(side="right", padx=(2, 6), pady=4)

    def _aplicar_timing_entries(modo_cambio: str):
        if selected_sprite is None:
            return
        try:
            v_ap = float(ent_ap.get().replace("s", "").strip())
            v_des = float(ent_des.get().replace("s", "").strip())
        except Exception:
            return
        # Soportar tanto segundo absoluto del video (t_ini..t_fin) como relativo (0..dur_bloque)
        if v_ap >= t_ini - 0.05 and t_ini > 0.0:
            rel_ini = v_ap - t_ini
        else:
            rel_ini = v_ap
        rel_ini = max(0.0, min(dur_bloque - 0.1, rel_ini))

        if modo_cambio == "fin":
            if v_des >= t_ini and t_ini > 0.0:
                rel_fin = v_des - t_ini
            else:
                rel_fin = v_des
            rel_fin = max(rel_ini + 0.1, min(dur_bloque, rel_fin))
        else:
            dur_prev = max(0.2, selected_sprite.t_fin_rel - selected_sprite.t_ini_rel)
            rel_fin = min(dur_bloque, rel_ini + dur_prev)

        selected_sprite.t_ini_rel = round(rel_ini, 2)
        selected_sprite.t_fin_rel = round(rel_fin, 2)
        _actualizar_panel_seleccion()
        _redibujar()

    ent_ap.bind("<Return>", lambda _: _aplicar_timing_entries("ini"))
    ent_ap.bind("<FocusOut>", lambda _: _aplicar_timing_entries("ini"))
    ent_des.bind("<Return>", lambda _: _aplicar_timing_entries("fin"))
    ent_des.bind("<FocusOut>", lambda _: _aplicar_timing_entries("fin"))

    def _actualizar_panel_seleccion():
        if selected_sprite is not None:
            nom_dsp = selected_sprite.nombre.title()
            texto_sel = f"🎯 {nom_dsp} | Tam: {int(round(selected_sprite.scale * 100))}%"
            if selected_sprite.tipo == "flecha" or abs(selected_sprite.rot) > 1.0:
                texto_sel += f" | {selected_sprite.rot:.0f}°"
            lbl_sel_info.configure(
                text=texto_sel,
                text_color="#38bdf8"
            )
            var_tracking.set(selected_sprite.tracking)
            chk_tracking.configure(state="normal")
            btn_quitar.configure(state="normal")
            for w_e in (ent_ap, ent_des, btn_t_now):
                w_e.configure(state="normal")
            abs_ini = t_ini + selected_sprite.t_ini_rel
            abs_fin = t_ini + selected_sprite.t_fin_rel
            ent_ap.delete(0, "end")
            ent_ap.insert(0, f"{abs_ini:.1f}")
            ent_des.delete(0, "end")
            ent_des.insert(0, f"{abs_fin:.1f}")
        else:
            lbl_sel_info.configure(
                text="Toca un elemento para mover, escalar o girar",
                text_color="#64748b"
            )
            chk_tracking.configure(state="disabled")
            btn_quitar.configure(state="disabled")
            for w_e in (ent_ap, ent_des):
                w_e.configure(state="normal")
                w_e.delete(0, "end")
                w_e.insert(0, "-")
                w_e.configure(state="disabled")
            btn_t_now.configure(state="disabled")

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
        if selected_sprite is not None:
            _aplicar_timing_entries("dur")
        c_s = next((s for s in sprites if s.tipo == "circulo"), None)
        if c_s:
            res_circulo = formatear_directiva_asset_manual(
                "circulo", "circulo", c_s.x, c_s.y, c_s.scale, 0.0, c_s.tracking,
                c_s.t_ini_rel, c_s.t_fin_rel, dur_bloque
            )
        else:
            res_circulo = "ninguno"

        f_s = next((s for s in sprites if s.tipo == "flecha"), None)
        if f_s:
            res_flecha = formatear_directiva_asset_manual(
                "flecha", "flecha", f_s.x, f_s.y, f_s.scale, f_s.rot, f_s.tracking,
                f_s.t_ini_rel, f_s.t_fin_rel, dur_bloque
            )
        else:
            res_flecha = "ninguna"

        e_s_list = [s for s in sprites if s.tipo == "emoji"]
        if e_s_list:
            parts = []
            for s in e_s_list:
                parts.append(
                    formatear_directiva_asset_manual(
                        "emoji", s.nombre, s.x, s.y, s.scale, s.rot, s.tracking,
                        s.t_ini_rel, s.t_fin_rel, dur_bloque
                    )
                )
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
        super().__init__(master, fg_color="#141416", corner_radius=12, border_width=1, border_color="#28282d")
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
        top_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))

        self.lbl_badge_idx = ctk.CTkLabel(
            top_frame, text=f"#{self.index + 1}",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#222225", corner_radius=6, width=28, height=24,
            text_color="#ffffff"
        )
        self.lbl_badge_idx.pack(side="left", padx=(0, 6))

        ctk.CTkLabel(top_frame, text="⏱", font=ctk.CTkFont(size=12), text_color="#707075").pack(side="left", padx=(0, 2))

        self.entry_t_ini = ctk.CTkEntry(
            top_frame, width=54, height=24, justify="center",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#1c1c1e", border_color="#2e2e32", text_color="#ffffff"
        )
        self.entry_t_ini.insert(0, seg_a_mmss(self.datos["t_ini"]))
        self.entry_t_ini.pack(side="left", padx=2)
        self.entry_t_ini.bind("<FocusOut>", self._on_ini_edited)
        self.entry_t_ini.bind("<Return>", self._on_ini_edited)

        ctk.CTkLabel(top_frame, text="→", font=ctk.CTkFont(size=12, weight="bold"), text_color="#707075").pack(side="left", padx=2)

        self.entry_t_fin = ctk.CTkEntry(
            top_frame, width=54, height=24, justify="center",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#1c1c1e", border_color="#2e2e32", text_color="#ffffff"
        )
        self.entry_t_fin.insert(0, seg_a_mmss(self.datos["t_fin"]))
        self.entry_t_fin.pack(side="left", padx=2)
        self.entry_t_fin.bind("<FocusOut>", self._on_fin_edited)
        self.entry_t_fin.bind("<Return>", self._on_fin_edited)

        self.lbl_duracion = ctk.CTkLabel(
            top_frame, text="", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#707075"
        )
        self.lbl_duracion.pack(side="left", padx=(6, 4))



        # Botones de acción a la derecha
        btn_del = ctk.CTkButton(
            top_frame, text="🗑", width=26, height=24, fg_color="#2a1719", hover_color="#381a1d",
            border_width=1, border_color="#451a22", text_color="#fb7185",
            font=ctk.CTkFont(size=11),
            command=lambda: self.on_delete(self.index)
        )
        btn_del.pack(side="right", padx=(3, 0))

        btn_down = ctk.CTkButton(
            top_frame, text="▼", width=24, height=24, fg_color="#202023", hover_color="#28282c",
            border_width=1, border_color="#2e2e32", text_color="#A0A0A5",
            font=ctk.CTkFont(size=10, weight="bold"),
            command=lambda: self.on_move(self.index, 1)
        )
        btn_down.pack(side="right", padx=2)

        btn_up = ctk.CTkButton(
            top_frame, text="▲", width=24, height=24, fg_color="#202023", hover_color="#28282c",
            border_width=1, border_color="#2e2e32", text_color="#A0A0A5",
            font=ctk.CTkFont(size=10, weight="bold"),
            command=lambda: self.on_move(self.index, -1)
        )
        btn_up.pack(side="right", padx=2)

        self.btn_toggle_card_assets = ctk.CTkButton(
            top_frame,
            text="▲ Ocultar" if self.mostrar_assets else "▼ Mostrar",
            width=76,
            height=24,
            fg_color="#202023" if self.mostrar_assets else "#18181b",
            hover_color="#28282c",
            border_width=1,
            border_color="#2e2e32",
            text_color="#A0A0A5",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=self._toggle_assets_local
        )
        self.btn_toggle_card_assets.pack(side="right", padx=4)

        # ---------------- FILA 2: CONTENEDOR DE ASSETS (LAZY LOAD) ----------------
        if self.mostrar_assets:
            self._asegurar_assets_frame()

        # ---------------- FILA 3: VOICEOVER / TEXTO DE NARRACIÓN ----------------
        vo_frame = ctk.CTkFrame(self, fg_color="transparent")
        vo_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(4, 10))
        vo_frame.grid_columnconfigure(0, weight=1)

        self.entry_texto = ctk.CTkEntry(
            vo_frame, height=34, font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#101012", border_color="#242428", text_color="#ffffff",
            corner_radius=10,
            placeholder_text="Escribe aquí la frase o locución de esta escena..."
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
            row_assets_1, "Efecto", LISTA_EFECTOS, self.datos.get("efecto", "ninguno"), width=105
        )

        sfx_partes = [s.strip() for s in str(self.datos.get("sfx", "")).split("+") if s.strip()]
        sfx1_val = sfx_partes[0] if len(sfx_partes) >= 1 else "ninguno"
        sfx2_val = sfx_partes[1] if len(sfx_partes) >= 2 else "ninguno"

        self.opt_sfx1 = self._crear_selector(
            row_assets_1, "SFX 1", LISTA_SFX, sfx1_val, width=105
        )
        self.opt_sfx2 = self._crear_selector(
            row_assets_1, "SFX 2", LISTA_SFX, sfx2_val, width=105
        )

        # Botón Assets a la derecha en la misma línea
        f_btn_pos = ctk.CTkFrame(row_assets_1, fg_color="transparent")
        f_btn_pos.pack(side="left", padx=3, pady=2)
        ctk.CTkLabel(
            f_btn_pos,
            text="Assets",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#707075",
        ).pack(anchor="w")
        btn_pos = ctk.CTkButton(
            f_btn_pos,
            text="Sin Assets",
            command=self._abrir_selector_posicion,
            height=26,
            width=116,
            corner_radius=8,
            fg_color="#242426",
            hover_color="#2e2e32",
            border_width=1,
            border_color="#38383e",
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        )
        btn_pos.pack()
        self.btn_pos = btn_pos
        self._actualizar_texto_btn_posicion()

        # Botón Altura Texto a la derecha en la misma línea
        f_btn_alt = ctk.CTkFrame(row_assets_1, fg_color="transparent")
        f_btn_alt.pack(side="left", padx=3, pady=2)
        ctk.CTkLabel(f_btn_alt, text="", font=ctk.CTkFont(size=10)).pack(anchor="w")
        self.btn_alt_toggle = ctk.CTkButton(
            f_btn_alt,
            text="Altura Texto",
            command=self._toggle_frame_altura,
            height=26,
            width=92,
            corner_radius=8,
            fg_color="#202023",
            hover_color="#28282c",
            border_width=1,
            border_color="#2e2e32",
            text_color="#A0A0A5",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        )
        self.btn_alt_toggle.pack()

        # Botón Tiempo Assets a la derecha en la misma línea (diseño limpio e integrado)
        f_btn_tas = ctk.CTkFrame(row_assets_1, fg_color="transparent")
        f_btn_tas.pack(side="left", padx=3, pady=2)
        ctk.CTkLabel(f_btn_tas, text="", font=ctk.CTkFont(size=10)).pack(anchor="w")
        self.btn_tiempo_assets_toggle = ctk.CTkButton(
            f_btn_tas,
            text="Tiempo Assets",
            command=self._toggle_frame_tiempo_assets,
            height=26,
            width=102,
            corner_radius=8,
            fg_color="#202023",
            hover_color="#28282c",
            border_width=1,
            border_color="#2e2e32",
            text_color="#A0A0A5",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        )
        self.btn_tiempo_assets_toggle.pack()

        # Fila de Tiempo de Assets (oculta por defecto, se despliega con '⏱ Tiempo Assets')
        self.frame_tiempo_assets = ctk.CTkFrame(self.assets_frame, fg_color="#121623", corner_radius=6)
        self._tiempo_assets_visible = False

        ctk.CTkLabel(
            self.frame_tiempo_assets,
            text="⏱ Assets  Aparece (s):",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94a3b8",
        ).pack(side="left", padx=(8, 4), pady=4)

        self.ent_asset_ini = ctk.CTkEntry(
            self.frame_tiempo_assets, width=48, height=23, justify="center",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#0e111a", border_color="#2a344c"
        )
        self.ent_asset_ini.pack(side="left", padx=(0, 6), pady=4)

        ctk.CTkLabel(
            self.frame_tiempo_assets,
            text="Desaparece (s):",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94a3b8",
        ).pack(side="left", padx=(6, 4), pady=4)

        self.ent_asset_fin = ctk.CTkEntry(
            self.frame_tiempo_assets, width=48, height=23, justify="center",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#0e111a", border_color="#2a344c"
        )
        self.ent_asset_fin.pack(side="left", padx=(0, 8), pady=4)

        self._refrescar_inputs_tiempo_assets()

        self.ent_asset_ini.bind("<Return>", lambda _: self._aplicar_tiempo_assets_card("ini"))
        self.ent_asset_ini.bind("<FocusOut>", lambda _: self._aplicar_tiempo_assets_card("ini"))
        self.ent_asset_fin.bind("<Return>", lambda _: self._aplicar_tiempo_assets_card("fin"))
        self.ent_asset_fin.bind("<FocusOut>", lambda _: self._aplicar_tiempo_assets_card("fin"))

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
                self.btn_alt_toggle.configure(fg_color="#202023", text_color="#A0A0A5")
        else:
            self.frame_altura.pack(fill="x", pady=(3, 2))
            self._altura_visible = True
            if hasattr(self, "btn_alt_toggle") and self.btn_alt_toggle.winfo_exists():
                self.btn_alt_toggle.configure(fg_color="#28282c", text_color="#ffffff")

    def _refrescar_inputs_tiempo_assets(self):
        if not hasattr(self, "ent_asset_ini"):
            return
        t_i = float(self.datos.get("t_ini", 0.0))
        t_f = max(t_i + 0.2, float(self.datos.get("t_fin", t_i + 4.0)))
        dur_b = max(0.2, round(t_f - t_i, 2))
        rel_ini, rel_fin = 0.0, dur_b
        for k_t, t_tipo in (("circulo", "circulo"), ("flecha", "flecha"), ("emoji", "emoji")):
            raw_v = str(self.datos.get(k_t, "")).strip()
            if raw_v and raw_v.lower() not in ("ninguno", "ninguna", "none", "no"):
                first_part = raw_v.split("+")[0].strip()
                m_info = parsear_directiva_asset_manual(first_part, t_tipo, 0.0, dur_b)
                if m_info["activo"]:
                    rel_ini = m_info["t_ini_rel"]
                    rel_fin = m_info["t_fin_rel"]
                    break
        abs_ini = t_i + rel_ini
        abs_fin = t_i + rel_fin
        for ent_w, val_f in ((self.ent_asset_ini, abs_ini), (self.ent_asset_fin, abs_fin)):
            ent_w.delete(0, "end")
            ent_w.insert(0, f"{val_f:.1f}")

    def _aplicar_tiempo_assets_card(self, modo_cambio: str):
        if not hasattr(self, "ent_asset_ini"):
            return
        t_i = float(self.datos.get("t_ini", 0.0))
        t_f = max(t_i + 0.2, float(self.datos.get("t_fin", t_i + 4.0)))
        dur_b = max(0.2, round(t_f - t_i, 2))
        try:
            v_ap = float(self.ent_asset_ini.get().replace("s", "").strip())
            v_des = float(self.ent_asset_fin.get().replace("s", "").strip())
        except Exception:
            self._refrescar_inputs_tiempo_assets()
            return

        rel_ini = (v_ap - t_i) if (v_ap >= t_i - 0.05 and t_i > 0.0) else v_ap
        rel_ini = max(0.0, min(dur_b - 0.1, rel_ini))
        if modo_cambio == "fin":
            rel_fin = (v_des - t_i) if (v_des >= t_i and t_i > 0.0) else v_des
            rel_fin = max(rel_ini + 0.1, min(dur_b, rel_fin))
        else:
            rel_fin = (v_des - t_i) if (v_des >= t_i and t_i > 0.0) else v_des
            if rel_fin <= rel_ini:
                rel_fin = min(dur_b, rel_ini + 2.0)

        rel_ini = round(rel_ini, 2)
        rel_fin = round(rel_fin, 2)

        for k_t, t_tipo in (("circulo", "circulo"), ("flecha", "flecha")):
            raw_v = str(self.datos.get(k_t, "")).strip()
            m_info = parsear_directiva_asset_manual(raw_v, t_tipo, 0.0, dur_b)
            if m_info["activo"]:
                self.datos[k_t] = formatear_directiva_asset_manual(
                    t_tipo, m_info["nombre"], m_info["x"], m_info["y"],
                    m_info["scale"], m_info["rot"], m_info["tracking"],
                    rel_ini, rel_fin, dur_b,
                )

        raw_em = str(self.datos.get("emoji", "")).strip()
        if raw_em and raw_em.lower() not in ("ninguno", "ninguna", "none", "no"):
            partes_em = []
            for p_e in raw_em.split("+"):
                m_e = parsear_directiva_asset_manual(p_e.strip(), "emoji", 0.0, dur_b)
                if m_e["activo"]:
                    partes_em.append(
                        formatear_directiva_asset_manual(
                            "emoji", m_e["nombre"], m_e["x"], m_e["y"],
                            m_e["scale"], m_e["rot"], m_e["tracking"],
                            rel_ini, rel_fin, dur_b,
                        )
                    )
            if partes_em:
                self.datos["emoji"] = "+".join(partes_em)

        self._refrescar_inputs_tiempo_assets()
        self.on_change()

    def _toggle_frame_tiempo_assets(self):
        if not hasattr(self, "frame_tiempo_assets") or not self.frame_tiempo_assets.winfo_exists():
            return
        if getattr(self, "_tiempo_assets_visible", False):
            self.frame_tiempo_assets.pack_forget()
            self._tiempo_assets_visible = False
            if hasattr(self, "btn_tiempo_assets_toggle") and self.btn_tiempo_assets_toggle.winfo_exists():
                self.btn_tiempo_assets_toggle.configure(fg_color="#202023", text_color="#A0A0A5")
        else:
            self._refrescar_inputs_tiempo_assets()
            self.frame_tiempo_assets.pack(fill="x", pady=(3, 2))
            self._tiempo_assets_visible = True
            if hasattr(self, "btn_tiempo_assets_toggle") and self.btn_tiempo_assets_toggle.winfo_exists():
                self.btn_tiempo_assets_toggle.configure(fg_color="#28282c", text_color="#ffffff")

    def _actualizar_texto_btn_posicion(self):
        if not hasattr(self, "btn_pos") or not self.btn_pos.winfo_exists():
            return
        activos = []
        v_f = str(self.datos.get("flecha", "ninguna")).strip().lower()
        if v_f not in ("", "ninguna", "ninguno", "none", "no", "-"):
            activos.append("Flecha")
        v_c = str(self.datos.get("circulo", "ninguno")).strip().lower()
        if v_c not in ("", "ninguna", "ninguno", "none", "no", "-"):
            activos.append("Círculo")
        v_e = str(self.datos.get("emoji", "ninguno")).strip().lower()
        if v_e not in ("", "ninguna", "ninguno", "none", "no", "-"):
            activos.append("Emoji")
        if activos:
            self.btn_pos.configure(text="✓ Assets", fg_color="#242426", hover_color="#2e2e32")
        else:
            self.btn_pos.configure(text="Sin Assets", fg_color="#242426", hover_color="#2e2e32")

    def _abrir_selector_posicion(self):
        def _on_aplicar(c_val, f_val, e_val):
            self.datos["circulo"] = c_val
            self.datos["flecha"] = f_val
            self.datos["emoji"] = e_val
            self._actualizar_texto_btn_posicion()
            self._refrescar_inputs_tiempo_assets()
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
            self.btn_toggle_card_assets.configure(text="▲ Ocultar", fg_color="#202023")
        else:
            self._sincronizar_estado()
            if hasattr(self, "assets_frame") and self.assets_frame.winfo_exists():
                self.assets_frame.grid_remove()
            self.btn_toggle_card_assets.configure(text="▼ Mostrar", fg_color="#18181b")
        self.on_change()

    def _crear_selector(self, parent, label: str, lista: List[str], val_actual: str, width: int = 120):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(side="left", padx=4, pady=2)
        ctk.CTkLabel(f, text=label, font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#707075").pack(anchor="w")

        val_clean = str(val_actual).strip()
        lista_final = list(lista)
        if val_clean and val_clean not in lista_final:
            lista_final.append(val_clean)

        opt = ctk.CTkOptionMenu(
            f, values=lista_final, width=width, height=26,
            corner_radius=8, font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="#1c1c1e", button_color="#28282d", button_hover_color="#33333a",
            text_color="#ffffff",
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
            "ARCHIVO_SALIDA": "auto",
            "OUTRO_LIKE": "si",
        }
        self.bloques: List[Dict] = []
        self.cards: List[BloqueGuionCard] = []
        self._modo_raw = False
        self.modo_profundo = True

        self._build_header()
        self._build_body()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 6))
        header.grid_columnconfigure(0, weight=1)

        self.entry_titulo = ctk.CTkEntry(
            header, height=34, corner_radius=12,
            fg_color="#121214", border_color="#2c2c32", border_width=1,
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            placeholder_text="Título editable del short..."
        )
        self.entry_titulo.grid(row=0, column=0, padx=(0, 8), pady=4, sticky="ew")
        self.entry_titulo.bind("<KeyRelease>", lambda _: self._actualizar_raw_interno())

        btn_add = ctk.CTkButton(
            header, text="+ Nuevo Bloque", width=124, height=34, corner_radius=12,
            fg_color="#242426", hover_color="#2e2e32",
            border_width=1, border_color="#38383e", text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._agregar_bloque_arriba
        )
        btn_add.grid(row=0, column=1, padx=4, pady=4)

        self.btn_toggle_raw = ctk.CTkButton(
            header, text="Texto Crudo", width=108, height=34, corner_radius=12,
            fg_color="#222226", hover_color="#2a2a2f",
            border_width=1, border_color="#333338", text_color="#A0A0A5",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._toggle_vista
        )
        self.btn_toggle_raw.grid(row=0, column=2, padx=(4, 0), pady=4)

    def _build_body(self):
        self.scroll_cards = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=8)
        self.scroll_cards.grid(row=1, column=0, sticky="nsew", padx=0, pady=2)
        self.scroll_cards.grid_columnconfigure(0, weight=1)

        self.raw_textbox = ctk.CTkTextbox(
            self, fg_color="#101012", border_color="#242428", border_width=1,
            corner_radius=12, text_color="#ffffff",
            font=ctk.CTkFont(family="Consolas", size=12)
        )
        self.raw_textbox.bind("<KeyRelease>", self._on_raw_edited_manually)

    def _toggle_modo_profundo(self):
        self.modo_profundo = not self.modo_profundo
        if self.modo_profundo:
            self.btn_toggle_modo.configure(text="Ver Assets (Todos)", fg_color="#242426")
        else:
            self.btn_toggle_modo.configure(text="Solo Voz (Todos)", fg_color="#1c1c1e")

        for c in self.cards:
            c.mostrar_assets = self.modo_profundo
            if self.modo_profundo:
                c._asegurar_assets_frame()
                c.btn_toggle_card_assets.configure(text="▲ Ocultar", fg_color="#202023")
            else:
                c._sincronizar_estado()
                if hasattr(c, "assets_frame") and c.assets_frame.winfo_exists():
                    c.assets_frame.grid_remove()
                c.btn_toggle_card_assets.configure(text="▼ Mostrar", fg_color="#18181b")

    def _toggle_vista(self):
        self._modo_raw = not self._modo_raw
        if self._modo_raw:
            self._actualizar_raw_interno()
            self.scroll_cards.grid_remove()
            self.raw_textbox.grid(row=1, column=0, sticky="nsew", padx=4, pady=2)
            self.btn_toggle_raw.configure(text="Vista Tarjetas", text_color="#ffffff")
        else:
            texto_actual = self.raw_textbox.get("1.0", "end").strip()
            self.cargar_desde_texto(texto_actual)
            self.raw_textbox.grid_remove()
            self.scroll_cards.grid(row=1, column=0, sticky="nsew", padx=0, pady=2)
            self.btn_toggle_raw.configure(text="Texto Crudo", text_color="#A0A0A5")

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

            def _norm_campo(val_raw: str, por_defecto: str = "ninguno") -> str:
                v = str(val_raw or "").strip()
                if v.lower() in ("", "-", "none", "no", "null", "normal", "ninguno", "ninguna"):
                    return por_defecto
                return v

            if len(partes) >= 8 and _es_alt(partes[6]):
                rango_t = partes[0].split("-")
                t_ini = mmss_a_seg(rango_t[0]) if len(rango_t) > 0 else 0.0
                t_fin = mmss_a_seg(rango_t[1]) if len(rango_t) > 1 else t_ini + 4.0
                if t_fin <= t_ini:
                    t_fin = t_ini + 4.0
                self.bloques.append({
                    "t_ini": t_ini,
                    "t_fin": t_fin,
                    "efecto": _norm_campo(partes[1], "ninguno"),
                    "sfx": _norm_campo(partes[2], "ninguno"),
                    "emoji": _norm_campo(partes[3], "ninguno"),
                    "flecha": _norm_campo(partes[4], "ninguna"),
                    "circulo": _norm_campo(partes[5], "ninguno"),
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
                    "efecto": _norm_campo(partes[1], "ninguno"),
                    "sfx": _norm_campo(partes[2], "ninguno"),
                    "emoji": _norm_campo(partes[3], "ninguno"),
                    "flecha": _norm_campo(partes[4], "ninguna"),
                    "circulo": _norm_campo(partes[5], "ninguno"),
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
            # Los primeros 2 bloques cargan desplegados al instante; el resto diferido para apertura inmediata (0ms)
            mostrar_ini = self.modo_profundo and (idx < 2)
            card = BloqueGuionCard(
                self.scroll_cards,
                index=idx,
                datos=b,
                on_change=self._actualizar_raw_interno,
                on_time_edit=self._on_block_time_edited,
                on_move=self._mover_bloque,
                on_delete=self._eliminar_bloque,
                mostrar_assets_inicial=mostrar_ini,
                ruta_video=self.ruta_video,
                on_preview_live=self.on_preview_live,
            )
            card.grid(row=idx, column=0, sticky="ew", padx=4, pady=4)
            self.cards.append(card)
            if self.modo_profundo and not mostrar_ini:
                card.mostrar_assets = True
                card.btn_toggle_card_assets.configure(text="▲ Ocultar", fg_color="#202023")
                self.after(18 * (idx - 1), lambda c_ref=card: (c_ref._asegurar_assets_frame() if c_ref.winfo_exists() and c_ref.mostrar_assets else None))

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
            for c in self.cards:
                if c._assets_creados:
                    c._guardar_valores_assets_a_datos()
            self.bloques[idx], self.bloques[target] = self.bloques[target], self.bloques[idx]
            if idx < len(self.cards) and target < len(self.cards):
                self.cards[idx], self.cards[target] = self.cards[target], self.cards[idx]
            t_curr = 0.0
            for j, b in enumerate(self.bloques):
                d = max(0.5, b["t_fin"] - b["t_ini"])
                b["t_ini"] = t_curr
                b["t_fin"] = t_curr + d
                t_curr += d
                if j < len(self.cards):
                    c_j = self.cards[j]
                    c_j.index = j
                    c_j.datos = b
                    c_j.lbl_badge_idx.configure(text=f"#{j + 1}")
                    c_j.grid_configure(row=j)
                    c_j.refrescar_tiempos_ui()

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
        idx_nuevo = len(self.bloques)
        self.bloques.append(nuevo)
        card = BloqueGuionCard(
            self.scroll_cards,
            index=idx_nuevo,
            datos=nuevo,
            on_change=self._actualizar_raw_interno,
            on_time_edit=self._on_block_time_edited,
            on_move=self._mover_bloque,
            on_delete=self._eliminar_bloque,
            mostrar_assets_inicial=self.modo_profundo,
            ruta_video=self.ruta_video,
            on_preview_live=self.on_preview_live,
        )
        card.grid(row=idx_nuevo, column=0, sticky="ew", padx=4, pady=4)
        self.cards.append(card)
        self._actualizar_raw_interno()

    def _eliminar_bloque(self, idx: int):
        if len(self.bloques) <= 1:
            return
        if 0 <= idx < len(self.bloques):
            eliminado = self.bloques.pop(idx)
            if idx < len(self.cards):
                c_del = self.cards.pop(idx)
                try:
                    c_del.destroy()
                except Exception:
                    pass
            dur = eliminado["t_fin"] - eliminado["t_ini"]
            for j in range(idx, len(self.bloques)):
                self.bloques[j]["t_ini"] = max(0.0, self.bloques[j]["t_ini"] - dur)
                self.bloques[j]["t_fin"] = max(self.bloques[j]["t_ini"] + 1.0, self.bloques[j]["t_fin"] - dur)
            for j, c_j in enumerate(self.cards):
                c_j.index = j
                if j < len(self.bloques):
                    c_j.datos = self.bloques[j]
                c_j.lbl_badge_idx.configure(text=f"#{j + 1}")
                c_j.grid_configure(row=j)
                c_j.refrescar_tiempos_ui()

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
