"""Serve the phone page locally and receive authenticated WebSocket commands."""

import argparse
import asyncio
import hmac
import io
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import sys
import webbrowser

from aiohttp import WSMsgType, web
import qrcode
import qrcode.image.svg
import trustme

from input_control import InputController

ROOT = Path(__file__).resolve().parent


def wifi_ip():
    if sys.platform == "darwin":
        result = subprocess.run(
            ["ipconfig", "getifaddr", "en0"], capture_output=True, text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
    # Choosing a route does not send a packet or require internet access.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        connection.connect(("192.0.2.1", 1))
        return connection.getsockname()[0]


def certificates(directory, host):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    cert, key = directory / "ca.pem", directory / "ca-key.pem"
    if cert.exists() and key.exists():
        ca = trustme.CA.from_pem(cert.read_bytes(), key.read_bytes())
    else:
        ca = trustme.CA(organization_name="MouseBoard Lite Local CA")
        ca.cert_pem.write_to_path(cert)
        ca.private_key_pem.write_to_path(key)
        key.chmod(0o600)
    server = ca.issue_cert(host, "localhost", "127.0.0.1")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    server.configure_cert(context)
    return context, cert


def qr_svg(value):
    image = qrcode.make(value, image_factory=qrcode.image.svg.SvgPathImage, border=2)
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode()


def phone_app(controller, token, origin):
    app = web.Application()
    active = None

    async def page(request):
        name = request.match_info.get("name", "index.html")
        if name not in ("index.html", "app.js", "motion.mjs", "style.css"):
            raise web.HTTPNotFound()
        return web.FileResponse(ROOT / "web" / name, headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": f"default-src 'self'; connect-src 'self' {origin.replace('http', 'ws', 1)}; frame-ancestors 'none'",
        })

    async def socket_handler(request):
        nonlocal active
        protocol = request.headers.get("Sec-WebSocket-Protocol", "")
        if request.headers.get("Origin") != origin or not hmac.compare_digest(protocol, "mouseboard." + token):
            raise web.HTTPForbidden(text="Scan the pairing QR on the computer.")
        if active is not None:
            raise web.HTTPConflict(text="One phone is already connected.")
        ws = web.WebSocketResponse(protocols=[protocol], max_msg_size=4096, timeout=1)
        active = ws
        close_code, close_reason = 1000, b"Disconnected"
        try:
            await ws.prepare(request)
            await ws.send_json({"type": "ready"})
            while True:
                # Stops a held button if the phone sleeps or loses Wi-Fi.
                event = await ws.receive(timeout=3)
                if event.type != WSMsgType.TEXT:
                    break
                try:
                    message = json.loads(event.data)
                    controller.handle(message)
                    if message.get("type") == "ping":
                        await ws.send_json({"type": "pong"})
                except (ValueError, TypeError) as error:
                    await ws.send_json({"type": "error", "message": str(error)})
                    # Reject malformed commands, but let an unsupported text edit be retried.
        except asyncio.TimeoutError:
            close_code, close_reason = 1001, b"Phone stopped responding"
        except Exception as error:
            print(f"Input stopped: {error}", flush=True)
            close_code, close_reason = 1011, b"Check desktop permission or failsafe"
        finally:
            # Release input before waiting for a disconnected peer's close handshake.
            controller.release()
            try:
                await ws.close(code=close_code, message=close_reason)
            finally:
                active = None
        return ws

    async def shutdown(_app):
        controller.release()
        if active is not None:
            await active.close(code=1001, message=b"Receiver stopped")

    app.router.add_get("/ws", socket_handler)
    app.router.add_get("/", page)
    app.router.add_get("/{name}", page)
    app.on_shutdown.append(shutdown)
    return app


def setup_app(ca_path, origin, token, setup_url):
    chrome_flags = "chrome://flags/#unsafely-treat-insecure-origin-as-secure"

    async def download(_request):
        return web.FileResponse(ca_path, headers={
            "Content-Type": "application/x-x509-ca-cert",
            "Content-Disposition": 'attachment; filename="MouseBoard-Lite-CA.crt"',
        })

    async def instructions(request):
        local = request.remote in ("127.0.0.1", "::1")
        pairing = f"{origin}/#{token}"
        content = f"""<!doctype html><meta name="viewport" content="width=device-width">
        <title>MouseBoard Lite setup</title><style>
        body{{font:17px system-ui;background:#101010;color:#eee;max-width:760px;margin:40px auto;padding:20px}}
        a{{color:#8bceff}}svg{{width:230px;height:230px;background:white;padding:12px}}
        li{{margin:20px 0}}code{{overflow-wrap:anywhere}}
        input{{width:100%;padding:12px;box-sizing:border-box;background:#222;color:#eee;border:1px solid #555}}
        button{{padding:10px 16px;margin-top:8px;cursor:pointer}}</style>
        <h1>MouseBoard Lite</h1><p>Keep your phone and computer on the same trusted Wi-Fi.</p>"""
        if ca_path is None:
            content += f"""<h2>Demo without a certificate</h2>
            <p>This is an unencrypted local demo. Use it only on your own trusted Wi-Fi.</p>
            <h2>Chrome settings QR</h2>{qr_svg(chrome_flags)}
            <p>Scan this QR first. If your scanner does not open Chrome settings,
            copy the scanned text and paste it into Chrome's address bar.</p>
            <label for="chrome-address">Chrome settings address</label>
            <input id="chrome-address" readonly value="{chrome_flags}" onclick="this.select()">
            <button onclick="document.getElementById('chrome-address').select();
            this.textContent = document.execCommand('copy') ? 'Copied' : 'Select the address and copy';">Copy address</button>
            <ol><li>Open the scanned address in <b>Chrome</b>.</li>
            <li>Under <b>Insecure origins treated as secure</b>, add this exact address:
            <p><code>{origin}</code></p>Set it to <b>Enabled</b> and tap <b>Relaunch</b>.</li>
            <li>Scan the Pair phone QR shown on the computer. Open it in Chrome,
            tap Connect, then Recenter.</li></ol>
            <p>After your demo, set this flag back to <b>Default</b> and relaunch Chrome.
            Do not add wildcards or other sites. If your managed browser blocks this
            test setting, use HTTPS mode instead.</p>"""
        else:
            content += """<ol><li>On the phone, download <a href="/ca.crt">the local CA certificate</a>.
        Install it in Android Settings → Security and privacy → More security settings →
        Install from device storage → CA certificate. Search Settings for “CA certificate”
        if the menu differs. Install only on your own phone.</li>
        <li>After installing the certificate, scan the pairing QR shown on the computer.</li>
        <li>Tap Connect on the phone, hold it screen-up, then tap Recenter.</li></ol>"""
        if local:
            content += f"""<h2>1. Phone setup</h2>{qr_svg(setup_url)}
            <p><code>{setup_url}</code></p><h2>2. Pair phone</h2>{qr_svg(pairing)}
            <p><a href="{pairing}">Open controller</a></p>
            <p>On Mac, allow the terminal running Python under System Settings →
            Privacy &amp; Security → Accessibility. Restart the script after changing permission.</p>
            <p>The pairing QR grants control. Keep it private. Ctrl+C stops the receiver.</p>"""
        return web.Response(text=content, content_type="text/html")

    app = web.Application()
    app.router.add_get("/", instructions)
    if ca_path is not None:
        app.router.add_get("/ca.crt", download)
    return app


async def run(args):
    host = str(ipaddress.IPv4Address(args.host or wifi_ip()))
    context, ca_path = (None, None) if args.demo_http else certificates(ROOT / ".local", host)
    token = secrets.token_urlsafe(24)
    origin = f"{'http' if args.demo_http else 'https'}://{host}:{args.port}"
    controller = InputController()
    receivers = [
        (phone_app(controller, token, origin), args.port, context),
        (setup_app(ca_path, origin, token, f"http://{host}:{args.setup_port}/"), args.setup_port, None),
    ]
    runners = []
    try:
        for app, port, tls in receivers:
            runner = web.AppRunner(app, access_log=None)
            runners.append(runner)
            await runner.setup()
            await web.TCPSite(runner, "0.0.0.0", port, ssl_context=tls).start()
        local_setup = f"http://127.0.0.1:{args.setup_port}/"
        print(f"\nMouseBoard Lite is ready.\nSetup and pairing QR: {local_setup}")
        print(f"Phone setup: http://{host}:{args.setup_port}/")
        if args.demo_http:
            print(f"HTTP demo: allow only {origin} in Chrome's insecure-origin test flag.")
            print("Traffic is unencrypted. Restore the flag to Default after your demo.")
        print("Ctrl+C stops control. Moving the desktop mouse to a screen corner also stops input.")
        if not args.no_open:
            webbrowser.open(local_setup)
        await asyncio.Event().wait()
    finally:
        for runner in reversed(runners):
            await runner.cleanup()
        controller.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", help="Computer's Wi-Fi IPv4 address (auto-detected by default)")
    parser.add_argument("--port", type=int, default=8443, help="Controller port")
    parser.add_argument("--setup-port", type=int, default=8080, help="Certificate setup port")
    parser.add_argument("--demo-http", action="store_true",
                        help="Unencrypted local demo; requires Chrome's per-origin secure-context test flag")
    parser.add_argument("--no-open", action="store_true", help="Do not open the desktop setup page")
    try:
        asyncio.run(run(parser.parse_args()))
    except KeyboardInterrupt:
        print("\nMouseBoard Lite stopped.")
