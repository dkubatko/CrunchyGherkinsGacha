import type {
  CardData,
  UserCollectionResponse,
  SlotSymbolSummary,
  SlotVerifyResponse,
  SlotSymbolInfo,
  CardConfigResponse,
  UserProfile,
  MegaspinInfo,
  RTBGameResponse,
  RTBGuessResponse,
  RTBCashOutResponse,
  RTBConfigResponse,
} from '../types';

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

  static async lockCard(
    cardId: number,
    userId: number,
    chatId: string,
    lock: boolean,
    initData: string
  ): Promise<{ success: boolean; locked: boolean; balance: number; message: string; lock_cost: number }> {
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

  static async burnCard(cardId: number, userId: number, chatId: string, initData: string): Promise<{ success: boolean; message: string; spins_awarded: number; new_spin_total: number }> {
    const response = await fetch(`${API_BASE_URL}/cards/burn`, {
      method: 'POST',
      headers: this.getHeaders(initData),
      body: JSON.stringify({ card_id: cardId, user_id: userId, chat_id: chatId })
    });

    if (!response.ok) {
      let detail = `Failed to burn card (Error ${response.status})`;
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

  static async fetchUserProfile(userId: number, chatId: string, initData: string): Promise<UserProfile> {
    const params = new URLSearchParams({
      chat_id: chatId
    });

    const response = await fetch(`${API_BASE_URL}/user/${encodeURIComponent(String(userId))}/profile?${params.toString()}`, {
      headers: this.getHeaders(initData)
    });

    if (!response.ok) {
      let detail = `Failed to fetch user profile (Error ${response.status})`;
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

  /**
   * Get a short-lived download token for a card image.
   * The token is valid for 5 minutes and can be reused within that window.
   */
  static async getDownloadToken(cardId: number, initData: string): Promise<string> {
    const response = await fetch(`${API_BASE_URL}/downloads/token/card/${cardId}`, {
      method: 'POST',
      headers: this.getHeaders(initData)
    });
    
    if (!response.ok) {
      throw new Error('Failed to get download token');
    }
    
    const data = await response.json();
    return data.token;
  }

  /**
   * Get the URL for viewing/downloading a card image.
   * Requires a token from getDownloadToken().
   */
  static getCardViewUrl(cardId: number, token: string): string {
    return `${API_BASE_URL}/cards/view/${cardId}.png?token=${encodeURIComponent(token)}`;
  }

  static async fetchCardConfig(initData: string): Promise<CardConfigResponse> {
    const response = await fetch(`${API_BASE_URL}/cards/config`, {
      headers: this.getHeaders(initData)
    });

    if (!response.ok) {
      if (response.status === 401) {
        throw new Error('Authentication failed. Please reopen the app from Telegram.');
      } else if (response.status >= 500) {
        throw new Error('Server error. Please try again later.');
      } else {
        throw new Error(`Failed to fetch card config (Error ${response.status})`);
      }
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
    initData: string,
    isMegaspin: boolean = false
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
        },
        is_megaspin: isMegaspin
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

  static async getUserSpins(userId: number, chatId: string, initData: string): Promise<{ spins: number; success: boolean; next_refresh_time?: string | null; megaspin?: MegaspinInfo | null }> {
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

  static async consumeUserSpin(userId: number, chatId: string, initData: string): Promise<{ success: boolean; spins_remaining?: number; message?: string; megaspin?: MegaspinInfo | null }> {
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

  static async consumeMegaspin(userId: number, chatId: string, initData: string): Promise<{ success: boolean; spins_remaining?: number; message?: string; megaspin?: MegaspinInfo | null }> {
    const response = await fetch(`${API_BASE_URL}/slots/megaspin`, {
      method: 'POST',
      headers: this.getHeaders(initData),
      body: JSON.stringify({
        user_id: userId,
        chat_id: chatId
      })
    });

    if (!response.ok) {
      let detail = `Failed to consume megaspin (Error ${response.status})`;
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

  static async verifyMegaspin(
    userId: number,
    chatId: string,
    randomNumber: number,
    symbols: SlotSymbolInfo[],
    initData: string
  ): Promise<SlotVerifyResponse> {
    const response = await fetch(`${API_BASE_URL}/slots/megaspin/verify`, {
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
      let detail = `Failed to verify megaspin (Error ${response.status})`;
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

  static async getMinesweeperGame(
    userId: number,
    chatId: string,
    initData: string
  ): Promise<{
    game_id: number;
    status: string;
    bet_card_title: string;
    card_rarity: string;
    revealed_cells: number[];
    moves_count: number;
    started_timestamp: string;
    last_updated_timestamp: string;
    reward_card_id?: number | null;
    mine_positions?: number[] | null;
    claim_point_positions?: number[] | null;
    card_icon?: string | null;
    claim_point_icon?: string | null;
    mine_icon?: string | null;
    next_refresh_time?: string | null;
  } | null> {
    const params = new URLSearchParams({
      user_id: userId.toString(),
      chat_id: chatId
    });

    const response = await fetch(`${API_BASE_URL}/minesweeper/game?${params.toString()}`, {
      headers: this.getHeaders(initData)
    });

    if (!response.ok) {
      let detail = `Failed to get minesweeper game (Error ${response.status})`;
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

    const data = await response.json();
    // API returns null if no game exists or cooldown expired
    return data;
  }

  static async createMinesweeperGame(
    userId: number,
    chatId: string,
    betCardId: number,
    initData: string
  ): Promise<{
    game_id: number;
    status: string;
    bet_card_title: string;
    card_rarity: string;
    revealed_cells: number[];
    moves_count: number;
    started_timestamp: string;
    last_updated_timestamp: string;
    reward_card_id?: number | null;
    mine_positions?: number[] | null;
    claim_point_positions?: number[] | null;
    card_icon?: string | null;
    claim_point_icon?: string | null;
    mine_icon?: string | null;
    next_refresh_time?: string | null;
  }> {
    const response = await fetch(`${API_BASE_URL}/minesweeper/game/create`, {
      method: 'POST',
      headers: this.getHeaders(initData),
      body: JSON.stringify({
        user_id: userId,
        chat_id: chatId,
        bet_card_id: betCardId
      })
    });

    if (!response.ok) {
      let detail = `Failed to create minesweeper game (Error ${response.status})`;
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

  static async updateMinesweeperGame(
    userId: number,
    gameId: number,
    cellIndex: number,
    initData: string
  ): Promise<{
    revealed_cells: number[];
    mine_positions?: number[] | null;
    claim_point_positions?: number[] | null;
    next_refresh_time?: string | null;
    status?: string | null;
    bet_card_rarity?: string | null;
    source_display_name?: string | null;
    claim_point_awarded?: boolean;
  }> {
    const response = await fetch(`${API_BASE_URL}/minesweeper/game/update`, {
      method: 'POST',
      headers: this.getHeaders(initData),
      body: JSON.stringify({
        user_id: userId,
        game_id: gameId,
        cell_index: cellIndex
      })
    });

    if (!response.ok) {
      let detail = `Failed to update minesweeper game (Error ${response.status})`;
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

  // ========== Ride the Bus (RTB) Methods ==========

  static async getRTBGame(
    userId: number,
    chatId: string,
    initData: string
  ): Promise<RTBGameResponse | null> {
    const params = new URLSearchParams({
      user_id: userId.toString(),
      chat_id: chatId
    });

    const response = await fetch(`${API_BASE_URL}/rtb/game?${params.toString()}`, {
      headers: this.getHeaders(initData)
    });

    if (!response.ok) {
      let detail = `Failed to get RTB game (Error ${response.status})`;
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

    const data = await response.json();
    return data;
  }

  static async startRTBGame(
    userId: number,
    chatId: string,
    betAmount: number,
    initData: string
  ): Promise<RTBGameResponse> {
    const response = await fetch(`${API_BASE_URL}/rtb/start`, {
      method: 'POST',
      headers: this.getHeaders(initData),
      body: JSON.stringify({
        user_id: userId,
        chat_id: chatId,
        bet_amount: betAmount
      })
    });

    if (!response.ok) {
      let detail = `Failed to start RTB game (Error ${response.status})`;
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

  static async makeRTBGuess(
    userId: number,
    gameId: number,
    guess: 'higher' | 'lower' | 'equal',
    initData: string
  ): Promise<RTBGuessResponse> {
    const response = await fetch(`${API_BASE_URL}/rtb/guess`, {
      method: 'POST',
      headers: this.getHeaders(initData),
      body: JSON.stringify({
        user_id: userId,
        game_id: gameId,
        guess: guess
      })
    });

    if (!response.ok) {
      let detail = `Failed to make RTB guess (Error ${response.status})`;
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

  static async cashOutRTB(
    userId: number,
    gameId: number,
    initData: string
  ): Promise<RTBCashOutResponse> {
    const response = await fetch(`${API_BASE_URL}/rtb/cashout`, {
      method: 'POST',
      headers: this.getHeaders(initData),
      body: JSON.stringify({
        user_id: userId,
        game_id: gameId
      })
    });

    if (!response.ok) {
      let detail = `Failed to cash out RTB game (Error ${response.status})`;
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

  static async getRTBConfig(initData: string, chatId?: string): Promise<RTBConfigResponse> {
    const params = new URLSearchParams();
    if (chatId) {
      params.set('chat_id', chatId);
    }
    
    const url = params.size > 0 
      ? `${API_BASE_URL}/rtb/config?${params.toString()}`
      : `${API_BASE_URL}/rtb/config`;
    
    const response = await fetch(url, {
      headers: this.getHeaders(initData)
    });

    if (!response.ok) {
      let detail = `Failed to get RTB config (Error ${response.status})`;
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