/**
 * Huush — Reconnect Page
 *
 * Phones only allow the microphone on HTTPS. On the board's local Wi-Fi address the
 * dashboard is plain HTTP, so this page finds the board's current secure (HTTPS) link
 * and shows it as a button.
 *
 * How the link gets here: startup/run-phone-vu-tunnel.sh starts the Cloudflare tunnel,
 * checks that it answers, and writes its address to assets/demo-url.txt every 10 seconds.
 * This page reads that file every 2.5 seconds.
 *
 * Only Cloudflare quick-tunnel addresses and hussh.tech are accepted, so the file cannot
 * be used to send people to an unrelated site.
 */

const CHECK_INTERVAL_MS = 2500;
const ALLOWED_DEMO_URL = /^https:\/\/([a-z0-9-]+\.trycloudflare\.com|([a-z0-9-]+\.)?hussh\.tech)(\/.*)?$/i;

const statusEl = document.querySelector('#status');
const linkEl = document.querySelector('#link');

/** Reads demo-url.txt and shows the secure link, or a waiting message if there is none yet. */
async function check() {
  try {
    const res = await fetch(`demo-url.txt?t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) throw new Error('demo-url.txt not published yet');

    const url = (await res.text()).trim();
    if (!ALLOWED_DEMO_URL.test(url)) throw new Error('address not on the allow list');

    linkEl.href = url;
    linkEl.hidden = false;
    statusEl.textContent = 'Ready. Open the secure demo, then tap Start microphone.';
  } catch {
    linkEl.hidden = true;
    statusEl.textContent = 'Board is starting or waiting for internet. This page checks automatically.';
  }
}

check();
setInterval(check, CHECK_INTERVAL_MS);
