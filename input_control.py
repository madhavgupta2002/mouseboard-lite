"""Translate a few validated messages into desktop mouse and keyboard actions."""

import math


class InputController:
    def __init__(self, backend=None):
        if backend is None:
            import pyautogui as backend
        self.backend = backend
        self.backend.PAUSE = 0
        self.held = set()

    @staticmethod
    def number(value, limit):
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError("Expected a number")
        if not math.isfinite(value):
            raise ValueError("Expected a finite number")
        return round(max(-limit, min(limit, value)))

    def handle(self, message):
        if not isinstance(message, dict):
            raise ValueError("Expected a message object")
        kind = message.get("type")
        if kind == "move":
            self.backend.moveRel(
                self.number(message.get("x"), 100),
                self.number(message.get("y"), 100),
            )
        elif kind == "button":
            button, down = message.get("button"), message.get("down")
            if button not in ("left", "right") or not isinstance(down, bool):
                raise ValueError("Invalid mouse button")
            if down and button not in self.held:
                self.backend.mouseDown(button=button)
                self.held.add(button)
            elif not down and button in self.held:
                self.backend.mouseUp(button=button)
                self.held.remove(button)
        elif kind == "scroll":
            self.backend.scroll(self.number(message.get("y"), 12))
        elif kind == "center":
            width, height = self.backend.size()
            self.backend.moveTo(width // 2, height // 2)
        elif kind == "text":
            remove, text = message.get("remove"), message.get("text")
            if type(remove) is not int or not 0 <= remove <= 256:
                raise ValueError("Invalid deletion length")
            if not isinstance(text, str) or len(text) > 256:
                raise ValueError("Text is too long")
            if any(not 32 <= ord(character) <= 126 for character in text):
                raise ValueError("Use an English keyboard and printable ASCII text")
            if remove:
                self.backend.press("backspace", presses=remove)
            if text:
                self.backend.write(text)
        elif kind == "key":
            key = message.get("key")
            if key not in ("enter", "backspace", "tab", "esc", "left", "right", "up", "down"):
                raise ValueError("Unsupported key")
            self.backend.press(key)
        elif kind == "release":
            self.release()
        elif kind != "ping":
            raise ValueError("Unknown message type")

    def release(self):
        # A connection loss must release a drag, even at PyAutoGUI's failsafe corner.
        held, self.held = self.held, set()
        failsafe = self.backend.FAILSAFE
        self.backend.FAILSAFE = False
        try:
            for button in held:
                self.backend.mouseUp(button=button)
        finally:
            self.backend.FAILSAFE = failsafe
