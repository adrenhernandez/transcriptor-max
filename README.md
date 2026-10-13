# Transcriptor Max

Transcriptor de videos de YouTube a partir de su link, con **Whisper large-v3** (vía Groq). Funciona aunque el video no tenga subtítulos.

- **Web:** GitHub Pages (`index.html`)
- **Motor:** GitHub Actions descarga el audio con `yt-dlp` y lo transcribe con Groq (`.github/workflows/transcribe.yml`, `scripts/transcribe.py`)
- **Resultados:** se guardan como JSON en la rama `data` (`transcripts/<id>.json`). Si vuelves a pedir un video ya transcrito, aparece al instante.

## Configuración (una sola vez)

1. **API key de Groq (gratis):** créala en https://console.groq.com/keys y guárdala como secreto del repo:
   ```
   gh secret set GROQ_API_KEY -R <usuario>/transcriptor-max
   ```
   (Pega la key cuando te la pida.) También puedes hacerlo en *Settings → Secrets and variables → Actions*.

2. **Token de GitHub para la web:** crea un token *fine-grained* en https://github.com/settings/personal-access-tokens/new
   - *Repository access:* solo `transcriptor-max`
   - *Permissions:* **Actions: Read and write** y **Contents: Read-only**

3. Abre la página, toca ⚙ y pega el token. Queda guardado solo en ese navegador.

## Si YouTube bloquea la descarga

A veces YouTube bloquea los servidores de GitHub y pide confirmar que no eres un bot. Para solucionarlo:

1. Exporta tus cookies de YouTube en formato Netscape (`cookies.txt`) con una extensión como *Get cookies.txt LOCALLY*, mientras tienes la sesión iniciada en youtube.com. Lo más seguro es usar una cuenta secundaria.
2. Guárdalas como secreto:
   ```
   gh secret set YT_COOKIES -R <usuario>/transcriptor-max < cookies.txt
   ```

## Límites

- Plan gratuito de Groq: unas 2 horas de audio por hora y 8 horas por día.
- Los videos largos se dividen en partes de 30 minutos de forma automática.
- El repo es público (requisito para usar GitHub Pages gratis), así que las transcripciones de la rama `data` también son visibles.
