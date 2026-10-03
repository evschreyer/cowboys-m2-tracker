"""Assemble the static GitHub Pages site in _site/ from the dashboard, engine and latest snapshot.

dashboard/index.html is written as page content (the claude.ai artifact format), so this wraps it
in a full HTML document with the same small reset the artifact host adds.
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_site")

HEAD = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>
</head><body>
"""


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    with open(os.path.join(ROOT, "dashboard/index.html")) as f:
        page = f.read()
    with open(os.path.join(OUT, "index.html"), "w") as f:
        f.write(HEAD + page + "\n</body></html>\n")
    shutil.copy(os.path.join(ROOT, "engine/engine.js"), OUT)
    shutil.copy(os.path.join(ROOT, "data/snapshots/latest.json"), OUT)
    with open(os.path.join(OUT, "robots.txt"), "w") as f:
        f.write("User-agent: *\nDisallow: /\n")
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    print("site built in", OUT)


if __name__ == "__main__":
    main()
