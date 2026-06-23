import { useCallback, useEffect, useRef, useState } from "react";
import { Sidebar, type NavKey } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import {
  CommandPalette,
  PaletteContext,
  type ComposerCommand,
  type PaletteTarget,
} from "./components/CommandPalette";
import { ComposerScreen, type ComposerInject } from "./screens/ComposerScreen";
import { DesignScreen } from "./screens/DesignScreen";
import { LibraryScreen } from "./screens/LibraryScreen";
import { DockingScreen } from "./screens/DockingScreen";
import { ToolsScreen } from "./screens/ToolsScreen";
import { SettingsScreen } from "./screens/SettingsScreen";
import "./App.css";

const TITLES: Record<NavKey, string> = {
  composer: "Composer",
  design: "Design",
  library: "Library",
  docking: "Docking",
  tools: "Tools",
  settings: "Settings",
};

export default function App() {
  const [nav, setNav] = useState<NavKey>("composer");

  // Cmd/Ctrl+K command palette.
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteTarget, setPaletteTarget] = useState<PaletteTarget | null>(null);
  // A command the palette pushes into the Composer (seed / prompt / open-editor); the bumping
  // nonce is what the Composer's effect keys off, so the same command can fire twice.
  const [inject, setInject] = useState<ComposerInject | null>(null);
  const nonce = useRef(0);

  const openFor = useCallback((target: PaletteTarget | null) => {
    setPaletteTarget(target);
    setPaletteOpen(true);
  }, []);

  // Global Cmd/Ctrl+K toggles the palette (works even while typing — a deliberate chord).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((cur) => !cur);
        setPaletteTarget(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function runComposerCommand(cmd: ComposerCommand) {
    nonce.current += 1;
    setInject({ ...cmd, nonce: nonce.current });
    setNav("composer");
  }

  return (
    <PaletteContext.Provider value={{ openFor }}>
      <div className="app">
        <Sidebar active={nav} onNavigate={setNav} />
        <main className="app__main">
          <TopBar title={TITLES[nav]} onOpenPalette={() => openFor(null)} />
          <div className="app__content">
            {nav === "composer" ? (
              <ComposerScreen inject={inject} />
            ) : nav === "design" ? (
              <DesignScreen />
            ) : nav === "library" ? (
              <LibraryScreen />
            ) : nav === "docking" ? (
              <DockingScreen />
            ) : nav === "tools" ? (
              <ToolsScreen />
            ) : (
              <SettingsScreen />
            )}
          </div>
        </main>
      </div>
      <CommandPalette
        open={paletteOpen}
        target={paletteTarget}
        onClose={() => setPaletteOpen(false)}
        onNavigate={(key) => {
          setNav(key);
          setPaletteOpen(false);
        }}
        onComposerCommand={(cmd) => {
          runComposerCommand(cmd);
          setPaletteOpen(false);
        }}
      />
    </PaletteContext.Provider>
  );
}
