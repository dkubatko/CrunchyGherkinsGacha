/**
 * API service for fetching card images from the server.
 */

interface CardImageResponse {
  card_id: number;
  image_b64: string;
}

interface FetchResult {
  loaded: Map<number, string>;
  failed: number[];
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://api.crunchygherkins.com';

export async function fetchCardImages(
  cardIds: number[],
  authToken: string
): Promise<FetchResult> {
  try {
    const response = await fetch(`${API_BASE_URL}/cards/images`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `tma ${authToken}`,
      },
      body: JSON.stringify({ card_ids: cardIds }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data: CardImageResponse[] = await response.json();
    const loaded = new Map<number, string>();

    data.forEach(({ card_id, image_b64 }) => {
      loaded.set(card_id, image_b64);
    });

    return {
      loaded,
      failed: cardIds.filter(id => !loaded.has(id)),
    };
  } catch (error) {
    console.error('Failed to fetch card images:', error);
    return { loaded: new Map(), failed: cardIds };
  }
}
