/**
 * API service for fetching aspect thumbnail images from the server.
 */

interface AspectImageResponse {
  aspect_id: number;
  image_b64: string;
}

interface FetchResult {
  loaded: Map<number, string>;
  failed: number[];
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

export async function fetchAspectImages(
  aspectIds: number[],
  authToken: string
): Promise<FetchResult> {
  try {
    const response = await fetch(`${API_BASE_URL}/aspects/thumbnails`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `tma ${authToken}`,
      },
      body: JSON.stringify({ aspect_ids: aspectIds }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data: AspectImageResponse[] = await response.json();
    const loaded = new Map<number, string>();

    data.forEach(({ aspect_id, image_b64 }) => {
      loaded.set(aspect_id, image_b64);
    });

    return {
      loaded,
      failed: aspectIds.filter(id => !loaded.has(id)),
    };
  } catch (error) {
    console.error('Failed to fetch aspect images:', error);
    return { loaded: new Map(), failed: aspectIds };
  }
}
