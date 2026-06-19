import threading

try:
    import tkinter as tk
except Exception:
    tk = None

from config import POPUP_DURATION_MS, USE_POPUP_STATUS


def show_status_popup(message: str):
    if not USE_POPUP_STATUS or tk is None:
        print(message)
        return

    def _worker():
        try:
            root = tk.Tk()
            root.title("")
            root.attributes("-topmost", True)
            root.overrideredirect(True)
            root.configure(bg="#111111")
            label = tk.Label(
                root,
                text=message,
                bg="#111111",
                fg="#ffffff",
                font=("Segoe UI", 12, "bold"),
                padx=16,
                pady=8,
            )
            label.pack()
            root.update_idletasks()
            w = root.winfo_width()
            h = root.winfo_height()
            sw = root.winfo_screenwidth()
            x = int((sw - w) / 2)
            y = 20
            root.geometry(f"{w}x{h}+{x}+{y}")
            root.after(POPUP_DURATION_MS, root.destroy)
            root.mainloop()
        except Exception:
            print(message)

    threading.Thread(target=_worker, daemon=True).start()
