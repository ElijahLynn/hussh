/**
 * Huush — Automatic Reconnection Handler
 * 
 * Provides a gentle fallback screen when the board is rebooting or the tunnel drops.
 * Probes the target server with a lightweight HEAD request every 2.5 seconds
 * and redirects immediately once the service recovers.
 */

// Interval in milliseconds between reconnection attempts
const PING_INTERVAL_MS = 2500;

// Resolve target URL from current query string (?next=...) or default to apex
const params = new URLSearchParams(window.location.search);
const targetUrl = params.get('next') || '/';

const statusNode = document.querySelector('#reconnect-status');

/**
 * Checks connectivity by sending a lightweight HEAD request with cache busting.
 */
async function checkConnectivity() {
  try {
    const probeUrl = `${targetUrl}${targetUrl.includes('?') ? '&' : '?'}_probe=${Date.now()}`;
    const response = await fetch(probeUrl, {
      method: 'HEAD',
      cache: 'no-store',
      mode: 'no-cors'
    });

    if (statusNode) {
      statusNode.textContent = 'Connection restored! Returning to dashboard…';
    }

    // Forward back to dashboard upon successful probe
    window.location.replace(targetUrl);
  } catch (err) {
    if (statusNode) {
      statusNode.textContent = 'Reconnecting to Huush board…';
    }
  }
}

// Start polling
setInterval(checkConnectivity, PING_INTERVAL_MS);
checkConnectivity();
