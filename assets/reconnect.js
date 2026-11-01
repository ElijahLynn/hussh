const ALLOWED_DEMO_URL = /^https:\/\/([a-z0-9-]+\.trycloudflare\.com|([a-z0-9-]+\.)?hussh\.tech)(\/.*)?$/i;

async function check() {
  const linkEl = document.querySelector('#link');
  const statusEl = document.querySelector('#status');
  try {
    const res = await fetch('demo-url.txt?t=' + Date.now(), { cache: 'no-store' });
    if (!res.ok) throw new Error('demo-url unavailable');
    const url = (await res.text()).trim();
    if (!ALLOWED_DEMO_URL.test(url)) throw new Error('untrusted tunnel target');
    linkEl.href = url;
    linkEl.hidden = false;
    statusEl.textContent = 'Ready. Open the secure demo, then tap Start microphone.';
  } catch {
    statusEl.textContent = 'Board is starting or waiting for internet. This page checks automatically.';
    linkEl.hidden = true;
  }
}

check();
setInterval(check, 2500);

