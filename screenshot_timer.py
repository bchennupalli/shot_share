#!/usr/bin/env python3
"""Run a local web app for authenticated screenshot capture."""

from __future__ import annotations

import argparse
import errno
import html
import http.cookies
import platform
import secrets
import signal
import string
import subprocess
import sys
import threading
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


PASSWORD_ALPHABET = string.ascii_uppercase + string.digits


def timestamped_file(output_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    return output_dir / f"screenshot_{stamp}.png"


def create_session_credentials() -> tuple[str, str]:
    user_id = f"{secrets.randbelow(1_000_000):06d}"
    password = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(6))
    return user_id, password


def save_session_credentials(output_dir: Path, user_id: str, password: str) -> Path:
    path = output_dir / "session_credentials.txt"
    path.write_text(f"user_id={user_id}\npassword={password}\n", encoding="utf-8")
    return path


def delete_file(path: Path) -> bool:
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError as exc:
        print(f"Could not delete {path}: {exc}", file=sys.stderr)
        return False


def delete_session_screenshots(paths: list[Path]) -> int:
    deleted = 0
    for path in paths:
        if delete_file(path):
            deleted += 1
    return deleted


def take_screenshot(path: Path) -> None:
    system = platform.system()

    if system == "Darwin":
        subprocess.run(["screencapture", "-x", str(path)], check=True)
        return

    if system == "Windows":
        ps_script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "Add-Type -AssemblyName System.Drawing;"
            "$bounds=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
            "$bmp=New-Object System.Drawing.Bitmap $bounds.Width,$bounds.Height;"
            "$graphics=[System.Drawing.Graphics]::FromImage($bmp);"
            "$graphics.CopyFromScreen($bounds.Location,[System.Drawing.Point]::Empty,$bounds.Size);"
            f"$bmp.Save('{path}',[System.Drawing.Imaging.ImageFormat]::Png);"
            "$graphics.Dispose();$bmp.Dispose();"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=True)
        return

    for command in (["gnome-screenshot", "-f", str(path)], ["scrot", str(path)]):
        try:
            subprocess.run(command, check=True)
            return
        except FileNotFoundError:
            continue

    raise RuntimeError("No supported screenshot command found on this system.")


class AppState:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir.resolve()
        self.user_id, self.password = create_session_credentials()
        self.credentials_path = save_session_credentials(
            self.output_dir, self.user_id, self.password
        )
        self.auth_token = secrets.token_urlsafe(32)
        self.failed_passwords = 0
        self.revoked = False
        self.screenshots: list[Path] = []
        self.lock = threading.Lock()
        self.server: ThreadingHTTPServer | None = None

    def is_authenticated(self, token: str | None) -> bool:
        with self.lock:
            return bool(token and token == self.auth_token and not self.revoked)

    def authenticate(self, user_id: str, password: str) -> tuple[bool, bool]:
        with self.lock:
            if self.revoked:
                return False, True

            if user_id == self.user_id and password == self.password:
                self.failed_passwords = 0
                return True, False

            if password != self.password:
                self.failed_passwords += 1

            if self.failed_passwords >= 3:
                self.revoke()
                return False, True

            return False, False

    def add_screenshot(self, path: Path) -> None:
        with self.lock:
            self.screenshots.append(path.resolve())

    def image_allowed(self, path: Path) -> bool:
        with self.lock:
            return path.resolve() in self.screenshots and not self.revoked

    def revoke(self) -> None:
        self.revoked = True
        self.user_id = ""
        self.password = ""
        self.auth_token = ""
        delete_file(self.credentials_path)

    def cleanup(self) -> int:
        with self.lock:
            self.revoke()
            screenshots = list(self.screenshots)
            self.screenshots.clear()
        return delete_session_screenshots(screenshots)

    def close_server(self) -> None:
        if self.server is not None:
            threading.Thread(target=self.server.shutdown, daemon=True).start()


def page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Arial, Helvetica, sans-serif;
      background: #f5f7fa;
      color: #18202b;
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
    }}
    main {{
      width: min(720px, calc(100vw - 32px));
      background: #ffffff;
      border: 1px solid #dce3ec;
      border-radius: 8px;
      box-shadow: 0 16px 40px rgba(30, 42, 58, 0.12);
      padding: 28px;
    }}
    h1 {{
      margin: 0 0 20px;
      font-size: 28px;
      line-height: 1.2;
    }}
    label {{
      display: block;
      font-size: 14px;
      font-weight: 700;
      margin: 16px 0 6px;
    }}
    input {{
      box-sizing: border-box;
      width: 100%;
      min-height: 44px;
      border: 1px solid #b8c3d1;
      border-radius: 6px;
      font-size: 16px;
      padding: 9px 11px;
    }}
    button {{
      min-height: 44px;
      border: 0;
      border-radius: 6px;
      background: #1665d8;
      color: #ffffff;
      cursor: pointer;
      font-size: 16px;
      font-weight: 700;
      padding: 0 18px;
    }}
    button:hover {{
      background: #0f55ba;
    }}
    a.button {{
      align-items: center;
      background: #1665d8;
      border-radius: 6px;
      color: #ffffff;
      display: inline-flex;
      font-size: 16px;
      font-weight: 700;
      min-height: 44px;
      padding: 0 18px;
      text-decoration: none;
    }}
    a.button:hover {{
      background: #0f55ba;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 20px;
    }}
    .message {{
      border-radius: 6px;
      margin: 0 0 18px;
      padding: 12px 14px;
      background: #fff4d8;
      border: 1px solid #e7c66b;
    }}
    .danger {{
      background: #ffe7e7;
      border-color: #ef9a9a;
    }}
    img {{
      display: block;
      width: 100%;
      height: auto;
      border: 1px solid #d3dce7;
      border-radius: 6px;
      margin-top: 20px;
    }}
    .secondary {{
      background: #41556e;
    }}
    .secondary:hover {{
      background: #33455b;
    }}
    .copy-status {{
      align-self: center;
      color: #41556e;
      font-size: 14px;
      min-height: 20px;
    }}
  </style>
</head>
<body>
  <main>
    {body}
  </main>
</body>
</html>
""".encode("utf-8")


def login_page(message: str = "", closed: bool = False) -> bytes:
    notice = ""
    if message:
        kind = "message danger" if closed else "message"
        notice = f'<div class="{kind}">{html.escape(message)}</div>'

    disabled = " disabled" if closed else ""
    return page(
        "Shot Share Login",
        f"""
    <h1>Shot Share</h1>
    {notice}
    <form method="post" action="/login">
      <label for="user_id">User ID</label>
      <input id="user_id" name="user_id" inputmode="numeric" autocomplete="username" required{disabled}>
      <label for="password">Password</label>
      <input id="password" name="password" autocomplete="current-password" required{disabled}>
      <div class="actions">
        <button type="submit"{disabled}>Login</button>
      </div>
    </form>
""",
    )


def capture_page(image_name: str = "", message: str = "") -> bytes:
    notice = f'<div class="message">{html.escape(message)}</div>' if message else ""
    safe_image_name = html.escape(image_name)
    image_url = f"/image/{safe_image_name}" if image_name else ""
    image = (
        f'<img id="screenshot" src="{image_url}" alt="Captured screenshot">'
        if image_name
        else ""
    )
    save_and_copy = (
        f"""
      <a class="button secondary" href="/download/{safe_image_name}">Save</a>
      <button class="secondary" id="copy-button" type="button" data-image="{image_url}">Copy</button>
      <span class="copy-status" id="copy-status" aria-live="polite"></span>
"""
        if image_name
        else ""
    )
    copy_script = (
        """
    <script>
      const copyButton = document.getElementById("copy-button");
      const copyStatus = document.getElementById("copy-status");
      if (copyButton && copyStatus) {
        copyButton.addEventListener("click", async () => {
          try {
            const response = await fetch(copyButton.dataset.image);
            const blob = await response.blob();
            await navigator.clipboard.write([
              new ClipboardItem({ [blob.type]: blob })
            ]);
            copyStatus.textContent = "Copied";
          } catch (error) {
            copyStatus.textContent = "Copy failed";
          }
        });
      }
    </script>
"""
        if image_name
        else ""
    )
    return page(
        "Capture Screenshot",
        f"""
    <h1>Capture Screenshot</h1>
    {notice}
    <div class="actions">
      <form method="post" action="/capture">
        <button type="submit">Capture</button>
      </form>
      {save_and_copy}
    </div>
    {image}
    {copy_script}
""",
    )


def closed_page() -> bytes:
    return page(
        "Session Closed",
        """
    <h1>Session Closed</h1>
    <div class="message danger">This session is closed. Screenshots were deleted and credentials were revoked.</div>
""",
    )


class ScreenshotHandler(BaseHTTPRequestHandler):
    state: AppState

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        route = urlparse(self.path).path

        if route == "/":
            if self.state.revoked:
                self.send_html(closed_page())
                return
            if self.is_logged_in():
                self.redirect("/capture")
                return
            self.send_html(login_page())
            return

        if route == "/capture":
            if not self.require_login():
                return
            query = parse_qs(urlparse(self.path).query)
            image_name = query.get("image", [""])[0]
            self.send_html(capture_page(image_name=image_name))
            return

        if route.startswith("/image/"):
            if not self.require_login():
                return
            self.send_image(route.removeprefix("/image/"))
            return

        if route.startswith("/download/"):
            if not self.require_login():
                return
            self.send_image(route.removeprefix("/download/"), download=True)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        route = urlparse(self.path).path

        if route == "/login":
            self.handle_login()
            return

        if route == "/capture":
            if not self.require_login():
                return
            self.handle_capture()
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def handle_login(self) -> None:
        form = self.read_form()
        ok, closed = self.state.authenticate(
            form.get("user_id", ""), form.get("password", "")
        )

        if ok:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/capture")
            self.send_header(
                "Set-Cookie", f"shot_share={self.state.auth_token}; HttpOnly; SameSite=Strict"
            )
            self.end_headers()
            return

        if closed:
            self.send_html(closed_page(), status=HTTPStatus.FORBIDDEN)
            self.state.close_server()
            return

        self.send_html(
            login_page("Login failed. After 3 wrong passwords, the session closes."),
            status=HTTPStatus.UNAUTHORIZED,
        )

    def handle_capture(self) -> None:
        path = timestamped_file(self.state.output_dir)
        try:
            take_screenshot(path)
            self.state.add_screenshot(path)
        except Exception as exc:
            self.send_html(
                capture_page(message=f"Screenshot failed: {exc}"),
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self.redirect(f"/capture?image={path.name}")

    def is_logged_in(self) -> bool:
        cookie_header = self.headers.get("Cookie", "")
        cookies = http.cookies.SimpleCookie(cookie_header)
        token = cookies.get("shot_share")
        return self.state.is_authenticated(token.value if token else None)

    def require_login(self) -> bool:
        if self.state.revoked:
            self.send_html(closed_page(), status=HTTPStatus.FORBIDDEN)
            return False
        if self.is_logged_in():
            return True
        self.redirect("/")
        return False

    def read_form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length).decode("utf-8")
        return {key: values[0] for key, values in parse_qs(data).items()}

    def redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def send_html(self, content: bytes, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_image(self, image_name: str, download: bool = False) -> None:
        path = (self.state.output_dir / image_name).resolve()
        if path.parent != self.state.output_dir or not self.state.image_allowed(path):
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            content = path.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/png")
        if download:
            self.send_header(
                "Content-Disposition", f'attachment; filename="{path.name}"'
            )
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def make_handler(state: AppState) -> type[ScreenshotHandler]:
    class BoundScreenshotHandler(ScreenshotHandler):
        pass

    BoundScreenshotHandler.state = state
    return BoundScreenshotHandler


def create_server(host: str, start_port: int, state: AppState) -> ThreadingHTTPServer:
    last_error: OSError | None = None
    for port in range(start_port, start_port + 20):
        try:
            return ThreadingHTTPServer((host, port), make_handler(state))
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE:
                raise
            last_error = exc

    raise OSError(
        f"No available local port found from {start_port} to {start_port + 19}."
    ) from last_error


def confirm_safe_use(host: str) -> bool:
    print("\nWARNING: Shot Share can capture and display screenshots from this computer.")
    print("Use this app only when you understand what will be captured.")
    print("Do not share your user ID, password, browser link, or screenshots with unknown people or strangers.")
    print("Screenshots captured in this session are deleted when the terminal session closes.")
    if host not in ("127.0.0.1", "localhost"):
        print(
            f"\nNOTE: The server will listen on {host}, which is reachable from other "
            "devices that can route to that address (e.g. over Tailscale or your LAN),"
            " not just this computer."
        )
    print("\n1. Approve")
    print("2. Decline")

    while True:
        choice = input("Choose 1 or 2: ").strip()
        if choice == "1":
            return True
        if choice == "2":
            return False
        print("Please enter 1 to approve or 2 to decline.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local screenshot web app.")
    parser.add_argument(
        "-o",
        "--output-dir",
        default="screenshots",
        help="Folder where temporary screenshots will be saved. Default: screenshots.",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=8000,
        help="Starting local web app port. Default: 8000.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help=(
            "Address to bind to. Default: 127.0.0.1 (this computer only). "
            "Use your Tailscale IP (e.g. 100.x.x.x) to allow access from another "
            "device on your tailnet."
        ),
    )
    args = parser.parse_args()

    if not confirm_safe_use(args.host):
        print("Declined. No session was started and no credentials were created.")
        return 0

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    state = AppState(output_dir)

    server = create_server(args.host, args.port, state)
    state.server = server

    def stop_program(signum: int, frame: object) -> None:
        state.close_server()

    signal.signal(signal.SIGINT, stop_program)
    signal.signal(signal.SIGTERM, stop_program)

    print(f"User ID: {state.user_id}")
    print(f"Password: {state.password}")
    print(f"Credentials saved to: {state.credentials_path}")
    actual_port = server.server_address[1]
    if actual_port != args.port:
        print(f"Port {args.port} was busy, using {actual_port} instead.")
    print(f"Open: http://{args.host}:{actual_port}")
    print("Press Ctrl+C to stop, delete session screenshots, and revoke credentials.")

    try:
        server.serve_forever()
    finally:
        server.server_close()
        deleted_count = state.cleanup()
        print(
            "\nSession closed. "
            f"Deleted {deleted_count} screenshot(s), revoked credentials."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
