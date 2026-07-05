import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { queryClient } from '@/services/query-client'
import { ErrorBoundary } from '@/components/feedback/error-boundary'
import App from '@/App'
import '@/styles/globals.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={200}>
          <App />
          <Toaster
            theme="dark"
            position="bottom-right"
            toastOptions={{
              style: {
                background: 'var(--color-surface-2)',
                border: '1px solid var(--color-border)',
                color: 'var(--color-text-primary)',
              },
            }}
          />
        </TooltipProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
)
