class AutomationSettings:
    def __init__(self, gui_enabled: bool = True, web_enabled: bool = True):
        self.gui_enabled = gui_enabled
        self.web_enabled = web_enabled

    def toggle_gui(self):
        self.gui_enabled = not self.gui_enabled

    def toggle_web(self):
        self.web_enabled = not self.web_enabled
