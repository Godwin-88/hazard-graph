import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './contexts/AuthContext';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { QuantifayaHeader } from './components/layout/QuantifayaHeader';
import { Dashboard } from './pages/Dashboard';
import GraphExplorer from './pages/GraphExplorer';
import AlertReview from './pages/AlertReview';
import Analytics from './pages/Analytics';
import ScenarioSimulator from './pages/ScenarioSimulator';
import Login from './pages/Login';
import { AssistantChat } from './components/assistant/AssistantChat';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen flex-col bg-[#0A0F1E]">
      <QuantifayaHeader />
      <main className="flex-1 overflow-hidden">{children}</main>
      <AssistantChat />
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />

            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Dashboard />
                  </Layout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/graph"
              element={
                <ProtectedRoute>
                  <Layout>
                    <GraphExplorer />
                  </Layout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/alerts"
              element={
                <ProtectedRoute requiredRole="officer">
                  <Layout>
                    <AlertReview />
                  </Layout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/analytics"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Analytics />
                  </Layout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/scenarios"
              element={
                <ProtectedRoute>
                  <Layout>
                    <ScenarioSimulator />
                  </Layout>
                </ProtectedRoute>
              }
            />

            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}