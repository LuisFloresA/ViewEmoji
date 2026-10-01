# GESTOS · SONIDOS · REACCIONES

Tabla de referencia del MVP. Los terminos de busqueda sirven para descargar
sonidos CC0 de Pixabay / Freesound / Mixkit y depositarlos en `assets/sounds/`.
Si el archivo no existe, la app usa el tono sintetizado de
`assets/sounds_fallback/` (ver `scripts/generate_fallback_sounds.py`).

| # | Gesto / Estado | Deteccion | Reaccion del avatar | Sonido | Termino busqueda (CC0) | Fallback |
|---|---|---|---|---|---|---|
| 1 | **Boca abierta** | Apertura `0.55-0.70` | Sorpresa (ojos abiertos) | `mouth_open` | `surprise wow`, `cartoon gasp` | `gasp` |
| 2 | **Pulgares arriba** | Pulgar arriba, resto cerrado | Sonrisa + aprobacion | `thumbs_up` | `success`, `yay`, `applause short` | `yay` |
| 3 | **Guiño (wink)** | Un ojo mucho mas cerrado que el otro | Guino comico | `wink` | `boing`, `cartoon pop`, `meme wink` | `pop` |
| 4 | **Cabeza inclinada** | Roll de la cara > 15 grados | Mirada curiosa | `head_tilt` | `curious`, `hmm cartoon` | `hum` |
| 5 | **Fruncir cenio** | Cejas juntas | Expresion seria | `frown` | `grumpy`, `ugh cartoon` | `buzz` |
| 6 | **Sonrisa amplia** | Esquinas de boca suben | Feliz, brilla | `big_smile` | `cheer`, `happy short` | `chime_up` |
| 7 | **Levantar cejas** | Cejas suben | Alerta / "hmm" | `eyebrows_up` | `ooh`, `cartoon surprise` | `ooh` |
| 8 | **Asentir (nod)** | Oscilacion vertical de la cara | Afirmativo | `nod` | `yes`, `okay cartoon` | `nod` |
| 9 | **Negar (shake)** | Oscilacion horizontal amplia | Negativo divertido | `shake` | `no`, `nah cartoon` | `womp` |
| 10 | **Puño cerrado** | 0-1 dedos extendidos | Energia | `fist` | `power`, `punch whoosh` | `whoosh` |
| 11 | **Palma abierta** | 4 dedos + pulgar separados | Parada / "alto" | `open_palm` | `stop`, `whoa cartoon` | `whoa` |
| 12 | **Sena V** | Indice + corazon arriba | Celebracion | `victory` | `win`, `victory cheer` | `fanfare` |
| 13 | **Boca muy abierta** | Apertura `> 0.85` | Meme clasico (shock) | `shock` | `mind blown`, `explosion cartoon` | `boom` |
| 14 | **Lengua fuera** | Apertura `0.70-0.85` sin sonrisa | Broma (el "aaah") | `tongue_out` | `silly`, `bleh cartoon` | `bleh` |
| 15 | **Sacudir cabeza rapido** | Cambios de lado sostenidos | Confusion / meme | `head_shake_fast` | `bruh`, `what cartoon` | `womp_womp` |
| 16 | **Manos levantadas** | 2 manos detectadas | Fiesta | `hands_up` | `yeah`, `party pop` | `pop` |

## Como se resuelve un choque de gestos

Si en un mismo frame se detectan varios gestos, **solo gana el de mayor
`priority`** (columna del `config/gestures.yaml`). Los de mayor prioridad:

`shock` 90 > `hands_up` 80 > `victory` 75 > `head_shake_fast` 70 >
`thumbs_up` 65 > `wink` 60 = `fist` 60 = `open_palm` 60 > `nod` 55 =
`shake` 55 > `frown` 50 > `big_smile` 45 = `tongue_out` 45 >
`mouth_open` 40 > `head_tilt` 35 > `eyebrows_up` 30

Por eso una sonrisa con las cejas arriba sale como `big_smile` y no como
sorpresa, y una boca muy abierta con cejas arriba sale como `shock`.

Si además ya hay una expresión de **igual o mayor** prioridad en curso, el
nuevo gesto se descarta entero: **la cara no cambia y el sonido tampoco
suena**, para que lo que ves y lo que oyes sean siempre lo mismo.

Las tres bandas de boca son **excluyentes** a proposito, para que una sola
postura no dispare tres sonidos: abrir un poco es sorpresa, abrir mucho sin
sonreir es el "aaah" tonto, y abrir muchísimo es shock.

## Expresiones disponibles (avatar)

`neutral` · `happy` · `excited` · `surprise` · `shock` · `alert` · `wink` ·
`curious` · `grumpy` · `confused` · `silly` · `stop` · `affirm` · `deny` ·
`powered` · `celebrate` · `ponder` · `bored` · `sleepy` · `dizzy` · `talk`

Las de reposo (`ponder`, `bored`, `sleepy`, `dizzy`, `talk`) las usa sobre
todo el modo idle, cuando no hay nadie delante.

## Descargar sonidos CC0

1. Ve a <https://pixabay.com/es/sound-effects/> o <https://mixkit.co/free-sound-effects/>
2. Busca con el termino indicado, filtra licencia CC0 / dominio publico.
3. Descarga y renombra segun la columna "Sonido" de la tabla.
4. Guarda en `assets/sounds/` (formatos aceptados: `.ogg`, `.wav`, `.mp3`).

El motor prueba primero `assets/sounds/` y si no encuentra el archivo cae
automaticamente al tono sintetizado de `assets/sounds_fallback/`.

## Ajustar deteccion

Los gestos son de **disparo por flanco**: suenan una vez cuando adoptas la
postura y **no se repiten mientras te la quedas**. Se rearman tras
`rearm_frames` frames sin la postura, para que puedas repetirlos a voluntad.

Los umbrales viven en `config/config.yaml` (seccion `gestures`):
`cooldown_ms` (minimo entre repeticiones), `min_hold_frames` (frames de
postura mantenida antes de disparar), `rearm_frames` (frames en los que NO hay
postura para poder repetir), `head_tilt_threshold_deg`, `head_nod_min_count`,
`head_shake_min_count` y `head_shake_min_interval_s` (segundos minimos entre
cambios de lado para que cuente como sacudida rapida).

## Tamano de la cara

`avatar.size_ratio` es el porcentaje de la ALTURA de la pantalla que ocupa la
cara, no un numero de pixeles. Asi se ve igual de bien en un portatil de 720p
que en el AIO a pantalla completa.

| `size_ratio` | 720p | 1080p |
|---|---|---|
| `0.60` | 290 px | 434 px |
| `0.70` (por defecto) | 338 px | 507 px |
| `0.85` | 411 px | 617 px |

Si prefieres un tamaño fijo, rellena `avatar.size` en pixeles y descarta
`size_ratio`.

## Seguimiento de la mirada

El avatar combina tres señales en `avatar.set_face_target`:

- **Posicion de la cara** (peso `gaze_w_pos`, 0.75 por defecto): tu avatar
  te sigue aunque estés muy quieto.
- **Direccion real de la mirada**: el desplazamiento del iris respecto al
  centro de cada ojo. Sirve para el detalle fino (mirar de reojo) sin
  depender de los parpadeos ni de la distancia a la camara.
- **Velocidad** (`gaze_w_vel`): el avatar "persigue" un movimiento rapido en
  vez de quedarse por detras.

MediaPipe no da un "mirar al frente" absoluto: depende de la persona, de la
camara y del encuadre, y de hecho varia bastante (en una prueba real el
centro estava en `0.68` en horizontal y `-0.57` en vertical, no en `0.5`).
Por eso la app **aprende sola tu postura neutra** (`gaze.base_k`), y solo
dentro de una zona muerta (`gaze.deadzone`): si te quedas mirando fijamente a
un lado, eso no se aprende como si fuera mirar al frente.

Para medirlo sin la ventana a pantalla completa:

```
python scripts/gaze_probe.py 20
```

Imprime la distribucion de la mirada. Lo que quieres es una **mediana cerca de
0** (sin tiron a un lado) y un **recorrido amplio** (que use el rango). Si la
mediana se va a `+/-1`, sube `gaze.gain_x` / `gaze.gain_y`.

## Acciones idle

Cuando no hay nadie delante (o nadie se mueve), el avatar no se congela:
elige al azar entre una lista de acciones con su propia expresion, duracion y
movimiento de pupilas. Entre dos acciones espera un intervalo al azar.

- Si quieres menos vida propia: sube `avatar.idle_min_gap` e `idle_max_gap`.
- Si no quieres ninguna: `avatar.idle_enabled: false`.
- La lista esta en `IDLE_ACTIONS` en `src/avatar.py`.

Consejo para calibrar: pon `debug.show_landmarks: true` y mira las metricas
que salen en pantalla (mirada, apertura de boca, inclinacion, sonrisa). Sube
`min_hold_frames` a 5-8 si hay falsos positivos por ruido; bajalo a 2 si
responde lento.

Ajusta en el AIO con las teclas:

- `D` · vista previa de la camara
- `S` · mostrar landmarks y metricas
- `ESC` / `Q` · salir
