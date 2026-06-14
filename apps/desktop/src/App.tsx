import { useState } from "react";
import { Sidebar, type NavKey } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { DesignScreen } from "./screens/DesignScreen";
import { LibraryScreen } from "./screens/LibraryScreen";
import { ToolsScreen } from "./screens/ToolsScreen";
import { SettingsScreen } from "./screens/SettingsScreen";
import "./App.css";

const TITLES: Record<NavKey, string> = {
  design: "Design",
  library: "Library",
  tools: "Tools",
  settings: "Settings",
};

export default function App() {
  const [nav, setNav] = useState<NavKey>("design");

  return (
    <div className="app">
      <Sidebar active={nav} onNavigate={setNav} />
      <main className="app__main">
        <TopBar title={TITLES[nav]} />
        <div className="app__content">
          {nav === "design" ? (
            <DesignScreen />
          ) : nav === "library" ? (
            <LibraryScreen />
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
