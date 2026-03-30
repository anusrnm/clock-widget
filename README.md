# Desktop Clock Widget

A sleek, always-on-top clock widget for Windows desktops. It floats in the top-right corner, stays off the taskbar, and delivers a calm minute-by-minute time readout.

## Features

- Smooth gradient background with crisp Segoe UI typography.
- Toggle between 12-hour and 24-hour display (double-click or use context menu).
- Optional "Stay on top" behavior accessible from the context menu or CLI.
- Transparent by default—switch to an opaque gradient anytime via the context menu or CLI flag.
- Shows hours and minutes without the noisy seconds (double-click still toggles between 12h/24h).
- Date line is hidden by default for a compact footprint—enable it when you need it.
- Right-click the widget for a quick menu with **Transparent background**, **Stay on top**, **Show date**, **Text color…**, **Toggle 12/24h**, and **Exit** options.
- Drag the widget anywhere on your screen.
- Escape key instantly closes the widget.
- Optional `--check` flag prints the current time once without launching the UI (handy for automated checks).

## Requirements

- Windows 10 or later (native drop shadow leverages Windows APIs).
- Python 3.9+

All dependencies are from the standard library; no additional packages are needed.

## Run It

```cmd
python clock_widget.py
```

### Optional Flags

- Force 12-hour mode (default if no flag supplied):

  ```cmd
  python clock_widget.py --12h
  ```

- Start in 24-hour mode:

  ```cmd
  python clock_widget.py --24h
  ```

- Start without forcing the window to stay above others:

  ```cmd
  python clock_widget.py --no-topmost
  ```

- Start in opaque mode (default is transparent):

  ```cmd
  python clock_widget.py --opaque
  ```

- (Re)force transparency explicitly:

  ```cmd
  python clock_widget.py --transparent
  ```

- Pick a custom text color:

  ```cmd
  python clock_widget.py --text-color #ffcc00
  ```

- Show the date line (hidden by default):

  ```cmd
  python clock_widget.py --show-date
  ```

- Explicitly hide the date line:

  ```cmd
  python clock_widget.py --no-date
  ```

- Perform a non-UI self-check:

  ```cmd
  python clock_widget.py --check
  ```

- Start with an alarm (blinks + beeps for 60s when reached):

  ```cmd
  python clock_widget.py --alarm 07:45
  python clock_widget.py --alarm "07:45 AM"
  ```

  Right-click the widget to Set alarm…, Clear alarm, or Stop alarm early.

### Multiple & Repeating Alarms

You can specify multiple alarms by repeating `--alarm`:

```cmd
python clock_widget.py --alarm 07:30@Mon,Wed,Fri --alarm 08:00@Daily --alarm 09:15 PM@Tue,Thu
```

Format:

```
HH:MM[ AM|PM][@Day1,Day2,...][+Duration]
```

Components:

- `HH:MM` – 24h or 12h with AM/PM.
- `@Day1,Day2,...` – Optional day filter. Accepts Mon,Tue,Wed,Thu,Fri,Sat,Sun (case-insensitive, first 3 letters used). `@Daily`, `@Everyday`, or `@All` means every day.
- `+Duration` – Optional alarm active length. Suffix `s` for seconds or `m` for minutes. Examples: `+90s`, `+2m`. Default is 60s if omitted.

Examples:

```cmd
python clock_widget.py --alarm 07:30@Mon,Wed,Fri+90s --alarm 08:00@Daily+2m
python clock_widget.py --alarm "09:15 PM+30s" --alarm 06:00@Sat,Sun
```

Context menu Alarms submenu lets you add, list, stop, and clear alarms at runtime. The list shows alarms in `HH:MM @ Days` format. Duration is honored internally (blink/beep stops when the window ends).

### Alarm Persistence

Alarms can persist across sessions.

By default they are saved to:

```
%USERPROFILE%\.desktop_clock_alarms.json
```

Use a custom file with:

```cmd
python clock_widget.py --alarms-file C:\path\to\my_alarms.json
```

They are automatically saved when you add, clear, stop all, or exit. You can manually reload or save via the Alarms submenu (Reload alarms / Save alarms). File format is a JSON array:

```json
[
  {"hour":7,"minute":30,"days":["mon","wed","fri"],"duration":90},
  {"hour":8,"minute":0,"days":null,"duration":120}
]
```

## Tips

- Double-click the widget to toggle between 12-hour and 24-hour formats.
- Use the context menu to quickly switch transparency, topmost behavior, or the date line.
- Toggle the **Show date** check to expand or shrink the widget without restarting.
- The **Text color…** menu item opens a color picker; the CLI flag accepts `#RGB` or `#RRGGBB` formats.
- If the widget ever hides behind another window, press `Alt+Tab` to bring it back or re-run the script.

## Run at Startup

1. Create a tiny launcher so Windows can start the clock:
   - **Batch file**: save `launch_clock.cmd` 
   - **Shortcut**: or create a shortcut that targets
     ```cmd
     C:\Windows\System32\cmd.exe /c "cd /d C:\path\to\clock && python clock_widget.py --transparent --no-date"
     ```
2. Place the launcher where Windows will run it:
   - **Startup folder** (quick): press `Win + R`, enter `shell:startup`, and drop in the batch file or shortcut.
   - **Task Scheduler** (more control): create a task that triggers “At log on” and starts `python` with `clock_widget.py` in the clock folder.
3. Log off/on (or reboot) once to confirm the clock appears automatically.

Enjoy your distraction-free desktop clock!
