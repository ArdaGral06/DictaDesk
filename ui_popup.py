import threading

try:
    import tkinter as tk
except Exception:
    tk = None

from config import AGENT_STEP_POPUP_MS, POPUP_DURATION_MS, USE_POPUP_STATUS

_BG = "#15202b"
_FG = "#e8edf4"
_SUB_FG = "#8fb4d9"
_ACCENT = "#3d7dd4"

_lock = threading.Lock()
_root = None
_title_label = None
_message_label = None
_frame = None
_after_id = None
_thread_started = False


def _ensure_ui_thread():
    global _root, _title_label, _message_label, _frame, _thread_started

    def _loop():
        global _root, _title_label, _message_label, _frame
        try:
            _root = tk.Tk()
            _root.withdraw()
            _root.title("")
            _root.attributes("-topmost", True)
            _root.overrideredirect(True)
            _root.configure(bg=_ACCENT)
            _frame = tk.Frame(_root, bg=_BG, padx=2, pady=2)
            _frame.pack(fill="both", expand=True)
            inner = tk.Frame(_frame, bg=_BG, padx=14, pady=10)
            inner.pack(fill="both", expand=True)
            _title_label = tk.Label(
                inner,
                text="",
                bg=_BG,
                fg=_SUB_FG,
                font=("Segoe UI", 10),
                wraplength=680,
                justify="center",
            )
            _title_label.pack()
            _message_label = tk.Label(
                inner,
                text="",
                bg=_BG,
                fg=_FG,
                font=("Segoe UI", 12, "bold"),
                wraplength=720,
                justify="center",
            )
            _message_label.pack(pady=(4, 0))
            _root.mainloop()
        except Exception:
            pass

    if not _thread_started:
        threading.Thread(target=_loop, daemon=True).start()
        _thread_started = True
        for _ in range(40):
            if _root is not None:
                break
            threading.Event().wait(0.05)


def _position_window():
    if _root is None:
        return
    _root.update_idletasks()
    w = _root.winfo_width()
    h = _root.winfo_height()
    sw = _root.winfo_screenwidth()
    x = int((sw - w) / 2)
    y = 24
    _root.geometry(f"{w}x{h}+{x}+{y}")


def show_status_popup(
    message: str,
    hold_ms: int | None = None,
    *,
    title: str | None = None,
):
    if not message and not title:
        return
    if not USE_POPUP_STATUS or tk is None:
        if title:
            print(f"{title}\n{message}".strip())
        else:
            print(message)
        return

    duration = hold_ms if hold_ms is not None else POPUP_DURATION_MS

    def _apply():
        global _after_id
        try:
            _ensure_ui_thread()
            if _root is None or _message_label is None:
                if title:
                    print(f"{title}\n{message}".strip())
                else:
                    print(message)
                return
            with _lock:
                if _title_label is not None:
                    if title:
                        _title_label.config(text=title)
                        _title_label.pack(pady=(0, 0))
                    else:
                        _title_label.config(text="")
                        _title_label.pack_forget()
                _message_label.config(text=message or "")
                _root.deiconify()
                _root.lift()
                _position_window()
                if _after_id is not None:
                    try:
                        _root.after_cancel(_after_id)
                    except Exception:
                        pass
                _after_id = _root.after(duration, _hide_popup)
        except Exception:
            if title:
                print(f"{title}\n{message}".strip())
            else:
                print(message)

    if threading.current_thread() is threading.main_thread() and _root is not None:
        _apply()
    else:
        if _root is not None:
            try:
                _root.after(0, _apply)
            except Exception:
                threading.Thread(target=_apply, daemon=True).start()
        else:
            threading.Thread(target=_apply, daemon=True).start()


def show_agent_step_popup(
    step: int,
    total: int,
    action: str,
    value: str = "",
    *,
    ui_lang: str = "tr",
):
    from i18n import t

    short_value = (value or "").strip()
    if len(short_value) > 48:
        short_value = short_value[:45] + "..."
    title = t(ui_lang, "command_popup_step_title", step=step, total=total)
    message = t(
        ui_lang,
        "command_popup_step",
        step=step,
        total=total,
        action=action or "-",
        value=short_value,
    )
    show_status_popup(message, hold_ms=AGENT_STEP_POPUP_MS, title=title)


def _hide_popup():
    global _after_id
    try:
        if _root is not None:
            _root.withdraw()
    except Exception:
        pass
    _after_id = None


def show_confirm_popup(message: str, ui_lang: str, on_result):
    if tk is None:
        print(message)
        return

    def _apply():
        try:
            _ensure_ui_thread()
            if _root is None:
                print(message)
                return
            from i18n import t

            win = tk.Toplevel(_root)
            win.title("")
            win.attributes("-topmost", True)
            win.configure(bg=_ACCENT)
            win.resizable(False, False)
            frame = tk.Frame(win, bg=_BG, padx=16, pady=12)
            frame.pack(padx=2, pady=2)
            tk.Label(
                frame,
                text=message,
                bg=_BG,
                fg=_FG,
                font=("Segoe UI", 11, "bold"),
                padx=8,
                pady=8,
                wraplength=640,
                justify="center",
            ).pack()
            btn_frame = tk.Frame(frame, bg=_BG)
            btn_frame.pack(pady=(4, 0))

            def _choose(value: str):
                try:
                    win.destroy()
                except Exception:
                    pass
                on_result(value)

            tk.Button(
                btn_frame,
                text=t(ui_lang, "confirm_popup_yes"),
                command=lambda: _choose("y"),
                width=10,
            ).pack(side="left", padx=6)
            tk.Button(
                btn_frame,
                text=t(ui_lang, "confirm_popup_no"),
                command=lambda: _choose("n"),
                width=10,
            ).pack(side="left", padx=6)
            win.update_idletasks()
            sw = win.winfo_screenwidth()
            w = win.winfo_width()
            h = win.winfo_height()
            win.geometry(f"{w}x{h}+{(sw - w) // 2}+80")
            _root.deiconify()
        except Exception:
            print(message)

    if _root is not None:
        try:
            _root.after(0, _apply)
        except Exception:
            threading.Thread(target=_apply, daemon=True).start()
    else:
        threading.Thread(target=_apply, daemon=True).start()
