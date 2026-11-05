# MouseBoard Lite

Turn a phone into a Wi-Fi mouse and keyboard using its browser. No phone APK or
desktop app installer: a small Python script runs on the computer.

This is a smaller, independent companion to
[MouseBoard](https://github.com/madhavgupta2002/mouseboard).

The phone and computer communicate directly over the same Wi-Fi. No account,
cloud service, internet connection, Bluetooth, or USB connection is used at runtime.

## What it does

- Turn the phone left/right and tilt it up/down to move the pointer.
- Tap Left or Right to click; keep a finger down to drag.
- Swipe the middle strip to scroll.
- Tap Recenter to reset the neutral pose and move the cursor to the screen center.
- Type with the phone's normal keyboard. Motion pauses while typing.
- Pause motion separately from clicking and typing.

This is a classroom MVP, designed to be read and explained.

## Run on your computer

Use Python **3.10+**. macOS and Windows are the intended desktop platforms.
The phone needs a browser with orientation sensors, such as Chrome on Android.

**Mac**

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python server.py
```

After setup, you can also double-click `Start MouseBoard Lite.command` on Mac.

If `python3 --version` is older than 3.10, install a current Python first.
On Mac, allow the terminal running Python in **System Settings → Privacy &
Security → Accessibility**, then restart the script. Screen Recording is not used.

**Windows, PowerShell**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe server.py
```

Allow Python on **private networks** if Windows Firewall asks.

## Connect your phone

### Classroom demo without a certificate (Chrome on Android)

Run `python server.py --demo-http`, or double-click `Start HTTP Demo.command` on
Mac. This uses plain HTTP and generates no certificates. It requires one
temporary, per-address Chrome test setting:

1. Scan **Phone setup** to see your computer's exact controller address.
2. Scan **Chrome settings QR**. If the scanner does not open the settings,
   copy the scanned text and paste it into Chrome's address bar. The setup page
   also has a **Copy address** button.
3. Under **Insecure origins treated as secure**, add the exact controller
   address shown on the setup page, including `http://` and the port.
4. Set the flag to **Enabled** and tap **Relaunch**.
5. Scan **Pair phone**, open it in Chrome, and tap **Connect**, then **Recenter**.

Use this mode only on your own trusted Wi-Fi: traffic, typing, and the pairing
code are **not encrypted**. After your demo, set the flag back to **Default** and
relaunch Chrome. Do not use a wildcard or add unrelated sites.

This is Chrome's [development workaround for testing secure-context features](https://www.chromium.org/Home/chromium-security/deprecating-powerful-features-on-insecure-origins/),
not a production deployment method. A managed browser may block the setting.
If the computer's Wi-Fi address changes, update the allowed address.

### HTTPS mode with a local certificate

Run `python server.py` or `Start MouseBoard Lite.command`.

The script opens a setup page on the computer with two QR codes:

1. Join the **same trusted Wi-Fi** on both devices.
2. Scan **Phone setup**. Download `MouseBoard-Lite-CA.crt`.
3. Install that certificate on your own phone. On Samsung, search Settings for
   **CA certificate**, then use **Install from device storage → CA certificate**.
   Menu wording varies by Android version; follow the warning shown by Android.
4. Scan **Pair phone** from the computer's page. Open the HTTPS page and tap
   **Connect**. Allow motion sensors if asked.
5. Hold the phone screen-up with its top edge away from you, then tap **Recenter**.

Browsers normally expose motion sensors only to secure pages. HTTPS mode's
certificate is created locally and kept in the ignored `.local/` directory.
Only the public certificate is downloadable; its private key stays on your
computer. You only install the certificate once per computer, unless `.local/`
is deleted. Remove it from Android's user credentials when you no longer use
the project.

The pairing QR changes each time the script starts. It grants control of the
computer: keep it private. Only one phone can connect at a time.

**Stop:** press Ctrl+C in the terminal. PyAutoGUI also stops input when the
desktop pointer reaches a screen corner. Reconnect after moving it away.

## If it cannot connect

- Keep the terminal running and the phone page visible. A sleeping phone or
  connection loss releases held mouse buttons within three seconds.
- If the setup page does not load, check the computer's Wi-Fi address. Override
  automatic detection with `python server.py --host 192.168.1.20`.
- The local ports are **8080** for certificate setup and **8443** for HTTPS/WSS.
  Permit them on your own private network if a firewall blocks them.
- Company or college guest Wi-Fi may block devices from reaching each other.
  This project cannot bypass that isolation; use a Wi-Fi network that permits
  local device communication.
- For a certificate error, check the phone's date/time, install the downloaded
  CA certificate, and open the fresh pairing link. Do not rely on bypassing the
  browser's certificate warning.
- If clicks work but motion does not, allow motion sensors in the site's
  browser permissions. Keep the phone screen-up and Recenter.
- If connected but desktop input does not work on Mac, check Accessibility
  permission for the program running Python, then restart it.

## Read the code

```text
server.py           Local HTTPS, pairing, certificate setup, WebSocket connection
input_control.py    Small validated message → desktop action mapping
web/
  index.html        Controls and native keyboard input field
  style.css         Minimal black layout
  app.js            Phone events and WebSocket messages
  motion.mjs        Orientation math, smoothing, keyboard text differences
tests/
  test_receiver.py  Desktop actions and real TLS/WebSocket integration tests
  motion.test.mjs   Sensor math and keyboard regression tests
docs/
  classroom.md      Presentation outline and worked examples
```

See [the classroom walkthrough](docs/classroom.md) for the data flow and math.

## Tests

```sh
python -m unittest discover -s tests -v
node --test tests/motion.test.mjs
```

Node 20+ is only needed to run the JavaScript tests. It is not needed to use
MouseBoard Lite. Tests use a fake desktop and never move your actual cursor.

## Limits

- The Python receiver must stay running; a browser page alone cannot control
  the operating system.
- Typing supports printable English/ASCII text with an English/US desktop
  keyboard layout. Emoji, arbitrary Unicode, keyboard shortcuts, and editing
  remote text outside the current typed segment are not implemented.
- Motion sensors and their accuracy depend on the phone/browser. Portrait,
  screen-up use is the supported posture; near-vertical motion may feel less
  natural.
- Recenter targets the primary display. This MVP does not map multiple monitors.
- Keep the phone page in the foreground. Reconnect after switching apps.
- A lost connection releases buttons; text already typed is not undone.

## Libraries

Four direct dependencies keep the project readable:
[aiohttp](https://docs.aiohttp.org/) handles HTTPS and WebSockets,
[PyAutoGUI](https://pyautogui.readthedocs.io/) controls desktop input,
[trustme](https://trustme.readthedocs.io/) generates local certificates, and
[qrcode](https://github.com/lincolnloop/python-qrcode) generates pairing QR codes.
Sensor conventions follow the [W3C Device Orientation specification](https://www.w3.org/TR/orientation-event/).
