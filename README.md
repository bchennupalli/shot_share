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

- The app binds only to `127.0.0.1`, so it's not reachable from other devices on your network.
- A new random User ID and password are generated each time you start the app.
- Don't share your login link, User ID, or password with anyone you don't trust — anyone with them can view screenshots taken during that session.
- After 3 incorrect password attempts, the session locks and shuts down automatically.
