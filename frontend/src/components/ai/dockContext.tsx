import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

type Dock = { open: boolean; wide: boolean; setOpen: (o: boolean) => void; setWide: (w: boolean) => void; ask: (q: string) => void; pending?: { id: number; q: string }; clear: () => void };
const Ctx = createContext<Dock>(null as unknown as Dock);
export const useAiDock = () => useContext(Ctx);

/** Holds whether the analyst panel is open (and wide), and lets any part of the app ask it a question. Ctrl/⌘ + K toggles it. */
export function AiDockProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [wide, setWide] = useState(false);
  const [pending, setPending] = useState<{ id: number; q: string } | undefined>();
  const ask = useCallback((q: string) => { setPending({ id: Date.now(), q }); setOpen(true); }, []);
  const clear = useCallback(() => setPending(undefined), []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen((o) => !o); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const value = useMemo(() => ({ open, wide, setOpen, setWide, ask, pending, clear }), [open, wide, ask, pending, clear]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

