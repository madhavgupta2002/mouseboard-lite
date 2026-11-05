"""Exercise the real HTTPS/WebSocket server with a fake desktop, never your cursor."""

import asyncio
import ssl
import tempfile
import unittest
from pathlib import Path

from aiohttp import ClientSession, TCPConnector, WSServerHandshakeError
from aiohttp.test_utils import TestServer

from input_control import InputController
from server import certificates, phone_app, qr_svg, setup_app


class Desktop:
    PAUSE = 0
    FAILSAFE = True

    def __init__(self):
        self.calls = []
        self.released = asyncio.Event()

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name == "mouseUp":
                self.released.set()
            if name == "size":
                return (1920, 1080)
        return record


class InputTests(unittest.TestCase):
    def setUp(self):
        self.desktop = Desktop()
        self.controller = InputController(self.desktop)

    def test_move_is_bounded(self):
        self.controller.handle({"type": "move", "x": 9000, "y": -9000})
        self.assertEqual(self.desktop.calls[-1], ("moveRel", (100, -100), {}))

    def test_center_uses_screen_dimensions(self):
        self.controller.handle({"type": "center"})
        self.assertEqual(self.desktop.calls[-1], ("moveTo", (960, 540), {}))

    def test_drag_ignores_duplicate_down_and_releases_on_disconnect(self):
        down = {"type": "button", "button": "left", "down": True}
        self.controller.handle(down)
        self.controller.handle(down)
        self.controller.release()
        self.assertEqual([call[0] for call in self.desktop.calls], ["mouseDown", "mouseUp"])
        self.assertFalse(self.controller.held)
        self.assertTrue(self.desktop.FAILSAFE)

    def test_autocorrect_deletes_before_replacement(self):
        self.controller.handle({"type": "text", "remove": 3, "text": "the "})
        self.assertEqual(self.desktop.calls, [
            ("press", ("backspace",), {"presses": 3}), ("write", ("the ",), {})
        ])

    def test_rejects_invalid_messages_before_any_input(self):
        messages = [
            [], {"type": "execute", "command": "something"},
            {"type": "move", "x": float("nan"), "y": 0},
            {"type": "move", "x": True, "y": 0},
            {"type": "button", "button": "middle", "down": True},
            {"type": "button", "button": "left", "down": "yes"},
            {"type": "text", "remove": -1, "text": "hello"},
            {"type": "text", "remove": 0, "text": "🙂"},
            {"type": "key", "key": "command"},
        ]
        for message in messages:
            with self.subTest(message=message), self.assertRaises(ValueError):
                self.controller.handle(message)
        self.assertEqual(self.desktop.calls, [])


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        context, self.ca = certificates(Path(self.directory.name), "127.0.0.1")
        self.desktop = Desktop()
        self.controller = InputController(self.desktop)
        self.server = TestServer(phone_app(self.controller, "classroom-test", "https://phone.test"), scheme="https")
        await self.server.start_server(ssl=context)
        self.client = ClientSession(connector=TCPConnector(ssl=ssl.create_default_context(cafile=str(self.ca))))

    async def asyncTearDown(self):
        await self.client.close()
        await self.server.close()
        self.directory.cleanup()

    async def connect(self, token="classroom-test", origin="https://phone.test"):
        return await self.client.ws_connect(
            self.server.make_url("/ws").with_scheme("wss"),
            protocols=["mouseboard." + token], headers={"Origin": origin},
        )

    async def flush(self, socket):
        await socket.send_json({"type": "ping"})
        self.assertEqual((await socket.receive_json(timeout=1))["type"], "pong")

    async def test_tls_page_and_private_files(self):
        async with self.client.get(self.server.make_url("/")) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("MouseBoard", await response.text())
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        async with self.client.get(self.server.make_url("/ca-key.pem")) as response:
            self.assertEqual(response.status, 404)

    async def test_wrong_code_and_origin_are_rejected(self):
        for options in ({"token": "wrong"}, {"origin": "https://unrelated.test"}):
            with self.assertRaises(WSServerHandshakeError) as rejected:
                await self.connect(**options)
            self.assertEqual(rejected.exception.status, 403)
        self.assertFalse(self.desktop.calls)

    async def test_only_one_phone_can_control_the_computer(self):
        first = await self.connect()
        self.assertEqual((await first.receive_json())["type"], "ready")
        with self.assertRaises(WSServerHandshakeError) as rejected:
            await self.connect()
        self.assertEqual(rejected.exception.status, 409)
        await first.close()

    async def test_commands_reach_desktop_and_disconnect_releases_drag(self):
        socket = await self.connect()
        await socket.receive_json()
        await socket.send_json({"type": "move", "x": 12, "y": -7})
        await socket.send_json({"type": "button", "button": "right", "down": True})
        await self.flush(socket)
        self.assertIn(("moveRel", (12, -7), {}), self.desktop.calls)
        self.assertEqual(self.controller.held, {"right"})
        await socket.close()
        await asyncio.wait_for(self.desktop.released.wait(), 1)
        self.assertFalse(self.controller.held)

    async def test_invalid_json_is_rejected_without_breaking_session(self):
        socket = await self.connect()
        await socket.receive_json()
        await socket.send_str("{broken")
        self.assertEqual((await socket.receive_json())["type"], "error")
        await self.flush(socket)
        await socket.close()

    async def test_silent_phone_times_out_and_releases_drag(self):
        socket = await self.connect()
        await socket.receive_json()
        await socket.send_json({"type": "button", "button": "left", "down": True})
        await self.flush(socket)
        await asyncio.wait_for(self.desktop.released.wait(), 4)
        self.assertFalse(self.controller.held)
        await socket.close()

    async def test_setup_serves_only_public_certificate(self):
        server = TestServer(setup_app(self.ca, "https://phone.test", "secret-test-code", "http://phone.test"))
        await server.start_server()
        try:
            async with self.client.get(server.make_url("/ca.crt")) as response:
                certificate = await response.text()
                self.assertIn("BEGIN CERTIFICATE", certificate)
                self.assertNotIn("PRIVATE KEY", certificate)
            async with self.client.get(server.make_url("/anything")) as response:
                self.assertEqual(response.status, 404)
        finally:
            await server.close()

    def test_local_ca_is_retained_across_restarts(self):
        before = self.ca.read_bytes()
        certificates(Path(self.directory.name), "192.168.1.200")
        self.assertEqual(self.ca.read_bytes(), before)


class HttpDemoTests(unittest.IsolatedAsyncioTestCase):
    async def test_plain_websocket_commands_and_csp(self):
        desktop = Desktop()
        server = TestServer(phone_app(InputController(desktop), "demo", "http://phone.test"))
        await server.start_server()
        try:
            async with ClientSession() as client:
                async with client.get(server.make_url("/")) as response:
                    self.assertIn("ws://phone.test", response.headers["Content-Security-Policy"])
                async with client.ws_connect(
                    server.make_url("/ws").with_scheme("ws"),
                    protocols=["mouseboard.demo"], headers={"Origin": "http://phone.test"},
                ) as connection:
                    self.assertEqual((await connection.receive_json())["type"], "ready")
                    await connection.send_json({"type": "move", "x": 6, "y": -4})
                    await connection.send_json({"type": "ping"})
                    self.assertEqual((await connection.receive_json())["type"], "pong")
                    self.assertIn(("moveRel", (6, -4), {}), desktop.calls)
        finally:
            await server.close()

    async def test_demo_setup_has_exact_origin_and_no_certificate_download(self):
        server = TestServer(setup_app(None, "http://192.168.1.20:8443", "demo-code", "http://phone.test"))
        await server.start_server()
        try:
            async with ClientSession() as client:
                async with client.get(server.make_url("/")) as response:
                    page = await response.text()
                    self.assertIn("chrome://flags/#unsafely-treat-insecure-origin-as-secure", page)
                    self.assertIn(qr_svg("chrome://flags/#unsafely-treat-insecure-origin-as-secure"), page)
                    self.assertIn('id="chrome-address"', page)
                    self.assertIn("Copy address", page)
                    self.assertIn("http://192.168.1.20:8443", page)
                    self.assertIn("unencrypted", page)
                async with client.get(server.make_url("/ca.crt")) as response:
                    self.assertEqual(response.status, 404)
        finally:
            await server.close()


if __name__ == "__main__":
    unittest.main()
