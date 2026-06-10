import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import { ChatProvider } from "./hooks/ChatContext";
import { ThemeProvider } from "./theme/ThemeProvider";
import "./theme/aurora.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <ChatProvider>
          <App />
        </ChatProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
