import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Dashboard } from '@/pages/Dashboard'
import { GraphExplorer } from '@/pages/GraphExplorer'

const queryClient = new QueryClient()

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/graph" element={<GraphExplorer />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}