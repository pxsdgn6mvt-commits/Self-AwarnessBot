import { useState, type FormEvent } from 'react'
import { Mail, CheckCircle, Loader2 } from 'lucide-react'

const COPY = {
  sectionLabel: 'Free Trial',
  heading: 'Your AI team is ready to start',
  subheading: '7 days free. No credit card. Cancel anytime.',
  emailPlaceholder: 'Your email address',
  specialtyLabel: 'I am a…',
  ctaButton: 'Get Free 7-Day Trial',
  successHeading: "You're in! Check your inbox.",
  successSub: 'We sent your trial access link. See you on the other side.',
  disclaimer: 'No credit card required · Cancel anytime · GDPR compliant',
}

const SPECIALTIES = [
  { value: '', label: 'I am a…' },
  { value: 'nail-master', label: 'Nail Master' },
  { value: 'hair-stylist', label: 'Hair Stylist' },
  { value: 'lash-artist', label: 'Lash Artist' },
  { value: 'other', label: 'Other Beauty Pro' },
]

type Status = 'idle' | 'loading' | 'success'

export default function EmailCapture() {
  const [email, setEmail] = useState('')
  const [specialty, setSpecialty] = useState('')
  const [status, setStatus] = useState<Status>('idle')

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!email || !specialty) return
    setStatus('loading')
    setTimeout(() => setStatus('success'), 1800)
  }

  return (
    <section
      id="trial"
      data-form="email-capture"
      className="py-24 px-4"
    >
      <div className="max-w-xl mx-auto text-center animate-on-scroll">
        <span className="inline-block text-amber-400 text-sm font-semibold tracking-widest uppercase mb-4">
          {COPY.sectionLabel}
        </span>
        <h2 className="text-4xl md:text-5xl font-bold text-white mb-4">
          {COPY.heading}
        </h2>
        <p className="text-slate-400 text-lg mb-10">{COPY.subheading}</p>

        {status === 'success' ? (
          <div className="flex flex-col items-center gap-4 rounded-2xl border border-amber-400/30 bg-amber-400/5 p-10">
            <CheckCircle className="w-12 h-12 text-amber-400" />
            <h3 className="text-xl font-bold text-white">{COPY.successHeading}</h3>
            <p className="text-slate-400">{COPY.successSub}</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={COPY.emailPlaceholder}
              className="w-full rounded-xl border border-slate-700 bg-slate-800/70 px-5 py-4 text-white placeholder-slate-500 focus:border-amber-400/60 focus:outline-none focus:ring-2 focus:ring-amber-400/20 transition-colors min-h-[52px]"
            />

            <div className="relative">
              <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 pointer-events-none" />
              <select
                required
                value={specialty}
                onChange={(e) => setSpecialty(e.target.value)}
                className="w-full appearance-none rounded-xl border border-slate-700 bg-slate-800/70 pl-11 pr-5 py-4 text-white focus:border-amber-400/60 focus:outline-none focus:ring-2 focus:ring-amber-400/20 transition-colors min-h-[52px] cursor-pointer"
              >
                {SPECIALTIES.map((s) => (
                  <option key={s.value} value={s.value} disabled={s.value === ''}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="submit"
              disabled={status === 'loading' || !email || !specialty}
              className="flex items-center justify-center gap-2 w-full rounded-xl bg-amber-400 px-6 py-4 font-bold text-slate-900 text-base hover:bg-amber-300 active:scale-[0.98] transition-all duration-150 disabled:opacity-60 disabled:cursor-not-allowed min-h-[52px]"
            >
              {status === 'loading' ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Setting up your trial…
                </>
              ) : (
                COPY.ctaButton
              )}
            </button>

            <p className="text-slate-500 text-xs mt-1">{COPY.disclaimer}</p>
          </form>
        )}
      </div>
    </section>
  )
}
