"""Shared helper for emitting the standalone website pages.

The templates are authored as fragments (<title>, <style>, markup, <script>) so they can
also be previewed as Artifacts, which supply their own document shell. Files written for
the user's own site need a real document — crucially a viewport meta, without which
phones lay the page out at ~980px and zoom out.

wrap_page() lifts the fragment's <title>/<style> into a proper <head> and returns a
complete, valid HTML document.
"""
import re

SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
{head}
</head>
<body>
{body}
</body>
</html>
"""


def wrap_page(fragment: str) -> str:
    head, body = [], fragment
    for pat in (r"<title>.*?</title>", r"<style>.*?</style>"):
        m = re.search(pat, body, re.S | re.I)
        if m:
            head.append(m.group(0))
            body = body.replace(m.group(0), "", 1)
    return SHELL.format(head="\n".join(head), body=body.strip())
