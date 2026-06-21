import { useState } from "react";
import { Sidebar, type NavKey } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { ComposerScreen } from "./screens/ComposerScreen";
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

  return (
    <div className="app">
      <Sidebar active={nav} onNavigate={setNav} />
      <main className="app__main">
        <TopBar title={TITLES[nav]} />
        <div className="app__content">
          {nav === "composer" ? (
            <ComposerScreen />
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
  );
}
