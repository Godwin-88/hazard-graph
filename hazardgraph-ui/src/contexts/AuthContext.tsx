import {
  createContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react';

interface UserPayload {
  id: number;
  username: string;
  role: string;
}

interface AuthState {
  user: UserPayload | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refreshToken: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextType | null>(null);

const API_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000') + '/api/v1';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    accessToken: null,
    isAuthenticated: false,
    isLoading: true,
  });

  const refreshTokenFn = useCallback(async () => {
    const storedRefresh = sessionStorage.getItem('refresh_token');
    if (!storedRefresh) {
      setState((prev) => ({ ...prev, isLoading: false }));
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: storedRefresh }),
      });

      if (!res.ok) {
        sessionStorage.removeItem('refresh_token');
        setState({
          user: null,
          accessToken: null,
          isAuthenticated: false,
          isLoading: false,
        });
        return;
      }

      const data = await res.json();
      const payload = decodeToken(data.access_token);
      setState({
        user: {
          id: Number(payload.sub) || 0,
          username: String(payload.sub || ''),
          role: String(payload.role || 'viewer'),
        },
        accessToken: data.access_token,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch {
      setState({
        user: null,
        accessToken: null,
        isAuthenticated: false,
        isLoading: false,
      });
    }
  }, []);

  useEffect(() => {
    refreshTokenFn();
  }, [refreshTokenFn]);

  const login = useCallback(
    async (username: string, password: string) => {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Login failed' }));
        throw new Error(err.detail || 'Login failed');
      }

      const data = await res.json();
      sessionStorage.setItem('refresh_token', data.refresh_token);

      setState({
        user: { id: data.user_id, username, role: data.role },
        accessToken: data.access_token,
        isAuthenticated: true,
        isLoading: false,
      });
    },
    []
  );

  const logout = useCallback(() => {
    sessionStorage.removeItem('refresh_token');
    setState({
      user: null,
      accessToken: null,
      isAuthenticated: false,
      isLoading: false,
    });
  }, []);

  return (
    <AuthContext.Provider
      value={{ ...state, login, logout, refreshToken: refreshTokenFn }}
    >
      {children}
    </AuthContext.Provider>
  );
}

function decodeToken(token: string): Record<string, unknown> {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(base64));
  } catch {
    return {};
  }
}