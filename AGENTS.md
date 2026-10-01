# AGENTS.md

Contexto completo del proyecto **ProjectViewEmoji / Avatar Interactivo**:
qué se pidió, qué se decidió y por qué, cómo está montado y cómo verificar
cualquier cambio. Está pensado para que otro agente (o persona) pueda
retomar el trabajo sin tener que reconstruir la historia.

- **Raíz:** `C:\Users\Luisp\Documents\Luis\ProjectViewEmoji`
- **Plataforma objetivo:** Windows 11 en el AIO del laboratorio
- **Idioma del código y la documentación:** español
- **Estado:** funcional y verificado con cámara real; publicado en
  `github.com/LuisFloresA/ViewEmoji`

---

## 1. Qué es

Avatar 2D que reacciona a la cara y a las manos de quien pasa por el
laboratorio. Se dibuja a pantalla completa en el **segundo monitor**, sigue a
la persona con una **cámara USB** y responde a gestos con **expresiones y
sonidos**. Cuando no hay nadie, el avatar hace cosas por su cuenta.

Procesamiento **local y en vivo**: no se graba ni se guarda imagen, audio ni
vídeo. Las fotos de diagnóstico se escriben solo cuando se pide explícitamente
(`S` para landmarks) y se quedan en `out/`, que está en `.gitignore`.

```
cámara USB  ──►  MediaPipe Tasks API  ──►  métricas de cara/manos
                                                  │
                                    GestureEngine (bandas + prioridades)
                                                  │
                          ┌───────────────────────┴──────────────────┐
                          │                                          │
                  Avatar 2D (pygame)                        SoundEngine
                  pantalla secundaria                  assets/sounds (CC0)
                                                       └─► fallback sintetizado
```

---

## 2. Solicitudes y cómo se resolvieron

### 2.1 Peticiones originales

| # | Solicitud | Estado |
|---|---|---|
| 1 | Avatar en el AIO, fullscreen en el **segundo monitor** | Hecho |
| 2 | Reaccionar a la **cámara USB** (nunca a la integrada) | Hecho |
| 3 | **Tabla de gestos + sonidos + términos de búsqueda CC0** | Hecho |
| 4 | Gestos que suenen **una vez** y no en bucle | Hecho |
| 5 | **Nada de Portainer**; nativo en Windows | Hecho |
| 6 | Sin grabación de imagen/audio | Hecho |
| 7 | Actualización por **Git** sin orquestador de contenedores | Hecho |
| 8 | Publicar en **GitHub** | Hecho (`LuisFloresA/ViewEmoji`) |
| 9 | Que arranque solo en **otra máquina** | Hecho (`install.bat` / `bootstrap.py`) |

### 2.2 Las cuatro peticiones de la última tanda

**a) Agrandar la cara.** Antes `avatar.size` era un número absoluto de píxeles,
así que se veía pequeña en pantallas grandes. Ahora `avatar.size_ratio` es un
**porcentaje de la altura de la pantalla**:

| `size_ratio` | 720p | 1080p |
|---|---|---|
| `0.60` | 290 px | 435 px |
| `0.70` (por defecto) | 338 px | 507 px |
| `0.85` | 411 px | 617 px |

> Decisión: porcentaje en vez de píxeles. El objetivo es el AIO a pantalla
> completa, pero la app también se prueba en un portátil de 720p; con una
> sola variable se ve igual de bien en ambos. Si se prefiere fijo,
> `avatar.size` en píxeles tiene prioridad sobre `size_ratio`.

**b) Arreglar el mapeo gesto→expresión.** Tres defectos reales:

1. **Bandas de boca solapadas.** `shock` (>0.85) y `mouth_open` (>0.55) se
   disparaban a la vez, y `tongue_out` (0.45-0.85) robaba los disparos de
   ambos. Una sola postura sonaba hasta tres veces.
   → Ahora son **excluyentes**:
   - `0.55 < apertura ≤ 0.70` → `mouth_open` (sorpresa)
   - `0.70 < apertura ≤ 0.85` y `sin sonrisa` → `tongue_out` (el "aaah" tonto)
   - `> 0.85` → `shock`

   El criterio de "sin sonrisa" es lo que da sentido a `tongue_out`: abrir
   mucho es un "aaah" de broma; abrir mucho **sonriendo** es `big_smile`, que
   tiene prioridad 45 y gana.

2. **Sonido sin imagen.** `main.py` reproducía el sonido siempre, incluso si
   `avatar.set_expression()` devolvía `False` por prioridad. Resultado: se
   oía un sonido cuya cara nunca se veía.
   → `main.py` ahora solo llama a `sound.play()` si la expresión se aplicó.
   Si la cara no cambia, el sonido no suena. Lo que ves y lo que oyes
   coinciden siempre.

3. **`wink` y `shake` no existían como detección.** Estaban en
   `config/gestures.yaml` (y por tanto en la tabla y en los sonidos) pero
   **no había código que los disparara**. El test antiguo solo comprobaba los
   12 que sí tenían detector, así que el hueco pasaba desapercibido.
   → Implementados:
   - `wink`: asetría de apertura ocular (EAR por ojo). Un parpadeo cierra los
     dos ojos; un guiño cierra uno, así que la asimetría es lo que lo
     distingue. Se exige además que el ojo cerrado no esté del todo cerrado.
   - `shake`: oscilación horizontal amplia de `face_x`, con mínimo de
     recorrido para no confundirlo con mover la cabeza de sitio a sitio.
   - **Guarda anti-regresión:** el test ahora falla si algún gesto declarado en
     `gestures.yaml` no tiene detección. Un gesto nuevo ya no puede quedarse
     roto en silencio.

**c) Seguimiento de mirada.** Este era el bug más serio y **no se detectó con
tests sintéticos**, sino midiendo con la cámara real (`scripts/calibrate_gaze.py`).

El cálculo original asumía que "mirar al frente" equivale a `0.5` en el
landmark del iris. Medido con la cámara real, el centro era:

- horizontal: **0.682** (no 0.5)
- vertical: **-0.574** (y la fórmula restaba un offset fijo que no cuadraba)

Con esos valores, la salida de `gaze_probe.py` daba medianas de **-0.914** y
**-1.000**: los ojos del avatar quedaban clavados arriba a la izquierda, y con
`gaze_w_pos: 0.62` (38 % de peso) ese error dominaba la señal.

Dos arreglos:

1. **Referencia con signo inequívoco.** Se mide el desplazamiento del iris
   respecto al **centro** de la abertura de cada ojo, no respecto a una esquina,
   y se normaliza con el ancho del ojo para no depender de la distancia a la
   cámara.
2. **Línea base adaptativa por persona.** MediaPipe no da un "mirar al frente"
   absoluto: depende de la persona, la cámara y el encuadre. La app aprende la
   postura neutra sola, **solo dentro de una zona muerta** (`gaze.deadzone`).
   Sin zona muerta, mirar fijamente a un lado acabaría aprendiéndose como
   neutra y el avatar volvería al centro.

Resultado medido tras el arreglo:

| | antes | después |
|---|---|---|
| `gaze_x` mediana | -0.914 | **-0.004** |
| `gaze_y` mediana | -1.000 | **-0.018** |
| `gaze_x` recorrido | 0.355 | **1.007** |
| `gaze_y` recorrido | 0.436 | **0.966** |

Mediana centrada = sin tirón; recorrido ~1.0 = usa todo el rango.

> Decisión: subir `gaze_w_pos` de 0.62 a **0.75**. La posición de la cara es
> la señal fiable y siempre disponible; el iris es el matiz fino. Pesarlo más
> hace que el avatar te siga aunque estés muy quieto, sin depender de que la
> cámara te detecte el iris con precisión.

**d) Animaciones idle.** El avatar se quedaba congelado sin nadie. Ahora elige
al azar entre **14 acciones**, cada una con su expresión, duración y movimiento
de pupilas propios, con un intervalo aleatorio entre ellas:

`look_around` · `think` · `sway` · `dance` · `sleepy` · `dizzy` · `bored` ·
`zoom_peek` · `spooked` · `chat` · `stretch` · `head_nod_alone` ·
`look_down_up` · `bounce`

No repite las 3 últimas para que no sea predecible. Se ajusta con
`avatar.idle_enabled` e `idle_min_gap` / `idle_max_gap`.

### 2.3 Petición 9: que arranque solo en otra máquina

`scripts\install.bat` + `scripts\bootstrap.py` dejan el proyecto ejecutable
en un equipo limpio. Verificado simulando una máquina nueva en una carpeta
temporal sin `venv/` ni `models/`: creó el entorno, instaló, descargó los
modelos y arrancó.

**El arreglo de OpenCV resultó ser imprescindible, no una precaution.** Al
instalar, `mediapipe` deja la 5.x pisando `cv2` y el módulo queda **ilegible**
en este equipo; `bootstrap.py` lo detecta (`cv2 es 'desconocida'`) y lo
reinstala. Sin ese paso, la app no habría arrancado en una máquina nueva.

> Decisión: la lógica de instalación está en `bootstrap.py` y no en el `.bat`.
> En batch hay que parsear versiones y rutas de forma frágil (y `endlocal`
> destruye variables si no se usa `endlocal & exit /b %VAR%`); en Python es
> código normal y testeable. El `.bat` solo busca un intérprete y llama.

### 2.4 Petición 10: elegir la cámara en el `.bat`

En el otro equipo la cámara no cargó. Dos causas posibles, y el selector
distingue las dos: la USB tiene otro nombre, o bien otro programa la tiene
ocupada.

- `scripts\select_camera.py` lista las cámaras **por nombre sin abrirlas**,
  deja elegir una y la anota en `config/config.yaml`.
- `run.bat` ofrece el selector **solo si el arranque falla**, no siempre:
  en el AIO debe arrancar solo y sin preguntar nada.
- `main.py` lista las cámaras que ve al fallar, en vez de un escueto
  "sin camara disponible" que no dice si el problema es que no hay, si
  está ocupada o si el config apunta a la equivocada.

> Decisión: se guarda el **nombre**, no el índice. DirectShow no garantiza
> el mismo orden entre arranques ni entre equipos, así que un `device_index`
> fijo puede acabar abriendo la integrada. Con `device_name`,
> `pick_index` busca el texto en cada arranque y el índice guardado queda
> solo como reserva.

> Decisión: el selector **no** usa `yaml.safe_dump`. Ese volcado borraba 36
> líneas de los 23 comentarios de `config.yaml`, que explican los límites de
> cada valor. Se reescribe solo la línea elegida y se conserva su comentario
> (`set_yaml_key`); `smoke_test.py::test_config_rewrite` lo vigila, incluido
> que `--auto` deje el archivo byte a byte igual.

### 2.5 Arreglos adicionales no pedidos

Salieron al verificar, y se corrigieron:

- **Tabla de 16 gestos con 2 sin detección** (ver 2.2b).
- **Conflicto de OpenCV.** `mediapipe` depende de `opencv-contrib-python`
  (5.x) y el proyecto fija `opencv-python==4.10.0.84`. Las dos distribuciones
  escriben en el **mismo módulo `cv2`**, así que gana la última instalada. La
  5.x no funciona en este equipo (Smart App Control).
  → `check_env.py` detecta el conflicto y dice cómo arreglarlo. Documentado en
  `requirements.txt` y `README.md`.
- **Pin de numpy obsoleto.** `requirements.txt` afirmaba que numpy 2.x era
  incompatible con OpenCV 4.10. Verificado que es falso con numpy 2.5.3
  (pruebas de `blob`, `resize`, `flip`, `cvtColor`, `circle`, `putText`).
  → Se quitó el `numpy<2`.
- **Imagen rota en el README.** Apuntaba a `out/expr_surprise.png`, y `out/`
  está en `.gitignore`: en GitHub no se habría visto.
  → Generada `docs/img/expresiones.png` con `scripts/make_expr_sheet.py`.
- **Bucle de cámara que parpadeaba los LED.** La app abría todas las cámaras
  para buscarlas. Ahora consulta los nombres por DirectShow con `pygrabber`
  y abre solo la elegida.
- **`run.bat` que se cerraba solo.** Tenía un `|` que cerraba el bloque antes
  de tiempo y se saltaba el arranque. Corregido y con `pause` al final.

---

## 3. Decisiones de diseño y por qué

| Decisión | Motivo |
|---|---|
| Ejecución nativa, **sin Portainer** | Requisito explícito. Un orquestador de contenedores añade una capa que en un AIO de laboratorio solo genera puntos de fallo. |
| Cámara por **nombre**, no por índice | Abrir todas para buscarlas encendía los LED de todos los sensores y dejaba la USB en mal estado. `pygrabber` lista los nombres sin abrirlos. |
| Un solo gesto ganador **por frame** | Si en un mismo frame saltan varios gestos, se queda el de mayor `priority`. Así la cara nunca muestra algo incoherente. |
| Prioridad también **entre frames** | Si ya hay una expresión de igual o mayor prioridad en curso, el gesto se descarta entero (cara **y** sonido). |
| Sonidos de **fallback sintetizado** | La app debe funcionar el primer día, sin descargas. Los `.ogg`/`.wav` de CC0 son opcionales. |
| Disparo de gestos **por flanco** | Un alumno quieto con la mano levantada no genera un bucle de sonidos. Se rearma tras `rearm_frames` sin la postura. |
| Gaze **adaptativo**, no constantes | No existe un "mirar al frente" absoluto entre personas y cámaras. Aprenderse en marcha es más robusto que calibrar a mano. |
| `size_ratio` **relativo** | Ver 2.2a. |
| Idioma del proyecto: **español** | Es lo que pide el usuario y lo que lee el personal del laboratorio. Los identificadores del código van sin acentos ni `ñ` para evitar líos de codificación; los comentarios y la documentación sí los llevan. |
| Tests sin hardware en `smoke_test.py` | El CI y la validación de cambios no dependen de que haya cámara ni pantalla. |

### Tabla de gestos, expresiones y prioridades

Fuente de verdad: `config/gestures.yaml`. Orden real por prioridad:

| id | expresión | prio | id | expresión | prio |
|---|---|---|---|---|---|
| `shock` | `shock` | 90 | `nod` | `affirm` | 55 |
| `hands_up` | `celebrate` | 80 | `shake` | `deny` | 55 |
| `victory` | `excited` | 75 | `frown` | `grumpy` | 50 |
| `head_shake_fast` | `confused` | 70 | `big_smile` | `happy` | 45 |
| `thumbs_up` | `happy` | 65 | `tongue_out` | `silly` | 45 |
| `wink` | `wink` | 60 | `mouth_open` | `surprise` | 40 |
| `fist` | `powered` | 60 | `head_tilt` | `curious` | 35 |
| `open_palm` | `stop` | 60 | `eyebrows_up` | `alert` | 30 |

**21 expresiones:** `neutral` `happy` `excited` `surprise` `shock` `alert`
`wink` `curious` `grumpy` `affirm` `deny` `confused` `silly` `stop`
`powered` `celebrate` `bored` `sleepy` `dizzy` `talk` `ponder`

---

## 4. Mapa del proyecto

```
src/
  main.py        (196)  bucle: cámara -> detección -> gestos -> render + audio
  gestures.py    (491)  Detector (MediaPipe + métricas) y GestureEngine
  avatar.py      (491)  avatar 2D, EXPRESSIONS, IDLE_ACTIONS
  camera.py      (170)  selección de cámara por nombre (prioriza USB)
  audio.py        (78)  reproducción con prioridad CC0 y fallback
  config.py       (82)  carga de YAML con valores por defecto

config/
  config.yaml     (86)  cámara, pantalla, avatar, gaze, umbrales, audio
  gestures.yaml  (183)  tabla gestos -> reacción + sonido (FUENTE DE VERDAD)

scripts/
  smoke_test.py           (447)  pruebas sin hardware
  test_camera.py           (43)  pruebas de selección de cámara (no abre nada)
  select_camera.py         (~150) selector interactivo: nombre de cámara a config.yaml
  check_env.py             (99)  diagnóstico; avisa del conflicto de OpenCV
  gaze_probe.py            (93)  mide la mirada en vivo (cámara real)
  calibrate_gaze.py       (101)  compara fórmulas de gaze sobre landmarks crudos
  make_expr_sheet.py       (64)  genera docs/img/expresiones.png
  download_models.py       (62)  descarga los .task de MediaPipe
  generate_fallback_sounds.py (83)  genera los tonos de respaldo
  update_check.py         (143)  polling de Git + tarea de Windows
  bootstrap.py            (~180) venv + dependencias + arreglo de OpenCV + modelos
  install.bat                     instalador (doble clic)
  run.bat                         arranque comodo (instala si falta)

docs/
  GESTOS_SONIDOS.md   tabla, prioridades, tamaño, gaze, idle, CC0
  img/expresiones.png hoja de contactos de las 21 expresiones

assets/
  sounds/           sonidos CC0 que descarga el usuario (opcional, vacío)
  sounds_fallback/  16 tonos sintetizados
```

Entorno: Python `3.14.4` · `mediapipe==1.0.1` · `opencv-python==4.10.0.84`
· `pygame-ce==2.5.8` · `PyYAML==6.0.3` · `screeninfo==0.8.1` · `pygrabber==0.2`

---

## 5. Cómo verificar un cambio

```bash
venv\Scripts\python.exe -m pyflakes src scripts        # debe salir limpio
venv\Scripts\python.exe -m compileall -q src scripts   # sin errores

# Sin cámara ni pantalla:
set SDL_VIDEODRIVER=dummy && set SDL_AUDIODRIVER=dummy
venv\Scripts\python.exe scripts\smoke_test.py          # TODO OK

# Selección de cámara, no abre dispositivos:
venv\Scripts\python.exe scripts\test_camera.py          # 10/10

# Mirada con la cámara real (requiere a alguien delante):
venv\Scripts\python.exe scripts\gaze_probe.py 20
```

`smoke_test.py` cubre: config y 16 gestos válidos · 16 sounds de fallback ·
13 gestos por frame · los 3 gestos de movimiento (`nod`, `shake`,
`head_shake_fast`) · **cobertura completa de la tabla** · sin rostro no hay
falsos positivos · disparo por flanco y rearme · prioridades (incluido el
descarte de la expresión) · bandas de boca excluyentes · tamaño de cara en
720p/1080p · 8+ acciones idle · render de 21 expresiones · audio 16/16 ·
reescritura de `config.yaml` sin perder comentarios.

> `test_config_rewrite()` importa `select_camera.set_yaml_key` y comprueba
> que reescribe el valor, conserva el comentario, no toca el resto del
> archivo y que `--auto` deja `config/config.yaml` byte a byte igual. Sin
> ese test, el selector podría borrar los 23 comentarios del YAML y nadie
> se enteraría hasta perderlos.

### Cómo leer `gaze_probe.py`

| Síntoma | Causa probable | Ajuste |
|---|---|---|
| Mediana lejos de 0 | línea base mal aprendida | subir `gaze.deadzone` |
| Mediana en ±1, saturada | ganancia excesiva | **bajar** `gaze.gain_x` / `gain_y` |
| Recorrido ~0 | la cámara no ve el iris, o la cara está muy lejos | comprobar luz y distancia |
| Salta a un extremo | `gaze.deadzone` mayor que el movimiento real | **bajar** `gaze.deadzone` |

> `gaze.deadzone` debe ser **menor** que el desplazamiento real de la mirada.
> Medido: el movimiento real da ~0.05, así que el valor por defecto es 0.02.
> Con 0.06 (el valor con el que se empezó) la zona muerta se tragaba el
> movimiento.

---

## 6. Restricciones del entorno

Cosas que fallan aquí y que conviene no deshacer:

- **Smart App Control** bloquea la instalación/importación de OpenCV 5.x y de
  las headless `>=4.12`. Por eso `opencv-python` está fijado a `4.10.0.84`.
- **Conflicto de OpenCV.** `mediapipe` arrastra `opencv-contrib-python` 5.x y
  ambos escriben en `cv2`. Si aparece 5.x:
  ```bash
  pip install --force-reinstall --no-deps opencv-python==4.10.0.84
  ```
  `check_env.py` lo avisa.
- **`pygame-ce`, no `pygame`.** No hay rueda de `pygame` oficial para Python
  3.14.
- **`pygrabber` es obligatorio** para elegir la USB por nombre. Sin él, la app
  avisa y cae al índice de `config.yaml`.
- **Modelos `.task` fuera del repo** (~11 MB). `scripts/download_models.py`.
  `.gitignore` los excluye.
- **Este entorno solo tiene un monitor** (`monitor 0`), así que
  `display.screen_index: 1` no se puede verificar aquí. En el AIO, el avatar
  debe salir en el segundo.

---

## 7. Limitaciones conocidas

- **No verificado visualmente.** El agente que hizo este trabajo no puede ver
  imágenes, así que la hoja de expresiones y el aspecto de la cara se
  validaron **por medios programáticos** (tamaño en píxeles, celdas no vacías),
  no a ojo. Falta una revisión humana en el AIO de: tamaño al 70 %, naturalidad
  de las pupilas y legibilidad de las 21 expresiones a pantalla completa.
- **MediaPipe no distingue una lengua realmente fuera.** `tongue_out` es una
  aproximación por apertura de boca sin sonrisa, y esa ambigüedad es la razón
  de que comparta banda con `mouth_open`.
- **`wink` es sensible a la calidad de la cámara.** Con el iris y los párpados
  mal detectados puede no dispararse. El umbral es 0.62 de asimetría; si
  falla en el AIO, es el primer ajuste.
- **`assets/sounds/` está vacío.** Solo hay los 16 tonos de fallback. Los
  términos de búsqueda CC0 están en `docs/GESTOS_SONIDOS.md`; nadie ha
  descargado todavía los audios reales. La carpeta lleva un `LEEME.md` para
  que exista tras clonar (git no rastrea carpetas vacías).
- **Actualizaciones por `update_check.py`:** hace `git reset --hard` si el
  remoto trae commits. Ojo en un repo con trabajo sin commitear.
- **Las peticiones originales de la §2.1 están hechas, y también la 9 y la 10.**
- **La instalación necesita internet** (PyPI y el CDN de Google para los
  modelos). En una máquina sin red hay que copiar `models/` a mano.

---

## 8. Convenciones

- Código y comentarios **en español**; identificadores sin acentos ni `ñ`.
- Las **bandas numéricas de un detector se centralizan en su función** y se
  documentan con el motivo de los límites, no solo con el valor.
- Todo valor ajustable vive en `config/config.yaml` (o `gestures.yaml`), no
  escrito a fuego en el código.
- `set_expression()` devuelve `bool`. **Quien lo llame debe usar el retorno**
  para decidir si suena algo; si no, se rompe la coherencia audio/visual.
- Un test nuevo que depende de la cámara real va en un script aparte
  (`gaze_probe.py`), no en `smoke_test.py`, que debe seguir corriendo sin
  hardware.
- Al añadir un gesto a `gestures.yaml`, añadir también su caso en
  `test_gesture_engine()`: la guarda de cobertura lo exigirá.
