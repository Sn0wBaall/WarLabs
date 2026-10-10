#!/usr/bin/env python3
"""
WarLabs — Gestor de laboratorios (interfaz gráfica)
Requiere: pip install customtkinter

La lógica de labs y Docker vive en warlabs_core.py, compartida con la CLI.
"""

from __future__ import annotations

import re
import sys
import threading
import time
import tkinter as tk
import tkinter.font as _tkfont
import webbrowser
from pathlib import Path

import customtkinter as ctk

sys.path.insert(0, str(Path(__file__).resolve().parent))

from warlabs_core import (  # noqa: E402
    Lab,
    build_image,
    check_flag,
    container_status,
    discover_labs,
    docker_problem,
    is_solved,
    port_conflicts,
    remove_container,
    reset_progress,
    run_command,
    snapshot,
    snapshot_error,
    start_container,
    stop_container,
    strip_md,
)

# ── Constantes ────────────────────────────────────────────────────────────────
STATUS_POLL_INTERVAL = 5     # segundos entre cada actualización de estado
SEARCH_DEBOUNCE_MS = 200     # evita reconstruir la lista en cada tecla

# ── Fuente ────────────────────────────────────────────────────────────────────
def _resolve_font():
    """Usa Hack Nerd Font si está disponible, si no Courier New."""
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
}

BADGE = {
    "Fácil":   ("#3fb950", "#1a3a22"),
    "Medio":   ("#e3b341", "#2d2a0f"),
    "Difícil": ("#f85149", "#3a1a1a"),
}


# ── Componentes UI ────────────────────────────────────────────────────────────

class StatusDot(ctk.CTkLabel):
    def __init__(self, parent, status="stopped", **kwargs):
        super().__init__(parent, text="●", text_color=self._color(status),
                         font=ctk.CTkFont(size=12), **kwargs)
        self._status = status

    @staticmethod
    def _color(status):
        return {"running": COLORS["green"],
                "paused": COLORS["yellow"],
                "unknown": COLORS["yellow"],
                "exited": COLORS["yellow"]}.get(status, COLORS["muted"])

    def set_status(self, status):
        self._status = status
        color = self._color(status)
        # Siempre desde el hilo principal vía after()
        self.after(0, lambda: self.configure(
            text="?" if status == "unknown" else "●", text_color=color))


class NivelBadge(ctk.CTkLabel):
    def __init__(self, parent, nivel, **kwargs):
        fg, bg = BADGE.get(nivel, (COLORS["muted"], COLORS["surface2"]))
        super().__init__(
            parent, text=nivel,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=fg, fg_color=bg, corner_radius=6, padx=8, pady=2,
            **kwargs
        )


class ConfirmDialog(ctk.CTkToplevel):
    """Diálogo de confirmación con estética consistente con WarLabs."""

    def __init__(self, parent, title: str, message: str, on_confirm,
                 confirm_text="■  Detener"):
        super().__init__(parent)
        self.on_confirm = on_confirm

        self.title("")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg"])
        self.overrideredirect(True)

        outer = ctk.CTkFrame(
            self, fg_color=COLORS["surface"], border_color=COLORS["red"],
            border_width=1, corner_radius=12,
        )
        outer.pack(padx=0, pady=0)

        title_bar = ctk.CTkFrame(outer, fg_color=COLORS["surface2"], corner_radius=0, height=36)
        title_bar.pack(fill="x", padx=0, pady=0)
        title_bar.pack_propagate(False)

        ctk.CTkLabel(
            title_bar, text=f"  ⚠  {title}",
            font=ctk.CTkFont(family=MONO, size=12, weight="bold"),
            text_color=COLORS["red"], anchor="w",
        ).pack(side="left", padx=12, pady=8)

        body = ctk.CTkFrame(outer, fg_color="transparent")
        body.pack(padx=24, pady=(16, 8))

        ctk.CTkLabel(
            body, text=message,
            font=ctk.CTkFont(family=MONO, size=12),
            text_color=COLORS["text"], justify="center", wraplength=320,
        ).pack(pady=(0, 20))

        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack()

        ctk.CTkButton(
            btn_row, text="Cancelar", font=ctk.CTkFont(size=12),
            fg_color=COLORS["surface2"], hover_color=COLORS["border"],
            text_color=COLORS["muted"], border_color=COLORS["border"],
            border_width=1, corner_radius=8, width=110, command=self._cancel,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row, text=confirm_text, font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLORS["red_dim"], hover_color="#5a2020",
            text_color=COLORS["red"], border_color=COLORS["red"],
            border_width=1, corner_radius=8, width=110, command=self._confirm,
        ).pack(side="left")

        self.bind("<Escape>", lambda e: self._cancel())

        self.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        dw, dh = self.winfo_width(), self.winfo_height()
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
            parent, fg_color=COLORS["surface"], border_color=COLORS["border"],
            border_width=1, corner_radius=10, **kwargs
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

        name_box = ctk.CTkFrame(top, fg_color="transparent")
        name_box.grid(row=0, column=0, sticky="w")
        name_box.columnconfigure(0, weight=0)

        ctk.CTkLabel(
            name_box, text=self.lab.name,
            font=ctk.CTkFont(family=MONO, size=14, weight="bold"),
            text_color=COLORS["cyan"], anchor="w",
        ).grid(row=0, column=0, sticky="w")

        if self.lab.flag:
            flag = ctk.CTkLabel(
                name_box, text="⚑", font=ctk.CTkFont(size=12),
                text_color=COLORS["yellow"], anchor="w",
            )
            flag.grid(row=0, column=1, padx=(6, 0))
            flag.bind("<Button-1>", self._click)

        # ✓ de superado: lo que se entrega con `warlabs solve`, guardado en disco.
        if is_solved(self.lab.name):
            done = ctk.CTkLabel(
                name_box, text="✓", font=ctk.CTkFont(family=MONO, size=13, weight="bold"),
                text_color=COLORS["green"], anchor="w",
            )
            done.grid(row=0, column=2, padx=(6, 0))
            done.bind("<Button-1>", self._click)

        self.dot = StatusDot(top, status="stopped")
        self.dot.grid(row=0, column=1, padx=(8, 0))

        NivelBadge(top, self.lab.level).grid(row=0, column=2, padx=(8, 0))

        desc = tk.Text(
            self, bg=COLORS["surface"], fg=COLORS["muted"], font=(MONO, 9),
            bd=0, highlightthickness=0, relief="flat", wrap="word",
            state="normal", padx=0, pady=0, cursor="arrow", height=3,
            spacing1=0, spacing3=0, insertbackground=COLORS["surface"],
        )
        desc.tag_configure("bold", font=(MONO, 9, "bold"), foreground=COLORS["text"])
        desc.tag_configure("code", font=(MONO, 8), foreground=COLORS["green"],
                           background=COLORS["surface2"])
        for part in re.split(r"(`[^`]+`|\*\*[^*]+\*\*)", strip_md(self.lab.desc)):
            desc.insert("end", part)
        desc.configure(state="disabled")
        desc.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))
        desc.bind("<Button-1>", self._click)

    def _click(self, event=None):
        self.on_select(self)

    def set_selected(self, val: bool):
        self._selected = val
        self.configure(
            border_color=COLORS["cyan"] if val else COLORS["border"],
            border_width=2 if val else 1,
        )

    def set_status(self, status: str) -> None:
        """Aplica un estado ya conocido (sin llamar a docker)."""
        # `?` cuando no se pudo preguntar a Docker: un punto apagado diría
        # "parado", que es una conclusión, no un dato.
        self.dot.set_status(status)
        if status == "unknown":
            self.dot.configure(text="?")


# ── Ventana principal ─────────────────────────────────────────────────────────

class WarLabsApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("WarLabs")
        self.geometry("1120x720")
        self.minsize(920, 620)
        self.configure(fg_color=COLORS["bg"])

        self.labs = discover_labs()
        self.cards: list[LabCard] = []
        self.selected_card: LabCard | None = None
        self._busy: set[str] = set()        # labs con una acción en curso
        self._search_job = None
        self._closing = False
        self._log_lock = threading.Lock()
        self._log_pending: list[tuple[str, str, str | None]] = []
        self._log_scheduled = False

        self._build_layout()
        self._populate_labs()
        self._start_status_loop()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

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
        hdr = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=0,
                            border_width=0, height=54)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
        hdr.columnconfigure(1, weight=1)
        hdr.grid_propagate(False)

        ctk.CTkLabel(
            hdr, text="  ⬡  WarLabs",
            font=ctk.CTkFont(family=MONO, size=18, weight="bold"),
            text_color=COLORS["green"],
        ).grid(row=0, column=0, padx=20, pady=14, sticky="w")

        ctk.CTkLabel(
            hdr, text="Gestor de laboratorios de hacking ético",
            font=ctk.CTkFont(size=11), text_color=COLORS["muted"],
        ).grid(row=0, column=1, sticky="w")

        right = ctk.CTkFrame(hdr, fg_color="transparent")
        right.grid(row=0, column=2, padx=20, sticky="e")

        # Limpiar el progreso guardado: los ✓ se releen de ~/.warlabs_solved.json,
        # así que hay que repintar las tarjetas después de borrarlo.
        self.btn_clear_progress = ctk.CTkButton(
            right, text="↺  Limpiar progreso", font=ctk.CTkFont(size=11),
            fg_color=COLORS["surface2"], hover_color=COLORS["border"],
            text_color=COLORS["muted"], border_color=COLORS["border"], border_width=1,
            corner_radius=8, width=150, command=self._confirm_clear_progress,
        )
        self.btn_clear_progress.pack(side="right", padx=(10, 0))

        self.btn_stop_all = ctk.CTkButton(
            right, text="■  Detener todos", font=ctk.CTkFont(size=11),
            fg_color=COLORS["red_dim"], hover_color="#5a2020",
            text_color=COLORS["red"], border_color=COLORS["red"], border_width=1,
            corner_radius=8, width=130, command=self._confirm_stop_all,
        )
        self.btn_stop_all.pack(side="right", padx=(10, 0))

        self.global_status = ctk.CTkLabel(
            right, text="", font=ctk.CTkFont(size=11), text_color=COLORS["muted"],
        )
        self.global_status.pack(side="right")

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=0,
                                    border_width=0, width=320)
        self.sidebar.grid(row=1, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.columnconfigure(0, weight=1)
        self.sidebar.rowconfigure(1, weight=1)

        top_bar = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 4))
        top_bar.columnconfigure(0, weight=1)

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self._on_search_change)
        entry = ctk.CTkEntry(
            top_bar, placeholder_text="Buscar laboratorio...",
            textvariable=self.search_var, fg_color=COLORS["surface2"],
            border_color=COLORS["border"], text_color=COLORS["text"],
            placeholder_text_color=COLORS["muted"], corner_radius=8,
            font=ctk.CTkFont(size=12),
        )
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        entry.bind("<Escape>", lambda e: self.search_var.set(""))

        filter_frame = ctk.CTkFrame(top_bar, fg_color="transparent")
        filter_frame.grid(row=0, column=1, sticky="e")

        self.nivel_var = ctk.StringVar(value="Todos")
        # un único disparador para buscador y filtro: así no se puebla dos veces
        self.nivel_var.trace_add("write", self._on_search_change)
        self._build_nivel_dropdown(filter_frame)

        self.lab_scroll = ctk.CTkScrollableFrame(
            self.sidebar, fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            label_text="", label_fg_color="transparent",
        )
        self.lab_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.lab_scroll.columnconfigure(0, weight=1)

        try:
            self.lab_scroll._label.grid_remove()
        except Exception:
            pass

    def _build_nivel_dropdown(self, parent):
        OPCIONES = [
            ("Todos", COLORS["text"], COLORS["surface2"]),
            ("Fácil", "#3fb950", "#1a3a22"),
            ("Medio", "#e3b341", "#2d2a0f"),
            ("Difícil", "#f85149", "#3a1a1a"),
        ]

        self._dropdown_open = False
        self._dropdown_popup = None

        self._btn_nivel = ctk.CTkButton(
            parent, text="Todos  ▾", font=ctk.CTkFont(size=11),
            fg_color=COLORS["surface2"], hover_color=COLORS["border"],
            text_color=COLORS["text"], border_color=COLORS["border"],
            border_width=1, corner_radius=8, width=100, height=28, anchor="w",
        )
        self._btn_nivel.pack()
        btn = self._btn_nivel

        def _update_btn_color_text(*_):
            val = self.nivel_var.get()
            for label, fg, bg in OPCIONES:
                if label == val:
                    btn.configure(
                        text=f"{label}  ▾", text_color=fg, fg_color=bg,
                        border_color=fg if val != "Todos" else COLORS["border"],
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

            def _select(label):
                # el trace de nivel_var ya repuebla la lista: no filtramos dos veces
                self.nivel_var.set(label)
                popup.destroy()
                self._dropdown_popup = None
                self._dropdown_open = False

            for label, fg, bg in OPCIONES:
                item = tk.Frame(popup, bg=bg, cursor="hand2")
                item.pack(fill="x")
                lbl = tk.Label(item, text=label, bg=bg, fg=fg,
                               font=(MONO, 10, "bold"), padx=10, pady=6, anchor="w")
                lbl.pack(fill="x")
                lbl.bind("<Button-1>", lambda e, s=label: _select(s))
                item.bind("<Button-1>", lambda e, s=label: _select(s))

                def _on_enter(e, w=item):
                    w.configure(bg=COLORS["border"])
                    for child in w.winfo_children():
                        child.configure(bg=COLORS["border"])

                def _on_leave(e, w=item, b=bg):
                    w.configure(bg=b)
                    for child in w.winfo_children():
                        child.configure(bg=b)

                for widget in (item, lbl):
                    widget.bind("<Enter>", _on_enter)
                    widget.bind("<Leave>", _on_leave)

            def _close_on_click_outside(e):
                if self._dropdown_popup is None:
                    return
                try:
                    wx, wy = popup.winfo_rootx(), popup.winfo_rooty()
                    ww, wh = popup.winfo_width(), popup.winfo_height()
                    if not (wx <= e.x_root <= wx + ww and wy <= e.y_root <= wy + wh):
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
            self.main, fg_color=COLORS["surface"], border_color=COLORS["border"],
            border_width=1, corner_radius=10,
        )
        self.info_panel.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        self.info_panel.columnconfigure(1, weight=1)
        self._build_placeholder_info()

        self.tabs = ctk.CTkTabview(
            self.main, fg_color=COLORS["surface"],
            segmented_button_fg_color=COLORS["surface2"],
            segmented_button_selected_color=COLORS["surface"],
            segmented_button_selected_hover_color=COLORS["surface"],
            segmented_button_unselected_color=COLORS["surface2"],
            segmented_button_unselected_hover_color=COLORS["border"],
            text_color=COLORS["text"], border_color=COLORS["border"],
            border_width=1, corner_radius=10,
        )
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.tabs.add("  Terminal  ")
        self.tabs.add("  README  ")

        self.log_box = ctk.CTkTextbox(
            self.tabs.tab("  Terminal  "), fg_color=COLORS["bg"],
            text_color=COLORS["green"], font=ctk.CTkFont(family=MONO, size=12),
            border_width=0, corner_radius=8, wrap="word", state="disabled",
        )
        self.log_box.pack(fill="both", expand=True, padx=8, pady=8)
        self.log_box.tag_config("error", foreground=COLORS["red"])
        self.log_box.tag_config("dim", foreground=COLORS["muted"])
        self.log_box.tag_config("ok", foreground=COLORS["green"])

        self.tabs.tab("  README  ").configure(fg_color=COLORS["bg"])

        self.readme_box = tk.Text(
            self.tabs.tab("  README  "), bg=COLORS["bg"], fg=COLORS["text"],
            font=(MONO, 12), bd=0, relief="flat", highlightthickness=0,
            wrap="word", state="disabled", padx=16, pady=12, cursor="arrow",
            insertbackground=COLORS["bg"], selectbackground=COLORS["surface2"],
            selectforeground=COLORS["text"],
        )
        self.readme_box.pack(fill="both", expand=True, padx=0, pady=0)

        self._bind_zoom(self.readme_box, self._zoom_readme)
        self._bind_zoom(self.log_box, self._zoom_log)

        self._readme_font_size = 12
        self._log_font_size = 12
        self._apply_readme_tags()
        self._log("WarLabs iniciado. Selecciona un laboratorio.")

    def _bind_zoom(self, widget, handler):
        """Ctrl+± / Ctrl+rueda para el zoom de un widget de texto."""
        for seq, delta in [
            ("<Control-Shift-equal>", +1), ("<Control-Shift-plus>", +1),
            ("<Control-plus>", +1), ("<Control-KP_Add>", +1),
            ("<Control-minus>", -1), ("<Control-KP_Subtract>", -1),
        ]:
            widget.bind(seq, lambda e, d=delta: (handler(d), "break")[1])
        widget.bind("<Control-0>", lambda e: (handler(0), "break")[1])

        def _wheel(e):
            handler(+1 if (e.num == 4 or e.delta > 0) else -1)
            return "break"

        widget.bind("<Control-MouseWheel>", _wheel)
        widget.bind("<Control-Button-4>", _wheel)
        widget.bind("<Control-Button-5>", _wheel)

    # ── Panel de información ──────────────────────────────────────────────────

    def _build_placeholder_info(self):
        for w in self.info_panel.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.info_panel, text="Selecciona un laboratorio de la lista",
            font=ctk.CTkFont(size=13), text_color=COLORS["muted"],
        ).pack(pady=24)

    def _build_lab_info(self, lab: Lab):
        for w in self.info_panel.winfo_children():
            w.destroy()

        self.info_panel.columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self.info_panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 2))

        ctk.CTkLabel(
            header, text=lab.name,
            font=ctk.CTkFont(family=MONO, size=18, weight="bold"),
            text_color=COLORS["cyan"],
        ).pack(side="left", anchor="w")
        NivelBadge(header, lab.level).pack(side="left", anchor="w", padx=(10, 0))

        ctk.CTkLabel(
            header, text=lab.image, font=ctk.CTkFont(family=MONO, size=10),
            text_color=COLORS["muted"], anchor="e",
        ).pack(side="right", anchor="e")

        if lab.objective:
            ctk.CTkLabel(
                self.info_panel, text=f"Objetivo: {strip_md(lab.objective)}",
                font=ctk.CTkFont(size=11), text_color=COLORS["purple"],
                anchor="w", justify="left", wraplength=640,
            ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 6))

        ctk.CTkLabel(
            self.info_panel, text=strip_md(lab.desc),
            font=ctk.CTkFont(size=11), text_color=COLORS["muted"],
            anchor="w", justify="left", wraplength=640,
        ).grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 8))

        # ── Endpoints ─────────────────────────────────────────────────────────
        endpoints = lab.endpoints()
        if endpoints:
            ep_frame = ctk.CTkFrame(self.info_panel, fg_color="transparent")
            ep_frame.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 8))
            for endpoint in endpoints:
                text = ctk.CTkLabel(
                    ep_frame, text=f"→ {endpoint.text}",
                    font=ctk.CTkFont(family=MONO, size=11),
                    text_color=COLORS["green"], anchor="w",
                )
                text.pack(side="left", padx=(0, 16))
                if endpoint.url:
                    text.bind("<Button-1>",
                              lambda e, url=endpoint.url: webbrowser.open(url))
                    text.configure(cursor="hand2")

        # ── Avisos del run.sh ────────────────────────────────────────────────
        warnings = lab.warnings()
        if warnings:
            warn = ctk.CTkLabel(
                self.info_panel, text="⚠ " + " ".join(warnings),
                font=ctk.CTkFont(size=10), text_color=COLORS["yellow"],
                anchor="w", justify="left", wraplength=640,
            )
            warn.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 8))

        # ── Botones ───────────────────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(self.info_panel, fg_color="transparent")
        btn_frame.grid(row=5, column=0, sticky="w", padx=18, pady=(0, 14))

        self.btn_launch = self._action_button(
            btn_frame, "▶  Lanzar", COLORS["green"], COLORS["green_dim"], "#255c30",
            lambda: self._launch_lab(lab), width=110)
        self.btn_stop = self._action_button(
            btn_frame, "■  Detener", COLORS["red"], COLORS["red_dim"], "#5a2020",
            lambda: self._confirm_stop(lab), width=110)
        self.btn_restart = self._action_button(
            btn_frame, "⟳  Reiniciar", COLORS["cyan"], COLORS["surface2"],
            COLORS["border"], lambda: self._restart_lab(lab), width=120)
        self.btn_check = self._action_button(
            btn_frame, "⚑  Verificar flag", COLORS["yellow"], COLORS["surface2"],
            COLORS["border"], lambda: self._check_flag(lab), width=140)

        for btn in (self.btn_launch, self.btn_stop, self.btn_restart, self.btn_check):
            btn.pack(side="left", padx=(0, 8))

        self.flag_result = ctk.CTkLabel(
            btn_frame, text="", font=ctk.CTkFont(size=11), text_color=COLORS["muted"],
            anchor="w",
        )
        self.flag_result.pack(side="left", padx=(4, 0))

        self._update_buttons(lab, container_status(lab))

    def _action_button(self, parent, text, fg, bg, hover, command, width=110):
        return ctk.CTkButton(
            parent, text=text, font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=bg, hover_color=hover, text_color=fg, border_color=fg,
            border_width=1, corner_radius=8, width=width, command=command,
        )

    def _update_buttons(self, lab: Lab, status: str):
        """Los botones reflejan el estado real del lab."""
        if not hasattr(self, "btn_launch"):
            return
        running = status == "running"
        busy = lab.name in self._busy
        self.btn_launch.configure(state="disabled" if (running or busy) else "normal")
        self.btn_stop.configure(state="disabled" if (not running or busy) else "normal")
        self.btn_restart.configure(state="disabled" if busy else "normal")
        self.btn_check.configure(state="disabled" if (busy or not lab.flag) else "normal")

    # ── Poblar / filtrar labs ────────────────────────────────────────────────

    def _populate_labs(self):
        for w in self.lab_scroll.winfo_children():
            w.destroy()
        self.cards.clear()

        query = self.search_var.get().strip().lower()
        nivel = self.nivel_var.get()

        filtered = [
            l for l in self.labs
            if (not query or query in l.name.lower() or query in strip_md(l.desc).lower()
                or query in strip_md(l.objective).lower())
            and (nivel == "Todos" or l.level == nivel)
        ]

        if not filtered:
            ctk.CTkLabel(
                self.lab_scroll, text="Sin resultados",
                text_color=COLORS["muted"], font=ctk.CTkFont(size=12),
            ).pack(pady=20)
            self._update_global_status(snapshot())
            return

        for lab in filtered:
            card = LabCard(self.lab_scroll, lab, on_select=self._select_card)
            card.pack(fill="x", padx=4, pady=4)
            self.cards.append(card)

        # Un solo `docker ps -a` para todas las tarjetas (antes era uno por lab,
        # y además se repetía en el hilo principal: por eso se colgaba al teclear).
        snap = snapshot()
        for card in self.cards:
            card.set_status(container_status(card.lab, snap))

        self._update_global_status(snap)

    def _update_global_status(self, snap):
        """Cabecera y botón "Detener todos".

        El recuento de activos va sobre TODOS los labs, no solo los visibles:
        si filtras a un nivel, "Detener todos" debe seguir viendo lo que haya en
        marcha, no solo lo que aparece en la lista.
        """
        running = [l for l in self.labs if container_status(l, snap) == "running"]
        activo = "activo" if len(running) == 1 else "activos"

        error = snapshot_error()
        if error:
            # Un contador a cero cuando no hemos podido preguntar es una
            # conclusión falsa: se dice lo que pasa y por qué.
            self.global_status.configure(text=f"Docker no disponible: {error[:44]}")
            self.global_status.configure(text_color=COLORS["yellow"])
        else:
            self.global_status.configure(
                text=f"{len(self.cards)} labs  •  {len(running)} {activo}")
        self.btn_stop_all.configure(state="normal" if running else "disabled")

    def _on_search_change(self, *_):
        """Debounce: una búsqueda por Escritura, no una por tecla."""
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.after(SEARCH_DEBOUNCE_MS, self._populate_labs)

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
        if lab.name in self._busy:
            return
        self._busy.add(lab.name)
        self._update_buttons(lab, container_status(lab))
        self._log(f"\n[+] Lanzando {lab.name}...")
        threading.Thread(target=self._run_launch, args=(lab,), daemon=True).start()

    def _run_launch(self, lab: Lab):
        for warning in lab.warnings():
            self._log(f"[~] {warning}", error=False)

        conflicts = port_conflicts(lab.ports, ignore=lab.name)
        if conflicts:
            for port, owner in conflicts:
                self._log(f"[!] Puerto {port} ya lo usa el contenedor '{owner}'.", error=True)
            self._log("[!] Detén el otro lab o cambia el puerto en su run.sh.", error=True)
            self._finish_action(lab)
            return

        # Build con salida en directo: en un Pi esto puede tardar minutos y
        # antes la GUI se quedaba congelada sin decir nada.
        def on_line(line: str):
            self._log(line, tag="dim", prefix="    ")

        result = build_image(lab, on_line)
        if not result.ok:
            self._log(f"[!] Error al construir la imagen {lab.image}", error=True)
            for line in result.output.splitlines()[-10:]:
                self._log(line, tag="dim", prefix="    ")
            self._finish_action(lab)
            return

        self._log(f"[+] Imagen {lab.image} construida.", tag="ok")

        ok, error = start_container(lab)
        if not ok:
            self._log(f"[!] Error al iniciar el contenedor:\n{error}", error=True)
            if "sysctl" in error.lower() or "is not allowed" in error:
                self._log("[!] Docker ha rechazado un --sysctl del run.sh.", error=True)
        else:
            self._log(f"[+] Laboratorio {lab.name} en ejecución.", tag="ok")
            for endpoint in lab.endpoints():
                self._log(f"    → {endpoint.text}", tag="ok")
            self.after(0, lambda: self.tabs.set("  Terminal  "))

        self._finish_action(lab)

    def _restart_lab(self, lab: Lab):
        if lab.name in self._busy:
            return
        self._busy.add(lab.name)
        self._update_buttons(lab, container_status(lab))
        self._log(f"\n[~] Reiniciando {lab.name}...")
        threading.Thread(target=self._run_restart, args=(lab,), daemon=True).start()

    def _run_restart(self, lab: Lab):
        if container_status(lab) == "running":
            ok, error = stop_container(lab)
            self._log("[+] Contenedor anterior detenido." if ok else f"[!] {error}")
        self._run_launch(lab)

    def _confirm_stop(self, lab: Lab):
        ConfirmDialog(
            parent=self,
            title="Detener laboratorio",
            message=f"¿Seguro que quieres detener\ny eliminar '{lab.name}'?\n\n"
                    f"This acción no se puede deshacer.",
            on_confirm=lambda: self._stop_lab(lab),
        )

    def _confirm_stop_all(self):
        snap = snapshot(force=True)
        running = [l for l in self.labs if container_status(l, snap) == "running"]
        if not running:
            self._log("[~] No hay laboratorios en ejecución.")
            return
        ConfirmDialog(
            parent=self,
            title="Detener todo",
            message=f"¿Detener y eliminar {len(running)} laboratorios?\n\n"
                    + "\n".join(f"· {lab.name}" for lab in running),
            on_confirm=self._stop_all,
            confirm_text="■  Detener todo",
        )

    def _confirm_clear_progress(self):
        """Diálogo para borrar el progreso de labs superados."""
        superados = [lab.name for lab in self.labs if is_solved(lab.name)]
        if not superados:
            self._log("[~] No hay ningún lab superado que limpiar.")
            return
        ConfirmDialog(
            parent=self,
            title="Limpiar progreso",
            message=f"¿Olvidar {len(superados)} lab(s) superados?\n\n"
                    + "\n".join(f"· {name}" for name in superados)
                    + "\n\nNo toca los contenedores, solo el registro.",
            on_confirm=self._clear_progress,
            confirm_text="↺  Limpiar",
        )

    def _clear_progress(self):
        cleared = reset_progress()
        if cleared:
            self._log(f"[+] Progreso olvidado: {', '.join(sorted(cleared))}.", tag="ok")
        else:
            self._log("[~] No había nada que limpiar.")
        # Los ✓ de las tarjetas salen del fichero borrado: hay que releerlo.
        self._populate_labs()

    def _stop_all(self):
        snap = snapshot(force=True)
        running = [l for l in self.labs if container_status(l, snap) == "running"]
        for lab in running:
            self._stop_lab(lab, confirm=False)

    def _stop_lab(self, lab: Lab, confirm: bool = True):
        if lab.name in self._busy:
            return
        if confirm:
            self._confirm_stop(lab)
            return
        self._busy.add(lab.name)
        self._update_buttons(lab, "running")
        self._log(f"\n[~] Deteniendo {lab.name}...")
        threading.Thread(target=self._run_stop, args=(lab,), daemon=True).start()

    def _run_stop(self, lab: Lab):
        ok, error = stop_container(lab)
        if ok:
            self._log(f"[+] Laboratorio {lab.name} detenido y eliminado.", tag="ok")
        else:
            self._log(f"[!] {error}", error=True)
        self._finish_action(lab)

    def _check_flag(self, lab: Lab):
        if lab.name in self._busy:
            return
        self._busy.add(lab.name)
        self._update_buttons(lab, container_status(lab))
        threading.Thread(target=self._run_check, args=(lab,), daemon=True).start()

    def _run_check(self, lab: Lab):
        result = check_flag(lab)
        if result.solved:
            self._log(f"[✓] ¡Lab superado! Flag: {result.detail}", tag="ok")
        else:
            self._log(f"[~] {result.detail}")
        self._finish_action(lab)
        # el resumen va también junto a los botones
        self.after(0, lambda: self._show_flag_result(result))

    def _show_flag_result(self, result):
        if not hasattr(self, "flag_result"):
            return
        self.flag_result.configure(
            text=f"✓ {result.detail}" if result.solved else result.detail,
            text_color=COLORS["green"] if result.solved else COLORS["muted"],
        )

    def _finish_action(self, lab: Lab):
        """Sale del estado 'ocupado', refresca estado y rehabilita botones."""
        self._busy.discard(lab.name)
        snap = snapshot(force=True)
        status = container_status(lab, snap)
        for card in self.cards:
            if card.lab.name == lab.name:
                card.set_status(status)
        self._update_global_status(snap)
        self.after(0, lambda: self._update_buttons(lab, status))

    # ── README ────────────────────────────────────────────────────────────────

    def _apply_readme_tags(self):
        s = self._readme_font_size
        self.readme_box.tag_configure("h1", font=(MONO, s + 8, "bold"),
                                      foreground=COLORS["cyan"], spacing1=12, spacing3=6)
        self.readme_box.tag_configure("h2", font=(MONO, s + 4, "bold"),
                                      foreground=COLORS["purple"], spacing1=10, spacing3=4)
        self.readme_box.tag_configure("h3", font=(MONO, s + 1, "bold"),
                                      foreground=COLORS["yellow"], spacing1=8, spacing3=2)
        self.readme_box.tag_configure("bold", font=(MONO, s, "bold"),
                                      foreground=COLORS["text"])
        self.readme_box.tag_configure("code", font=(MONO, s - 1), foreground=COLORS["green"],
                                      background=COLORS["surface2"])
        self.readme_box.tag_configure("codeblock", font=(MONO, s - 1),
                                      foreground=COLORS["green"],
                                      background=COLORS["surface2"],
                                      lmargin1=16, lmargin2=16, spacing1=2, spacing3=2)
        self.readme_box.tag_configure("bullet", font=(MONO, s), foreground=COLORS["cyan"],
                                      lmargin1=16, lmargin2=28)
        self.readme_box.tag_configure("muted", font=(MONO, s), foreground=COLORS["muted"])
        self.readme_box.tag_configure("hr", font=(MONO, s), foreground=COLORS["border"],
                                      spacing1=4, spacing3=4)
        self.readme_box.configure(font=(MONO, s))

    def _zoom_readme(self, delta):
        if delta == 0:
            self._readme_font_size = 12
        else:
            self._readme_font_size = max(8, min(28, self._readme_font_size + delta))
        self._apply_readme_tags()

    def _zoom_log(self, delta):
        if delta == 0:
            self._log_font_size = 12
        else:
            self._log_font_size = max(8, min(28, self._log_font_size + delta))
        self.log_box.configure(font=ctk.CTkFont(family=MONO, size=self._log_font_size))

    def _load_readme(self, lab: Lab):
        rb = self.readme_box
        rb.configure(state="normal")
        rb.delete("1.0", "end")

        if not (lab.readme and lab.readme.exists()):
            rb.insert("end", "Sin README disponible para este laboratorio.", "muted")
            rb.configure(state="disabled")
            return

        lines = lab.readme.read_text(encoding="utf-8", errors="replace").splitlines()
        in_code = False
        code_buf: list[str] = []

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
            elif re.match(r"^[-_*]{3,}$", line.strip()):
                rb.insert("end", "─" * 55 + "\n", "hr")
            elif re.match(r"^[-*+] ", line):
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
        for part in re.split(r"(`[^`]+`|\*\*[^*]+\*\*)", text):
            if part.startswith("`") and part.endswith("`"):
                rb.insert("end", part[1:-1], "code")
            elif part.startswith("**") and part.endswith("**"):
                rb.insert("end", part[2:-2], "bold")
            else:
                rb.insert("end", part)

    # ── Terminal log ──────────────────────────────────────────────────────────

    def _log(self, msg, error=False, tag=None, prefix="  "):
        """Escribe en el terminal siempre desde el hilo principal.

        El build puede soltar cientos de líneas seguidas; agruparlas evita generar
        un `after()` por línea desde el hilo que habla con Docker.
        """
        if self._closing:
            return
        tag = tag or ("error" if error else None)

        with self._log_lock:
            self._log_pending.append((prefix, str(msg), tag))
            if self._log_scheduled:
                return
            self._log_scheduled = True

        self.after(40, self._flush_log)

    def _flush_log(self):
        with self._log_lock:
            pending, self._log_pending = self._log_pending, []
            self._log_scheduled = False
        if not pending or self._closing:
            return
        self.log_box.configure(state="normal")
        for prefix, msg, tag in pending:
            for line in msg.splitlines() or [""]:
                self.log_box.insert("end", prefix + line + "\n", tag)
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    def _clear_log(self):
        def _do_clear():
            with self._log_lock:
                self._log_pending.clear()
            self.log_box.configure(state="normal")
            self.log_box.delete("1.0", "end")
            self.log_box.configure(state="disabled")
        self.after(0, _do_clear)

    # ── Status loop ───────────────────────────────────────────────────────────

    def _refresh_all_statuses(self):
        if self._closing:
            return
        # El worker solo habla con Docker; el toque de Tk ocurre una vez, aquí.
        snap = snapshot(force=True)
        self.after(0, lambda: self._apply_statuses(snap))

    def _apply_statuses(self, snap):
        if self._closing:
            return
        for card in self.cards:
            card.set_status(container_status(card.lab, snap))
        self._update_global_status(snap)
        if self.selected_card and hasattr(self, "btn_launch"):
            self._update_buttons(
                self.selected_card.lab,
                container_status(self.selected_card.lab, snap),
            )

    def _start_status_loop(self):
        def loop():
            while True:
                time.sleep(STATUS_POLL_INTERVAL)
                if self._closing:
                    return
                self._refresh_all_statuses()

        threading.Thread(target=loop, daemon=True).start()

    # ── Cierre ────────────────────────────────────────────────────────────────

    def _on_close(self):
        self._closing = True
        running = [l for l in self.labs if container_status(l) == "running"]
        if running:
            names = "\n".join(f"· {lab.name}" for lab in running)
            ConfirmDialog(
                parent=self,
                title="Salir con labs activos",
                message=f"Hay {len(running)} contenedores en marcha:\n\n{names}\n\n"
                        f"¿Detenerlos y salir, o salir igualmente?",
                on_confirm=lambda: self._quit_and_stop(running),
                confirm_text="■  Detener y salir",
            )
            return
        self.destroy()

    def _quit_and_stop(self, labs):
        threading.Thread(target=lambda: [stop_container(l) for l in labs],
                         daemon=True).start()
        self._closing = True
        self.destroy()

    def report_callback_exception(self, exc, val, tb):
        """Silencia los eventos obsoletos de widgets ya destruidos.

        Al cambiar de lab se destruyen y recrean los widgets del panel; queda
        algún `<Configure>` en cola para un botón que ya no existe y customtkinter
        lo reporta como TclError. Los errores de verdad siguen mostrándose.
        """
        if isinstance(val, tk.TclError) and "invalid command name" in str(val):
            return
        super().report_callback_exception(exc, val, tb)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    app = WarLabsApp()
    problem = docker_problem()
    if problem:
        app._log(f"[!] {problem}", error=True)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
