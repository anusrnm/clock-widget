import argparse
import datetime as _datetime
import sys
try:  # winsound only on Windows; fail gracefully elsewhere
    import winsound
except ImportError:  # pragma: no cover
    winsound = None
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from tkinter import colorchooser, simpledialog
from typing import List, Optional, Tuple

try:
    import ctypes
except ImportError:  # pragma: no cover - ctypes is in the stdlib, but keep guard for completeness
    ctypes = None


@dataclass(frozen=True)
class Palette:
    background_top: str = "#1f2937"
    background_bottom: str = "#111827"
    accent: str = "#60a5fa"
    text_primary: str = "#f9fbf9"
    text_secondary: str = "#9ca3af"

@dataclass
class AlarmEntry:
    hour: int
    minute: int
    days: Optional[set]  # None means daily (every day)
    end_time: Optional[_datetime.datetime] = None
    active: bool = False
    duration_seconds: int = 60


class ClockWidget:
    WIDTH = 260
    HEIGHT_TIME_ONLY = 80
    HEIGHT_WITH_DATE = 120
    FONT_FAMILY = "Segoe UI"
    DATE_TEXT_COLOR = "#39ff14"

    def __init__(
        self,
        twenty_four_hour: bool = False,
        stay_on_top: bool = True,
        transparent: bool = True,
        text_color: Optional[str] = None,
        show_date: bool = False,
        alarm_time: Optional[str] = None,
        alarms_file: Optional[str] = None,
    ) -> None:
        self.twenty_four_hour = twenty_four_hour
        self.palette = Palette()
        self.transparent_key = "#010101"
        self.transparent = transparent
        self.show_date = show_date
        self.height = self.HEIGHT_WITH_DATE if self.show_date else self.HEIGHT_TIME_ONLY
        self.root = tk.Tk()
        self.root.title("")
        self.root.geometry(f"{self.WIDTH}x{self.height}")
        self.root.configure(bg=self.palette.background_bottom)
        self.root.overrideredirect(True)
        self.is_topmost = stay_on_top
        self.root.attributes("-topmost", self.is_topmost)
        self.root.attributes("-alpha", 0.96 if not self.transparent else 1.0)

        self.time_font = tkfont.Font(root=self.root, family=self.FONT_FAMILY, size=32, weight="bold")
        self.ampm_font = tkfont.Font(root=self.root, family=self.FONT_FAMILY, size=16)
        self.date_font = tkfont.Font(root=self.root, family=self.FONT_FAMILY, size=13, weight="bold")
        self._compute_layout_metrics()
        self.am_pm_spacing = 6

        normalized_color = self._normalize_hex_color(text_color) if text_color else self.palette.text_primary
        self.text_color = normalized_color
        self.secondary_text_color = self._derive_secondary_color(self.text_color)
        self.date_color = self.DATE_TEXT_COLOR

        self.topmost_var = tk.BooleanVar(value=self.is_topmost)
        self.transparent_var = tk.BooleanVar(value=self.transparent)
        self.show_date_var = tk.BooleanVar(value=self.show_date)

        if sys.platform == "win32":
            self._hide_from_taskbar()
            self._add_shadow()

        self.canvas = tk.Canvas(
            self.root,
            width=self.WIDTH,
            height=self.height,
            highlightthickness=0,
            bd=0,
            bg=self.palette.background_bottom,
        )
        self.canvas.pack(fill="both", expand=True)

        self._draw_static_elements()
        self._create_bindings()
        self._create_context_menu()
        self._place_top_right()

        # Multi-alarm related state
        self.alarms: List[AlarmEntry] = []
        self.alarm_blink_state = True
        self._original_time_color = self.text_color
        self._original_ampm_color = self.secondary_text_color
        self.alarm_triggered = False  # global flag if any alarm currently active
        self.alarm_end_time = None    # retained from single alarm for backward compatibility (not used now)
        # Persistence path (delay importing Path at top-level for minimal change footprint)
        from pathlib import Path as _Path
        self.alarms_file = _Path(alarms_file).expanduser() if alarms_file else _Path.home() / ".desktop_clock_alarms.json"
        # Load persisted alarms (before adding any from CLI so CLI can override duplicates)
        try:
            self._load_alarms()
        except Exception:
            pass
        if alarm_time:
            try:
                entry = self._parse_alarm_definition(alarm_time)
                if entry:
                    self.alarms.append(entry)
            except ValueError:
                pass

        self._update_clock()


    def _hide_from_taskbar(self) -> None:
        if ctypes is None:
            return
        hwnd = self.root.winfo_id()
        # Apply the WS_EX_TOOLWINDOW style and remove WS_EX_APPWINDOW so it stays off the taskbar
        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_APPWINDOW = 0x00040000
        try:
            current_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            new_style = (current_style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOACTIVATE = 0x0010
            SWP_FRAMECHANGED = 0x0020
            ctypes.windll.user32.SetWindowPos(
                hwnd,
                None,
                0,
                0,
                0,
                0,
                SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )
        except Exception:
            # If anything goes wrong, fallback gracefully without crashing
            pass

    def _add_shadow(self) -> None:
        # Add a native drop shadow for a more modern feel (Windows 10+)
        if ctypes is None:
            return
        hwnd = self.root.winfo_id()
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        attribute = ctypes.c_int(1)
        try:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(attribute),
                ctypes.sizeof(attribute),
            )
        except Exception:
            pass

        DWMWA_BORDER_COLOR = 34
        border_color = ctypes.c_int(0x30363d)
        try:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_BORDER_COLOR,
                ctypes.byref(border_color),
                ctypes.sizeof(border_color),
            )
        except Exception:
            pass

    def _create_bindings(self) -> None:
        self.canvas.bind("<ButtonPress-1>", self._start_move)
        self.canvas.bind("<B1-Motion>", self._do_move)
        self.canvas.bind("<Double-Button-1>", lambda _event: self.toggle_time_format())
        self.canvas.bind("<Button-3>", self._show_menu)
        self.root.bind("<Escape>", lambda _event: self.quit())

    def _create_context_menu(self) -> None:
        self.menu = tk.Menu(self.root, tearoff=0, bg="#1f2937", fg="#f9fafb", activebackground="#2563eb", activeforeground="#f9fafb")
        # Transparency
        self.menu.add_checkbutton(
            label="Transparent background",
            variable=self.transparent_var,
            command=self._on_transparent_toggle,
            onvalue=True,
            offvalue=False,
        )
        # Topmost
        self.menu.add_checkbutton(
            label="Stay on top",
            variable=self.topmost_var,
            command=self._on_topmost_toggle,
            onvalue=True,
            offvalue=False,
        )
        # Date toggle
        self.menu.add_checkbutton(
            label="Show date",
            variable=self.show_date_var,
            command=self._on_show_date_toggle,
            onvalue=True,
            offvalue=False,
        )
        self.menu.add_separator()
        # Text color
        self.menu.add_command(label="Text color…", command=self._choose_text_color)
        self.menu.add_separator()
        # Alarms submenu
        alarms_menu = tk.Menu(self.menu, tearoff=0, bg="#1f2937", fg="#f9fafb", activebackground="#2563eb", activeforeground="#f9fafb")
        alarms_menu.add_command(label="Add alarm…", command=self._prompt_add_alarm)
        alarms_menu.add_command(label="List alarms", command=self._show_alarm_list)
        alarms_menu.add_command(label="Stop active alarms", command=self.stop_all_alarms)
        alarms_menu.add_command(label="Clear all alarms", command=self.clear_all_alarms)
        alarms_menu.add_separator()
        alarms_menu.add_command(label="Reload alarms", command=self._reload_alarms)
        alarms_menu.add_command(label="Save alarms", command=self._save_alarms)
        self.menu.add_cascade(label="Alarms", menu=alarms_menu)
        self.menu.add_separator()
        # Time format toggle
        self.menu.add_command(label="Toggle 12/24h", command=self.toggle_time_format)
        self.menu.add_separator()
        # Exit
        self.menu.add_command(label="Exit", command=self.quit)

    def _show_menu(self, event: tk.Event) -> None:
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def toggle_time_format(self) -> None:
        self.twenty_four_hour = not self.twenty_four_hour
        self._update_clock(force=True)

    def toggle_topmost(self) -> None:
        self.set_topmost(not self.is_topmost)

    def set_topmost(self, enabled: bool) -> None:
        self.is_topmost = bool(enabled)
        self.root.attributes("-topmost", self.is_topmost)
        if self.topmost_var.get() != self.is_topmost:
            self.topmost_var.set(self.is_topmost)

    def _on_topmost_toggle(self) -> None:
        self.set_topmost(self.topmost_var.get())

    def set_transparent(self, enabled: bool) -> None:
        self.transparent = bool(enabled)
        if self.transparent_var.get() != self.transparent:
            self.transparent_var.set(self.transparent)
        self._render_background()

    def _on_transparent_toggle(self) -> None:
        self.set_transparent(self.transparent_var.get())

    def set_show_date(self, enabled: bool) -> None:
        new_state = bool(enabled)
        if self.show_date == new_state:
            if self.show_date_var.get() != self.show_date:
                self.show_date_var.set(self.show_date)
            return
        self.show_date = new_state
        if self.show_date_var.get() != self.show_date:
            self.show_date_var.set(self.show_date)
        self.height = self.HEIGHT_WITH_DATE if self.show_date else self.HEIGHT_TIME_ONLY
        self._compute_layout_metrics()
        self._apply_size()
        self._render_background()
        self._update_date_visibility()
        self._update_clock(force=True)

    def _on_show_date_toggle(self) -> None:
        self.set_show_date(self.show_date_var.get())

    def _start_move(self, event: tk.Event) -> None:
        self._drag_offset = (event.x, event.y)

    def _do_move(self, event: tk.Event) -> None:
        x = event.x_root - self._drag_offset[0]
        y = event.y_root - self._drag_offset[1]
        self.root.geometry(f"+{x}+{y}")

    def _draw_static_elements(self) -> None:
        self.background_items: List[int] = []
        self._render_background()

        self.time_text = self.canvas.create_text(
            self.WIDTH // 2,
            self.time_y,
            text="",
            fill=self.text_color,
            font=self.time_font,
            anchor="e",
        )

        self.am_pm_text = self.canvas.create_text(
            self.WIDTH // 2,
            self.time_y,
            text="",
            fill=self.secondary_text_color,
            font=self.ampm_font,
            anchor="w",
        )

        self.date_text = self.canvas.create_text(
            self.WIDTH // 2,
            self.date_y,
            text="",
            fill=self.secondary_text_color,
            font=self.date_font,
        )
        self._apply_text_colors()
        self._update_date_visibility()

    def _draw_gradient_background(self) -> List[int]:
        top_rgb = self._hex_to_rgb(self.palette.background_top)
        bottom_rgb = self._hex_to_rgb(self.palette.background_bottom)
        steps = self.height
        items: List[int] = []
        for i in range(steps):
            ratio = i / max(steps - 1, 1)
            color = self._interpolate(top_rgb, bottom_rgb, ratio)
            hex_color = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
            line = self.canvas.create_line(0, i, self.WIDTH, i, fill=hex_color)
            self.canvas.tag_lower(line)
            items.append(line)
        return items

    def _render_background(self) -> None:
        for item in getattr(self, "background_items", []):
            self.canvas.delete(item)
        self.background_items = []
        if self.transparent:
            self.root.configure(bg=self.transparent_key)
            self.canvas.configure(bg=self.transparent_key)
            self.root.attributes("-alpha", 1.0)
            self._apply_transparent_color(self.transparent_key)
        else:
            self.root.configure(bg=self.palette.background_bottom)
            self.canvas.configure(bg=self.palette.background_bottom)
            self.root.attributes("-alpha", 0.96)
            self._apply_transparent_color(None)
            self.background_items = self._draw_gradient_background()

    def _apply_transparent_color(self, color: str | None) -> None:
        if sys.platform != "win32":
            return
        try:
            if color:
                self.root.attributes("-transparentcolor", color)
            else:
                self.root.attributes("-transparentcolor", "")
        except tk.TclError:
            pass

    def _normalize_hex_color(self, value: Optional[str]) -> str:
        if not value:
            return self.palette.text_primary
        value = value.strip()
        if not value.startswith("#"):
            value = f"#{value}"
        if len(value) == 4:
            value = "#" + "".join(ch * 2 for ch in value[1:])
        if len(value) != 7:
            raise ValueError("Color must be in #RRGGBB format")
        return value.lower()

    def _derive_secondary_color(self, base_hex: str) -> str:
        r, g, b = self._hex_to_rgb(base_hex)
        blend = (
            min(255, int(r + (255 - r) * 0.35)),
            min(255, int(g + (255 - g) * 0.35)),
            min(255, int(b + (255 - b) * 0.35)),
        )
        return self._rgb_to_hex(blend)

    @staticmethod
    def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def _compute_layout_metrics(self) -> None:
        if self.show_date:
            self.time_y = 34
            time_half = self.time_font.metrics("linespace") // 2
            date_half = self.date_font.metrics("linespace") // 2
            min_gap = 2
            self.date_y = self.time_y + time_half + min_gap + date_half
        else:
            self.time_y = self.height // 2
            self.date_y = self.height - 20

    def _apply_size(self) -> None:
        self.canvas.configure(height=self.height)
        if self.root.winfo_viewable():
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            self.root.geometry(f"{self.WIDTH}x{self.height}+{x}+{y}")
        else:
            self.root.geometry(f"{self.WIDTH}x{self.height}")
        self.canvas.coords(self.date_text, self.WIDTH // 2, self.date_y)

    @staticmethod
    def _hex_to_rgb(value: str) -> Tuple[int, int, int]:
        value = value.lstrip("#")
        lv = len(value)
        return tuple(int(value[i : i + lv // 3], 16) for i in range(0, lv, lv // 3))

    @staticmethod
    def _interpolate(start: Tuple[int, int, int], end: Tuple[int, int, int], ratio: float) -> Tuple[int, int, int]:
        return tuple(int(start[i] + (end[i] - start[i]) * ratio) for i in range(3))

    def _update_clock(self, force: bool = False) -> None:
        now = _datetime.datetime.now()
        if self.twenty_four_hour:
            main_time = now.strftime("%H:%M")
            suffix = ""
        else:
            display = now.strftime("%I:%M %p")
            main_time, suffix = display.split(" ")
            main_time = main_time.lstrip("0") or "0"
        date_string = now.strftime("%d-%b-%Y") if self.show_date else ""

        if force or getattr(self, "_last_time", None) != main_time or getattr(self, "_last_suffix", None) != suffix:
            self.canvas.itemconfigure(self.time_text, text=main_time)
            self._layout_time(main_time, suffix)
            self._last_time = main_time
            self._last_suffix = suffix

        if self.show_date:
            if force or getattr(self, "_last_date", None) != date_string:
                self.canvas.itemconfigure(self.date_text, text=date_string)
                self.canvas.coords(self.date_text, self.WIDTH // 2, self.date_y)
                self._last_date = date_string
        elif getattr(self, "_last_date", None) is not None:
            self.canvas.itemconfigure(self.date_text, text="")
            self._last_date = None

        if force:
            self._update_date_visibility()

        # Alarm monitoring (check each tick but only react when minute matches)
        self._evaluate_alarms(now)

        self.root.after(1000, self._update_clock)

    def _layout_time(self, main_time: str, suffix: str) -> None:
        suffix = suffix.strip()
        spacing = self.am_pm_spacing if suffix else 0
        main_width = self.time_font.measure(main_time)
        suffix_width = self.ampm_font.measure(suffix) if suffix else 0
        total_width = main_width + spacing + suffix_width
        left_edge = (self.WIDTH / 2) - (total_width / 2)
        time_x = left_edge + main_width
        self.canvas.coords(self.time_text, time_x, self.time_y)
        if suffix:
            ampm_x = left_edge + main_width + spacing
            self.canvas.itemconfigure(self.am_pm_text, text=suffix, state="normal")
            self.canvas.coords(self.am_pm_text, ampm_x, self.time_y)
        else:
            self.canvas.itemconfigure(self.am_pm_text, text="", state="hidden")

    def _apply_text_colors(self) -> None:
        self.canvas.itemconfigure(self.time_text, fill=self.text_color)
        self.canvas.itemconfigure(self.am_pm_text, fill=self.secondary_text_color)
        self.canvas.itemconfigure(self.date_text, fill=self.date_color)

    def _update_date_visibility(self) -> None:
        state = "normal" if self.show_date else "hidden"
        self.canvas.itemconfigure(self.date_text, state=state)

    def set_text_color(self, color: str) -> None:
        normalized = self._normalize_hex_color(color)
        if normalized == self.text_color:
            return
        self.text_color = normalized
        self.secondary_text_color = self._derive_secondary_color(self.text_color)
        self._apply_text_colors()

    def _choose_text_color(self) -> None:
        _rgb, hex_value = colorchooser.askcolor(initialcolor=self.text_color, parent=self.root, title="Select text color")
        if hex_value:
            self.set_text_color(hex_value)

    def _place_top_right(self) -> None:
        screen_width = self.root.winfo_screenwidth()
        x = screen_width - self.WIDTH - 20
        y = 20
        self.root.geometry(f"{self.WIDTH}x{self.height}+{x}+{y}")

    def run(self) -> None:
        self.root.mainloop()

    def quit(self) -> None:
        try:
            if hasattr(self, "_save_alarms"):
                self._save_alarms()
        except Exception:
            pass
        self.root.destroy()

    # ---------------- Alarm Helpers -----------------
    def _parse_alarm_string(self, value: Optional[str]) -> Optional[Tuple[int, int]]:
        if not value:
            return None
        v = value.strip()
        if not v:
            return None
        # Allow optional AM/PM
        ampm = None
        parts = v.split()
        if len(parts) == 2:
            v, ampm = parts[0], parts[1].lower()
            if ampm not in {"am", "pm"}:
                raise ValueError("Alarm suffix must be AM or PM")
        if ":" not in v:
            raise ValueError("Alarm must be in HH:MM format")
        hh_str, mm_str = v.split(":", 1)
        if not (hh_str.isdigit() and mm_str.isdigit()):
            raise ValueError("Hour and minute must be numeric")
        hour = int(hh_str)
        minute = int(mm_str)
        if ampm:
            if hour < 1 or hour > 12:
                raise ValueError("Hour must be 1-12 when AM/PM specified")
            # Convert to 24h
            if ampm == "pm" and hour != 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
        else:
            if hour < 0 or hour > 23:
                raise ValueError("Hour must be 0-23 in 24h format")
        if minute < 0 or minute > 59:
            raise ValueError("Minute must be 0-59")
        return (hour, minute)

    def set_alarm(self, alarm_str: str) -> None:
        parsed = self._parse_alarm_string(alarm_str)
        self.alarm_time_str = alarm_str
        self.alarm_time_tuple = parsed
        self.alarm_active = parsed is not None
        self.alarm_triggered = False
        self.alarm_end_time = None
        if self.alarm_active:
            self._schedule_alarm_check()

    def clear_alarm(self) -> None:
        self.alarm_time_str = None
        self.alarm_time_tuple = None
        self.alarm_active = False
        self.stop_alarm()

    def stop_alarm(self) -> None:
        if self.alarm_triggered:
            self.alarm_triggered = False
            # Restore colors
            self.canvas.itemconfigure(self.time_text, fill=self._original_time_color)
            self.canvas.itemconfigure(self.am_pm_text, fill=self._original_ampm_color)
        self.alarm_end_time = None

    def _schedule_alarm_check(self) -> None:
        # Placeholder for any future optimization; currently alarm is checked each _update_clock tick.
        pass

    def _start_alarm_effect(self) -> None:
        self.alarm_triggered = True
        self.alarm_end_time = _datetime.datetime.now() + _datetime.timedelta(seconds=60)  # 1 minute alarm window
        self._alarm_blink()
        self._alarm_beep()

    def _alarm_blink(self) -> None:
        if not self.alarm_triggered:
            return
        now = _datetime.datetime.now()
        if self.alarm_end_time and now >= self.alarm_end_time:
            self.stop_alarm()
            return
        # Toggle colors between accent and original
        if self.alarm_blink_state:
            self.canvas.itemconfigure(self.time_text, fill=self.palette.accent)
            self.canvas.itemconfigure(self.am_pm_text, fill=self.palette.accent)
        else:
            self.canvas.itemconfigure(self.time_text, fill=self._original_time_color)
            self.canvas.itemconfigure(self.am_pm_text, fill=self._original_ampm_color)
        self.alarm_blink_state = not self.alarm_blink_state
        # Blink every 500ms
        self.root.after(500, self._alarm_blink)

    def _alarm_beep(self) -> None:
        if not self.alarm_triggered:
            return
        now = _datetime.datetime.now()
        if self.alarm_end_time and now >= self.alarm_end_time:
            return
        if winsound:
            try:
                winsound.Beep(880, 250)  # frequency, duration ms
            except RuntimeError:
                pass
        else:  # Fallback - no winsound (unlikely on Windows); do nothing
            pass
        # Schedule next beep every 2 seconds
        self.root.after(2000, self._alarm_beep)

    def _prompt_set_alarm(self) -> None:
        alarm_str = simpledialog.askstring("Set Alarm", "Enter alarm time (HH:MM or HH:MM AM/PM)", parent=self.root)
        if alarm_str:
            try:
                self.set_alarm(alarm_str)
            except ValueError as exc:
                tk.messagebox.showerror("Invalid alarm", str(exc))
    # -------- Multi Alarm Support ---------
    def _parse_alarm_definition(self, spec: str) -> Optional[AlarmEntry]:
        if not spec:
            return None
        # Extract duration if present (+NNs or +NNm) at end
        duration_seconds = 60
        dur_index = spec.find("+")
        if dur_index != -1:
            maybe_dur = spec[dur_index + 1 :].strip()
            spec_core = spec[:dur_index].rstrip()
            if maybe_dur:
                unit = maybe_dur[-1].lower()
                number_part = maybe_dur[:-1] if unit in {"s", "m"} else maybe_dur
                if number_part.isdigit():
                    value = int(number_part)
                    if unit == "m":
                        value *= 60
                    duration_seconds = max(1, value)
                # else ignore malformed duration
            spec = spec_core
        parts = spec.split("@", 1)
        time_part = parts[0].strip()
        days_part = parts[1].strip() if len(parts) == 2 else None
        # Reuse single alarm parser (returns hour, minute)
        hm = self._parse_alarm_string(time_part)
        if not hm:
            return None
        hour, minute = hm
        days_set: Optional[set] = None
        if days_part:
            if days_part.lower() in {"daily", "everyday", "all"}:
                days_set = None
            else:
                tokens = [t.strip() for t in days_part.split(",") if t.strip()]
                valid_days = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
                mapped = set()
                for t in tokens:
                    key = t[:3].lower()
                    if key not in valid_days:
                        raise ValueError(f"Invalid day: {t}")
                    mapped.add(key)
                days_set = mapped
        return AlarmEntry(hour=hour, minute=minute, days=days_set, duration_seconds=duration_seconds)

    def _evaluate_alarms(self, now: _datetime.datetime) -> None:
        if not self.alarms:
            return
        any_active = False
        weekday_map = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        today_key = weekday_map[now.weekday()]
        for alarm in self.alarms:
            # Clear finished
            if alarm.active and alarm.end_time and now >= alarm.end_time:
                alarm.active = False
                alarm.end_time = None
            # Trigger if time matches and (days None or includes today)
            if not alarm.active and now.hour == alarm.hour and now.minute == alarm.minute:
                if alarm.days is None or today_key in alarm.days:
                    alarm.active = True
                    alarm.end_time = now + _datetime.timedelta(seconds=alarm.duration_seconds)
        # Determine if any currently active
        for alarm in self.alarms:
            if alarm.active:
                any_active = True
                break
        if any_active:
            if not self.alarm_triggered:
                self.alarm_triggered = True
                self._alarm_blink()  # start blinking loop
                self._alarm_beep()   # start beep loop
        else:
            if self.alarm_triggered:
                self.alarm_triggered = False
                # Restore colors
                self.canvas.itemconfigure(self.time_text, fill=self._original_time_color)
                self.canvas.itemconfigure(self.am_pm_text, fill=self._original_ampm_color)

    def stop_all_alarms(self) -> None:
        for alarm in self.alarms:
            alarm.active = False
            alarm.end_time = None
        self.alarm_triggered = False
        self.canvas.itemconfigure(self.time_text, fill=self._original_time_color)
        self.canvas.itemconfigure(self.am_pm_text, fill=self._original_ampm_color)
        if hasattr(self, "_save_alarms"):
            self._save_alarms()

    def clear_all_alarms(self) -> None:
        self.stop_all_alarms()
        self.alarms.clear()
        if hasattr(self, "_save_alarms"):
            self._save_alarms()

    def _prompt_add_alarm(self) -> None:
        spec = simpledialog.askstring(
            "Add Alarm",
            "Enter alarm: HH:MM or HH:MM AM/PM optionally @days and +duration (e.g. 07:30@Mon,Wed,Fri+90s, 07:30+2m, 07:30@Daily)",
            parent=self.root,
        )
        if not spec:
            return
        try:
            entry = self._parse_alarm_definition(spec)
            if entry:
                self.alarms.append(entry)
                try:
                    self._save_alarms()
                except Exception:
                    pass
        except ValueError as exc:
            tk.messagebox.showerror("Invalid alarm", str(exc))

    def _show_alarm_list(self) -> None:
        lines = []
        for a in self.alarms:
            days_desc = "Daily" if a.days is None else ",".join(sorted(d.title() for d in a.days))
            lines.append(f"{a.hour:02d}:{a.minute:02d} @ {days_desc}")
        if not lines:
            lines = ["(No alarms)"]
        tk.messagebox.showinfo("Alarms", "\n".join(lines))

    # ----- Persistence helpers -----
    def _serialize_alarm(self, a: AlarmEntry) -> dict:
        return {
            "hour": a.hour,
            "minute": a.minute,
            "days": None if a.days is None else sorted(a.days),
            "duration": a.duration_seconds,
        }

    def _deserialize_alarm(self, data: dict) -> Optional[AlarmEntry]:
        try:
            hour = int(data.get("hour"))
            minute = int(data.get("minute"))
            duration = int(data.get("duration", 60))
            days_raw = data.get("days")
            days_set = None if days_raw is None else {str(d)[:3].lower() for d in days_raw}
            return AlarmEntry(hour=hour, minute=minute, days=days_set, duration_seconds=duration)
        except Exception:
            return None

    def _load_alarms(self) -> None:
        try:
            if not getattr(self, "alarms_file", None) or not self.alarms_file.exists():
                return
            import json as _json
            with self.alarms_file.open("r", encoding="utf-8") as f:
                raw = _json.load(f)
            if isinstance(raw, list):
                for item in raw:
                    entry = self._deserialize_alarm(item)
                    if entry:
                        self.alarms.append(entry)
        except Exception:
            pass

    def _save_alarms(self) -> None:
        try:
            if not getattr(self, "alarms_file", None):
                return
            import json as _json
            payload = [self._serialize_alarm(a) for a in self.alarms]
            with self.alarms_file.open("w", encoding="utf-8") as f:
                _json.dump(payload, f, indent=2)
        except Exception:
            pass

    def _reload_alarms(self) -> None:
        self.alarms.clear()
        self._load_alarms()
        tk.messagebox.showinfo("Alarms", "Reloaded alarms from disk.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Floating desktop clock widget.")
    parser.add_argument(
        "--24h",
        dest="twenty_four",
        action="store_true",
        help="Start in 24-hour format instead of the default 12-hour.",
    )
    parser.add_argument(
        "--12h",
        dest="twenty_four",
        action="store_false",
        help="Start in 12-hour format (default).",
    )
    parser.add_argument(
        "--no-topmost",
        dest="topmost",
        action="store_false",
        help="Start without keeping the window above other windows.",
    )
    parser.add_argument(
        "--show-date",
        dest="show_date",
        action="store_true",
        help="Display the date under the time.",
    )
    parser.add_argument(
        "--no-date",
        dest="show_date",
        action="store_false",
        help="Hide the date under the time (default).",
    )
    parser.add_argument(
        "--transparent",
        dest="transparent",
        action="store_true",
        help="Start with a fully transparent background (default).",
    )
    parser.add_argument(
        "--opaque",
        dest="transparent",
        action="store_false",
        help="Start with an opaque background.",
    )
    parser.set_defaults(twenty_four=False, topmost=True, show_date=False, transparent=True)
    parser.add_argument(
        "--text-color",
        dest="text_color",
        type=str,
        help="Hex color for the time text (e.g., #ffcc00).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run a quick self-check and print the current time without starting the GUI.",
    )
    parser.add_argument(
        "--alarm",
        action="append",
        metavar="SPEC",
        help=(
            "Add an alarm. Format: HH:MM or HH:MM AM/PM optionally followed by @days (e.g., 07:30@Mon,Wed,Fri or 07:30@Daily). "
            "May be repeated."
        ),
    )
    parser.add_argument(
        "--alarms-file",
        type=str,
        help="Path to JSON file storing persistent alarms (defaults to ~/.desktop_clock_alarms.json).",
    )
    return parser.parse_args()


def _self_check(twenty_four_hour: bool) -> None:
    now = _datetime.datetime.now()
    fmt = "%H:%M" if twenty_four_hour else "%I:%M %p"
    print(f"Current time: {now.strftime(fmt)}")


def main() -> None:
    args = _parse_args()
    if args.check:
        _self_check(twenty_four_hour=args.twenty_four)
        return
    try:
        first_alarm = args.alarm[0] if args.alarm else None
        widget = ClockWidget(
            twenty_four_hour=args.twenty_four,
            stay_on_top=args.topmost,
            transparent=args.transparent,
            text_color=args.text_color,
            show_date=args.show_date,
            alarm_time=first_alarm,
            alarms_file=args.alarms_file,
        )
        # Add remaining alarms if any
        if args.alarm and len(args.alarm) > 1:
            for spec in args.alarm[1:]:
                try:
                    entry = widget._parse_alarm_definition(spec)
                    if entry:
                        widget.alarms.append(entry)
                except ValueError:
                    pass
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        widget.run()
    except KeyboardInterrupt:
        widget.quit()
        print("\nKeyboard interrupt received, exiting.", file=sys.stderr)


if __name__ == "__main__":
    main()
