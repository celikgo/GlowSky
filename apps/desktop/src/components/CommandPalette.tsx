/**
 * The Cmd/Ctrl+K command palette — quick navigation plus **inline actions on a molecule**
 * (the MVP "Cmd+K on a molecule: make analogs / modify property" item). Opened globally with
 * the keyboard, or scoped to a specific molecule from a card's ⌘K button (via `usePalette`).
 *
 * Molecule actions don't compute here — they compose a Composer turn (set the seed + prefill a
 * natural-language prompt) and hand off to the chat, so there's one design path, not two.
 */
import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react"
import type { NavKey } from "./Sidebar"

export interface PaletteTarget {
  smiles: string
  name?: string | null
}

/** What a molecule action injects into the Composer. */
export interface ComposerCommand {
  seed?: string
  prompt?: string
  openEditor?: boolean
}

/** Lets any component (e.g. a molecule card) open the palette, optionally scoped to a molecule. */
export const PaletteContext = createContext<{ openFor: (target: PaletteTarget | null) => void }>({
  openFor: () => {},
})

export function usePalette() {
  return useContext(PaletteContext)
}

interface Command {
  id: string
  title: string
  hint: string
  group: "Navigate" | "Molecule"
  run: () => void
}

const NAV: { key: NavKey; label: string }[] = [
  { key: "composer", label: "Composer" },
  { key: "design", label: "Design" },
  { key: "library", label: "Library" },
  { key: "docking", label: "Docking" },
  { key: "tools", label: "Tools" },
  { key: "settings", label: "Settings" },
]

/** Molecule inline actions, each a (title, prompt) the Composer runs. */
const MOL_ACTIONS: { id: string; title: string; prompt?: string; openEditor?: boolean }[] = [
  { id: "analogs", title: "Make analogs", prompt: "Make 12 analogs, drug-like, no PAINS" },
  {
    id: "polar",
    title: "Make more polar (lower logP)",
    prompt: "Make 10 analogs with lower logP, no PAINS",
  },
  { id: "smaller", title: "Make smaller (MW<300)", prompt: "Make 10 analogs with MW<300, drug-like" },
  {
    id: "druglike",
    title: "Make drug-like analogs (Lipinski, no PAINS)",
    prompt: "Make 12 drug-like analogs, Lipinski, no PAINS",
  },
  { id: "draw", title: "Draw / edit a molecule", openEditor: true },
]

export function CommandPalette({
  open,
  target,
  onClose,
  onNavigate,
  onComposerCommand,
}: {
  open: boolean
  target: PaletteTarget | null
  onClose: () => void
  onNavigate: (key: NavKey) => void
  onComposerCommand: (cmd: ComposerCommand) => void
}) {
  const [query, setQuery] = useState("")
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)

  // Reset query + focus the input each time the palette opens.
  useEffect(() => {
    if (open) {
      setQuery("")
      setActive(0)
      // focus after the element is shown
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open])

  const commands = useMemo<Command[]>(() => {
    const mol: Command[] = MOL_ACTIONS.map((a) => ({
      id: `mol-${a.id}`,
      title: target?.name && a.prompt ? `${a.title} — ${target.name}` : a.title,
      hint: a.openEditor ? "open the 2D editor" : "runs in the Composer",
      group: "Molecule",
      run: () =>
        onComposerCommand(
          a.openEditor
            ? { openEditor: true }
            : { seed: target?.smiles, prompt: a.prompt },
        ),
    }))
    const nav: Command[] = NAV.map((n) => ({
      id: `nav-${n.key}`,
      title: `Go to ${n.label}`,
      hint: "navigate",
      group: "Navigate",
      run: () => onNavigate(n.key),
    }))
    return [...mol, ...nav]
  }, [target, onNavigate, onComposerCommand])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return commands
    return commands.filter((c) => `${c.title} ${c.hint} ${c.group}`.toLowerCase().includes(q))
  }, [commands, query])

  if (!open) return null

  function runAt(i: number) {
    const cmd = filtered[i]
    if (!cmd) return
    cmd.run()
    onClose()
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault()
      setActive((i) => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setActive((i) => Math.max(i - 1, 0))
    } else if (e.key === "Enter") {
      e.preventDefault()
      runAt(active)
    } else if (e.key === "Escape") {
      e.preventDefault()
      onClose()
    }
  }

  return (
    <div className="palette-overlay" onClick={onClose}>
      <div className="palette" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="palette__input"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setActive(0)
          }}
          onKeyDown={onKeyDown}
          placeholder="Type a command — navigate, or act on a molecule…"
        />
        {target ? (
          <div className="palette__target">
            Acting on <span className="mono">{target.name || target.smiles}</span>
          </div>
        ) : null}
        <div className="palette__list">
          {filtered.length === 0 ? (
            <div className="palette__empty">No matching commands.</div>
          ) : (
            filtered.map((c, i) => (
              <button
                key={c.id}
                className={`palette__item ${i === active ? "palette__item--active" : ""}`}
                onMouseEnter={() => setActive(i)}
                onClick={() => runAt(i)}
              >
                <span className="palette__itemtitle">{c.title}</span>
                <span className="palette__itemgroup">{c.group}</span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
