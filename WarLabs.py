#!/usr/bin/env python3
"""
WarLabs — Gestor de laboratorios
Requiere: pip install customtkinter
"""

import customtkinter as ctk
import subprocess
import threading
import re
import os
import sys
import json
import time
import tkinter as tk
import tkinter.font as _tkfont

from pathlib import Path
from dataclasses import dataclass

# ── Constantes ────────────────────────────────────────────────────────────────
STATUS_POLL_INTERVAL = 8   # segundos entre cada actualización de estado

# ── Fuente ────────────────────────────────────────────────────────────────────
def _resolve_font():
    """Usa Hack Nerd Font si está disponible, sino Courier New como fallback."""
    try:
        root = tk.Tk()
        root.withdraw()
        families = _tkfont.families(root)
        root.destroy()
        for name in ("Hack Nerd Font", "Hack Nerd Font Mono", "Hack"):
            if name in families:
                return name
    except Exception:
        pass
    return "Courier New"

MONO = _resolve_font()

# ── Tema ──────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

COLORS = {
    "bg":        "#0d1117",
    "surface":   "#161b22",
    "surface2":  "#1c2128",
    "border":    "#30363d",
    "green":     "#3fb950",
    "green_dim": "#1a3a22",
    "cyan":      "#79c0ff",
    "purple":    "#bc8cff",
    "yellow":    "#e3b341",
    "red":       "#f85149",
    "red_dim":   "#3a1a1a",
    "text":      "#e6edf3",
    "muted":     "#8b949e",
    "tag_easy":  "#1a3a22",
    "tag_med":   "#2d2a0f",
    "tag_hard":  "#3a1a1a",
}

BADGE = {
    "Fácil":   ("#3fb950", "#1a3a22"),
    "Medio":   ("#e3b341", "#2d2a0f"),
    "Difícil": ("#f85149", "#3a1a1a"),
}

# ── Dataclass Lab ─────────────────────────────────────────────────────────────
@dataclass
class Lab:
    name:   str
    nivel:  str
    path:   Path
    desc:   str
    readme: Path | None

# ── Descubrimiento de labs ────────────────────────────────────────────────────
def _find_base_dir():
    """Sube desde la ubicación del script hasta encontrar la raíz de WarLabs."""
    candidate = Path(__file__).resolve().parent
    for _ in range(5):
        if (candidate / "Facil").exists() or (candidate / "Medio").exists():
            return candidate
        candidate = candidate.parent
    return Path(__file__).resolve().parent

BASE_DIR = _find_base_dir()

NIVEL_MAP = {
    "Facil":   "Fácil",
    "Medio":   "Medio",
    "Dificil": "Difícil",
}

def discover_labs() -> list[Lab]:
    labs = []
    for nivel_dir in ["Facil", "Medio", "Dificil"]:
        nivel_path = BASE_DIR / nivel_dir
        if not nivel_path.exists():
            continue
        for lab_dir in sorted(nivel_path.iterdir()):
            if not lab_dir.is_dir():
                continue
            if not (lab_dir / "Dockerfile").exists():
                continue
            readme = lab_dir / "README.md"
            desc = ""
            nivel_label = NIVEL_MAP.get(nivel_dir, nivel_dir)
            if readme.exists():
                lines = readme.read_text(encoding="utf-8").splitlines()
                for i, line in enumerate(lines):
                    if line.strip().startswith("### Descripción"):
                        for j in range(i + 1, min(i + 5, len(lines))):
                            if lines[j].strip():
                                desc = lines[j].strip()
                                break
                        break
            labs.append(Lab(
                name=lab_dir.name,
                nivel=nivel_label,
                path=lab_dir,
                desc=desc or "Sin descripción disponible.",
                readme=readme if readme.exists() else None,
            ))
    return labs


def get_image_name(lab: Lab) -> str:
    run_sh = lab.path / "run.sh"
    if run_sh.exists():
        for line in run_sh.read_text().splitlines():
            if "image_name=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return f"warlabs/{lab.name.lower()}"


def container_status(lab: Lab) -> str:
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", lab.name],
            capture_output=True, text=True, timeout=3
        )
        s = result.stdout.strip()
        return s if s else "stopped"
    except Exception:
        return "stopped"


# ── Componentes UI ────────────────────────────────────────────────────────────

class StatusDot(ctk.CTkLabel):
    def __init__(self, parent, status="stopped", **kwargs):
        color = COLORS["green"] if status == "running" else COLORS["muted"]
        super().__init__(parent, text="●", text_color=color,
                         font=ctk.CTkFont(size=12), **kwargs)
        self._status = status

    def set_status(self, status):
        self._status = status
        color = COLORS["green"] if status == "running" else COLORS["muted"]
        # Siempre desde el hilo principal vía after()
        self.after(0, lambda: self.configure(text_color=color))


class NivelBadge(ctk.CTkLabel):
    def __init__(self, parent, nivel, **kwargs):
        fg, bg = BADGE.get(nivel, (COLORS["muted"], COLORS["surface2"]))
        super().__init__(
            parent, text=nivel,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=fg,
            fg_color=bg,
            corner_radius=6,
            padx=8, pady=2,
            **kwargs
        )


class ConfirmDialog(ctk.CTkToplevel):
    """Diálogo de confirmación con estética consistente con WarLabs."""

    def __init__(self, parent, title: str, message: str, on_confirm):
        super().__init__(parent)
        self.on_confirm = on_confirm

        self.title("")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg"])
        self.overrideredirect(True)

        # Borde exterior
        outer = ctk.CTkFrame(
            self,
            fg_color=COLORS["surface"],
            border_color=COLORS["red"],
            border_width=1,
            corner_radius=12,
        )
        outer.pack(padx=0, pady=0)

        # ── Barra de título ───────────────────────────────────────────────────
        title_bar = ctk.CTkFrame(outer, fg_color=COLORS["surface2"], corner_radius=0,
                                  height=36)
        title_bar.pack(fill="x", padx=0, pady=0)
        title_bar.pack_propagate(False)

        ctk.CTkLabel(
            title_bar,
            text=f"  ⚠  {title}",
            font=ctk.CTkFont(family=MONO, size=12, weight="bold"),
            text_color=COLORS["red"],
            anchor="w",
        ).pack(side="left", padx=12, pady=8)

        # ── Cuerpo ────────────────────────────────────────────────────────────
        body = ctk.CTkFrame(outer, fg_color="transparent")
        body.pack(padx=24, pady=(16, 8))

        ctk.CTkLabel(
            body,
            text=message,
            font=ctk.CTkFont(family=MONO, size=12),
            text_color=COLORS["text"],
            justify="center",
            wraplength=320,
        ).pack(pady=(0, 20))

        # ── Botones ───────────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack()

        ctk.CTkButton(
            btn_row,
            text="Cancelar",
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["surface2"],
            hover_color=COLORS["border"],
            text_color=COLORS["muted"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            width=110,
            command=self._cancel,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row,
            text="■  Detener",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLORS["red_dim"],
            hover_color="#5a2020",
            text_color=COLORS["red"],
            border_color=COLORS["red"],
            border_width=1,
            corner_radius=8,
            width=110,
            command=self._confirm,
        ).pack(side="left")

        # Cerrar con Escape
        self.bind("<Escape>", lambda e: self._cancel())

        # Centrar sobre el padre
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        dw = self.winfo_width()
        dh = self.winfo_height()
        self.geometry(f"+{px + (pw - dw)//2}+{py + (ph - dh)//2}")

        self.lift()
        self.focus_force()
        self.grab_set()

    def _confirm(self):
        self.grab_release()
        self.destroy()
        self.on_confirm()

    def _cancel(self):
        self.grab_release()
        self.destroy()


class LabCard(ctk.CTkFrame):
    def __init__(self, parent, lab: Lab, on_select, **kwargs):
        super().__init__(
            parent,
            fg_color=COLORS["surface"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=10,
            **kwargs
        )
        self.lab = lab
        self.on_select = on_select
        self._selected = False
        self._build()
        self.bind("<Button-1>", self._click)
        for w in self.winfo_children():
            w.bind("<Button-1>", self._click)

    def _build(self):
        self.columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        top.columnconfigure(0, weight=1)

        name_lbl = ctk.CTkLabel(
            top, text=self.lab.name,
            font=ctk.CTkFont(family=MONO, size=14, weight="bold"),
            text_color=COLORS["cyan"], anchor="w"
        )
        name_lbl.grid(row=0, column=0, sticky="w")

        self.dot = StatusDot(top, status="stopped")
        self.dot.grid(row=0, column=1, padx=(8, 0))

        NivelBadge(top, self.lab.nivel).grid(row=0, column=2, padx=(8, 0))

        desc = tk.Text(
            self,
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(MONO, 9),
            bd=0,
            highlightthickness=0,
            relief="flat",
            wrap="word",
            state="normal",
            padx=0, pady=0,
            cursor="arrow",
            height=3,
            spacing1=0, spacing3=0,
            insertbackground=COLORS["surface"],
        )
        desc.tag_configure("bold", font=(MONO, 9, "bold"), foreground=COLORS["text"])
        desc.tag_configure("code", font=(MONO, 8), foreground=COLORS["green"],
                           background=COLORS["surface2"])
        for part in re.split(r"(`[^`]+`|\*\*[^*]+\*\*)", self.lab.desc):
            if part.startswith("**") and part.endswith("**"):
                desc.insert("end", part[2:-2], "bold")
            elif part.startswith("`") and part.endswith("`"):
                desc.insert("end", part[1:-1], "code")
            else:
                desc.insert("end", part)
        desc.configure(state="disabled")
        desc.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))
        desc.bind("<Button-1>", self._click)

    def _click(self, event=None):
        self.on_select(self)

    def set_selected(self, val: bool):
        self._selected = val
        if val:
            self.configure(border_color=COLORS["cyan"], border_width=2)
        else:
            self.configure(border_color=COLORS["border"], border_width=1)

    def refresh_status(self):
        status = container_status(self.lab)
        self.dot.set_status(status)   # thread-safe: usa after() internamente
        return status


# ── Ventana principal ─────────────────────────────────────────────────────────

class WarLabsApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("WarLabs")
        self.geometry("1080x680")
        self.minsize(900, 600)
        self.configure(fg_color=COLORS["bg"])

        self.labs = discover_labs()
        self.cards: list[LabCard] = []
        self.selected_card: LabCard | None = None
        self._log_lock = threading.Lock()

        self._build_layout()
        self._populate_labs()
        self._start_status_loop()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_layout(self):
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        self._build_header()
        self._build_sidebar()
        self._build_main()

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=COLORS["surface"],
                            corner_radius=0, border_width=0,
                            height=54)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
        hdr.columnconfigure(1, weight=1)
        hdr.grid_propagate(False)

        ctk.CTkLabel(
            hdr,
            text="  ⬡  WarLabs",
            font=ctk.CTkFont(family=MONO, size=18, weight="bold"),
            text_color=COLORS["green"]
        ).grid(row=0, column=0, padx=20, pady=14, sticky="w")

        ctk.CTkLabel(
            hdr,
            text="Gestor de laboratorios de hacking ético",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["muted"]
        ).grid(row=0, column=1, sticky="w")

        self.global_status = ctk.CTkLabel(
            hdr, text="", font=ctk.CTkFont(size=11),
            text_color=COLORS["muted"]
        )
        self.global_status.grid(row=0, column=2, padx=20, sticky="e")

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(
            self, fg_color=COLORS["surface"],
            corner_radius=0, border_width=0,
            width=300
        )
        self.sidebar.grid(row=1, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.columnconfigure(0, weight=1)
        self.sidebar.rowconfigure(0, weight=0, minsize=0)
        self.sidebar.rowconfigure(1, weight=1)

        top_bar = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 4))
        top_bar.columnconfigure(0, weight=1)

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self._filter_labs)
        ctk.CTkEntry(
            top_bar,
            placeholder_text="Buscar laboratorio...",
            textvariable=self.search_var,
            fg_color=COLORS["surface2"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            placeholder_text_color=COLORS["muted"],
            corner_radius=8,
            font=ctk.CTkFont(size=12)
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))

        filter_frame = ctk.CTkFrame(top_bar, fg_color="transparent")
        filter_frame.grid(row=0, column=1, sticky="e")

        self.nivel_var = ctk.StringVar(value="Todos")
        self._build_nivel_dropdown(filter_frame)

        self.lab_scroll = ctk.CTkScrollableFrame(
            self.sidebar,
            fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            label_text="",
            label_fg_color="transparent",
        )
        self.lab_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.lab_scroll.columnconfigure(0, weight=1)

        try:
            self.lab_scroll._label.grid_remove()
        except Exception:
            pass

    def _build_nivel_dropdown(self, parent):
        OPCIONES = [
            ("Todos",    COLORS["text"],   COLORS["surface2"]),
            ("Fácil",    "#3fb950",        "#1a3a22"),
            ("Medio",    "#e3b341",        "#2d2a0f"),
            ("Difícil",  "#f85149",        "#3a1a1a"),
        ]

        self._dropdown_open = False
        self._dropdown_popup = None

        self._btn_nivel = ctk.CTkButton(
            parent,
            text="Todos  ▾",
            font=ctk.CTkFont(size=11),
            fg_color=COLORS["surface2"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            width=100,
            height=28,
            anchor="w",
        )
        self._btn_nivel.pack()
        btn = self._btn_nivel

        def _update_btn_color_text(*_):
            val = self.nivel_var.get()
            for label, fg, bg in OPCIONES:
                if label == val:
                    btn.configure(
                        text=f"{label}  ▾",
                        text_color=fg,
                        fg_color=bg,
                        border_color=fg if val != "Todos" else COLORS["border"]
                    )
                    break

        self.nivel_var.trace_add("write", _update_btn_color_text)

        def _toggle(e=None):
            if self._dropdown_open and self._dropdown_popup:
                self._dropdown_popup.destroy()
                self._dropdown_popup = None
                self._dropdown_open = False
                return

            self._dropdown_open = True
            popup = tk.Toplevel(self)
            self._dropdown_popup = popup
            popup.overrideredirect(True)
            popup.configure(bg=COLORS["border"])

            bx = btn.winfo_rootx()
            by = btn.winfo_rooty() + btn.winfo_height() + 2
            popup.geometry(f"88x{len(OPCIONES)*30}+{bx}+{by}")

            for label, fg, bg in OPCIONES:
                def _select(l=label):
                    self.nivel_var.set(l)
                    self._filter_labs()
                    popup.destroy()
                    self._dropdown_popup = None
                    self._dropdown_open = False

                item = tk.Frame(popup, bg=bg, cursor="hand2")
                item.pack(fill="x")
                lbl = tk.Label(
                    item, text=label,
                    bg=bg, fg=fg,
                    font=(MONO, 10, "bold"),
                    padx=10, pady=6,
                    anchor="w"
                )
                lbl.pack(fill="x")
                lbl.bind("<Button-1>", lambda e, s=_select: s())
                item.bind("<Button-1>", lambda e, s=_select: s())

                def _on_enter(e, w=item, b=bg):
                    w.configure(bg=COLORS["border"])
                    for c in w.winfo_children():
                        c.configure(bg=COLORS["border"])

                def _on_leave(e, w=item, b=bg):
                    w.configure(bg=b)
                    for c in w.winfo_children():
                        c.configure(bg=b)

                item.bind("<Enter>", _on_enter)
                item.bind("<Leave>", _on_leave)
                lbl.bind("<Enter>", _on_enter)
                lbl.bind("<Leave>", _on_leave)

            def _close_on_click_outside(e):
                if self._dropdown_popup is None:
                    return
                try:
                    wx, wy = popup.winfo_rootx(), popup.winfo_rooty()
                    ww, wh = popup.winfo_width(), popup.winfo_height()
                    mx, my = e.x_root, e.y_root
                    if not (wx <= mx <= wx + ww and wy <= my <= wy + wh):
                        popup.destroy()
                        self._dropdown_popup = None
                        self._dropdown_open = False
                except Exception:
                    self._dropdown_popup = None
                    self._dropdown_open = False

            self.bind("<Button-1>", _close_on_click_outside)

        btn.configure(command=_toggle)

    def _build_main(self):
        self.main = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        self.main.grid(row=1, column=1, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(1, weight=1)

        self.info_panel = ctk.CTkFrame(
            self.main, fg_color=COLORS["surface"],
            border_color=COLORS["border"], border_width=1,
            corner_radius=10
        )
        self.info_panel.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        self.info_panel.columnconfigure(1, weight=1)
        self._build_placeholder_info()

        self.tabs = ctk.CTkTabview(
            self.main,
            fg_color=COLORS["surface"],
            segmented_button_fg_color=COLORS["surface2"],
            segmented_button_selected_color=COLORS["surface"],
            segmented_button_selected_hover_color=COLORS["surface"],
            segmented_button_unselected_color=COLORS["surface2"],
            segmented_button_unselected_hover_color=COLORS["border"],
            text_color=COLORS["text"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=10
        )
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.tabs.add("  Terminal  ")
        self.tabs.add("  README  ")

        self.log_box = ctk.CTkTextbox(
            self.tabs.tab("  Terminal  "),
            fg_color=COLORS["bg"],
            text_color=COLORS["green"],
            font=ctk.CTkFont(family=MONO, size=12),
            border_width=0,
            corner_radius=8,
            wrap="word",
            state="disabled"
        )
        self.log_box.pack(fill="both", expand=True, padx=8, pady=8)

        self.tabs.tab("  README  ").configure(fg_color=COLORS["bg"])

        self.readme_box = tk.Text(
            self.tabs.tab("  README  "),
            bg=COLORS["bg"],
            fg=COLORS["text"],
            font=(MONO, 12),
            bd=0,
            relief="flat",
            highlightthickness=0,
            wrap="word",
            state="disabled",
            padx=16,
            pady=12,
            cursor="arrow",
            insertbackground=COLORS["bg"],
            selectbackground=COLORS["surface2"],
            selectforeground=COLORS["text"],
        )
        self.readme_box.pack(fill="both", expand=True, padx=0, pady=0)

        # ── Zoom README ───────────────────────────────────────────────────────
        self._readme_font_size = 12
        for seq, delta in [
            ("<Control-Shift-equal>", +1), ("<Control-Shift-plus>", +1),
            ("<Control-plus>", +1), ("<Control-KP_Add>", +1),
            ("<Control-minus>", -1), ("<Control-KP_Subtract>", -1),
            ("<Control-0>", 0),
        ]:
            self.readme_box.bind(seq, lambda e, d=delta: self._zoom_readme(d))

        def _scroll_readme(e):
            if e.num == 4 or e.delta > 0:
                self._zoom_readme(+1)
            else:
                self._zoom_readme(-1)
            return "break"

        self.readme_box.bind("<Control-MouseWheel>", _scroll_readme)
        self.readme_box.bind("<Control-Button-4>",   _scroll_readme)
        self.readme_box.bind("<Control-Button-5>",   _scroll_readme)

        # ── Zoom Terminal ─────────────────────────────────────────────────────
        self._log_font_size = 12

        def _zoom_log(delta):
            if delta == 0:
                self._log_font_size = 12
            else:
                self._log_font_size = max(8, min(28, self._log_font_size + delta))
            self.log_box.configure(font=ctk.CTkFont(family=MONO, size=self._log_font_size))

        for seq, delta in [
            ("<Control-Shift-equal>", +1), ("<Control-Shift-plus>", +1),
            ("<Control-plus>", +1), ("<Control-KP_Add>", +1),
            ("<Control-minus>", -1), ("<Control-KP_Subtract>", -1),
            ("<Control-0>", 0),
        ]:
            self.log_box.bind(seq, lambda e, d=delta: _zoom_log(d))

        def _scroll_log(e):
            if e.num == 4 or e.delta > 0:
                _zoom_log(+1)
            else:
                _zoom_log(-1)
            return "break"

        self.log_box.bind("<Control-MouseWheel>", _scroll_log)
        self.log_box.bind("<Control-Button-4>",   _scroll_log)
        self.log_box.bind("<Control-Button-5>",   _scroll_log)

        self._apply_readme_tags()
        self._log("WarLabs iniciado. Selecciona un laboratorio.")

    def _build_placeholder_info(self):
        for w in self.info_panel.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.info_panel,
            text="Selecciona un laboratorio de la lista",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["muted"]
        ).pack(pady=24)

    def _build_lab_info(self, lab: Lab):
        for w in self.info_panel.winfo_children():
            w.destroy()

        self.info_panel.columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self.info_panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 2))

        ctk.CTkLabel(
            header,
            text=lab.name,
            font=ctk.CTkFont(family=MONO, size=18, weight="bold"),
            text_color=COLORS["cyan"]
        ).pack(side="left", anchor="w")

        NivelBadge(header, lab.nivel).pack(side="left", anchor="w", padx=(10, 0))

        plain = re.sub(r"\*\*([^*]+)\*\*", r"\1", lab.desc)
        plain = re.sub(r"`([^`]+)`", r"\1", plain)
        ctk.CTkLabel(
            self.info_panel,
            text=plain,
            font=ctk.CTkFont(size=11),
            text_color=COLORS["muted"],
            anchor="w", justify="left", wraplength=600
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))

        btn_frame = ctk.CTkFrame(self.info_panel, fg_color="transparent")
        btn_frame.grid(row=2, column=0, sticky="w", padx=18, pady=(0, 14))

        self.btn_launch = ctk.CTkButton(
            btn_frame, text="▶  Lanzar",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLORS["green_dim"],
            hover_color="#255c30",
            text_color=COLORS["green"],
            border_color=COLORS["green"],
            border_width=1,
            corner_radius=8,
            width=110,
            command=lambda: self._launch_lab(lab)
        )
        self.btn_launch.pack(side="left", padx=(0, 8))

        self.btn_stop = ctk.CTkButton(
            btn_frame, text="■  Detener",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLORS["red_dim"],
            hover_color="#5a2020",
            text_color=COLORS["red"],
            border_color=COLORS["red"],
            border_width=1,
            corner_radius=8,
            width=110,
            command=lambda: self._confirm_stop(lab)
        )
        self.btn_stop.pack(side="left")

    # ── Poblar labs ───────────────────────────────────────────────────────────

    def _populate_labs(self, query="", nivel="Todos"):
        for w in self.lab_scroll.winfo_children():
            w.destroy()
        self.cards.clear()

        filtered = [
            l for l in self.labs
            if (query.lower() in l.name.lower() or query.lower() in l.desc.lower())
            and (nivel == "Todos" or l.nivel == nivel)
        ]

        if not filtered:
            ctk.CTkLabel(
                self.lab_scroll, text="Sin resultados",
                text_color=COLORS["muted"], font=ctk.CTkFont(size=12)
            ).pack(pady=20)
            return

        for lab in filtered:
            card = LabCard(self.lab_scroll, lab, on_select=self._select_card)
            card.pack(fill="x", padx=4, pady=4)
            self.cards.append(card)

        threading.Thread(target=self._refresh_all_statuses, daemon=True).start()

        running = sum(1 for c in self.cards if container_status(c.lab) == "running")
        self.global_status.configure(
            text=f"{len(filtered)} labs  •  {running} activos"
        )

    def _filter_labs(self, *args):
        self._populate_labs(
            query=self.search_var.get(),
            nivel=self.nivel_var.get()
        )

    def _select_card(self, card: LabCard):
        if self.selected_card:
            try:
                self.selected_card.set_selected(False)
            except Exception:
                pass
        self.selected_card = card
        card.set_selected(True)
        self._build_lab_info(card.lab)
        self._clear_log()
        self._load_readme(card.lab)

    # ── Acciones Docker ───────────────────────────────────────────────────────

    def _launch_lab(self, lab: Lab):
        self.btn_launch.configure(state="disabled", text="Construyendo...")
        self._log(f"\n[+] Lanzando {lab.name}...")
        threading.Thread(target=self._run_launch, args=(lab,), daemon=True).start()

    def _run_launch(self, lab: Lab):
        image = get_image_name(lab)
        path = str(lab.path)

        self._log(f"[~] Construyendo imagen {image}...")
        build = subprocess.run(
            ["docker", "build", "-t", image, "."],
            cwd=path, capture_output=True, text=True
        )
        if build.returncode != 0:
            self._log(f"[!] Error al construir:\n{build.stderr}", error=True)
            self.after(0, lambda: self.btn_launch.configure(
                state="normal", text="▶  Lanzar"))
            return

        self._log("[+] Imagen construida.")

        ports = self._parse_ports(lab)
        port_args = []
        for host, cont in ports:
            port_args += ["-p", f"0.0.0.0:{host}:{cont}"]

        run_cmd = ["docker", "run", "-d", "--name", lab.name] + port_args + [image]
        run = subprocess.run(run_cmd, capture_output=True, text=True)

        if run.returncode != 0:
            err = run.stderr.strip()
            if "already in use" in err or "Conflict" in err:
                self._log(f"[!] El contenedor '{lab.name}' ya está corriendo.", error=True)
            else:
                self._log(f"[!] Error al iniciar:\n{err}", error=True)
        else:
            lab_ip = self._get_local_ip()
            self._log(f"[+] Laboratorio {lab.name} corriendo.")
            if ports:
                for h, c in ports:
                    if c == "22":
                        self._log(f"    → ssh {lab_ip} -p {h}")
                    else:
                        self._log(f"    → http://{lab_ip}:{h}")

        self.after(0, lambda: self.btn_launch.configure(
            state="normal", text="▶  Lanzar"))
        self.after(0, self._refresh_all_statuses)

    def _confirm_stop(self, lab: Lab):
        """Muestra diálogo de confirmación antes de detener el laboratorio."""
        ConfirmDialog(
            parent=self,
            title="Detener laboratorio",
            message=f"¿Seguro que quieres detener\ny eliminar '{lab.name}'?\n\nEsta acción no se puede deshacer.",
            on_confirm=lambda: self._stop_lab(lab),
        )

    def _stop_lab(self, lab: Lab):
        self.btn_stop.configure(state="disabled", text="Deteniendo...")
        self._log(f"\n[~] Deteniendo {lab.name}...")
        threading.Thread(target=self._run_stop, args=(lab,), daemon=True).start()

    def _run_stop(self, lab: Lab):
        stop = subprocess.run(
            ["docker", "rm", "-f", lab.name],
            capture_output=True, text=True
        )
        if stop.returncode == 0:
            self._log(f"[+] Laboratorio {lab.name} detenido y eliminado.")
        else:
            self._log(f"[!] {stop.stderr.strip()}", error=True)

        self.after(0, lambda: self.btn_stop.configure(
            state="normal", text="■  Detener"))
        self.after(0, self._refresh_all_statuses)

    def _get_local_ip(self) -> str:
        """Detecta la IP local de la red (wlan0 → eth0 → fallback socket)."""
        import socket
        for iface in ("wlan0", "eth0", "ens33", "enp0s3", "wlan1"):
            try:
                result = subprocess.run(
                    ["ip", "-o", "-4", "addr", "show", iface],
                    capture_output=True, text=True
                )
                if result.returncode == 0 and result.stdout.strip():
                    m = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', result.stdout)
                    if m:
                        return m.group(1)
            except Exception:
                pass
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "localhost"

    def _parse_ports(self, lab: Lab) -> list[tuple[str, str]]:
        run_sh = lab.path / "run.sh"
        ports = []
        if not run_sh.exists():
            return ports
        content = run_sh.read_text()
        ssh = re.search(r'ssh_port="(\d+)"', content)
        web = re.search(r'web_port="(\d+)"', content)
        if ssh:
            ports.append((ssh.group(1), "22"))
        if web:
            p = web.group(1)
            ports.append((p, p))
        return ports

    # ── README ────────────────────────────────────────────────────────────────

    def _apply_readme_tags(self):
        s = self._readme_font_size
        self.readme_box.tag_configure("h1",
            font=(MONO, s + 8, "bold"), foreground=COLORS["cyan"],
            spacing1=12, spacing3=6)
        self.readme_box.tag_configure("h2",
            font=(MONO, s + 4, "bold"), foreground=COLORS["purple"],
            spacing1=10, spacing3=4)
        self.readme_box.tag_configure("h3",
            font=(MONO, s + 1, "bold"), foreground=COLORS["yellow"],
            spacing1=8, spacing3=2)
        self.readme_box.tag_configure("bold",
            font=(MONO, s, "bold"), foreground=COLORS["text"])
        self.readme_box.tag_configure("code",
            font=(MONO, s - 1), foreground=COLORS["green"],
            background=COLORS["surface2"])
        self.readme_box.tag_configure("codeblock",
            font=(MONO, s - 1), foreground=COLORS["green"],
            background=COLORS["surface2"],
            lmargin1=16, lmargin2=16, spacing1=2, spacing3=2)
        self.readme_box.tag_configure("bullet",
            font=(MONO, s),
            foreground=COLORS["cyan"], lmargin1=16, lmargin2=28)
        self.readme_box.tag_configure("muted",
            font=(MONO, s), foreground=COLORS["muted"])
        self.readme_box.tag_configure("hr",
            font=(MONO, s), foreground=COLORS["border"],
            spacing1=4, spacing3=4)
        self.readme_box.configure(font=(MONO, s))

    def _zoom_readme(self, delta):
        if delta == 0:
            self._readme_font_size = 12
        else:
            self._readme_font_size = max(8, min(28, self._readme_font_size + delta))
        self._apply_readme_tags()

    def _load_readme(self, lab: Lab):
        rb = self.readme_box
        rb.configure(state="normal")
        rb.delete("1.0", "end")

        if not (lab.readme and lab.readme.exists()):
            rb.insert("end", "Sin README disponible para este laboratorio.", "muted")
            rb.configure(state="disabled")
            return

        lines = lab.readme.read_text(encoding="utf-8").splitlines()
        in_code = False
        code_buf = []

        for line in lines:
            if line.strip().startswith("```"):
                if not in_code:
                    in_code = True
                    code_buf = []
                else:
                    in_code = False
                    rb.insert("end", "\n".join(code_buf) + "\n", "codeblock")
                    rb.insert("end", "\n")
                continue
            if in_code:
                code_buf.append(line)
                continue

            if line.startswith("### "):
                rb.insert("end", line[4:] + "\n", "h3")
            elif line.startswith("## "):
                rb.insert("end", line[3:] + "\n", "h2")
            elif line.startswith("# "):
                rb.insert("end", line[2:] + "\n", "h1")
            elif re.match(r'^[-_*]{3,}$', line.strip()):
                rb.insert("end", "─" * 55 + "\n", "hr")
            elif re.match(r'^[-*+] ', line):
                rb.insert("end", "  • ", "bullet")
                self._insert_inline(rb, line[2:])
                rb.insert("end", "\n")
            elif line.strip() == "":
                rb.insert("end", "\n")
            else:
                self._insert_inline(rb, line)
                rb.insert("end", "\n")

        rb.configure(state="disabled")

    def _insert_inline(self, rb, text):
        """Procesa bold (**) e inline code (`) dentro de una línea."""
        pattern = re.compile(r'(`[^`]+`|\*\*[^*]+\*\*)')
        parts = pattern.split(text)
        for part in parts:
            if part.startswith('`') and part.endswith('`'):
                rb.insert("end", part[1:-1], "code")
            elif part.startswith('**') and part.endswith('**'):
                rb.insert("end", part[2:-2], "bold")
            else:
                rb.insert("end", part)

    # ── Terminal log ──────────────────────────────────────────────────────────

    def _log(self, msg, error=False):
        def _write():
            with self._log_lock:
                self.log_box.configure(state="normal")
                prefix = "  "
                if error:
                    self.log_box.insert("end", prefix + msg + "\n", "error")
                else:
                    self.log_box.insert("end", prefix + msg + "\n")
                self.log_box.configure(state="disabled")
                self.log_box.see("end")
        self.after(0, _write)

    def _clear_log(self):
        """Limpia el terminal al cambiar de laboratorio."""
        def _do_clear():
            with self._log_lock:
                self.log_box.configure(state="normal")
                self.log_box.delete("1.0", "end")
                self.log_box.configure(state="disabled")
        self.after(0, _do_clear)

    # ── Status loop ───────────────────────────────────────────────────────────

    def _refresh_all_statuses(self):
        running = 0
        for card in self.cards:
            s = card.refresh_status()
            if s == "running":
                running += 1
        total = len(self.cards)
        self.after(0, lambda: self.global_status.configure(
            text=f"{total} labs  •  {running} activos"
        ))

    def _start_status_loop(self):
        def loop():
            while True:
                time.sleep(STATUS_POLL_INTERVAL)
                self._refresh_all_statuses()
        threading.Thread(target=loop, daemon=True).start()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = WarLabsApp()
    app.mainloop()
