// SEC-3 idle logout (S3-4): a screen that reloads itself is not a person using the app.
//
// Requests started inside asBackground(fn) are sent with the header X-Background-Refresh: 1, and
// the backend does not count them as activity. So a screen left open still logs out after the
// idle time. A person's clicks, and the first load of a screen they open, are normal requests.
//
// The flag only covers requests started synchronously inside fn (before its first await): every
// automatic refresh starts its requests that way.
let background = false;

export function asBackground(fn) {
  background = true;
  try {
    return fn();
  } finally {
    background = false;
  }
}

export function isBackground() {
  return background;
}
