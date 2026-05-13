import { useState, useEffect, useRef } from 'react'
import { MessageCircle, X, ArrowRight } from 'lucide-react'
import clsx from 'clsx'

const COPY = {
  triggerLabel: 'Chat with AI Receptionist',
  demoTitle: "Anna's AI Assistant",
  demoSubtitle: 'Online · Usually replies instantly',
  ctaHeading: 'This runs 24/7 for YOUR clients',
  ctaButton: 'Get AIBeautyKit — €59/mo',
  ctaSub: '7-day free trial · No credit card',
}

type MessageType = 'user' | 'ai'

interface Message {
  id: number
  type: MessageType
  text: string
  animate: boolean
}

const SCRIPT: { type: MessageType; text: string }[] = [
  { type: 'user', text: 'Hi, I want to book a nail appointment' },
  {
    type: 'ai',
    text: "Hi! 👋 I'm Anna's AI assistant. We have openings Tuesday 14:00 or Wednesday 11:00. Which works for you?",
  },
  { type: 'user', text: 'Tuesday works!' },
  {
    type: 'ai',
    text: 'Perfect! Can I get your name and phone number to confirm the booking? 📅',
  },
]

function TypewriterText({
  text,
  active,
  onComplete,
}: {
  text: string
  active: boolean
  onComplete: () => void
}) {
  const [display, setDisplay] = useState('')
  const [done, setDone] = useState(false)
  const calledComplete = useRef(false)

  useEffect(() => {
    if (!active) {
      setDisplay(text)
      setDone(true)
      return
    }
    setDisplay('')
    setDone(false)
    calledComplete.current = false
    let i = 0
    const id = setInterval(() => {
      i++
      setDisplay(text.slice(0, i))
      if (i >= text.length) {
        clearInterval(id)
        setDone(true)
      }
    }, 22)
    return () => clearInterval(id)
  }, [text, active])

  useEffect(() => {
    if (done && active && !calledComplete.current) {
      calledComplete.current = true
      const t = setTimeout(onComplete, 600)
      return () => clearTimeout(t)
    }
  }, [done, active, onComplete])

  return (
    <span className={clsx(active && !done && 'cursor-blink')}>{display}</span>
  )
}

export default function ChatDemo() {
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [currentTyping, setCurrentTyping] = useState(-1)
  const [showCTA, setShowCTA] = useState(false)
  const [scriptIndex, setScriptIndex] = useState(0)
  const bottomRef = useRef<HTMLDivElement>(null)
  const started = useRef(false)

  useEffect(() => {
    if (isOpen && !started.current) {
      started.current = true
      advanceScript(0)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, showCTA])

  function advanceScript(index: number) {
    if (index >= SCRIPT.length) {
      setTimeout(() => setShowCTA(true), 800)
      return
    }

    const step = SCRIPT[index]

    if (step.type === 'user') {
      setTimeout(() => {
        setMessages((prev) => [
          ...prev,
          { id: index, type: 'user', text: step.text, animate: false },
        ])
        setScriptIndex(index + 1)
        setTimeout(() => advanceScript(index + 1), 900)
      }, 600)
    } else {
      setTimeout(() => {
        setMessages((prev) => [
          ...prev,
          { id: index, type: 'ai', text: step.text, animate: true },
        ])
        setCurrentTyping(index)
        setScriptIndex(index + 1)
      }, 700)
    }
  }

  function handleTypewriterComplete() {
    setCurrentTyping(-1)
    const nextIndex = scriptIndex
    if (nextIndex < SCRIPT.length) {
      advanceScript(nextIndex)
    } else {
      setTimeout(() => setShowCTA(true), 800)
    }
  }

  function handleOpen() {
    setIsOpen(true)
  }

  function handleClose() {
    setIsOpen(false)
  }

  return (
    <>
      {/* Floating trigger button */}
      <button
        onClick={handleOpen}
        className={clsx(
          'fixed bottom-6 right-6 z-40 flex items-center gap-2.5 rounded-full bg-amber-400 px-5 py-3.5 text-slate-900 font-semibold text-sm shadow-xl hover:bg-amber-300 active:scale-95 transition-all duration-150',
          isOpen && 'hidden',
        )}
        aria-label="Open AI receptionist demo"
      >
        <MessageCircle className="w-5 h-5" />
        <span className="hidden sm:inline">{COPY.triggerLabel}</span>
      </button>

      {/* Chat widget */}
      {isOpen && (
        <div className="fixed bottom-6 right-6 z-50 w-[340px] sm:w-[380px] rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl overflow-hidden flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between gap-3 px-4 py-3.5 bg-slate-800 border-b border-slate-700">
            <div className="flex items-center gap-3">
              <div className="relative">
                <div className="w-9 h-9 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-slate-900 font-bold text-xs">
                  AI
                </div>
                <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-emerald-400 border-2 border-slate-800" />
              </div>
              <div>
                <p className="text-white text-sm font-semibold">{COPY.demoTitle}</p>
                <p className="text-emerald-400 text-xs">{COPY.demoSubtitle}</p>
              </div>
            </div>
            <button
              onClick={handleClose}
              className="text-slate-400 hover:text-white transition-colors p-1 min-w-[36px] min-h-[36px] flex items-center justify-center"
              aria-label="Close chat"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Messages */}
          <div className="flex flex-col gap-3 p-4 overflow-y-auto max-h-72 min-h-[180px]">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={clsx(
                  'flex',
                  msg.type === 'user' ? 'justify-end' : 'justify-start',
                )}
              >
                <div
                  className={clsx(
                    'max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
                    msg.type === 'user'
                      ? 'bg-amber-400 text-slate-900 font-medium rounded-br-sm'
                      : 'bg-slate-700 text-slate-100 rounded-bl-sm',
                  )}
                >
                  {msg.animate ? (
                    <TypewriterText
                      text={msg.text}
                      active={currentTyping === msg.id}
                      onComplete={handleTypewriterComplete}
                    />
                  ) : (
                    msg.text
                  )}
                </div>
              </div>
            ))}

            {/* CTA overlay after demo ends */}
            {showCTA && (
              <div className="mt-2 rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 text-center">
                <p className="text-amber-400 font-semibold text-sm mb-3">
                  {COPY.ctaHeading}
                </p>
                <a
                  href="#trial"
                  onClick={handleClose}
                  className="inline-flex items-center justify-center gap-2 w-full rounded-lg bg-amber-400 px-4 py-2.5 text-slate-900 font-bold text-sm hover:bg-amber-300 transition-colors"
                >
                  {COPY.ctaButton}
                  <ArrowRight className="w-4 h-4" />
                </a>
                <p className="text-slate-500 text-xs mt-2">{COPY.ctaSub}</p>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        </div>
      )}
    </>
  )
}
