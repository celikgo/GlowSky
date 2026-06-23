/**
 * The Composer — the conversational, multi-turn front door to the design loop ("Cursor for
 * Chemists"). A chemist types intent in natural language; each turn is either a design run
 * (analogs stream in as cards) or a conversational reply. Molecules can be `@`-attached as
 * context or drawn, and a working seed carries across turns so follow-ups ("now lower logP")
 * build on the last structure. Design results reuse the same cards + multi-select + save-to-
 * library flow as the one-shot Design screen.
 */
import { useEffect, useMemo, useRef, useState } from "react"
import {
  api,
  type Candidate,
  type ChatContextMolecule,
  type ChatWireMessage,
  type DesignPlan,
  type TraceEntry,
} from "../lib/api"
import { MoleculeCard } from "./MoleculeCard"
import { MoleculeEditorModal } from "../components/MoleculeEditorModal"
import { SaveToLibraryModal } from "./SaveToLibraryModal"
import { ContextPickerModal } from "./ContextPickerModal"
import type { ComposerCommand } from "../components/CommandPalette"

/** A command pushed in from the Cmd+K palette; `nonce` re-fires the effect for repeat commands. */
export interface ComposerInject extends ComposerCommand {
  nonce: number
}

function selKey(c: Candidate): string {
  return c.inchikey + c.modification
}

/** The assistant's accumulating state for one turn (filled milestone by milestone). */
interface AssistantTurn {
  kind: "pending" | "design" | "chat" | "need_seed" | "error"
  text: string
  plan: DesignPlan | null
  candidates: Candidate[]
  trace: TraceEntry[]
  runId: string | null
}

type Message =
  | { id: number; role: "user"; content: string; context: ChatContextMolecule[] }
  | { id: number; role: "assistant"; turn: AssistantTurn }

const SUGGESTIONS = [
  "Make 12 analogs of aspirin with MW<300, no PAINS, drug-like",
  "What does QED measure?",
]

let _nextId = 1
const newId = () => _nextId++

export function ComposerScreen({ inject }: { inject: ComposerInject | null }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [seed, setSeed] = useState("")
  const [pendingContext, setPendingContext] = useState<ChatContextMolecule[]>([])
  const [streaming, setStreaming] = useState(false)

  const [editorOpen, setEditorOpen] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [saveOpen, setSaveOpen] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const cancelRef = useRef<(() => void) | null>(null)
  const threadRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => () => cancelRef.current?.(), [])
  // Keep the latest turn in view as content streams in.
  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" })
  }, [messages])

  // Apply a Cmd+K palette command: set the seed (if the action targeted a molecule), prefill the
  // prompt, and/or open the editor. Keyed on the nonce so the same command can fire repeatedly.
  useEffect(() => {
    if (!inject) return
    if (inject.seed !== undefined) setSeed(inject.seed)
    if (inject.prompt !== undefined) setInput(inject.prompt)
    if (inject.openEditor) setEditorOpen(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inject?.nonce])

  /** Patch the assistant turn with the given id (the streaming target). */
  function patchTurn(id: number, fn: (t: AssistantTurn) => AssistantTurn) {
    setMessages((ms) =>
      ms.map((m) => (m.id === id && m.role === "assistant" ? { ...m, turn: fn(m.turn) } : m)),
    )
  }

  function send() {
    const text = input.trim()
    if (!text || streaming) return
    cancelRef.current?.()

    const userMsg: Message = { id: newId(), role: "user", content: text, context: pendingContext }
    const assistantId = newId()
    const assistantMsg: Message = {
      id: assistantId,
      role: "assistant",
      turn: { kind: "pending", text: "", plan: null, candidates: [], trace: [], runId: null },
    }

    // Wire history = every prior message + this user turn (stateless server).
    const history: ChatWireMessage[] = [
      ...messages.map((m): ChatWireMessage =>
        m.role === "user"
          ? { role: "user", content: m.content }
          : { role: "assistant", content: m.turn.text },
      ),
      { role: "user", content: text },
    ]
    const turnContext = pendingContext

    setMessages((ms) => [...ms, userMsg, assistantMsg])
    setInput("")
    setPendingContext([])
    setSelected(new Set())
    setStreaming(true)

    cancelRef.current = api.streamChat(history, seed || null, turnContext, {
      onPlan: (_parent, plan) => patchTurn(assistantId, (t) => ({ ...t, kind: "design", plan })),
      onCandidate: (c) =>
        patchTurn(assistantId, (t) => ({ ...t, candidates: [...t.candidates, c] })),
      onTrace: (tr) => patchTurn(assistantId, (t) => ({ ...t, trace: [...t.trace, tr] })),
      onRanked: (order) =>
        patchTurn(assistantId, (t) => {
          const idx = new Map(order.map((k, i) => [k, i]))
          const candidates = [...t.candidates].sort(
            (a, b) => (idx.get(a.inchikey) ?? Infinity) - (idx.get(b.inchikey) ?? Infinity),
          )
          return { ...t, candidates }
        }),
      onAssistantText: (txt) => patchTurn(assistantId, (t) => ({ ...t, text: txt })),
      onComplete: (res) => {
        patchTurn(assistantId, (t) => ({
          ...t,
          kind: res.kind === "design" ? "design" : res.kind === "chat" ? "chat" : "need_seed",
          text: res.text || t.text,
          // The design result is authoritative for the final set + order.
          plan: res.design?.plan ?? t.plan,
          candidates: res.design?.candidates ?? t.candidates,
          trace: res.design?.trace ?? t.trace,
          runId: res.design?.run_id ?? t.runId,
        }))
        if (res.seed) setSeed(res.seed)
        setStreaming(false)
      },
      onError: (msg) => {
        patchTurn(assistantId, (t) => ({ ...t, kind: "error", text: msg }))
        setStreaming(false)
      },
    })
  }

  function toggleSelect(c: Candidate) {
    setSelected((cur) => {
      const next = new Set(cur)
      const k = selKey(c)
      if (next.has(k)) next.delete(k)
      else next.add(k)
      return next
    })
  }

  // Every candidate across the conversation, for resolving the save selection.
  const allCandidates = useMemo(
    () =>
      messages.flatMap((m) => (m.role === "assistant" ? m.turn.candidates : [])),
    [messages],
  )
  const selectedCandidates = useMemo(
    () => allCandidates.filter((c) => selected.has(selKey(c))),
    [allCandidates, selected],
  )

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends; Shift+Enter newlines (chat convention).
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="composer">
      <div className="composer__thread" ref={threadRef}>
        {messages.length === 0 ? (
          <div className="composer__empty">
            <div className="composer__emptytitle">Design by conversation</div>
            <div className="composer__emptybody">
              Describe what you want, attach or draw a seed, and iterate. Try:
            </div>
            <div className="composer__suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="chip chip--btn" onClick={() => setInput(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m) =>
            m.role === "user" ? (
              <UserBubble key={m.id} content={m.content} context={m.context} />
            ) : (
              <AssistantBubble
                key={m.id}
                turn={m.turn}
                selected={selected}
                onToggleSelect={toggleSelect}
              />
            ),
          )
        )}
      </div>

      {/* Composer dock */}
      <div className="composer__dock card">
        <div className="composer__seedline">
          <span className="composer__seedlabel">Seed</span>
          {seed ? (
            <span className="chip mono composer__seedchip">
              {seed}
              <button className="composer__chipx" onClick={() => setSeed("")} aria-label="Clear seed">
                ✕
              </button>
            </span>
          ) : (
            <span className="composer__seednone">none — draw or attach one</span>
          )}
          <button className="chip chip--btn" onClick={() => setEditorOpen(true)}>
            ✎ Draw
          </button>
          <button className="chip chip--btn" onClick={() => setPickerOpen(true)}>
            @ Context
          </button>
          {selectedCandidates.length > 0 ? (
            <>
              <span className="library__spacer" />
              <button className="btn btn--sm" onClick={() => setSaveOpen(true)}>
                ⊕ Save {selectedCandidates.length} to library
              </button>
            </>
          ) : null}
        </div>

        {pendingContext.length > 0 ? (
          <div className="composer__ctxchips">
            {pendingContext.map((c, i) => (
              <span key={`${c.smiles}-${i}`} className="chip composer__ctxchip">
                @ {c.name || c.smiles}
                <button
                  className="composer__chipx"
                  onClick={() => setPendingContext((cur) => cur.filter((_, j) => j !== i))}
                  aria-label="Remove context"
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        ) : null}

        <div className="composer__inputrow">
          <textarea
            className="textarea composer__input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask, or describe a design — e.g. “make 10 analogs, MW<300, no PAINS”"
            rows={2}
          />
          <button className="btn" onClick={send} disabled={streaming || !input.trim()}>
            {streaming ? <span className="spinner" /> : "➤"}
            {streaming ? "Working…" : "Send"}
          </button>
        </div>
      </div>

      <MoleculeEditorModal
        open={editorOpen}
        initialSmiles={seed}
        title="Draw the seed molecule"
        onClose={() => setEditorOpen(false)}
        onUse={(smiles) => {
          setSeed(smiles)
          setEditorOpen(false)
        }}
      />
      <ContextPickerModal
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onAttach={(mols) => {
          setPendingContext((cur) => [...cur, ...mols])
          // If no seed yet, the first attached molecule becomes the working seed.
          setSeed((cur) => cur || mols[0]?.smiles || "")
          setPickerOpen(false)
        }}
      />
      <SaveToLibraryModal
        open={saveOpen}
        candidates={selectedCandidates}
        onClose={() => setSaveOpen(false)}
        onSaved={() => {
          setSaveOpen(false)
          setSelected(new Set())
        }}
      />
    </div>
  )
}

function UserBubble({
  content,
  context,
}: {
  content: string
  context: ChatContextMolecule[]
}) {
  return (
    <div className="msg msg--user">
      <div className="msg__bubble">
        {content}
        {context.length > 0 ? (
          <div className="msg__ctx">
            {context.map((c, i) => (
              <span key={`${c.smiles}-${i}`} className="chip chip--accent mono">
                @ {c.name || c.smiles}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}

function AssistantBubble({
  turn,
  selected,
  onToggleSelect,
}: {
  turn: AssistantTurn
  selected: Set<string>
  onToggleSelect: (c: Candidate) => void
}) {
  const kept = turn.candidates.filter((c) => c.passed_filters).length
  return (
    <div className="msg msg--assistant">
      <div className="msg__avatar">✦</div>
      <div className="msg__bubble msg__bubble--assistant">
        {turn.kind === "pending" && turn.candidates.length === 0 && !turn.text ? (
          <div className="msg__thinking">
            <span className="spinner" /> Thinking…
          </div>
        ) : null}

        {turn.plan ? (
          <div className="summary">
            <span className="chip chip--accent">
              {turn.candidates.length} generated · {kept} passed
            </span>
            {Object.entries(turn.plan.constraints)
              .filter(([, v]) => v !== null && v !== false)
              .map(([k, v]) => (
                <span className="chip" key={k}>
                  {k.replace(/_/g, " ")}: {String(v)}
                </span>
              ))}
          </div>
        ) : null}

        {turn.candidates.length > 0 ? (
          <div className="grid grid--inchat">
            {turn.candidates.map((c) => (
              <MoleculeCard
                key={selKey(c)}
                candidate={c}
                selected={selected.has(selKey(c))}
                onToggleSelect={() => onToggleSelect(c)}
              />
            ))}
          </div>
        ) : null}

        {turn.text ? <div className="msg__text">{turn.text}</div> : null}

        {turn.runId ? (
          <div className="msg__exports">
            <button
              className="chip chip--btn"
              onClick={() => api.downloadRun(turn.runId as string, "ipynb")}
            >
              ⬇ notebook
            </button>
            <button
              className="chip chip--btn"
              onClick={() => api.downloadRun(turn.runId as string, "md")}
            >
              ⬇ report
            </button>
          </div>
        ) : null}
      </div>
    </div>
  )
}
