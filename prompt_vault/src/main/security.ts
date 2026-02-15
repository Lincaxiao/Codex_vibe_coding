export const TRUSTED_DEV_PROTOCOL = "http:";
export const TRUSTED_DEV_HOSTNAME = "127.0.0.1";
export const TRUSTED_DEV_PORT = "5173";

function parseUrl(rawUrl: string): URL | null {
  try {
    return new URL(rawUrl);
  } catch {
    return null;
  }
}

export function isAllowedDevServerUrl(rawUrl: string): boolean {
  const parsed = parseUrl(rawUrl);
  if (!parsed) {
    return false;
  }

  return (
    parsed.protocol === TRUSTED_DEV_PROTOCOL &&
    parsed.hostname === TRUSTED_DEV_HOSTNAME &&
    parsed.port === TRUSTED_DEV_PORT
  );
}

export function isTrustedSenderUrl(rawUrl: string): boolean {
  const parsed = parseUrl(rawUrl);
  if (!parsed) {
    return false;
  }

  if (parsed.protocol === "file:") {
    return true;
  }

  return isAllowedDevServerUrl(rawUrl);
}
