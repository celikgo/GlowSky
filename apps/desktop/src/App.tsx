import { useCallback, useEffect, useRef, useState } from "react";
import { Sidebar, type NavKey } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import {
  CommandPalette,
  PaletteContext,
  type ComposerCommand,
  type PaletteTarget,
} from "./components/CommandPalette";
import {
  MoleculeInspector,
  InspectContext,
  type InspectTarget,
} from "./components/MoleculeInspector";
import { ComposerScreen, type ComposerInject } from "./screens/ComposerScreen";
import { DesignScreen } from "./screens/DesignScreen";
import { LibraryScreen } from "./screens/LibraryScreen";
import { DockingScreen } from "./screens/DockingScreen";
import { RetroScreen } from "./screens/RetroScreen";
import { SarScreen } from "./screens/SarScreen";
import { ToolsScreen } from "./screens/ToolsScreen";
import { SettingsScreen } from "./screens/SettingsScreen";
import "./App.css";

const TITLES: Record<NavKey, string> = {
  composer: "Composer",
  design: "Design",
  library: "Library",
  docking: "Docking",
  retro: "Retrosynthesis",
  sar: "Matched Pairs & SAR",
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

  // Molecule inspector (medicinal-chemistry deep-dive), openable from any card.
  const [inspectTarget, setInspectTarget] = useState<InspectTarget | null>(null);
  const inspect = useCallback((t: InspectTarget) => setInspectTarget(t), []);

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
     <InspectContext.Provider value={{ inspect }}>
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
            ) : nav === "retro" ? (
              <RetroScreen />
            ) : nav === "sar" ? (
              <SarScreen />
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
      <MoleculeInspector target={inspectTarget} onClose={() => setInspectTarget(null)} />
     </InspectContext.Provider>
    </PaletteContext.Provider>
  );
}
