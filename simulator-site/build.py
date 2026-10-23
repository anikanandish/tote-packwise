r"""Rebuilds index.html from page.html + a fresh copy of the built-in catalogue.

Only needed if you change the seed data. Run from the backend folder's venv:
    python ..\simulator-site\build.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
src = (HERE / "page.html").read_text(encoding="utf-8")
data = json.loads((HERE / "builtin-data.json").read_text(encoding="utf-8"))
head = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n')
title_end = src.index("</style>") + len("</style>")
page = head + src[:title_end] + "\n</head>\n<body>\n" + src[title_end:].replace(
    "__BUILTIN_DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")) + "\n</body>\n</html>\n"
# The local site ships its own copy of Three.js so 3D works without internet.
page = page.replace('src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"', 'src="vendor/three.min.js"')
(HERE / "index.html").write_text(page, encoding="utf-8")
print("Wrote", HERE / "index.html")
