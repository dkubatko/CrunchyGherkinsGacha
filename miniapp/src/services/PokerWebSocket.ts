import { io, type Socket } from 'socket.io-client';
import { usePokerStore, type PokerGameState } from '../stores/usePokerStore';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://api.crunchygherkins.com';

interface PokerErrorPayload {
  message?: string;
}

export class PokerWebSocket {
  private socket: Socket | null = null;
  private chatId: string;
  private userId: number;
  private initData: string;
  private readonly maxReconnectAttempts = 5;
  private readonly reconnectDelayMs = 3000;

  constructor(chatId: string, userId: number, initData: string) {
    this.chatId = chatId;
    this.userId = userId;
    this.initData = initData;
  }

  private createSocket(): Socket {
    return io(`${API_BASE_URL}/poker`, {
      path: '/socket.io',
      auth: {
        chat_id: this.chatId,
        user_id: this.userId,
        init_data: this.initData,
      },
      query: {
        chat_id: this.chatId,
        user_id: String(this.userId),
        init_data: this.initData,
      },
      transports: ['websocket', 'polling'],
      forceNew: true,
      reconnection: true,
      reconnectionAttempts: this.maxReconnectAttempts,
      reconnectionDelay: this.reconnectDelayMs,
    });
  }

  connect(): void {
    if (this.socket) {
      if (this.socket.connected) {
        return;
      }

      this.socket.connect();
      usePokerStore.getState().setConnectionStatus('connecting');
      return;
    }

    usePokerStore.getState().setConnectionStatus('connecting');
    usePokerStore.getState().setError(null);

    const socket = this.createSocket();
    this.registerHandlers(socket);
    this.socket = socket;
  }

  private registerHandlers(socket: Socket): void {
    socket.on('connect', () => {
      usePokerStore.getState().setConnectionStatus('connected');
      usePokerStore.getState().setError(null);
    });

    socket.on('disconnect', (reason) => {
      console.log('Poker socket disconnected:', reason);
      usePokerStore.getState().setConnectionStatus('disconnected');
    });

    socket.on('connect_error', (error) => {
      console.error('Poker socket connect_error:', error);
      usePokerStore.getState().setConnectionStatus('error');
      usePokerStore.getState().setError(error?.message || 'Failed to connect to server');
    });

    socket.io.on('reconnect_attempt', () => {
      usePokerStore.getState().setConnectionStatus('connecting');
    });

    socket.io.on('reconnect_failed', () => {
      usePokerStore.getState().setConnectionStatus('error');
      usePokerStore.getState().setError('Failed to reconnect to server');
    });

    socket.on('game_state', (data: PokerGameState | null) => {
      usePokerStore.getState().setGameState(data ?? null);
    });

    socket.on('player_joined', (data: PokerGameState) => {
      usePokerStore.getState().setGameState(data);
    });

    socket.on('poker_error', (payload: PokerErrorPayload) => {
      usePokerStore.getState().setError(payload?.message ?? 'Unknown error');
    });
  }

  join(spinBalance: number): void {
    if (!this.socket) {
      usePokerStore.getState().setError('Not connected to server');
      return;
    }

    this.socket.emit('join', { spin_balance: spinBalance });
  }

  async reset(): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/poker/${this.chatId}/reset`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `tma ${this.initData}`,
      },
    });

    if (!response.ok) {
      throw new Error('Failed to reset game');
    }

    const result = await response.json();
    console.log('Game reset:', result);
  }

  disconnect(): void {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
    }

    usePokerStore.getState().setConnectionStatus('disconnected');
  }

  isConnected(): boolean {
    return Boolean(this.socket?.connected);
  }
}
