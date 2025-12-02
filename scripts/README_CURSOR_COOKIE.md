# How to Get Your Cursor Session Cookie

To download your Cursor usage data, you need to provide your session cookie.

## Method 1: Browser Developer Tools

1. Open your browser (Perplexity/Cursor browser or Chrome/Firefox)
2. Go to https://cursor.com and make sure you're logged in
3. Open Developer Tools:
   - **Chrome/Edge**: Press `F12` or `Ctrl+Shift+I` (Windows/Linux) / `Cmd+Option+I` (Mac)
   - **Firefox**: Press `F12` or `Ctrl+Shift+I` (Windows/Linux) / `Cmd+Option+I` (Mac)
4. Go to the **Application** tab (Chrome) or **Storage** tab (Firefox)
5. In the left sidebar, expand **Cookies** > **https://cursor.com**
6. Find the cookie named `session` (or `__session` or similar)
7. Copy the **Value** of that cookie

## Method 2: Browser Extension

You can use a browser extension like "Cookie Editor" to easily view and copy cookies.

## Setting the Cookie

### Option A: Environment Variable (Recommended)
```bash
export CURSOR_SESSION_COOKIE='your_cookie_value_here'
```

### Option B: Cookie File
Create a file `~/.cursor_cookie` or `cursor_cookie.txt` in the project root:
```bash
echo 'your_cookie_value_here' > ~/.cursor_cookie
# OR
echo 'your_cookie_value_here' > cursor_cookie.txt
```

### Option C: Full Cookie String
If you have the full cookie string (like `session=abc123; other=xyz`), you can use that too.

## Running the Script

After setting the cookie, run:
```bash
python3 scripts/build_hours.py
```

The script will automatically find and use your cookie from any of the above sources.
