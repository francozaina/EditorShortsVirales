# ⚡ Editor Shorts Studio v1.0

Aplicación de escritorio y motor automatizado de edición de **YouTube Shorts** con:
- **Descarga directa desde YouTube (`yt-dlp`)** o carga de archivos `.mp4` locales.
- **Narración con Voz Neuronal IA** (`Edge-TTS` expresivo con prosodia de YouTuber o `ElevenLabs` opcional) + masterización de estudio con `FFmpeg`.
- **Subtítulos Dinámicos Luminosos**: Resplandor neón multicapa (*Gaussian Neon Aura* + *Inner Halo* + brillo especular superior + pulso reactivo al volumen de la voz) con colores automáticos de alto impacto (Amarillo Ciber, Verde Esmeralda, Rojo Carmesí y Cian Eléctrico).
- **Seguimiento Inteligente de Objetivos (*Optical Flow + Saliencia*)**: Las **Flechas Rojas** (`fotos/flecha.png`) y **Círculos Rojos** (`fotos/circulo_rojo.png`) detectan y persiguen suavemente a los objetos en movimiento dentro de la zona indicada, manteniéndose sincronizados incluso durante zooms o sacudidas de cámara.
- **19 Efectos de Sonido (`sfx/`) y 7 Emojis Animados (`emojis/`)** sincronizados automáticamente.

---

## 🚀 Cómo Iniciar la App

Haz doble clic en **`Iniciar_Editor.bat`** o ejecuta por consola:

```powershell
python "Editor_Shorts_Studio.py"
```

También puedes usarla por línea de comandos pasándole un archivo o link de YouTube y un guion:

```powershell
python "Editor_Shorts_Studio.py" "video_input.mp4" "guion_video.txt"
```

---

## 📝 Formato del Guion (`guion_video.txt`)

Cada línea de `[GUION]` tiene **7 columnas** separadas por `|`:

```text
TIEMPO | EFECTO | SFX | EMOJI | FLECHA | CIRCULO | TEXTO
```

### Ejemplo Completo:
```text
TITULO_SUPERIOR:
MODO_ENCUADRE: full
VOLUMEN_VIDEO_ORIGINAL: 0
ARCHIVO_SALIDA: auto

[GUION]
TIEMPO | EFECTO | SFX | EMOJI | FLECHA | CIRCULO | TEXTO
00:00 - 00:05 | zoom_impacto | crowd_shocked | sorprendido:derecha | izquierda | izquierda | ¡El noventa y nueve por ciento no cree cómo será la pizza en el año dos mil cincuenta! ¡En el dos mil traía muchísimo queso!
00:05 - 00:10 | zoom_in | whoosh+xp_Error | enojo:izquierda | centro | ninguno | ¡En el dos mil veintiséis ya le ponen muy poco queso y se corta enseguida!
00:10 - 00:14 | alerta_roja | riser_suction | diablo:derecha | centro | centro:grande | ¡Pero mira la estafa increíble que nos van a vender en el dos mil cincuenta!
00:14 - 00:19 | brillo_epico | cash_ting+party_horn | fiesta:izquierda | izquierda | ninguno | ¡Es pura salsa sin nada de queso! ¡Una verdadera estafa!
```

---

## 🎨 Guía Rápida de Columnas y Assets

1. **`TIEMPO`**:
   - Rango en el video base `MM:SS - MM:SS` (ej. `00:00 - 00:05`) o `auto` para reparto proporcional automático.
2. **`EFECTO`** (Efecto visual de cámara y atmósfera):
   - `zoom_impacto`, `zoom_in`, `zoom_out`, `flash`, `temblor`, `alerta_roja`, `brillo_epico`, `blanco_negro`, `ninguno`.
3. **`SFX`** (Archivos en `sfx/`, puedes combinar dos con `+`, ej. `whoosh+ding`):
   - `awww`, `boxing_bell`, `camera_flash`, `camera_shooter`, `cartoon_laugh`, `cash_ting`, `click`, `crowd_shocked`, `ding`, `error`, `fart`, `good_idea`, `kids_yeyy`, `party_horn`, `pop`, `punch`, `riser_suction`, `whoosh`, `xp_Error`, `ninguno`.
4. **`EMOJI`** (Archivos en `emojis/`, opcional `:derecha` o `:izquierda`):
   - `diablo`, `enojo`, `fiesta`, `lloro`, `risa`, `sorprendido`, `sueno`, `ninguno`.
5. **`FLECHA`** (`fotos/flecha.png` con seguimiento del objetivo):
   - `centro`, `izquierda`, `derecha`, `arriba`, `abajo`, `auto` (persigue el objeto con más movimiento), `X,Y` (0-100%), `X1,Y1->X2,Y2` o `ninguna`.
6. **`CIRCULO`** (`fotos/circulo_rojo.png` con seguimiento del objetivo):
   - `centro`, `izquierda`, `derecha`, `arriba`, `abajo`, `auto`, `X,Y`, `si` (mismo objetivo que la flecha) o `ninguno`. Opcional modificador de tamaño `:chico`, `:medio`, `:grande`.
7. **`TEXTO`**:
   - Frase que narrará la voz IA y se mostrará en subtítulos luminosos palabra por palabra.

---

## 🤖 Generar Guiones con IA

Dentro de la interfaz gráfica tienes el botón **"🤖 Copiar Prompt para IA"** (o puedes abrir el archivo `PROMPT_PARA_IA_GUIONES.txt`), listo para pegar en ChatGPT, Claude o Gemini.
