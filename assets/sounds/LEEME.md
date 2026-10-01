# Sonidos CC0 (opcional)

Los sonidos reales del avatar van en esta carpeta. **Es opcional**: si un
gesto no tiene aqui su fichero, la app usa automaticamente el tono
sintetizado de `../sounds_fallback/`, asi que funciona desde el primer dia
sin descargar nada.

## Como añadir un sonido

1. Descarga un efecto con licencia **CC0 / dominio publico** desde:
   - <https://pixabay.com/es/sound-effects/>
   - <https://mixkit.co/free-sound-effects/>
   - <https://freesound.org/>
2. Renombralo con el identificador del gesto (por ejemplo `gasp.wav`).
   La lista completa esta en `../../config/gestures.yaml`.
3. Dejalo aqui. Formatos aceptados: `.ogg`, `.wav`, `.mp3`.

El motor prueba primero esta carpeta y, si no encuentra el fichero, cae al
fallback sintetizado. Por eso un sonido equivocado no rompe nada.

## Terminos de busqueda sugeridos

Estan en `../../docs/GESTOS_SONIDOS.md`, uno por gesto.