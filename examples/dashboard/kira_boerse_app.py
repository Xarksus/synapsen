#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# KIRA Bio-Sync Dashboard — der schöne Web-Look in einem EIGENEN App-Fenster
# (WebKit2-WebView, KEIN Browser, keine Tabs/URL-Leiste). Regeneriert die Daten
# alle 60s. Start: kira-python kira_boerse_app.py
# ─────────────────────────────────────────────────────────────────────────────
import os
# NVIDIA + Wayland: WebKit2/GTK3 über XWayland + ohne DMABUF-Renderer (sonst Crash)
os.environ.setdefault("GDK_BACKEND", "x11")
os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
os.environ.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")

import gi, sys, subprocess
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, WebKit2, GLib, Gdk

GEN  = "/kirazone/kira/tools/kira_boerse.py"
HTML = "/tmp/kira_boerse.html"

def regenerate():
    try:
        subprocess.run([sys.executable, GEN], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def reload_page(web):
    regenerate()
    web.load_uri(f"file://{HTML}")
    return True  # keep the timer alive

def on_destroy(*_):
    Gtk.main_quit()

# ── Erstes HTML generieren ───────────────────────────────────────────────────
regenerate()

# ── Fenster rein prozedural erstellen (Python 3.14 + PyGObject Kompatibilität) ─
win = Gtk.Window.new(Gtk.WindowType.TOPLEVEL)
win.set_title("KIRA Bio-Sync Dashboard")
win.set_default_size(1200, 820)
win.set_icon_name("utilities-system-monitor")
win.set_wmclass("kira-dashboard", "KIRA Bio-Sync Dashboard")

web = WebKit2.WebView()
# Dunkler Hintergrund während des Ladens (kein weißes Blitzen)
try:
    rgba = Gdk.RGBA()
    rgba.red, rgba.green, rgba.blue, rgba.alpha = 0.039, 0.051, 0.071, 1.0
    web.set_background_color(rgba)
except Exception:
    pass

win.add(web)

# destroy-Signal über delete-event abfangen (Python 3.14 PyGObject Bug)
try:
    win.connect("destroy", on_destroy)
except TypeError:
    # Fallback: delete-event oder einfach quit bei Window-Close
    try:
        win.connect("delete-event", lambda *_: Gtk.main_quit())
    except TypeError:
        pass  # Gtk.main_quit wird manuell bei Window-Close getriggert

# Erste Seite laden
web.load_uri(f"file://{HTML}")

# Auto-Refresh alle 60 Sekunden
GLib.timeout_add_seconds(60, reload_page, web)

win.show_all()
Gtk.main()
