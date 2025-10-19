import { usePokerStore, type PokerGameState } from '../stores/usePokerStore';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://api.crunchygherkins.com';

interface PokerMessage {
  type: string;
  data?: PokerGameState;
  message?: string;
  [key: string]: unknown;
}

export class PokerWebSocket {
  private ws: WebSocket | null = null;
  private chatId: string;
  private userId: number;
  private initData: string;
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 3000;
  private shouldReconnect = true;
  private isConnecting = false;

  constructor(chatId: string, userId: number, initData: string) {
    this.chatId = chatId;
    this.userId = userId;
    this.initData = initData;
  }

  private getWebSocketUrl(): string {
    const wsProtocol = API_BASE_URL.startsWith('https') ? 'wss' : 'ws';
    const baseUrl = API_BASE_URL.replace(/^https?:\/\//, '');
    return `${wsProtocol}://${baseUrl}/ws/poker/${this.chatId}`;
  }

  connect(): void {
    if (this.isConnecting) {
      console.log('WebSocket connection already in progress');
      return;
    }

    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      console.log('WebSocket already connected or connecting');
      return;
    }

    const wsUrl = this.getWebSocketUrl();
    console.log('Connecting to poker WebSocket:', wsUrl);

    this.isConnecting = true;
    usePokerStore.getState().setConnectionStatus('connecting');
    usePokerStore.getState().setError(null);

    try {
      this.ws = new WebSocket(wsUrl);
      this.setupEventHandlers();
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      this.isConnecting = false;
      usePokerStore.getState().setConnectionStatus('error');
      usePokerStore.getState().setError('Failed to connect to server');
      this.scheduleReconnect();
    }
  }

  private setupEventHandlers(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.isConnecting = false;
      this.reconnectAttempts = 0;
      usePokerStore.getState().setConnectionStatus('connected');
      usePokerStore.getState().setError(null);

      // Send initial connection message with initData for validation
      this.sendMessage({
        type: 'connect',
        user_id: this.userId,
        init_data: this.initData,
      });
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        this.handleMessage(message);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    this.ws.onerror = (event) => {
      console.error('WebSocket error:', event);
      this.isConnecting = false;
      usePokerStore.getState().setConnectionStatus('error');
      usePokerStore.getState().setError('Connection error occurred');
    };

    this.ws.onclose = (event) => {
      console.log('WebSocket disconnected:', event.code, event.reason);
      console.log('Was clean close?', event.wasClean);
      console.log('Should reconnect?', this.shouldReconnect);
      this.isConnecting = false;
      usePokerStore.getState().setConnectionStatus('disconnected');

      if (this.shouldReconnect) {
        this.scheduleReconnect();
      }
    };
  }

  private handleMessage(message: PokerMessage): void {
    console.log('Received message:', message);

    switch (message.type) {
      case 'error':
        usePokerStore.getState().setError(message.message || 'Unknown error');
        break;

      case 'game_state':
        // Allow null data for reset
        usePokerStore.getState().setGameState(message.data || null);
        break;

      case 'player_joined':
        if (message.data) {
          // setGameState will automatically extract and cache any slot icons present in players
          usePokerStore.getState().setGameState(message.data);
        }
        break;

      default:
        console.warn('Unknown message type:', message.type);
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimeout) {
      console.log('Reconnection already scheduled, skipping');
      return;
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('Max reconnection attempts reached');
      usePokerStore.getState().setError('Failed to connect after multiple attempts');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * this.reconnectAttempts;
    
    console.log(`Scheduling reconnection attempt ${this.reconnectAttempts} in ${delay}ms`);
    
    this.reconnectTimeout = setTimeout(() => {
      this.reconnectTimeout = null;
      console.log('Attempting to reconnect...');
      this.connect();
    }, delay);
  }

  sendMessage(message: PokerMessage): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.error('WebSocket not connected, cannot send message');
      usePokerStore.getState().setError('Not connected to server');
      return;
    }

    try {
      this.ws.send(JSON.stringify(message));
    } catch (error) {
      console.error('Failed to send message:', error);
      usePokerStore.getState().setError('Failed to send message');
    }
  }

  join(spinBalance: number): void {
    this.sendMessage({
      type: 'join',
      spin_balance: spinBalance,
    });
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
    this.shouldReconnect = false;
    this.isConnecting = false;

    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    usePokerStore.getState().setConnectionStatus('disconnected');
  }

  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }
}
