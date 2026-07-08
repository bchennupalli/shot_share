# Shot Share

A local, authenticated web app for capturing and sharing screenshots from your Mac. Runs entirely on your machine (no external dependencies) — it starts a small web server on `127.0.0.1`, gives you a one-time login, and lets you trigger a screenshot and view/download/copy it from the browser.

Screenshots and credentials are session-scoped: they're deleted automatically when you stop the app (Ctrl+C) or after 3 failed login attempts.

## Requirements

- macOS (uses the built-in `screencapture` command)
- Python 3.10+ (macOS ships with Python 3, but you can also install via Homebrew)

## Install

1. Clone or download this repo, then open Terminal and go to the project folder:

   ```bash
   cd ~/Downloads/shot_share
   ```

2. (Optional but recommended) Check you have a recent Python 3:

   ```bash
   python3 --version
   ```

   If it's missing or too old, install it with Homebrew:

   ```bash
   brew install python
   ```

No other packages are required — the app only uses the Python standard library.

## Run

From the project folder:

```bash
python3 screenshot_timer.py
```

You'll be asked to confirm you understand what the app does (type `1` to approve). It will then print something like:

```
User ID: 041982
Password: K3X9QZ
Credentials saved to: /Users/you/Downloads/shot_share/screenshots/session_credentials.txt
Open: http://127.0.0.1:8000
Press Ctrl+C to stop, delete session screenshots, and revoke credentials.
```

1. Open the printed `http://127.0.0.1:8000` link in your browser.
2. Log in with the User ID and Password shown in the terminal.
3. Click **Capture** to take a screenshot, then **Save**, **Copy**, or view it inline.

Press `Ctrl+C` in the terminal when you're done — this shuts the server down, deletes the captured screenshots, and revokes the session credentials.

### Optional flags

```bash
python3 screenshot_timer.py --output-dir screenshots --port 8000
```

- `-o / --output-dir` — folder to temporarily store screenshots (default: `screenshots`)
- `-p / --port` — starting port to bind to; if busy, it tries the next few ports (default: `8000`)
- `--host` — address to bind to (default: `127.0.0.1`, this computer only). Used below for remote access.

## Accessing it from another computer (different networks)

The app must keep running on the Mac whose screen you want to capture — a cloud VM (AWS/Azure/GCP) would only capture the *cloud server's* screen, not yours, so that's not the right tool here. Instead, use a tunnel from your Mac. Two options:

### Option A: Cloudflare Tunnel (recommended — fast, no account needed)

This runs a lightweight `cloudflared` process on your Mac that opens a fast, temporary public HTTPS URL forwarding straight to the app running on `127.0.0.1`. It's noticeably quicker than Tailscale's relay when a direct P2P connection isn't available.

1. **Install cloudflared** (one-time):

   ```bash
   brew install cloudflared
   ```

2. **Start Shot Share as normal** (default `127.0.0.1`, no `--host` needed) in one terminal tab:

   ```bash
   cd ~/Downloads/shot_share
   python3 screenshot_timer.py
   ```

   Note the port it prints (default `8000`).

3. **In a second terminal tab**, start the tunnel pointing at that port:

   ```bash
   cloudflared tunnel --url http://127.0.0.1:8000
   ```

   It prints a random public URL like `https://random-words-1234.trycloudflare.com`. This changes every time you start the tunnel.

4. **Share** that `trycloudflare.com` URL along with the User ID and password (from step 2) with the other person — over a trusted channel only.

5. On the other machine, just open that URL in a browser (no Tailscale or any install needed there), log in, and click **Capture**.

6. When done: `Ctrl+C` the tunnel first, then `Ctrl+C` the app (this deletes screenshots and revokes credentials).

> This exposes the app to the public internet (anyone with the URL can reach the login page), unlike the Tailscale option below. The app's own protections still apply — a password is required and the session locks after 3 wrong attempts — but because the URL isn't private, don't leave the tunnel running longer than you need it, and only send the URL/credentials to the person you intend to share with.

### Option B: Tailscale (private network, a bit slower)

If you'd rather not expose anything to the public internet, put both machines on the same private [Tailscale](https://tailscale.com) network (free for personal use) instead — it's a VPN mesh where only your own devices can reach each other. This is slower when Tailscale can't establish a direct peer-to-peer link and falls back to relaying traffic.

1. **Install Tailscale on both machines** and sign in with the same account:

   ```bash
   brew install --cask tailscale
   ```

   Open the Tailscale app once on each machine and log in (Machine A = the one running the screenshot app, Machine B = the one that will view screenshots).

2. **On Machine A**, find its Tailscale IP:

   ```bash
   tailscale ip -4
   ```

   This prints something like `100.101.102.103`.

3. **On Machine A**, start Shot Share bound to that Tailscale IP instead of localhost:

   ```bash
   cd ~/Downloads/shot_share
   python3 screenshot_timer.py --host 100.101.102.103
   ```

   It will print the User ID, Password, and a URL like `http://100.101.102.103:8000`.

4. **Share with the other system**: send the User ID, password, and that URL to whoever is using Machine B (only over a trusted channel — e.g. a message to yourself or someone you trust, not a public post).

5. **On Machine B**, make sure Tailscale is running and signed into the same account, then open the shared URL in a browser, log in with the User ID/password, and click **Capture** — it will trigger a screenshot on Machine A and display it in the browser on Machine B.

6. When done, go back to the terminal on Machine A and press `Ctrl+C` to stop the server, delete the screenshots, and revoke the credentials.

> Binding to `--host 127.0.0.1` (the default) keeps the app reachable only from the same machine. Binding to a Tailscale IP makes it reachable from any device on your tailnet, so only do this over Tailscale (or another private VPN) — never bind to a public/LAN IP without one, since the credentials are meant for one trusted session, not internet-wide exposure.

## Running it whenever you want

Since this is a single script, you can just re-run the same command from the project folder any time:

```bash
cd ~/Downloads/shot_share && python3 screenshot_timer.py
```

To make this quicker, add a shell alias. Open `~/.zshrc` in a text editor (zsh is the default shell on modern macOS) and add:

```bash
alias shotshare="cd ~/Downloads/shot_share && python3 screenshot_timer.py"
```

Then reload your shell config:

```bash
source ~/.zshrc
```

Now you can start the app from anywhere by just typing:

```bash
shotshare
```

## Security notes

- By default the app binds only to `127.0.0.1`, so it's not reachable from other devices. Only pass `--host` with a Tailscale (or other private VPN) IP if you intend for another trusted device to connect.
- A new random User ID and password are generated each time you start the app.
- Don't share your login link, User ID, or password with anyone you don't trust — anyone with them can view screenshots taken during that session.
- After 3 incorrect password attempts, the session locks and shuts down automatically.
