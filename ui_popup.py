import threading

try:
    import tkinter as tk
except Exception:
    tk = None

from config import AGENT_STEP_POPUP_MS, POPUP_DURATION_MS, USE_POPUP_STATUS


_lock = threading.Lock()
_root = None
_label = None
_after_id = None
_thread_started = False


def _ensure_ui_thread():
    global _root, _label, _thread_started

    def _loop():
        global _root, _label
        try:
            _root = tk.Tk()
            _root.withdraw()
            _root.title("")
            _root.attributes("-topmost", True)
            _root.overrideredirect(True)
            _root.configure(bg="#111111")
            _label = tk.Label(
                _root,
                text="",
                bg="#111111",
                fg="#ffffff",
                font=("Segoe UI", 12, "bold"),
                padx=16,
                pady=8,
                wraplength=720,
                justify="center",
            )
            _label.pack()
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
    y = 20
    _root.geometry(f"{w}x{h}+{x}+{y}")


def show_status_popup(message: str, hold_ms: int | None = None):
    if not message:
        return
    if not USE_POPUP_STATUS or tk is None:
        print(message)
        return

    duration = hold_ms if hold_ms is not None else POPUP_DURATION_MS

    def _apply():
        global _after_id
        try:
            _ensure_ui_thread()
            if _root is None or _label is None:
                print(message)
                return
            with _lock:
                _label.config(text=message)
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
    message = t(
        ui_lang,
        "command_popup_step",
        step=step,
        total=total,
        action=action or "-",
        value=short_value,
    )
    show_status_popup(message, hold_ms=AGENT_STEP_POPUP_MS)


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
            win.configure(bg="#111111")
            win.resizable(False, False)
            tk.Label(
                win,
                text=message,
                bg="#111111",
                fg="#ffffff",
                font=("Segoe UI", 11, "bold"),
                padx=16,
                pady=10,
                wraplength=640,
                justify="center",
            ).pack()
            btn_frame = tk.Frame(win, bg="#111111")
            btn_frame.pack(pady=(0, 12))

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
