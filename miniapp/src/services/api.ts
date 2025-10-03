import type { CardData, UserCollectionResponse, SlotSymbolSummary, SlotVerifyResponse, SlotSymbolInfo } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://api.crunchygherkins.com';

export class ApiService {
  private static getHeaders(initData?: string | null): HeadersInit {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };
    
    if (initData) {
      headers['Authorization'] = `tma ${initData}`;
    }
    
    return headers;
  }

  static async fetchUserCards(userId: number, initData: string, chatId?: string | null): Promise<UserCollectionResponse> {
    const params = new URLSearchParams();
    if (chatId) {
      params.set('chat_id', chatId);
    }

    const endpoint = `${API_BASE_URL}/cards/${encodeURIComponent(String(userId))}`;
    const url = params.size > 0 ? `${endpoint}?${params.toString()}` : endpoint;

    const response = await fetch(url, {
      headers: this.getHeaders(initData)
    });
    
    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('User not found. They may not have any cards yet.');
      } else if (response.status === 401) {
        throw new Error('Authentication failed. Please reopen the app from Telegram.');
      } else if (response.status >= 500) {
        throw new Error('Server error. Please try again later.');
      } else {
        throw new Error(`Failed to fetch cards (Error ${response.status})`);
      }
    }
    
    return response.json();
  }

  static async fetchAllCards(initData: string, chatId?: string): Promise<CardData[]> {
    const params = new URLSearchParams();
    if (chatId) {
      params.set('chat_id', chatId);
    }

    const endpoint = `${API_BASE_URL}/cards/all`;
    const url = params.size > 0 ? `${endpoint}?${params.toString()}` : endpoint;

    const response = await fetch(url, {
      headers: this.getHeaders(initData)
    });
    
    if (!response.ok) {
      throw new Error('Failed to fetch all cards');
    }
    
    return response.json();
  }

  static async fetchCardImagesBatch(cardIds: number[], initData: string): Promise<Record<number, string>> {
    if (cardIds.length === 0) {
      return {};
    }

    const response = await fetch(`${API_BASE_URL}/cards/images`, {
      method: 'POST',
      headers: this.getHeaders(initData),
      body: JSON.stringify({ card_ids: cardIds })
    });

    if (!response.ok) {
      throw new Error('Failed to fetch card images batch');
    }

    const payload: Array<{ card_id: number; image_b64: string }> = await response.json();
    return payload.reduce<Record<number, string>>((acc, item) => {
      acc[item.card_id] = item.image_b64;
      return acc;
    }, {});
  }

  static async fetchTradeOptions(cardId: number, initData: string): Promise<CardData[]> {
    const endpoint = `${API_BASE_URL}/trade/${encodeURIComponent(String(cardId))}/options`;

    const response = await fetch(endpoint, {
      headers: this.getHeaders(initData)
    });

    if (!response.ok) {
      throw new Error('Failed to fetch trade options');
    }

    return response.json();
  }

  static async fetchCardDetails(cardId: number, initData: string): Promise<CardData> {
    const response = await fetch(`${API_BASE_URL}/cards/detail/${encodeURIComponent(String(cardId))}`, {
      headers: this.getHeaders(initData)
    });

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('Card not found. It may have been removed.');
      } else if (response.status === 401) {
        throw new Error('Authentication failed. Please reopen the app from Telegram.');
      }
      throw new Error(`Failed to load card (Error ${response.status})`);
    }

    return response.json();
  }

  static async shareCard(cardId: number, userId: number, initData: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/cards/share`, {
      method: 'POST',
      headers: this.getHeaders(initData),
      body: JSON.stringify({ card_id: cardId, user_id: userId })
    });

    if (!response.ok) {
      let detail = `Failed to share card (Error ${response.status})`;
      try {
        const payload = await response.json();
        if (payload?.detail) {
          detail = payload.detail;
        }
      } catch {
        // ignore parse errors
      }
      throw new Error(detail);
    }
  }

  static async lockCard(cardId: number, userId: number, chatId: string, lock: boolean, initData: string): Promise<{ success: boolean; locked: boolean; balance: number; message: string }> {
    const response = await fetch(`${API_BASE_URL}/cards/lock`, {
      method: 'POST',
      headers: this.getHeaders(initData),
      body: JSON.stringify({ card_id: cardId, user_id: userId, chat_id: chatId, lock })
    });

    if (!response.ok) {
      let detail = `Failed to lock/unlock card (Error ${response.status})`;
      try {
        const payload = await response.json();
        if (payload?.detail) {
          detail = payload.detail;
        }
      } catch {
        // ignore parse errors
      }
      throw new Error(detail);
    }

    return response.json();
  }

  static async fetchClaimBalance(userId: number, chatId: string, initData: string): Promise<{ balance: number; user_id: number; chat_id: string }> {
    const params = new URLSearchParams({
      chat_id: chatId
    });

    const response = await fetch(`${API_BASE_URL}/user/${encodeURIComponent(String(userId))}/claims?${params.toString()}`, {
      headers: this.getHeaders(initData)
    });

    if (!response.ok) {
      let detail = `Failed to fetch claim balance (Error ${response.status})`;
      try {
        const payload = await response.json();
        if (payload?.detail) {
          detail = payload.detail;
        }
      } catch {
        // ignore parse errors
      }
      throw new Error(detail);
    }

    return response.json();
  }

  static async fetchCardImage(cardId: number, initData: string): Promise<string> {
    const response = await fetch(`${API_BASE_URL}/cards/image/${cardId}`, {
      headers: this.getHeaders(initData)
    });
    
    if (!response.ok) {
      throw new Error('Failed to fetch image');
    }
    
    return response.json();
  }

  static async fetchSlotSymbols(chatId: string, initData: string): Promise<SlotSymbolSummary[]> {
    const response = await fetch(`${API_BASE_URL}/chat/${encodeURIComponent(chatId)}/slot-symbols`, {
      headers: this.getHeaders(initData)
    });

    if (!response.ok) {
      if (response.status === 401) {
        throw new Error('Authentication failed. Please reopen the app from Telegram.');
      } else if (response.status === 404) {
        throw new Error('Chat not found.');
      } else if (response.status >= 500) {
        throw new Error('Server error. Please try again later.');
      } else {
        throw new Error(`Failed to fetch slot symbols (Error ${response.status})`);
      }
    }

    return response.json();
  }

  static async processSlotsVictory(
    userId: number, 
    chatId: string, 
    rarity: string, 
    sourceId: number, 
    sourceType: 'user' | 'character' | 'claim', 
    initData: string
  ): Promise<{ status: string; message: string }> {
    const response = await fetch(`${API_BASE_URL}/slots/victory`, {
      method: 'POST',
      headers: this.getHeaders(initData),
      body: JSON.stringify({
        user_id: userId,
        chat_id: chatId,
        rarity: rarity,
        source: {
          id: sourceId,
          type: sourceType
        }
      })
    });

    if (!response.ok) {
      let detail = `Failed to process slots victory (Error ${response.status})`;
      try {
        const payload = await response.json();
        if (payload?.detail) {
          detail = payload.detail;
        }
      } catch {
        // ignore parse errors
      }
      throw new Error(detail);
    }

    return response.json();
  }

  static async getUserSpins(userId: number, chatId: string, initData: string): Promise<{ spins: number; success: boolean }> {
    const params = new URLSearchParams({
      user_id: userId.toString(),
      chat_id: chatId
    });

    const response = await fetch(`${API_BASE_URL}/slots/spins?${params.toString()}`, {
      headers: this.getHeaders(initData)
    });

    if (!response.ok) {
      let detail = `Failed to get user spins (Error ${response.status})`;
      try {
        const payload = await response.json();
        if (payload?.detail) {
          detail = payload.detail;
        }
      } catch {
        // ignore parse errors
      }
      throw new Error(detail);
    }

    return response.json();
  }

  static async consumeUserSpin(userId: number, chatId: string, initData: string): Promise<{ success: boolean; spins_remaining?: number; message?: string }> {
    const response = await fetch(`${API_BASE_URL}/slots/spins`, {
      method: 'POST',
      headers: this.getHeaders(initData),
      body: JSON.stringify({
        user_id: userId,
        chat_id: chatId
      })
    });

    if (!response.ok) {
      let detail = `Failed to consume spin (Error ${response.status})`;
      try {
        const payload = await response.json();
        if (payload?.detail) {
          detail = payload.detail;
        }
      } catch {
        // ignore parse errors
      }
      throw new Error(detail);
    }

    return response.json();
  }

  static async verifySlotSpin(
    userId: number,
    chatId: string,
    randomNumber: number,
    symbols: SlotSymbolInfo[],
    initData: string
  ): Promise<SlotVerifyResponse> {
    const response = await fetch(`${API_BASE_URL}/slots/verify`, {
      method: 'POST',
      headers: this.getHeaders(initData),
      body: JSON.stringify({
        user_id: userId,
        chat_id: chatId,
        random_number: randomNumber,
        symbols: symbols
      })
    });

    if (!response.ok) {
      let detail = `Failed to verify slot spin (Error ${response.status})`;
      try {
        const payload = await response.json();
        if (payload?.detail) {
          detail = payload.detail;
        }
      } catch {
        // ignore parse errors
      }
      throw new Error(detail);
    }

    return response.json();
  }

  static async processClaimWin(
    userId: number,
    chatId: string,
    amount: number,
    initData: string
  ): Promise<{ success: boolean; balance: number }> {
    const response = await fetch(`${API_BASE_URL}/slots/claim-win`, {
      method: 'POST',
      headers: this.getHeaders(initData),
      body: JSON.stringify({
        user_id: userId,
        chat_id: chatId,
        amount: amount
      })
    });

    if (!response.ok) {
      let detail = `Failed to process claim win (Error ${response.status})`;
      try {
        const payload = await response.json();
        if (payload?.detail) {
          detail = payload.detail;
        }
      } catch {
        // ignore parse errors
      }
      throw new Error(detail);
    }

    return response.json();
  }
}