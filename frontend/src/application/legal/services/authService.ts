/**
 * Servicio de autenticación para OAuth2 + JWT
 * Se conecta con el backend de IA Jurídica
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface RegisterData {
  email: string;
  username: string;
  password: string;
  full_name?: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  refresh_token?: string;
}

export interface User {
  id: string;
  email: string;
  username: string;
  full_name?: string;
  picture?: string;
  role: string;
  roles: string[];
  is_active: boolean;
}

export interface AuthState {
  isAuthenticated: boolean;
  user: User | null;
  token: string | null;
}

const TOKEN_KEY = 'auth_token';
const REFRESH_TOKEN_KEY = 'refresh_token';
const USER_KEY = 'auth_user';

class AuthService {
  private token: string | null = null;
  private refreshToken: string | null = null;
  private user: User | null = null;
  private listeners: Set<(state: AuthState) => void> = new Set();

  constructor() {
    // Ya no cargamos desde localStorage por seguridad
    // Verificamos autenticación con el backend
  }

  // ── Storage ───────────────────────────────────────────────────────────────

  private loadFromStorage() {
    // Deshabilitado por seguridad - usamos httpOnly cookies
    // Las cookies se manejan automáticamente por el navegador
  }

  private saveToStorage() {
    // Deshabilitado por seguridad - usamos httpOnly cookies
  }

  private clearStorage() {
    // Deshabilitado por seguridad - usamos httpOnly cookies
  }

  // ── State Management ───────────────────────────────────────────────────────

  private notifyListeners() {
    const state: AuthState = {
      isAuthenticated: !!this.token,
      user: this.user,
      token: this.token,
    };
    
    this.listeners.forEach(listener => listener(state));
  }

  subscribe(listener: (state: AuthState) => void) {
    this.listeners.add(listener);
    
    // Emitir estado actual inmediatamente
    listener({
      isAuthenticated: !!this.token,
      user: this.user,
      token: this.token,
    });
    
    return () => {
      this.listeners.delete(listener);
    };
  }

  getState(): AuthState {
    return {
      isAuthenticated: !!this.token,
      user: this.user,
      token: this.token,
    };
  }

  setState(state: AuthState) {
    this.token = state.token;
    this.user = state.user;
    this.notifyListeners();
  }

  // ── Auth Methods ───────────────────────────────────────────────────────────

  async login(credentials: LoginCredentials): Promise<void> {
    const formData = new FormData();
    formData.append('username', credentials.username);
    formData.append('password', credentials.password);

    const response = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      credentials: 'include',  // Importante: incluir cookies
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Error de autenticación' }));
      throw new Error(error.detail || 'Error de autenticación');
    }
    
    // Las cookies se establecen automáticamente por el backend
    // Verificar autenticación obteniendo el usuario actual
    await this.fetchCurrentUser();
    this.notifyListeners();
  }

  async register(data: RegisterData): Promise<AuthResponse> {
    const response = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Error de registro' }));
      throw new Error(error.detail || 'Error de registro');
    }

    const result: AuthResponse = await response.json();
    
    // Si el registro devuelve tokens, guardarlos
    if (result.access_token) {
      this.token = result.access_token;
      this.refreshToken = result.refresh_token || null;
      await this.fetchCurrentUser();
      this.saveToStorage();
      this.notifyListeners();
    }
    
    return result;
  }

  async logout(): Promise<void> {
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        credentials: 'include',  // Importante: incluir cookies
      });
    } catch {
      // Ignorar error de logout
    } finally {
      this.token = null;
      this.refreshToken = null;
      this.user = null;
      this.notifyListeners();
    }
  }

  async refreshAccessToken(): Promise<string> {
    if (!this.refreshToken) {
      throw new Error('No refresh token disponible');
    }

    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ refresh_token: this.refreshToken }),
    });

    if (!response.ok) {
      this.logout();
      throw new Error('Error al refrescar token');
    }

    const data: AuthResponse = await response.json();
    
    this.token = data.access_token;
    this.saveToStorage();
    this.notifyListeners();
    
    return data.access_token;
  }

  private async fetchCurrentUser(): Promise<void> {
    const response = await fetch(`${API_BASE}/auth/me`, {
      credentials: 'include',  // Importante: incluir cookies httpOnly
    });

    if (!response.ok) {
      throw new Error('Error al obtener usuario');
    }

    this.user = await response.json();
  }

  async getCurrentUser(): Promise<User | null> {
    if (this.user) return this.user;
    
    if (this.token) {
      try {
        await this.fetchCurrentUser();
        this.saveToStorage();
      } catch {
        return null;
      }
    }
    
    return this.user;
  }

  // ── Request Wrapper ─────────────────────────────────────────────────────────

  async authenticatedRequest<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      credentials: 'include',  // Importante: incluir cookies httpOnly
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (response.status === 401) {
      // Intentar refrescar token usando cookies
      try {
        const refreshResponse = await fetch(`${API_BASE}/auth/refresh`, {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ refresh_token: 'from_cookie' }),
        });
        
        if (refreshResponse.ok) {
          // Reintentar la solicitud
          return this.authenticatedRequest<T>(endpoint, options);
        }
      } catch {
        this.logout();
        throw new Error('Sesión expirada');
      }
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Error en la solicitud' }));
      throw new Error(error.detail || 'Error en la solicitud');
    }

    return response.json();
  }

  // ── Getters ───────────────────────────────────────────────────────────────

  get isAuthenticated(): boolean {
    return !!this.token;
  }

  get currentUser(): User | null {
    return this.user;
  }

  get accessToken(): string | null {
    return this.token;
  }
}

// Singleton
export const authService = new AuthService();
