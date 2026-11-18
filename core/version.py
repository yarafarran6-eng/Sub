"""Shown in the page header and on the login screen, so anyone can see which version of the site is really running.
With every change: set BUILD_DATE to today and raise BUILD_NO by one."""
BUILD_DATE = "2026-11-18"
BUILD_NO = 15
BUILD = f"{BUILD_DATE} · {BUILD_NO}"
