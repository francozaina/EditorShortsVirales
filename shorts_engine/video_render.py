# -*- coding: utf-8 -*-
import asyncio
import cv2
import json
import math
import os
import random
import re
import shutil
import subprocess
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .config import (
    WIDTH, HEIGHT, FPS, CPU_THREADS, WIN_NO_WINDOW, WIN_STARTUPINFO,
    BASE_DIR, ASSETS_DIR, EMOJIS_DIR, FONTS_DIR, FOTOS_DIR, SFX_DIR, MUSICA_DIR,
    TEMP_DIR, OUTPUT_DIR, ConfigGuion, SegmentoVideoGuion, PalabraSubtitulo,
    MODO_ENCUADRE_DEFAULT, VOLUMEN_VOZ_NARRADOR, VOLUMEN_AUDIO_VIDEO_ORIGINAL,
    VOLUMEN_MUSICA_FONDO, SUBTITLE_OFFSET_SEC, DURACION_CALLOUTS_DEFAULT, _quitar_acentos
)
from .parser_guion import cargar_guion_video
from .subtitulos import renderizar_subtitulos_luminosos, cargar_fuente, asegurar_fuente_mrbeast, estampar_rgba_en_rgb_inplace
from .audio_tts import (
    generar_voz_y_timestamps_segmento, alinear_palabras_con_onda_real, masterizar_voz_estudio_ffmpeg,
    intentar_voz_elevenlabs, GestorAudioSFX
)
from .vision_tracker import RastreadorObjetivosVideo
from .smart_camara import (
    SmartCamara916,
    compilar_trayectoria_a_expresion_ffmpeg,
    calcular_trayectoria_x_escalada_1920,
    transformar_coordenada_global_a_crop_916,
)
from .scene_cuts import DetectorCortesEscena
from .thumbnail_picker import SelectorPortadaViral
from motor_optimizado import realzar_frame_viral

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

        # Matrices NumPy RGBA pre-rasterizadas para renderizado Zero-Copy a 120+ FPS
        self.circulo_base_np: Optional[np.ndarray] = (
            np.array(self.circulo_base, dtype=np.uint8) if self.circulo_base else None
        )
        self.flecha_base_np: Optional[np.ndarray] = (
            np.array(self.flecha_base, dtype=np.uint8) if self.flecha_base else None
        )
        self.emojis_cache_np: Dict[str, np.ndarray] = {
            k: np.array(v, dtype=np.uint8) for k, v in self.emojis_cache.items()
        }
        self.vineta_roja_np: np.ndarray = np.array(self.vineta_roja_base, dtype=np.uint8)
        self.vineta_oscura_np: np.ndarray = np.array(self.vineta_oscura_base, dtype=np.uint8)

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
    ) -> Tuple[np.ndarray, List[Tuple[float, float]]]:
        """
        Aplica el efecto visual elegido sobre `frame_rgb` (1080x1920) y transforma
        las coordenadas de los objetivos rastreados `(vx, vy) -> (screen_x, screen_y)`
        de forma 100% in-place en NumPy/OpenCV (Zero-Copy a 120+ FPS).
        """
        progreso = min(1.0, max(0.0, t_seg / max(0.1, dur_seg)))
        fx, fy = foco_video

        zoom = 1.0
        shake_x, shake_y = 0.0, 0.0

        if efecto == "zoom_impacto":
            pulso_ini = math.sin(min(1.0, t_seg / 0.26) * math.pi) if t_seg < 0.26 else 0.0
            zoom = 1.0 + 0.14 * pulso_ini + 0.08 * progreso
            if t_seg < 0.28:
                amort = math.exp(-t_seg * 12.0)
                shake_x = 16.0 * math.sin(t_seg * 68.0) * amort
                shake_y = 12.0 * math.cos(t_seg * 54.0) * amort
        elif efecto == "zoom_in":
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
        elif efecto == "spotlight":
            curva = progreso * progreso * (3.0 - 2.0 * progreso)
            zoom = 1.05 + 0.06 * curva
        else:
            zoom = 1.0 + 0.05 * progreso

        # Centro base estable con anclaje elástico (Tethered Pivot)
        crop_w = WIDTH / zoom
        crop_h = HEIGHT / zoom
        pivote_x = (WIDTH * 0.5) + (fx - (WIDTH * 0.5)) * 0.35
        pivote_y = (HEIGHT * 0.5) + (fy - (HEIGHT * 0.5)) * 0.35

        max_dx = WIDTH * 0.14
        max_dy = HEIGHT * 0.14
        cx_base = float(np.clip(pivote_x, (WIDTH * 0.5) - max_dx, (WIDTH * 0.5) + max_dx))
        cy_base = float(np.clip(pivote_y, (HEIGHT * 0.5) - max_dy, (HEIGHT * 0.5) + max_dy))

        x0 = float(np.clip(cx_base + shake_x - crop_w / 2.0, 0.0, WIDTH - crop_w))
        y0 = float(np.clip(cy_base + shake_y - crop_h / 2.0, 0.0, HEIGHT - crop_h))

        ix0 = int(round(x0))
        iy0 = int(round(y0))
        ix1 = min(WIDTH, max(ix0 + 16, int(round(x0 + crop_w))))
        iy1 = min(HEIGHT, max(iy0 + 16, int(round(y0 + crop_h))))

        if ix0 > 0 or iy0 > 0 or ix1 < WIDTH or iy1 < HEIGHT:
            recorte = frame_rgb[iy0:iy1, ix0:ix1]
            frame_zoomed = cv2.resize(recorte, (WIDTH, HEIGHT), interpolation=cv2.INTER_LINEAR)
        else:
            frame_zoomed = frame_rgb.copy()

        scale_x = WIDTH / float(max(1, ix1 - ix0))
        scale_y = HEIGHT / float(max(1, iy1 - iy0))
        puntos_pantalla: List[Tuple[float, float]] = []
        for vx, vy in puntos_rastreados:
            sx = (vx - float(ix0)) * scale_x
            sy = (vy - float(iy0)) * scale_y
            sx = float(np.clip(sx, 48.0, WIDTH - 48.0))
            sy = float(np.clip(sy, 64.0, HEIGHT - 180.0))
            puntos_pantalla.append((sx, sy))

        if (efecto == "temblor" and t_seg < 0.7) or (efecto == "zoom_impacto" and t_seg < 0.18):
            shift = int(round(7.0 * math.exp(-t_seg * 6.0)))
            if shift >= 2:
                out_rgb = frame_zoomed.copy()
                out_rgb[:, shift:, 0] = frame_zoomed[:, :-shift, 0]
                out_rgb[:, :-shift, 2] = frame_zoomed[:, shift:, 2]
                frame_zoomed = out_rgb

        # Efectos visuales de atmósfera y color en NumPy/OpenCV puro
        if efecto == "blanco_negro":
            gris = cv2.cvtColor(frame_zoomed, cv2.COLOR_RGB2GRAY)
            gris_contraste = cv2.convertScaleAbs(gris, alpha=1.22, beta=0)
            frame_zoomed = cv2.cvtColor(gris_contraste, cv2.COLOR_GRAY2RGB)
            estampar_rgba_en_rgb_inplace(frame_zoomed, self.vineta_oscura_np, WIDTH // 2, HEIGHT // 2)

        elif efecto == "alerta_roja":
            pulso_rojo = 0.45 + 0.55 * abs(math.sin(t_seg * 6.5))
            estampar_rgba_en_rgb_inplace(
                frame_zoomed, self.vineta_roja_np, WIDTH // 2, HEIGHT // 2, opacidad_extra=pulso_rojo
            )

        elif efecto == "brillo_epico":
            hsv = cv2.cvtColor(frame_zoomed, cv2.COLOR_RGB2HSV)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1].astype(np.float32) * 1.26, 0, 255).astype(np.uint8)
            hsv[:, :, 2] = np.clip(hsv[:, :, 2].astype(np.float32) * 1.08, 0, 255).astype(np.uint8)
            frame_zoomed = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
            if t_seg < 0.30:
                alpha_dorado = float(np.clip(90.0 * (1.0 - t_seg / 0.30) / 255.0, 0.0, 1.0))
                capa_dorada = np.zeros_like(frame_zoomed)
                capa_dorada[:] = (255, 215, 60)
                cv2.addWeighted(capa_dorada, alpha_dorado, frame_zoomed, 1.0 - alpha_dorado, 0.0, frame_zoomed)

        elif efecto == "flash":
            if t_seg < 0.32:
                alpha_flash = float(np.clip(220.0 * ((1.0 - t_seg / 0.32) ** 1.8) / 255.0, 0.0, 1.0))
                capa_blanca = np.full_like(frame_zoomed, 255)
                cv2.addWeighted(capa_blanca, alpha_flash, frame_zoomed, 1.0 - alpha_flash, 0.0, frame_zoomed)

        elif efecto == "spotlight":
            if puntos_pantalla:
                foco_pt_x, foco_pt_y = puntos_pantalla[0]
            else:
                foco_pt_x, foco_pt_y = float(WIDTH // 2), float(HEIGHT // 2)

            sx = int(foco_pt_x * 270.0 / WIDTH)
            sy = int(foco_pt_y * 480.0 / HEIGHT)
            mascara_spot = np.full((480, 270), 102, dtype=np.uint8)
            cv2.circle(mascara_spot, (sx, sy), 65, 255, -1)
            mascara_suave = cv2.GaussianBlur(mascara_spot, (45, 45), 0)
            full_mask_1ch = cv2.resize(mascara_suave, (WIDTH, HEIGHT), interpolation=cv2.INTER_LINEAR)
            full_mask_3ch = cv2.merge([full_mask_1ch, full_mask_1ch, full_mask_1ch])
            cv2.multiply(frame_zoomed, full_mask_3ch, frame_zoomed, scale=1.0 / 255.0)

        if t_seg < 0.06 and efecto != "flash":
            alpha_tr = float(np.clip(55.0 * (1.0 - t_seg / 0.06) / 255.0, 0.0, 1.0))
            if alpha_tr > 0.015:
                capa_blanca = np.full_like(frame_zoomed, 255)
                cv2.addWeighted(capa_blanca, alpha_tr, frame_zoomed, 1.0 - alpha_tr, 0.0, frame_zoomed)

        return frame_zoomed, puntos_pantalla

    def dibujar_circulo_rojo(
        self,
        lienzo: np.ndarray,
        activo: bool,
        target_xy: Tuple[float, float],
        tamano_mod: str,
        t_seg: float,
        dur_seg: float,
        t_inicio_callout: float = 0.04,
    ) -> float:
        """
        Dibuja el circulo rojo animado directamente in-place sobre `lienzo` (NumPy RGB)
        usando escalado SIMD ultra-rapido. Devuelve el radio visible exterior.
        """
        if not activo or self.circulo_base_np is None:
            return 0.0

        dur_mostrar = min(dur_seg - 0.05, t_inicio_callout + self.duracion_callouts)
        if t_seg < t_inicio_callout or t_seg > dur_mostrar:
            return 0.0

        mapa_diametro = {
            "chico": 240,
            "medio": 350,
            "grande": 460,
        }
        diam_base = mapa_diametro.get(tamano_mod, 475)

        t_rel = t_seg - t_inicio_callout
        if t_rel < 0.22:
            p_in = max(0.0, min(1.0, t_rel / 0.18))
            escala = 0.25 + 0.88 * math.sin(p_in * math.pi * 0.65)
            alpha_f = min(1.0, p_in * 1.6)
        elif t_seg > dur_mostrar - 0.18:
            p_out = max(0.0, (dur_mostrar - t_seg) / 0.18)
            escala = 0.75 + 0.25 * p_out
            alpha_f = p_out
        else:
            escala = 1.0 + 0.025 * math.sin(t_rel * 3.5)
            alpha_f = 1.0

        diam_actual = max(48, int(round(diam_base * escala)))
        circ_scaled = cv2.resize(
            self.circulo_base_np, (diam_actual, diam_actual), interpolation=cv2.INTER_LINEAR
        )
        tx, ty = int(round(target_xy[0])), int(round(target_xy[1]))
        estampar_rgba_en_rgb_inplace(lienzo, circ_scaled, tx, ty, opacidad_extra=alpha_f)
        return diam_actual * 0.406

    def dibujar_flecha_roja(
        self,
        lienzo: np.ndarray,
        activo: bool,
        target_xy: Tuple[float, float],
        radio_circulo_activo: float,
        t_seg: float,
        dur_seg: float,
        t_inicio_callout: float = 0.04,
        angulo_forzado: Optional[float] = None,
    ) -> None:
        """
        Dibuja la flecha roja animada apuntando hacia `target_xy` directamente in-place sobre `lienzo`.
        Soporta rotación libre en grados (angulo_forzado) según la dirección de aproximación.
        """
        if not activo or self.flecha_base_np is None:
            return

        dur_mostrar = min(dur_seg - 0.05, t_inicio_callout + self.duracion_callouts)
        if t_seg < t_inicio_callout or t_seg > dur_mostrar:
            return

        tx, ty = target_xy
        if angulo_forzado is not None:
            rad = math.radians(angulo_forzado)
            ux = math.cos(rad)
            uy = math.sin(rad)
            angulo_grados = -math.degrees(math.atan2(uy, ux))
        else:
            if tx < WIDTH * 0.48:
                ux, uy = 0.82, -0.57
            elif tx > WIDTH * 0.52:
                ux, uy = -0.82, -0.57
            else:
                ux, uy = 0.78, -0.62
            angulo_grados = -math.degrees(math.atan2(uy, ux))

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
        fl_scaled = cv2.resize(
            self.flecha_base_np, (tam_flecha, tam_flecha), interpolation=cv2.INTER_LINEAR
        )
        if abs(angulo_grados) > 0.5:
            cx_f, cy_f = tam_flecha * 0.5, tam_flecha * 0.5
            mat_rot = cv2.getRotationMatrix2D((cx_f, cy_f), angulo_grados, 1.0)
            fl_scaled = cv2.warpAffine(
                fl_scaled,
                mat_rot,
                (tam_flecha, tam_flecha),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0, 0),
            )

        gap_objetivo = (radio_circulo_activo + 8.0) if radio_circulo_activo > 10.0 else 6.0
        rebote = 10.0 * (1.0 - math.cos(t_seg * math.pi * 2.2)) * 0.5
        dist_centro_a_punta = tam_flecha * 0.472
        dist_total = gap_objetivo + rebote + dist_centro_a_punta

        cx = int(round(tx + ux * dist_total))
        cy = int(round(ty + uy * dist_total))
        estampar_rgba_en_rgb_inplace(lienzo, fl_scaled, cx, cy, opacidad_extra=alpha_f)

    def dibujar_flecha_outro_like(
        self,
        lienzo: np.ndarray,
        t_seg: float,
        dur_seg: float = 1.0,
    ) -> None:
        """
        Dibuja la flecha roja animada apuntando al boton de Like directamente in-place sobre `lienzo`.
        """
        if self.flecha_base_np is None:
            return

        if t_seg < 0.12:
            p_in = max(0.0, t_seg / 0.12)
            escala = 0.50 + 0.55 * math.sin(p_in * math.pi * 0.5)
            alpha_f = min(1.0, p_in * 1.5)
        elif t_seg > dur_seg - 0.10:
            p_out = max(0.0, (dur_seg - t_seg) / 0.10)
            escala = 0.85 + 0.15 * p_out
            alpha_f = p_out
        else:
            escala = 1.0
            alpha_f = 1.0

        tam_flecha = max(120, int(round(360 * escala)))
        fl_scaled = cv2.resize(
            self.flecha_base_np, (tam_flecha, tam_flecha), interpolation=cv2.INTER_LINEAR
        )
        # Rotar 180 grados de forma instantanea (flip horizontal y vertical)
        fl_scaled = cv2.flip(fl_scaled, -1)

        target_x = 985.0
        target_y = 1040.0
        rebote = 25.0 * abs(math.sin(t_seg * 10.0))
        dist_punta = 15.0 + rebote

        pos_x = int(round(target_x - tam_flecha - dist_punta))
        pos_y = int(round(target_y - tam_flecha / 2.0))
        cx = pos_x + tam_flecha // 2
        cy = pos_y + tam_flecha // 2

        estampar_rgba_en_rgb_inplace(lienzo, fl_scaled, cx, cy, opacidad_extra=alpha_f)

    def dibujar_emoji(
        self,
        lienzo: np.ndarray,
        nombre_emoji: Optional[str],
        posicion_solicitada: str,
        target_principal_xy: Optional[Tuple[float, float]],
        t_seg: float,
        dur_seg: float,
    ) -> None:
        if not nombre_emoji:
            return

        # Soporte para múltiples emojis en escena separados por '+'
        if "+" in str(nombre_emoji):
            for sub_em in str(nombre_emoji).split("+"):
                sub_em = sub_em.strip()
                if not sub_em:
                    continue
                nom_s = sub_em
                pos_s = posicion_solicitada
                if ":" in sub_em:
                    nom_s, pos_s = sub_em.split(":", 1)
                self.dibujar_emoji(lienzo, nom_s, pos_s, target_principal_xy, t_seg, dur_seg)
            return

        if ":" in str(nombre_emoji):
            p_nom, p_pos = str(nombre_emoji).split(":", 1)
            nombre_emoji = p_nom
            if posicion_solicitada in ("", "auto", "multi"):
                posicion_solicitada = p_pos

        clave = _quitar_acentos(str(nombre_emoji).strip().lower())
        if clave.startswith("fijo:"):
            clave = clave[5:]
            posicion_solicitada = f"fijo:{posicion_solicitada}"

        base_np = self.emojis_cache_np.get(clave)
        if base_np is None:
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
        em_scaled = cv2.resize(
            base_np, (tam_actual, tam_actual), interpolation=cv2.INTER_LINEAR
        )

        # Ángulo dinámico o personalizado (@rot)
        rot_manual = 0.0
        pos_str = str(posicion_solicitada or "")
        m_rot = re.search(r"@(\d+(?:\.\d+)?)", pos_str)
        if m_rot:
            rot_manual = float(m_rot.group(1))

        angulo = rot_manual + 7.5 * math.sin(t_seg * 5.8)
        if abs(angulo) > 0.4:
            cx_e, cy_e = tam_actual * 0.5, tam_actual * 0.5
            mat_rot = cv2.getRotationMatrix2D((cx_e, cy_e), angulo, 1.0)
            em_scaled = cv2.warpAffine(
                em_scaled,
                mat_rot,
                (tam_actual, tam_actual),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0, 0),
            )

        pos_efectiva = pos_str.replace(f"@{m_rot.group(1)}", "") if m_rot else pos_str
        es_fijo = "fijo:" in pos_efectiva
        pos_efectiva = pos_efectiva.replace("fijo:", "")

        pos_map = {
            "derecha": (WIDTH - 195, 330),
            "izquierda": (195, 330),
            "arriba_der": (WIDTH - 190, 240),
            "arriba_izq": (190, 240),
            "centro": (WIDTH // 2, 340),
            "abajo": (WIDTH - 195, 1060),
        }

        # Soporte para coordenadas X, Y porcentuales
        m_coord = re.search(r"(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)", pos_efectiva)
        if m_coord:
            cx = int(round((float(m_coord.group(1)) / 100.0) * WIDTH))
            cy = int(round((float(m_coord.group(2)) / 100.0) * HEIGHT))
        else:
            if target_principal_xy is not None and not es_fijo:
                tx, ty = target_principal_xy
                if pos_efectiva == "auto":
                    pos_efectiva = "izquierda" if tx >= WIDTH * 0.5 else "derecha"
                elif pos_efectiva == "derecha" and tx > WIDTH * 0.62 and abs(ty - 340) < 230:
                    pos_efectiva = "izquierda"
                elif pos_efectiva == "izquierda" and tx < WIDTH * 0.38 and abs(ty - 340) < 230:
                    pos_efectiva = "derecha"
            elif pos_efectiva == "auto":
                pos_efectiva = "derecha"
            cx, cy = pos_map.get(pos_efectiva, pos_map["derecha"])

        if not es_fijo and target_principal_xy is not None and m_coord:
            tx, ty = target_principal_xy
            cx = int(round(cx * 0.75 + tx * 0.25))
            cy = int(round(cy * 0.75 + ty * 0.25))

        cy += int(round(9.0 * math.sin(t_seg * 6.2)))
        estampar_rgba_en_rgb_inplace(lienzo, em_scaled, cx, cy, opacidad_extra=alpha_factor)






def obtener_info_video(ruta_video: Path) -> Tuple[float, int, int, float]:
    """
    Devuelve (duracion_seg, ancho, alto, fps) exactos del video de entrada.
    """
    if not ruta_video.exists():
        raise FileNotFoundError(f"No se encontró el archivo de video: {ruta_video}")
    w, h, fps, dur = 1080, 1920, 30.0, 0.0
    try:
        res = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate,duration:format=duration",
                "-of", "json",
                str(ruta_video),
            ],
            capture_output=True,
            text=True,
            check=False,
            creationflags=WIN_NO_WINDOW,
            startupinfo=WIN_STARTUPINFO,
        )
        if res.returncode == 0 and res.stdout:
            d = json.loads(res.stdout)
            st = d.get("streams", [{}])[0]
            fmt = d.get("format", {})
            w = int(st.get("width") or 1080)
            h = int(st.get("height") or 1920)
            fps_str = str(st.get("r_frame_rate") or "30/1")
            fps = eval(fps_str) if "/" in fps_str else float(fps_str)
            dur = float(st.get("duration") or fmt.get("duration") or 0.0)
    except Exception:
        pass

    if dur <= 0.1 or fps <= 0:
        try:
            cap = cv2.VideoCapture(str(ruta_video), cv2.CAP_FFMPEG)
            if not cap.isOpened():
                cap = cv2.VideoCapture(str(ruta_video))
            fps = fps or cap.get(cv2.CAP_PROP_FPS) or 30.0
            n_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            w = w or int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1080)
            h = h or int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1920)
            cap.release()
            if dur <= 0.1 and n_frames > 0 and fps > 0:
                dur = float(n_frames) / float(fps)
        except (Exception, SystemError, BaseException):
            pass

    if dur <= 0.1:
        dur = 15.0
    return max(0.5, dur), w, h, float(fps)


def asegurar_formato_short(
    ruta_video: Path,
    progreso_cb: Optional[Callable[[float, str], None]] = None,
) -> Path:
    """
    Garantiza que el video cumpla con los requisitos estrictos de YouTube Shorts:
    1. Formato vertical (ancho <= alto, idealmente 1080x1920 con fondo desenfocado si es horizontal).
    2. Duracion estrictamente menor o igual a 59.9 segundos (si excede 60s, YouTube lo publica como Video normal).
    Si el video ya cumple ambos requisitos, se devuelve la ruta intacta sin re-procesar.
    """
    if not ruta_video.exists():
        return ruta_video

    dur, w, h, fps = obtener_info_video(ruta_video)
    es_horizontal = (w > h)
    # YouTube admite Shorts de hasta 60.0s exactos; evitar recortes innecesarios si mide <= 60.05s
    es_largo = (dur > 60.05)

    if not es_horizontal and not es_largo:
        # El video ya es vertical 9:16 y dura <=60s: devolver el archivo original intacto (cero pérdida de calidad)
        return ruta_video

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    salida_short = OUTPUT_DIR / f"{ruta_video.stem}_short.mp4"

    if salida_short.exists() and salida_short.stat().st_size > 1024:
        # Verificar que el cache no sea mas viejo que el video importado
        if salida_short.stat().st_mtime >= ruta_video.stat().st_mtime:
            dur_s, w_s, h_s, _ = obtener_info_video(salida_short)
            if w_s <= h_s and dur_s <= 60.05:
                return salida_short
        else:
            try:
                salida_short.unlink()
            except OSError:
                pass

    msg = "Adaptando video a formato vertical YouTube Shorts en maxima calidad (1080x1920 60 FPS)..."
    if progreso_cb:
        progreso_cb(0.1, msg)
    print(f"[*] {msg}")

    # Obtener el mejor encoder disponible en el sistema (GPU NVENC/AMF o CPU libx264 de alta calidad)
    _, enc_args = detectar_encoder_video()

    cmd = ["ffmpeg", "-y", "-i", str(ruta_video)]
    if es_largo:
        cmd.extend(["-t", "59.9"])

    if es_horizontal:
        filtro = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
            "[0:v]scale=1080:-2:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
        )
        cmd.extend([
            "-filter_complex", filtro,
            "-map", "[v]",
            "-map", "0:a?",
            *enc_args,
            "-r", "60",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
        ])
    else:
        # Ya es vertical pero excede 60s: recortar preservando máxima fidelidad visual
        cmd.extend([
            "-map", "0:v",
            "-map", "0:a?",
            *enc_args,
            "-r", "60",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
        ])

    cmd.append(str(salida_short))

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            creationflags=WIN_NO_WINDOW,
            startupinfo=WIN_STARTUPINFO,
        )
        if res.returncode == 0 and salida_short.exists() and salida_short.stat().st_size > 1024:
            print(f"[✓] Video adaptado con exito a YouTube Shorts: {salida_short.name}")
            return salida_short
        else:
            print(f"[!] Aviso al adaptar short con ffmpeg: {res.stderr[:200] if res.stderr else 'error desconocido'}")
    except Exception as e_adapt:
        print(f"[!] Error ejecutando adaptacion de short: {e_adapt}")

    return ruta_video


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

    # Evitar que el ultimo segmento quede huerfano con duracion insignificante (<3.4s)
    if n_segs > 1 and len(limites_seg) >= 2:
        dur_ultimo = limites_seg[-1] - limites_seg[-2]
        if dur_ultimo < 3.4:
            faltante = 3.4 - dur_ultimo
            min_prev = limites_seg[-3] + 2.0 if len(limites_seg) >= 3 else 1.0
            limites_seg[-2] = max(min_prev, limites_seg[-2] - faltante)

    # Convertir los limites de tiempo a indices de fotograma exactos a 60 FPS
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
    x_left_global_1920: Optional[np.ndarray] = None,
) -> List[np.ndarray]:
    """
    Extrae el rango [t_ini, t_fin] a velocidad real 1.0x (60 FPS) sin cámara lenta
    y devuelve exactamente `total_frames_salida` fotogramas RGB (1080x1920).
    Aplica recorte móvil inteligente 9:16 con SmartCamara916 dentro del motor de FFmpeg.
    """
    dur_clip = max(0.05, t_fin - t_ini)
    fps_extraccion = float(FPS)

    if modo_encuadre == "full" and x_left_global_1920 is not None and len(x_left_global_1920) > 0:
        idx_ini_global = max(0, int(round(t_ini * fps_extraccion)))
        idx_fin_global = idx_ini_global + total_frames_salida
        indices_seguros = np.clip(
            np.arange(idx_ini_global, idx_fin_global), 0, len(x_left_global_1920) - 1
        )
        x_left_seg = x_left_global_1920[indices_seguros]
        expr_x = compilar_trayectoria_a_expresion_ffmpeg(x_left_seg, fps=fps_extraccion)
        filtro_vf = (
            f"scale=-2:{HEIGHT}:flags=bicubic,"
            f"crop={WIDTH}:{HEIGHT}:'{expr_x}':0,"
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
    elif modo_encuadre == "blur":
        filtro_vf = (
            f"split[bg][fg];"
            f"[bg]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={WIDTH}:{HEIGHT},boxblur=24:4,eq=brightness=-0.12[bg_b];"
            f"[fg]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease:flags=lanczos[fg_s];"
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
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos,"
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
        proc = subprocess.Popen(
            cmd_ff,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=WIN_NO_WINDOW,
            startupinfo=WIN_STARTUPINFO,
        )
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
        try:
            cap = cv2.VideoCapture(str(ruta_video), cv2.CAP_FFMPEG)
            if not cap.isOpened():
                cap = cv2.VideoCapture(str(ruta_video))
            fps_orig = cap.get(cv2.CAP_PROP_FPS) or 30.0
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t_ini) * 1000.0)
            max_leer = max(2, int(round(dur_clip * fps_orig)))
            for _ in range(max_leer):
                try:
                    ret, frame_bgr = cap.read()
                except (Exception, SystemError, BaseException):
                    break
                if not ret or frame_bgr is None:
                    break
                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                h, w, _ = frame_rgb.shape
                scale = max(WIDTH / float(w), HEIGHT / float(h))
                nw, nh = int(round(w * scale)), int(round(h * scale))
                resized = cv2.resize(frame_rgb, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
                x0 = (nw - WIDTH) // 2
                y0 = (nh - HEIGHT) // 2
                frames_raw.append(resized[y0 : y0 + HEIGHT, x0 : x0 + WIDTH].copy())
            cap.release()
        except (Exception, SystemError, BaseException):
            pass

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


_ENCODER_SELECCIONADO: Optional[Tuple[str, List[str]]] = None


def detectar_encoder_video(forzar_cpu: bool = False) -> Tuple[str, List[str]]:
    """
    Detecta y prueba qué codificador de video H.264 acelerado por hardware
    (NVIDIA NVENC, AMD AMF o Intel QSV) o CPU (libx264) es compatible
    y funcional en la GPU/sistema actual mediante una prueba real de 1 frame.
    Si forzar_cpu=True, utiliza libx264 equilibrado sin tocar la GPU (ideal al jugar).
    """
    hilos_cpu = min(16, CPU_THREADS)
    args_cpu = [
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-threads", str(hilos_cpu), "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
    ]
    if forzar_cpu:
        return ("libx264", args_cpu)

    global _ENCODER_SELECCIONADO
    if _ENCODER_SELECCIONADO is not None:
        return _ENCODER_SELECCIONADO

    candidatos: List[Tuple[str, List[str]]] = [
        # NVIDIA NVENC (preset p6 alta calidad, 16M bitrate para 1080p)
        ("h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p2", "-cq", "19", "-b:v", "16M", "-maxrate", "20M", "-bufsize", "32M", "-pix_fmt", "yuv420p"]),
        # AMD Radeon AMF (modo calidad, 16M bitrate para 1080p)
        ("h264_amf", ["-c:v", "h264_amf", "-quality", "quality", "-rc", "vbr_peak", "-b:v", "16M", "-maxrate", "20M", "-pix_fmt", "yuv420p"]),
        # Intel Quick Sync Video
        ("h264_qsv", ["-c:v", "h264_qsv", "-preset", "veryslow", "-b:v", "16M", "-maxrate", "20M", "-pix_fmt", "yuv420p"]),
    ]

    for nombre, args in candidatos:
        try:
            # Probar si el encoder inicializa correctamente en el hardware actual (256x256 cumple el mínimo de AMD y NVIDIA)
            cmd_test = [
                "ffmpeg", "-y", "-v", "error",
                "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.04",
                *args,
                "-f", "null", "-"
            ]
            res = subprocess.run(
                cmd_test,
                capture_output=True,
                check=False,
                creationflags=WIN_NO_WINDOW,
                startupinfo=WIN_STARTUPINFO,
            )
            if res.returncode == 0:
                _ENCODER_SELECCIONADO = (nombre, args)
                return _ENCODER_SELECCIONADO
        except Exception:
            continue

    # Fallback CPU ultrafast (libx264 ultrafast CRF 18, todos los hilos)
    _ENCODER_SELECCIONADO = ("libx264", args_cpu)
    return _ENCODER_SELECCIONADO


def detectar_encoder_nvidia() -> str:
    encoder, _ = detectar_encoder_video()
    return encoder


MAX_CIRCULOS_POR_VIDEO = 2
MAX_FLECHAS_POR_VIDEO = 2


def _limitar_circulos_guion(
    segmentos: List[SegmentoVideoGuion],
    max_circulos: int = MAX_CIRCULOS_POR_VIDEO,
    max_flechas: int = MAX_FLECHAS_POR_VIDEO,
) -> None:
    """
    Limita tanto los círculos rojos como las flechas rojas para que aparezcan de forma
    espaciada y menos frecuente, evitando saturar todos los segmentos del Short.
    """
    # 0. Bloquear zonas vagas ('centro', 'auto', etc.) para círculos:
    # Solo se permiten círculos con detección de objeto real (box:[...] o coordenada validada)
    for s in segmentos:
        if s.circulo:
            c_norm = _quitar_acentos(str(s.circulo).strip().lower())
            if c_norm in ("centro", "center", "medio", "middle", "auto") or c_norm.startswith("centro:"):
                s.circulo = None

    con_circulo = [i for i, s in enumerate(segmentos) if s.circulo]
    if len(con_circulo) > max_circulos:
        prioridad = sorted(con_circulo, key=lambda i: (0 if segmentos[i].tamano_circulo == "grande" else 1, i))
        conservar = set(prioridad[:max_circulos])
        for i in con_circulo:
            if i not in conservar:
                segmentos[i].circulo = None
        print(
            f"[*] Círculo rojo limitado a {max_circulos} segmento(s): "
            f"{', '.join(str(i + 1) for i in sorted(conservar))}."
        )

    # Ambos (círculo y flecha) pueden coexistir apuntando al mismo foco de atención
    pass

    # Limitar la frecuencia de flechas rojas (espaciadas, evitando segmentos consecutivos)
    con_flecha = [i for i, s in enumerate(segmentos) if s.flecha]
    if len(con_flecha) > max_flechas:
        seleccionadas: List[int] = []
        for idx in con_flecha:
            # Preferir segmentos no consecutivos para que la aparición sea intermitente
            if not seleccionadas or (idx - seleccionadas[-1]) >= 2:
                seleccionadas.append(idx)
            if len(seleccionadas) >= max_flechas:
                break
        # Si aún faltan hasta llegar al tope permitido, completar
        for idx in con_flecha:
            if len(seleccionadas) >= max_flechas:
                break
            if idx not in seleccionadas:
                seleccionadas.append(idx)

        conservar_flechas = set(seleccionadas[:max_flechas])
        for i in con_flecha:
            if i not in conservar_flechas:
                segmentos[i].flecha = None
        print(
            f"[*] Flechas rojas limitadas a {len(conservar_flechas)} segmento(s) clave: "
            f"{', '.join(str(i + 1) for i in sorted(conservar_flechas))}."
        )

    # El último bloque del video jamás debe tener flecha de seguimiento de video,
    # porque el editor agrega automáticamente el Outro de 1 segundo con flecha apuntando al botón de Like.
    if segmentos and segmentos[-1].flecha:
        segmentos[-1].flecha = None


def seleccionar_musica_fondo(tono: Optional[str] = None) -> Optional[Path]:
    """
    Selecciona la pista de musica de fondo apropiada segun el tono o nombre elegido:
    - 'sin_musica' / 'ninguna' -> None (sin musica de fondo)
    - nombre exacto de la pista en /musica (ej. 'Fondo 1', 'Fondo 2', 'Inspiracional', etc.) -> pista exacta
    - 'triste' / 'sad' / 'drama' -> busca Triste.* en la carpeta /musica
    - 'inspiracional' / 'emotivo' / 'superacion' -> busca Inspiracional.* en la carpeta /musica
    - cualquier otro tono (o por defecto) -> elige aleatoriamente entre los fondos.
    """
    MUSICA_DIR.mkdir(parents=True, exist_ok=True)
    archivos = [
        p for p in MUSICA_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in (".mp3", ".wav", ".m4a", ".aac", ".ogg")
    ]
    if not archivos:
        return None

    t_clean = (tono or "").strip().lower()

    # 0. Sin Musica explicito
    if t_clean in ("sin_musica", "sin musica", "ninguna", "ninguno", "none", "off", "silencio", "mute"):
        return None

    # 0.5 Coincidencia exacta o parcial por nombre de archivo / stem (ej: 'Fondo 1', 'Inspiracional')
    if t_clean and t_clean not in ("auto", "fondo", "neutral"):
        for p in archivos:
            stem_low = p.stem.lower()
            if t_clean == stem_low or t_clean == stem_low.replace(" ", "_"):
                return p
        for p in archivos:
            if t_clean in p.stem.lower():
                return p

    # 1. Tono Triste
    if any(k in t_clean for k in ("trist", "sad", "dram", "pena", "llor", "depre")):
        pistas_tristes = [p for p in archivos if "trist" in p.stem.lower() or "sad" in p.stem.lower()]
        if pistas_tristes:
            return random.choice(pistas_tristes)

    # 2. Tono Inspiracional / Emotivo / Superacion
    if any(k in t_clean for k in ("inspirac", "motivac", "emotiv", "superac", "epico_final", "triumph")):
        pistas_insp = [p for p in archivos if "inspirac" in p.stem.lower() or "insp" in p.stem.lower()]
        if pistas_insp:
            return random.choice(pistas_insp)

    # 3. Fondos generales
    fondos = [
        p for p in archivos
        if "trist" not in p.stem.lower()
        and "sad" not in p.stem.lower()
        and "inspirac" not in p.stem.lower()
        and "insp" not in p.stem.lower()
    ]
    if fondos:
        return random.choice(fondos)

    return random.choice(archivos)


async def editar_video_con_guion(
    ruta_video: Path,
    ruta_guion: Path,
    voz_override: Optional[str] = None,
    modo_encuadre_override: Optional[str] = None,
    progreso_cb: Optional[object] = None,
    cancelar_check: Optional[Callable[[], bool]] = None,
    encoder_override: Optional[str] = None,
) -> Path:
    def _notificar_prog(frac_0_1: float, detalle: str) -> None:
        if callable(progreso_cb):
            try:
                progreso_cb(float(np.clip(frac_0_1, 0.0, 1.0)), detalle)
            except Exception:
                pass

    print("=" * 78)
    print(" EDITOR SHORTS STUDIO v1.0 - AUTOMATIZACIÓN DE SHORTS (VOZ IA + TRACKING)")
    print("=" * 78)

    for carpeta in [EMOJIS_DIR, FONTS_DIR, FOTOS_DIR, SFX_DIR, MUSICA_DIR, TEMP_DIR, OUTPUT_DIR]:
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

    cortes_detectados_video: List[float] = []
    # 0. Escaneo inteligente de cortes de cámara e imantación de bloques (Snap a cortes reales)
    try:
        detector_cortes = DetectorCortesEscena(fps_escaneo=12.0)
        cortes_reales = detector_cortes.detectar_cortes(str(ruta_video))
        if cortes_reales:
            cortes_detectados_video = list(cortes_reales)
        if cortes_reales:
            tiempos_brutos = [(float(s.t_inicio_video or 0.0), float(s.t_fin_video or dur_video_origen)) for s in config.segmentos]
            tiempos_ajustados = detector_cortes.ajustar_bloques_guion_a_cortes(
                tiempos_brutos, cortes_reales, ventana_imantacion_seg=0.45
            )
            for seg_obj, (t_ini_c, t_fin_c) in zip(config.segmentos, tiempos_ajustados):
                seg_obj.t_inicio_video = t_ini_c
                seg_obj.t_fin_video = t_fin_c
            print(f"[*] Cortes de escena detectados ({len(cortes_reales)}). Bloques del guion sincronizados a los cortes de plano.")
    except Exception as e_cortes:
        print(f"[*] Escaneo de cortes omitido: {e_cortes}")

    # 1. Fijar los tramos reales 1.0x de cada segmento sobre `dur_video_origen` ANTES de generar la voz
    # para que el video de fondo NUNCA vaya en cámara lenta y dure exactamente lo mismo que `video_input`.
    tiempos_reales = _asignar_tiempos_reales_segmentos(config.segmentos, dur_video_origen)

    # 1.5 Pre-calcular encuadre inteligente 9:16 (SmartCamara916) si el modo es 'full'
    x_left_global_1920: Optional[np.ndarray] = None
    w_escalado_1920: int = WIDTH
    if config.modo_encuadre == "full":
        try:
            camara_smart = SmartCamara916(ancho_analisis=320, fps_muestreo=6.0)
            x_left_global_1920, w_escalado_1920 = calcular_trayectoria_x_escalada_1920(
                camara_smart, str(ruta_video), fps_salida=float(FPS), ancho_target=WIDTH, alto_target=HEIGHT
            )
            print(f"[*] SmartCamara916 activa: encuadre 9:16 dinámico con física de gimbal ({w_escalado_1920}x{HEIGHT}).")
        except Exception as e_cam:
            print(f"[!] SmartCamara916 fallback a centrado estático: {e_cam}")
            x_left_global_1920 = None
            w_escalado_1920 = WIDTH

    gestor_assets = GestorEfectosYAssets(EMOJIS_DIR, FOTOS_DIR, duracion_callouts=config.duracion_callouts)
    gestor_sfx = GestorAudioSFX(SFX_DIR)

    datos_segmentos = []
    archivos_audio_seg: List[Path] = []
    n_segs = max(1, len(config.segmentos))

    # 2. Generar voz IA en PARALELO para todos los segmentos (asyncio.gather)
    # Esto reduce el tiempo de TTS de ~12s en serie a ~2s en paralelo.
    nom_voz_corta = config.voz_narrador.split("-")[-1].replace("Neural", "")
    _notificar_prog(0.05, f"Síntesis vocal paralela ({nom_voz_corta}) para {n_segs} bloques...")

    async def _generar_voz_segmento(idx: int, seg, dur_seg_exacta: float):
        if cancelar_check and cancelar_check():
            raise InterruptedError("TTS cancelado.")
        ruta_mp3 = TEMP_DIR / f"{seg.id_segmento}.mp3"
        sfx_str = "+".join(seg.sfx_lista) if seg.sfx_lista else "-"
        info_seg = (
            f"{seg.t_inicio_video:.1f}s-{seg.t_fin_video:.1f}s | efecto={seg.efecto_visual} | "
            f"sfx={sfx_str} | emoji={seg.emoji or '-'} | flecha={seg.flecha or '-'} | circulo={seg.circulo or '-'}"
        )
        print(f"[+] TTS [{idx + 1}/{n_segs}] ({info_seg}): {seg.texto_voz}")
        dur_voz, palabras_sub, ini_voz, fin_voz = await generar_voz_y_timestamps_segmento(
            seg.texto_voz,
            ruta_mp3,
            voz_edge=config.voz_narrador,
            dur_objetivo_seg=dur_seg_exacta,
        )
        return idx, palabras_sub

    # Lanzar todos los TTS en paralelo
    tareas_tts = [
        _generar_voz_segmento(idx, seg, dur_seg_exacta)
        for idx, (seg, (_, dur_seg_exacta)) in enumerate(zip(config.segmentos, tiempos_reales))
    ]
    resultados_tts = await asyncio.gather(*tareas_tts)
    # resultados_tts: lista de (idx, palabras_sub) ordenada por asyncio.gather (misma que la lista original)
    palabras_por_seg = {idx: palabras for idx, palabras in resultados_tts}

    # Mezclar SFX en serie (sin latencia de red) y armar datos_segmentos
    for idx, (seg, (total_frames_seg, dur_seg_exacta)) in enumerate(zip(config.segmentos, tiempos_reales)):
        if cancelar_check and cancelar_check():
            raise InterruptedError("Edición cancelada por el usuario.")
        _notificar_prog(
            0.05 + 0.30 * (idx / float(n_segs)),
            f"Mezcla SFX (bloque {idx + 1}/{n_segs})...",
        )
        palabras_sub = palabras_por_seg[idx]
        ruta_mp3 = TEMP_DIR / f"{seg.id_segmento}.mp3"
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
            permitir_cola_voz=(idx == len(config.segmentos) - 1),
        )
        archivos_audio_seg.append(ruta_mix_wav)
        datos_segmentos.append([seg, total_frames_seg, dur_seg_exacta, palabras_sub, rms_env])

    # 2.5 Generar Outro automatico con llamada visual al Like (campana ding, flecha animada y texto neon)
    extra_remate = 0.0
    if archivos_audio_seg:
        try:
            with wave.open(str(archivos_audio_seg[-1]), "r") as wf_last:
                dur_real_last = wf_last.getnframes() / float(wf_last.getframerate())
                dur_teorica_last = datos_segmentos[-1][2]
                if dur_real_last > dur_teorica_last:
                    extra_remate = min(1.2, dur_real_last - dur_teorica_last)
        except Exception:
            pass

    dur_outro_seg = round(0.85 + extra_remate, 2)
    total_frames_outro = int(round(FPS * dur_outro_seg))

    print(f"[*] Configurando Outro final de {dur_outro_seg}s con sonido de campana (ding) y texto luminoso...")

    # Subtitulos sincronizados para el Outro: ¡DEJA TU LIKE!
    palabras_sub_outro = [
        PalabraSubtitulo(texto="¡DEJA", inicio_seg=0.00, fin_seg=0.25),
        PalabraSubtitulo(texto="TU", inicio_seg=0.25, fin_seg=0.50),
        PalabraSubtitulo(texto="LIKE!", inicio_seg=0.50, fin_seg=dur_outro_seg, forzar_destaque=True),
    ]

    # Generar pista de audio para el Outro con sonido de campana (ding)
    ruta_mix_outro_wav = TEMP_DIR / "seg_outro_mix.wav"
    sr_audio = gestor_sfx.sr
    n_samples_outro = int(round(sr_audio * dur_outro_seg))
    mezcla_outro = np.zeros(n_samples_outro, dtype=np.float32)

    ding_pcm = gestor_sfx.obtener_pcm("ding")
    if ding_pcm is not None and len(ding_pcm) > 0:
        n_copiar = min(n_samples_outro, len(ding_pcm))
        mezcla_outro[:n_copiar] = ding_pcm[:n_copiar] * 0.85
    else:
        pop_pcm = gestor_sfx.obtener_pcm("pop")
        if pop_pcm is not None and len(pop_pcm) > 0:
            n_copiar = min(n_samples_outro, len(pop_pcm))
            mezcla_outro[:n_copiar] = pop_pcm[:n_copiar] * 0.85

    fade_samples = min(int(sr_audio * 0.06), n_samples_outro // 4)
    if fade_samples > 0:
        mezcla_outro[-fade_samples:] *= np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)

    mezcla_outro = np.clip(mezcla_outro, -0.98, 0.98)
    pcm_outro_bytes = (mezcla_outro * 32767).astype(np.int16).tobytes()

    with wave.open(str(ruta_mix_outro_wav), "w") as wf_out:
        wf_out.setnchannels(1)
        wf_out.setsampwidth(2)
        wf_out.setframerate(sr_audio)
        wf_out.writeframes(pcm_outro_bytes)

    archivos_audio_seg.append(ruta_mix_outro_wav)
    rms_env_outro = calcular_envolvente_rms(ruta_mix_outro_wav, FPS)

    _notificar_prog(0.38, "Masterizando pista de audio final (Voz + Efectos SFX + Música de fondo)...")

    # 3. Unir el audio maestro de la voz IA + Efectos SFX (el audio original del video descargado se MUTEA completamente)
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

    # 3.1 Inyección de SFX 'whoosh' dinámico en cada corte de escena detectado (estilo reels virales)
    if cortes_detectados_video:
        try:
            whoosh_pcm = gestor_sfx.obtener_pcm("whoosh")
            if whoosh_pcm is not None and len(whoosh_pcm) > 0:
                with wave.open(str(ruta_voz_maestra), "r") as wf_in:
                    audio_bytes = wf_in.readframes(wf_in.getnframes())
                master_pcm = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                sr_m = 44100

                whooshes_aplicados = 0
                ultimo_t = -999.0
                for t_corte in cortes_detectados_video:
                    if t_corte < 0.35 or t_corte > (dur_video_origen - 0.6):
                        continue
                    if (t_corte - ultimo_t) < 0.75:
                        continue
                    ultimo_t = t_corte
                    # Sincronizar cresta acústica del whoosh con el fotograma de corte (~70ms antes)
                    idx_ini = max(0, int(round((t_corte - 0.07) * sr_m)))
                    idx_fin = min(len(master_pcm), idx_ini + len(whoosh_pcm))
                    n_samp = idx_fin - idx_ini
                    if n_samp > 0:
                        master_pcm[idx_ini:idx_fin] += whoosh_pcm[:n_samp] * 0.42
                        whooshes_aplicados += 1

                if whooshes_aplicados > 0:
                    master_pcm = np.clip(master_pcm, -0.98, 0.98)
                    pcm_out_bytes = (master_pcm * 32767).astype(np.int16).tobytes()
                    with wave.open(str(ruta_voz_maestra), "w") as wf_out:
                        wf_out.setnchannels(1)
                        wf_out.setsampwidth(2)
                        wf_out.setframerate(sr_m)
                        wf_out.writeframes(pcm_out_bytes)
                    print(f"[*] Efecto Whoosh de reels añadido con éxito en {whooshes_aplicados} corte(s) de escena detectado(s).")
        except Exception as e_whoosh:
            print(f"[!] Aviso al superponer whoosh en cortes de escena: {e_whoosh}")

    # 3.5 Selección y mezcla inteligente de Música de Fondo desde /musica según el tono del Short
    ruta_audio_final = TEMP_DIR / "audio_final_combinado.wav"
    dur_total_audio = 0.0
    try:
        with wave.open(str(ruta_voz_maestra), "r") as wf_check:
            dur_total_audio = wf_check.getnframes() / float(wf_check.getframerate())
    except Exception:
        dur_total_audio = dur_video_origen + dur_outro_seg

    tono_efectivo = config.tono_video
    if tono_efectivo and str(tono_efectivo).lower().strip() in ("sin_musica", "sin musica", "ninguna", "ninguno", "none", "off", "silencio", "mute"):
        pista_musica = None
    else:
        if not tono_efectivo or tono_efectivo in ("auto", "fondo", "neutral"):
            texto_completo = f"{config.titulo_youtube} {config.descripcion_youtube} {' '.join(s.texto_voz for s in config.segmentos)}".lower()
            if any(w in texto_completo for w in ("triste", "tristeza", "llorando", "llorar", "pena", "depresivo", "lamentable", "tragedia")):
                tono_efectivo = "triste"
            elif any(w in texto_completo for w in ("inspiracional", "inspiracion", "motivacion", "superacion", "emotivo", "emocionante", "lagrimas de emocion", "salvar", "rescate")):
                tono_efectivo = "inspiracional"

        pista_musica = seleccionar_musica_fondo(tono_efectivo)

    if pista_musica and pista_musica.exists():
        # Volumen óptimo: presente en todo momento pero con ducking sutil cuando la voz habla
        vol_bgm = max(0.12, min(0.22, getattr(config, "volumen_musica", 0.18)))
        # Ajuste de volumen por pista: Fondo 2 atenuado (0.24), Fondo 1 muy atenuado (0.05) por copyright
        nom_pista = pista_musica.stem.lower()
        if "fondo 2" in nom_pista or "fondo_2" in nom_pista:
            vol_bgm = 0.24
        elif "fondo 1" in nom_pista or "fondo_1" in nom_pista:
            vol_bgm = 0.05
        fade_start = max(0.5, dur_total_audio - 0.4)
        # Ducking dramático de BGM en risers y frenazos de disco (corte a silencio de fondo)
        filtros_duck_dramatico = []
        t_acum_bgm = 0.0
        for seg_item in datos_segmentos:
            s_obj, _, dur_s = seg_item[0], seg_item[1], seg_item[2]
            sfx_nombres = [str(s).lower() for s in (s_obj.sfx_lista or [])]
            if any("record_scratch" in s or "riser_suction" in s for s in sfx_nombres):
                t_ini_d = t_acum_bgm
                t_fin_d = min(t_acum_bgm + 0.85, t_acum_bgm + dur_s)
                filtros_duck_dramatico.append(f"between(t,{t_ini_d:.2f},{t_fin_d:.2f})")
            t_acum_bgm += dur_s

        filtro_dramatico_str = ""
        if filtros_duck_dramatico:
            cond_duck = "+".join(filtros_duck_dramatico)
            filtro_dramatico_str = f",volume=0.20:enable='{cond_duck}'"
            print(f"[*] Ducking dramático de música activo en {len(filtros_duck_dramatico)} momentos de tensión/corte.")

        print(f"[*] Música de fondo con ducking sutil: '{pista_musica.name}' (tono: '{tono_efectivo}', volumen: {vol_bgm:.2f}).")
        filter_str = (
            f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={vol_bgm:.2f}{filtro_dramatico_str},afade=t=out:st={fade_start:.2f}:d=0.4,highpass=f=60,equalizer=f=2500:t=q:w=1.5:g=-3.0[bgm];"
            f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[voz_mix][voz_sc];"
            f"[bgm][voz_sc]sidechaincompress=threshold=0.08:ratio=3.5:attack=50:release=300[bgm_duck];"
            f"[voz_mix][bgm_duck]amix=inputs=2:duration=first:dropout_transition=0:weights='1 1':normalize=0[pre_master];"
            f"[pre_master]loudnorm=I=-14.0:TP=-1.0:LRA=7.0:linear=true,aresample=48000[aout]"
        )
        res_mix = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(ruta_voz_maestra),
                "-stream_loop", "-1", "-i", str(pista_musica),
                "-filter_complex", filter_str,
                "-map", "[aout]",
                "-ar", "44100", "-ac", "1",
                str(ruta_audio_final),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=WIN_NO_WINDOW,
            startupinfo=WIN_STARTUPINFO,
        )
        if res_mix.returncode != 0 or not ruta_audio_final.exists():
            print("[!] Falló la mezcla de música de fondo, usando narración y SFX limpios.")
            ruta_audio_final = ruta_voz_maestra
        else:
            print(f"[+] Audio final masterizado con éxito (Voz IA + Ruidos/SFX + Música '{pista_musica.stem}').")
    else:
        print("[*] No se encontró pista de música de fondo en /musica, usando narración y SFX limpios.")
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
    forzar_cpu = (encoder_override == "cpu")
    encoder, args_codec = detectar_encoder_video(forzar_cpu=forzar_cpu)

    def _ejecutar_render(enc_actual: str, args_actual: List[str]) -> Path:
        if "amf" in enc_actual:
            tipo_gpu = "Aceleración Hardware AMD Radeon (AMF)"
        elif "nvenc" in enc_actual:
            tipo_gpu = "Aceleración Hardware NVIDIA (NVENC)"
        elif "qsv" in enc_actual:
            tipo_gpu = "Aceleración Hardware Intel (QSV)"
        else:
            tipo_gpu = "Procesador CPU Equilibrado (libx264 fast CRF 18)"
        print(f"[*] Renderizando Short final con {enc_actual} [{tipo_gpu}] ({WIDTH}x{HEIGHT} a {FPS} FPS)...")

        cmd_ffmpeg = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{WIDTH}x{HEIGHT}",
            "-pix_fmt", "rgb24",
            "-r", str(FPS),
            "-i", "-",
            "-i", str(ruta_audio_final),
            *args_actual,
            "-colorspace", "bt709",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-color_range", "tv",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            str(ruta_mp4_final),
        ]

        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        ruta_err_ffmpeg = TEMP_DIR / "ffmpeg_render_error.log"
        f_err = open(ruta_err_ffmpeg, "w", encoding="utf-8", errors="replace")
        proceso_ffmpeg = subprocess.Popen(
            cmd_ffmpeg,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=f_err,
            creationflags=WIN_NO_WINDOW,
            startupinfo=WIN_STARTUPINFO,
        )

        ultimo_frame_lienzo: Optional[np.ndarray] = None
        frame_portada_candidato: Optional[np.ndarray] = None
        prioridad_portada: int = 0

        try:
            # 5. Renderizar segmento por segmento con seguimiento de objetivos (Optical Flow) y subtítulos luminosos
            for idx_seg, (seg, total_frames_seg, dur_seg_exacta, palabras_sub, rms_env) in enumerate(datos_segmentos):
                if cancelar_check and cancelar_check():
                    try:
                        if proceso_ffmpeg and proceso_ffmpeg.stdin:
                            proceso_ffmpeg.stdin.close()
                        proceso_ffmpeg.terminate()
                        f_err.close()
                    except Exception:
                        pass
                    if ruta_mp4_final.exists():
                        try:
                            ruta_mp4_final.unlink()
                        except Exception:
                            pass
                    raise InterruptedError("Edición cancelada por el usuario.")
                _notificar_prog(
                    0.40 + 0.58 * (idx_seg / float(max(1, len(datos_segmentos)))),
                    f"Render 60 FPS: Segmento {idx_seg + 1}/{len(datos_segmentos)} (Subtítulos Neón + Tracking)...",
                )
                t_vid_ini = float(seg.t_inicio_video or 0.0)
                t_vid_fin = float(seg.t_fin_video or dur_video_origen)

                frames_seg_rgb = extraer_frames_segmento_video(
                    ruta_video=ruta_video,
                    t_ini=t_vid_ini,
                    t_fin=t_vid_fin,
                    total_frames_salida=total_frames_seg,
                    modo_encuadre=config.modo_encuadre,
                    x_left_global_1920=x_left_global_1920,
                )

                # Calcular trayectorias rastreadas por visión artificial para FLECHA y CIRCULO
                mismo_objetivo = bool(
                    seg.flecha and seg.circulo and (_quitar_acentos(seg.flecha) == _quitar_acentos(seg.circulo))
                )

                idx_ancla_global = max(0, int(round(t_vid_ini * FPS)))
                x_ancla_seg = int(x_left_global_1920[min(idx_ancla_global, len(x_left_global_1920) - 1)]) if (x_left_global_1920 is not None and len(x_left_global_1920) > 0) else 0

                trayectoria_flecha: Optional[List[Tuple[float, float]]] = None
                trayectoria_circulo: Optional[List[Tuple[float, float]]] = None

                if seg.circulo:
                    trayectoria_circulo = RastreadorObjetivosVideo.calcular_trayectoria(
                        frames_seg_rgb,
                        seg.circulo,
                        t_inicio_seg=t_vid_ini,
                        t_fin_seg=t_vid_fin,
                        x_left_en_frame_ancla=x_ancla_seg,
                        w_escalado_1920=w_escalado_1920,
                    )
                if seg.flecha:
                    if mismo_objetivo and trayectoria_circulo is not None:
                        trayectoria_flecha = trayectoria_circulo
                    else:
                        trayectoria_flecha = RastreadorObjetivosVideo.calcular_trayectoria(
                            frames_seg_rgb,
                            seg.flecha,
                            t_inicio_seg=t_vid_ini,
                            t_fin_seg=t_vid_fin,
                        )

                # Calcular segundo relativo exacto para la aparición del círculo/flecha según t_ancla
                t_ini_callout_circulo = 0.04
                if seg.circulo:
                    from .config import parsear_directiva_circulo
                    info_c = parsear_directiva_circulo(seg.circulo, t_vid_ini, t_vid_fin)
                    if info_c.activo and info_c.t_ancla is not None:
                        t_ancla_rel = max(0.0, float(info_c.t_ancla) - t_vid_ini)
                        t_ini_callout_circulo = max(0.04, min(dur_seg_exacta - 0.4, t_ancla_rel - 0.12))

                t_ini_callout_flecha = t_ini_callout_circulo if mismo_objetivo else 0.04

                print(
                    f"    -> Renderizando segmento {idx_seg + 1}/{len(datos_segmentos)} "
                    f"({total_frames_seg} frames | video {t_vid_ini:.1f}s..{t_vid_fin:.1f}s | callout desde {t_ini_callout_circulo:.2f}s)..."
                )

                for f_idx in range(total_frames_seg):
                    t_seg = f_idx / float(FPS)
                    rms_val = float(rms_env[f_idx]) if f_idx < len(rms_env) else 0.0
                    frame_rgb = frames_seg_rgb[f_idx]

                    if f_idx % max(1, FPS // 2) == 0:
                        frac_seg = (idx_seg + (f_idx / float(total_frames_seg))) / float(max(1, len(datos_segmentos)))
                        _notificar_prog(
                            0.40 + 0.54 * frac_seg,
                            f"Render 60 FPS: Segmento {idx_seg + 1}/{len(datos_segmentos)} (Subtítulos Neón + Tracking)...",
                        )

                    pt_c_vid = trayectoria_circulo[f_idx] if (trayectoria_circulo and t_seg >= t_ini_callout_circulo) else (WIDTH / 2.0, HEIGHT * 0.44)
                    pt_f_vid = trayectoria_flecha[f_idx] if (trayectoria_flecha and t_seg >= t_ini_callout_flecha) else pt_c_vid
                    foco_camara = pt_c_vid if (trayectoria_circulo and t_seg >= t_ini_callout_circulo) else (pt_f_vid if (trayectoria_flecha and t_seg >= t_ini_callout_flecha) else (WIDTH / 2.0, HEIGHT * 0.46))

                    lienzo, pts_pantalla = gestor_assets.aplicar_efecto_camara_y_transformar_puntos(
                        frame_rgb=frame_rgb,
                        efecto=seg.efecto_visual,
                        t_seg=t_seg,
                        dur_seg=dur_seg_exacta,
                        foco_video=foco_camara,
                        puntos_rastreados=[pt_c_vid, pt_f_vid],
                    )
                    pt_c_screen, pt_f_screen = pts_pantalla[0], pts_pantalla[1]

                    # 1) Círculo Rojo siguiendo al objetivo (solo activo desde su tiempo ancla)
                    radio_circulo = gestor_assets.dibujar_circulo_rojo(
                        lienzo=lienzo,
                        activo=bool(seg.circulo),
                        target_xy=pt_c_screen,
                        tamano_mod=seg.tamano_circulo,
                        t_seg=t_seg,
                        dur_seg=dur_seg_exacta,
                        t_inicio_callout=t_ini_callout_circulo,
                    )

                    # 2) Flecha Roja siguiendo al objetivo (con soporte de rotación personalizada @deg)
                    radio_para_flecha = radio_circulo if mismo_objetivo else 0.0
                    ang_flecha = None
                    if seg.flecha:
                        m_ang = re.search(r"@(\d+(?:\.\d+)?)", str(seg.flecha))
                        if m_ang:
                            try:
                                ang_flecha = float(m_ang.group(1))
                            except Exception:
                                pass

                    gestor_assets.dibujar_flecha_roja(
                        lienzo=lienzo,
                        activo=bool(seg.flecha),
                        target_xy=pt_f_screen,
                        radio_circulo_activo=radio_para_flecha,
                        t_seg=t_seg,
                        dur_seg=dur_seg_exacta,
                        t_inicio_callout=t_ini_callout_flecha,
                        angulo_forzado=ang_flecha,
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
                    y_centro_seg = getattr(seg, "y_subtitulos", 1340) or 1340
                    renderizar_subtitulos_luminosos(
                        lienzo=lienzo,
                        palabras=palabras_sub,
                        t_actual=t_seg,
                        nivel_voz_rms=rms_val,
                        y_centro=y_centro_seg,
                        palabras_verdes_extra=config.palabras_verdes_extra,
                        palabras_rojas_extra=config.palabras_rojas_extra,
                        palabras_cian_extra=config.palabras_cian_extra,
                    )

                    if proceso_ffmpeg.poll() is not None:
                        try:
                            if proceso_ffmpeg.stdin:
                                proceso_ffmpeg.stdin.close()
                        except Exception:
                            pass
                        proceso_ffmpeg.terminate()
                        f_err.flush()
                        f_err.close()
                        err_txt = ""
                        try:
                            err_txt = ruta_err_ffmpeg.read_text(encoding="utf-8", errors="replace").strip()
                        except Exception:
                            pass
                        raise RuntimeError(
                            f"FFmpeg se cerró antes de tiempo con código {proceso_ffmpeg.returncode}.\n"
                            f"Detalles:\n{err_txt}"
                        )

                    # Captura de portada de máximo impacto (prioriza clímax con círculo o flecha)
                    if seg.circulo and f_idx == total_frames_seg // 2:
                        frame_portada_candidato = lienzo.copy()
                        prioridad_portada = 3
                    elif seg.flecha and f_idx == total_frames_seg // 2 and prioridad_portada < 2:
                        frame_portada_candidato = lienzo.copy()
                        prioridad_portada = 2
                    elif prioridad_portada < 1 and idx_seg == max(1, len(datos_segmentos) // 3) and f_idx == total_frames_seg // 2:
                        frame_portada_candidato = lienzo.copy()
                        prioridad_portada = 1

                    if idx_seg == len(datos_segmentos) - 1 and f_idx == total_frames_seg - 1:
                        ultimo_frame_lienzo = lienzo.copy()

                    if proceso_ffmpeg.stdin:
                        try:
                            if isinstance(lienzo, np.ndarray):
                                frame_salida = realzar_frame_viral(lienzo)
                                proceso_ffmpeg.stdin.write(memoryview(frame_salida))
                            else:
                                proceso_ffmpeg.stdin.write(lienzo.convert("RGB").tobytes())
                        except OSError as e:
                            try:
                                proceso_ffmpeg.stdin.close()
                            except Exception:
                                pass
                            proceso_ffmpeg.terminate()
                            f_err.flush()
                            f_err.close()
                            err_txt = ""
                            try:
                                err_txt = ruta_err_ffmpeg.read_text(encoding="utf-8", errors="replace").strip()
                            except Exception:
                                pass
                            raise RuntimeError(
                                f"Error al enviar frame a FFmpeg ({e}).\nDetalles del encoder:\n{err_txt}"
                            ) from e

            # 6. Renderizar Outro automático de 0.7 segundos (Freeze-Frame + Desenfoque + Flecha al Like + Subtítulo Luminoso)
            if ultimo_frame_lienzo is not None and total_frames_outro > 0:
                _notificar_prog(0.97, "Renderizando outro dinámico (campana de like y flecha animada a 60 FPS)...")
                print("[*] Renderizando Outro final (Freeze-frame + desenfoque + flecha al Like)...")
                if isinstance(ultimo_frame_lienzo, np.ndarray):
                    bg_blur = cv2.GaussianBlur(ultimo_frame_lienzo, (31, 31), 16)
                    lienzo_base_outro = cv2.multiply(bg_blur, 0.65).astype(np.uint8)
                else:
                    bg_blur = ultimo_frame_lienzo.filter(ImageFilter.GaussianBlur(16))
                    oscurecedor = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 95))
                    lienzo_base_outro = Image.alpha_composite(bg_blur.convert("RGBA"), oscurecedor)

                for f_idx in range(total_frames_outro):
                    t_seg = f_idx / float(FPS)
                    rms_val = float(rms_env_outro[f_idx]) if f_idx < len(rms_env_outro) else 0.0
                    lienzo_out = lienzo_base_outro.copy()

                    if f_idx % max(1, FPS // 2) == 0:
                        _notificar_prog(0.95, "Renderizando outro final con flecha a 60 FPS...")

                    # Flecha Roja al botón de Like de YouTube Shorts (X: 985, Y: 1040)
                    gestor_assets.dibujar_flecha_outro_like(
                        lienzo=lienzo_out,
                        t_seg=t_seg,
                        dur_seg=dur_outro_seg,
                    )

                    # Subtítulo neón animado
                    renderizar_subtitulos_luminosos(
                        lienzo=lienzo_out,
                        palabras=palabras_sub_outro,
                        t_actual=t_seg,
                        nivel_voz_rms=rms_val,
                        y_centro=1340,
                        palabras_verdes_extra={"LIKE!", "LIKE"},
                    )

                    if proceso_ffmpeg.poll() is not None:
                        try:
                            if proceso_ffmpeg.stdin:
                                proceso_ffmpeg.stdin.close()
                        except Exception:
                            pass
                        proceso_ffmpeg.terminate()
                        f_err.flush()
                        f_err.close()
                        err_txt = ""
                        try:
                            err_txt = ruta_err_ffmpeg.read_text(encoding="utf-8", errors="replace").strip()
                        except Exception:
                            pass
                        raise RuntimeError(
                            f"FFmpeg se cerró antes de tiempo durante el outro con código {proceso_ffmpeg.returncode}.\n"
                            f"Detalles:\n{err_txt}"
                        )

                    if proceso_ffmpeg.stdin:
                        try:
                            if isinstance(lienzo_out, np.ndarray):
                                frame_out_salida = realzar_frame_viral(lienzo_out)
                                proceso_ffmpeg.stdin.write(memoryview(frame_out_salida))
                            else:
                                proceso_ffmpeg.stdin.write(lienzo_out.convert("RGB").tobytes())
                        except OSError as e:
                            try:
                                proceso_ffmpeg.stdin.close()
                            except Exception:
                                pass
                            proceso_ffmpeg.terminate()
                            f_err.flush()
                            f_err.close()
                            err_txt = ""
                            try:
                                err_txt = ruta_err_ffmpeg.read_text(encoding="utf-8", errors="replace").strip()
                            except Exception:
                                pass
                            raise RuntimeError(f"Error al enviar frame de outro a FFmpeg ({e}).\nDetalles:\n{err_txt}") from e

            if proceso_ffmpeg.stdin:
                try:
                    proceso_ffmpeg.stdin.close()
                except Exception:
                    pass
            proceso_ffmpeg.wait()
            f_err.flush()
            f_err.close()

            if proceso_ffmpeg.returncode != 0:
                err_txt = ""
                try:
                    err_txt = ruta_err_ffmpeg.read_text(encoding="utf-8", errors="replace").strip()
                except Exception:
                    pass
                raise RuntimeError(f"FFmpeg finalizó con código {proceso_ffmpeg.returncode}.\nDetalles:\n{err_txt}")

            # Guardar fotograma clave de portada viral de alto CTR
            ruta_portada = OUTPUT_DIR / f"portada_{ruta_mp4_final.stem}.jpg"
            portada_guardada = False
            try:
                selector_portada = SelectorPortadaViral(num_candidatos=14)
                ok_p, info_p = selector_portada.extraer_mejor_portada(str(ruta_mp4_final), str(ruta_portada))
                if ok_p:
                    portada_guardada = True
                    print(f"[+] Portada viral de alto CTR seleccionada y guardada: {ruta_portada.name} (Score: {info_p.get('score_total')})")
            except Exception as e_pv:
                print(f"[!] Selector de portada heurístico: {e_pv}")

            if not portada_guardada and frame_portada_candidato is not None:
                try:
                    if isinstance(frame_portada_candidato, np.ndarray):
                        Image.fromarray(frame_portada_candidato).save(str(ruta_portada), "JPEG", quality=95)
                    else:
                        frame_portada_candidato.convert("RGB").save(str(ruta_portada), "JPEG", quality=95)
                    print(f"[+] Fotograma clave de portada guardado (fallback): {ruta_portada.name}")
                except Exception as e_portada:
                    print(f"[!] No se pudo guardar fotograma de portada: {e_portada}")

            return ruta_mp4_final
        finally:
            try:
                if not f_err.closed:
                    f_err.close()
            except Exception:
                pass

    try:
        resultado = _ejecutar_render(encoder, args_codec)
    except Exception as e:
        if isinstance(e, InterruptedError):
            raise
        if encoder != "libx264":
            print(f"[!] Falló la GPU ({encoder}): {e}")
            print("[*] Reintentando renderizado automáticamente con Procesador CPU equilibrado (libx264 fast CRF 18)...")
            _notificar_prog(0.40, "GPU sin memoria suficiente. Reintentando por CPU equilibrada...")
            if ruta_mp4_final.exists():
                try:
                    ruta_mp4_final.unlink()
                except Exception:
                    pass
            enc_cpu, args_cpu = detectar_encoder_video(forzar_cpu=True)
            resultado = _ejecutar_render(enc_cpu, args_cpu)
        else:
            raise

    _notificar_prog(1.0, "Renderizado 60 FPS completado con éxito.")
    print("=" * 78)
    print(f"[ÉXITO] Short generado y listo en: {resultado}")
    print("=" * 78)
    return resultado


