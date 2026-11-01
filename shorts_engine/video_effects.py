"""
Módulo de efectos y grading de color para video por canal (anti content-ID y personalidad visual).
"""
import cv2
import numpy as np


def realzar_frame_viral(frame_rgb: np.ndarray, modo_color: str = "Vibrante Estándar") -> np.ndarray:
    """Realza contraste y saturación con huella visual diferenciada por canal."""
    try:
        if modo_color == "Cálido Intenso":
            alpha_c, beta_c, sat_m = 1.08, 4, 1.18
        elif modo_color == "Frío Cinematográfico":
            alpha_c, beta_c, sat_m = 1.09, -2, 1.08
        elif modo_color == "Alto Contraste Punch":
            alpha_c, beta_c, sat_m = 1.12, 2, 1.15
        else:
            alpha_c, beta_c, sat_m = 1.06, 2, 1.12

        out = cv2.convertScaleAbs(frame_rgb, alpha=alpha_c, beta=beta_c)
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
        return frame_rgb
