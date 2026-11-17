# Almanackify

Convierte libros (EPUB/PDF), artículos, videos de YouTube (transcripción) o texto al formato "Almanack":
párrafos cortos, preguntas en negrita, cajas grises tipo tweet y una cadena ↓ de resumen por capítulo.
Sin IA: las cajas se eligen del propio texto con un puntaje estadístico.

## Instalar
    pip install -r requirements.txt

## Usar (comando)
    python -m almanackify libro.epub -o salida            # libro entero
    python -m almanackify libro.epub --chapter 2 -o salida
    python -m almanackify "https://youtu.be/XXXX" -o salida
    python -m almanackify libro.pdf --every 150 --no-chain

## Usar desde Claude Code (MCP)
    claude mcp add almanackify -- python -m almanackify.mcp_server
Herramientas: `almanackify`, `almanackify_extract`, `almanackify_render`.
Los archivos salen por defecto en ~/Almanackify. El EPUB se manda al Kindle con Send to Kindle.
