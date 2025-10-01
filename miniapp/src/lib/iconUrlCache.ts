const iconUrlCache = new Map<string, string>();

const decodeBase64 = (base64: string): Uint8Array => {
  const normalized = base64.trim();
  const binaryString = atob(normalized);
  const length = binaryString.length;
  const bytes = new Uint8Array(length);

  for (let i = 0; i < length; i += 1) {
    bytes[i] = binaryString.charCodeAt(i);
  }

  return bytes;
};

export const getIconObjectUrl = (iconb64: string): string => {
  const cached = iconUrlCache.get(iconb64);
  if (cached) {
    return cached;
  }

  const bytes = decodeBase64(iconb64);
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
  const blob = new Blob([buffer], { type: 'image/png' });
  const url = URL.createObjectURL(blob);
  iconUrlCache.set(iconb64, url);
  return url;
};

export const clearIconObjectUrls = (): void => {
  for (const url of iconUrlCache.values()) {
    URL.revokeObjectURL(url);
  }
  iconUrlCache.clear();
};
