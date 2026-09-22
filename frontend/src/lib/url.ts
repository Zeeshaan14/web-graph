// Lets every URL field in the app accept a bare domain ("lakshx.in",
// "www.example.com") as-is, not just a full "https://lakshx.in" -- the
// scheme gets filled in here before the value is sent to the backend,
// rather than forcing the user to type it by hand every time.
//
// Native <input type="url"> constraint validation actually REJECTS a
// bare domain (it requires an absolute URL, scheme included), so fields
// using this rely on plain type="text" instead -- this function is what
// makes that safe, not the browser's own validation.
export function normalizeUrlInput(value: string): string {
  const trimmed = value.trim();

  if (!trimmed) return trimmed;

  // Already has a scheme (https://, http://, or any other) -- left
  // exactly as typed, so an explicit http:// still works for local/
  // plain-http testing instead of being silently upgraded.
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(trimmed)) return trimmed;

  return `https://${trimmed}`;
}
