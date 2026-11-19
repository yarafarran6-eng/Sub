"""Shown in the page header and on the login screen, so anyone can see which version of the site is really running.
With every change: set BUILD_DATE to today and raise BUILD_NO by one.
When the page layout code (core/manual.py replace_page_text) improves, ALSO raise manual.LAYOUT_VER so «update old pages» redoes older pasted pages."""
BUILD_DATE = "2026-11-19"
BUILD_NO = 27
BUILD = f"{BUILD_DATE} · {BUILD_NO}"
