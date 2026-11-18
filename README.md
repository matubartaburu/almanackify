# Almanackify

Turn anything you read into a pocket Almanack.

Paste a link, a transcript or a book. Get short paragraphs, gray idea boxes and a ↓ chain that sums up each chapter, as an
**EPUB made for your Kindle** (and a PDF).

The format is inspired by *The Almanack of Naval Ravikant* (Eric Jorgenson). This project is not affiliated with or endorsed by
the book, its author or Naval Ravikant.

## Why

Some books read lighter when the pages breathe: short paragraphs and the sentence worth remembering pulled out in a box.
Almanackify does that to text you already have.

## How it works

- **Input:** an article link, a YouTube link (uses the transcript), an EPUB, a PDF, a `.txt`/`.srt`/`.vtt` file, or pasted text.
- **No AI needed.** Long paragraphs are split, and the boxes are picked from the text itself with a statistical score
  (TF-IDF, sentence centrality and an "aphorism" heuristic). Boxes must make sense on their own: sentences that point back to
  earlier text ("this phenomenon", "such lines", "for example…") and list fragments ("Fourthly, …") are skipped.
- **Trade-off:** script-picked boxes are less sharp than ones written by a person or a model. For that, there is a hybrid mode
  (see MCP below): Claude writes the boxes into a JSON and the script only renders it.
- **Questions in bold:** the tool does not invent questions. They stay in bold when the source already marks them, and in
  hybrid mode Claude can add them.
- **Output:** EPUB (Kindle) and PDF (5.5 × 8.5 in, EB Garamond).

## Quick start

    git clone <this repo> && cd almanackify
    python3 -m venv .venv && source .venv/bin/activate
    pip install .                          # WeasyPrint needs Pango (macOS: brew install pango)

Tested on Python 3.14 (macOS). It is not on PyPI yet.

**Web interface** (runs on your machine, `127.0.0.1` only):

    almanackify-server                     # opens http://127.0.0.1:8742

Paste a link, drop a file or paste text. You get a cover, the EPUB/PDF, and each idea box can be saved as a 16:9 image to share.
The page opens on a 3D shelf: your converted books (newest in front, older ones by their spines) or, the first time, sample books
made from public-domain texts. Click a book to open it; use the arrow keys to browse.

**Command line:**

    almanackify "https://standardebooks.org/ebooks/ralph-waldo-emerson/essays/text/self-reliance" \
        --title "Self-Reliance" --author "Ralph Waldo Emerson" -o out
    almanackify book.epub --chapter 2 -o out
    almanackify book.pdf --every 150 --no-chain

**From Claude Code (MCP):**

    claude mcp add almanackify -- python -m almanackify.mcp_server

Tools: `almanackify`, `almanackify_extract` (structure only, so Claude can write the boxes) and `almanackify_render`.
Files go to `~/Documents/Almanackify` by default (the web interface keeps its working files in `~/.almanackify/web`).

## Reading on a Kindle

Send the EPUB with [Send to Kindle](https://www.amazon.com/sendtokindle) or email it to your `@kindle.com` address (your sender
must be on Amazon's approved list).

What the EPUB does for the Kindle:

- Embeds **static** EB Garamond fonts (regular, bold, italic, bold italic), subset to Latin characters (about 50 KB each).
  Variable fonts are a risk on Kindle renderers, so the variable file used for the PDF is not shipped in the EPUB.
- Includes a cover (title, author and one strong idea box) so the book looks right in your Library.
- Keeps the contents page out of the reading order, so the book opens on the title page.
- Passes **EPUBCheck** (EPUB 3.4 rules) with zero errors and zero warnings.

Honest status: it has been validated with EPUBCheck, but visual results on a physical Kindle are still being collected.
`examples/almanackify-kindle-test.epub` is a short book that contains every block type and explains what you should see. Send it
to your device and tell me what looks wrong.

Sample books on the page are regenerated with `python scripts/build_demo.py` (public-domain texts from Standard Ebooks).

## Development

    pip install -e . -r requirements-dev.txt
    python -m unittest discover -s tests   # unit tests: extraction quality, EPUB structure, web API and its security
    python scripts/e2e_ui.py               # end-to-end UI test with headless Chrome (needs the server running and internet)

Validate an EPUB: `java -jar $(find .venv -name epubcheck.jar) your.epub` (needs a Java runtime).

The web server never accepts local file paths, requires a custom header on every `POST` (so other web pages cannot call it from
your browser), checks the `Host` header, and only listens on `127.0.0.1`.

## Limits

- Converting a YouTube link uses its transcript; auto-generated captions have no punctuation and give worse results. This path
  and article extraction depend on the network and on the site, and are the least tested.
- Do not publish converted text you do not have the right to share. The examples in this repo are public domain.

## Credits

- **EB Garamond** by The EB Garamond Project Authors, SIL Open Font License 1.1 (`almanackify/fonts/OFL.txt`).
- Interface patterns from [21st.dev](https://21st.dev), rewritten in plain CSS and JS: the vertical titled stepper (by sean0205), and the behavior of a "File Upload" component (a row for every file, rejected ones included; a drag counter that does not flicker). The DevTool Landing Page (by mokshithgujjeti) was studied for the walkthrough idea, and the 3D shelf was built from the preview of "3D Book Carousel Reading Mode" (by aloksivastava1025), not from its code.
