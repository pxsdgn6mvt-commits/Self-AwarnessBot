import { useEffect, useState, useRef } from 'react'
import {
  Calendar,
  Megaphone,
  Video,
  Search,
  ImageIcon,
  Users,
  ArrowRight,
  Shield,
  Globe,
  Clock,
  Check,
  ChevronRight,
  Zap,
} from 'lucide-react'
import FAQ from '../components/FAQ'
import Testimonials from '../components/Testimonials'
import EmailCapture from '../components/EmailCapture'
import ChatDemo from '../components/ChatDemo'

// ─── Copy constants ───────────────────────────────────────────────────────────
const COPY = {
  nav: {
    brand: 'AIBeautyKit',
    links: ['Features', 'Testimonials', 'FAQ', 'Pricing'],
    cta: 'Start Free Trial',
  },
  hero: {
    badge: 'New · AI Team of 6 in one subscription',
    heading: 'Your AI Team of 6\nfor €29/month',
    sub: 'Stop spending 15 hours a week on admin, content and marketing. Let AI handle it all — bookings, Instagram, SEO, and client messages — 24/7.',
    ctaPrimary: 'Start Free Trial',
    ctaSecondary: 'See How It Works',
    disclaimer: 'No credit card required · 7-day free trial · Cancel anytime',
    socialProof: '500+ masters across 8 European countries',
  },
  stats: [
    { value: 500, suffix: '+', label: 'Beauty Pros' },
    { value: 8, suffix: '', label: 'Countries' },
    { value: 15, suffix: 'h', label: 'Saved / Week' },
    { value: 30, suffix: '%', label: 'More Bookings' },
  ],
  features: {
    sectionLabel: 'Your AI Team',
    heading: '6 specialists. One subscription.',
    sub: 'Hire your full AI team today — each one an expert in their role, working around the clock so you can focus on your craft.',
    items: [
      {
        icon: Calendar,
        title: 'AI Receptionist',
        desc: 'Books appointments 24/7 via Instagram DM, WhatsApp, and your website. Never misses a booking, never sleeps.',
        color: 'text-sky-400',
        bg: 'bg-sky-400/10',
      },
      {
        icon: Megaphone,
        title: 'AI Marketer',
        desc: 'Creates seasonal campaigns, flash sale announcements, referral programs, and promotional content automatically.',
        color: 'text-rose-400',
        bg: 'bg-rose-400/10',
      },
      {
        icon: Video,
        title: 'AI Videographer',
        desc: 'Writes Reels hooks, scripts, and captions that stop the scroll. Trend-aware, beauty-specific, always on-brand.',
        color: 'text-violet-400',
        bg: 'bg-violet-400/10',
      },
      {
        icon: Search,
        title: 'AI SEO Specialist',
        desc: 'Optimises your Google Business profile, builds local keywords, and ensures new clients in your area find you first.',
        color: 'text-emerald-400',
        bg: 'bg-emerald-400/10',
      },
      {
        icon: ImageIcon,
        title: 'AI Content Creator',
        desc: 'Produces daily Instagram posts, Stories, carousels, and hashtag sets — all in your voice, all ready to publish.',
        color: 'text-amber-400',
        bg: 'bg-amber-400/10',
      },
      {
        icon: Users,
        title: 'AI Community Manager',
        desc: 'Replies to comments, handles DMs, and keeps your community engaged — even while you are with a client.',
        color: 'text-pink-400',
        bg: 'bg-pink-400/10',
      },
    ],
  },
  howItWorks: {
    sectionLabel: 'How It Works',
    heading: 'Up and running in 20 minutes',
    steps: [
      {
        num: '01',
        title: 'Connect your accounts',
        desc: 'Link Instagram, your booking system (Timma / Vello), and WhatsApp in one click.',
      },
      {
        num: '02',
        title: 'Train your AI in your style',
        desc: 'Answer 10 quick questions about your services, prices, and tone. Your AI learns your brand voice.',
      },
      {
        num: '03',
        title: 'Watch it work',
        desc: 'Your AI team starts creating content, handling bookings, and growing your presence from day one.',
      },
    ],
  },
  roi: {
    sectionLabel: 'Return on Investment',
    heading: 'Your first month pays for itself',
    sub: 'Adjust the slider to see your personal ROI estimate.',
    sliderLabel: 'Clients per month',
    labels: {
      revenueIncrease: 'Est. extra revenue',
      timeSaved: 'Hours saved / month',
      netRoi: 'Net ROI',
      planCost: 'Pro plan cost',
    },
  },
  pricing: {
    sectionLabel: 'Pricing',
    heading: 'One price. Full AI team.',
    sub: 'No hidden fees. Cancel anytime.',
    plans: [
      {
        name: 'Starter',
        price: '€29',
        period: '/month',
        tagline: 'For solo masters who want great content',
        features: [
          'AI Content Creator',
          'Daily Instagram posts & captions',
          'Hashtag generator',
          'Content calendar (1 month ahead)',
          'Up to 100 posts / month',
          '1 social account',
          'Email support',
        ],
        cta: 'Start Free Trial',
        highlight: false,
      },
      {
        name: 'Pro',
        price: '€59',
        period: '/month',
        tagline: 'Full AI team — the choice of 80% of our masters',
        badge: 'Most Popular',
        features: [
          'Everything in Starter',
          'AI Receptionist (24/7 booking)',
          'AI SEO Specialist',
          'AI Marketer & Community Manager',
          'Reel scripts & video hooks',
          'Auto-post to Instagram',
          'Timma / Vello integration',
          '3 social accounts',
          'Priority support (2h response)',
        ],
        cta: 'Start Free Trial',
        highlight: true,
      },
      {
        name: 'Agency',
        price: '€99',
        period: '/month',
        tagline: 'For studios and multi-master teams',
        features: [
          'Everything in Pro',
          'Up to 5 beauty masters',
          'White-label AI assistant',
          'Dedicated account manager',
          'Custom AI brand voice',
          'Advanced analytics dashboard',
          'API access',
          'SLA support',
        ],
        cta: 'Contact Sales',
        highlight: false,
      },
    ],
  },
  trust: [
    { icon: Shield, label: 'GDPR Compliant', sub: 'EU servers · Helsinki' },
    { icon: Globe, label: '8 Countries', sub: 'Finland, Estonia & more' },
    { icon: Clock, label: '24/7 Active', sub: 'Never misses a booking' },
    { icon: Zap, label: '10–15x ROI', sub: 'In your first month' },
  ],
  footer: {
    brand: 'AIBeautyKit 3.0',
    tagline: 'AI-powered growth for beauty professionals.',
    copy: '© 2025 AIBeautyKit. All rights reserved.',
  },
}

// ─── Counter animation hook ───────────────────────────────────────────────────
function useCounter(end: number, inView: boolean, duration = 1800) {
  const [count, setCount] = useState(0)
  useEffect(() => {
    if (!inView) return
    let start = 0
    const steps = Math.ceil(duration / 16)
    const increment = end / steps
    const id = setInterval(() => {
      start += increment
      if (start >= end) {
        setCount(end)
        clearInterval(id)
      } else {
        setCount(Math.floor(start))
      }
    }, 16)
    return () => clearInterval(id)
  }, [end, inView, duration])
  return count
}

// ─── Stat counter card ────────────────────────────────────────────────────────
function StatCard({
  value,
  suffix,
  label,
  delay,
}: {
  value: number
  suffix: string
  label: string
  delay: number
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [inView, setInView] = useState(false)
  const count = useCounter(value, inView)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setInView(true) },
      { threshold: 0.5 },
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  return (
    <div
      ref={ref}
      className="animate-on-scroll text-center"
      style={{ transitionDelay: `${delay}ms` }}
    >
      <div className="text-4xl font-black text-amber-400 tabular-nums">
        {count}
        {suffix}
      </div>
      <div className="text-slate-400 text-sm mt-1">{label}</div>
    </div>
  )
}

// ─── ROI Calculator ───────────────────────────────────────────────────────────
function ROICalculator() {
  const [clients, setClients] = useState(20)
  const extraBookings = Math.round(clients * 0.27)
  const avgBookingValue = 65
  const revenueIncrease = extraBookings * avgBookingValue
  const hoursFreed = 15 * 4 // per month
  const planCost = 59
  const netRoi = Math.round(((revenueIncrease - planCost) / planCost) * 100)

  return (
    <section id="roi" className="py-24 px-4 bg-slate-900/40">
      <div className="max-w-3xl mx-auto">
        <div className="text-center mb-12 animate-on-scroll">
          <span className="inline-block text-amber-400 text-sm font-semibold tracking-widest uppercase mb-4">
            {COPY.roi.sectionLabel}
          </span>
          <h2 className="text-4xl md:text-5xl font-bold text-white mb-4">
            {COPY.roi.heading}
          </h2>
          <p className="text-slate-400 text-lg">{COPY.roi.sub}</p>
        </div>

        <div className="animate-on-scroll rounded-2xl border border-slate-700/60 bg-slate-800/50 p-8">
          {/* Slider */}
          <div className="mb-8">
            <div className="flex justify-between items-center mb-3">
              <label className="text-slate-300 text-sm font-medium">
                {COPY.roi.sliderLabel}
              </label>
              <span className="text-amber-400 font-bold text-lg">{clients}</span>
            </div>
            <input
              type="range"
              min={5}
              max={60}
              value={clients}
              onChange={(e) => setClients(Number(e.target.value))}
              className="w-full h-2 rounded-full appearance-none bg-slate-700 accent-amber-400 cursor-pointer"
            />
            <div className="flex justify-between text-slate-500 text-xs mt-1">
              <span>5</span>
              <span>60</span>
            </div>
          </div>

          {/* Results grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              {
                label: COPY.roi.labels.revenueIncrease,
                value: `+€${revenueIncrease}`,
                color: 'text-emerald-400',
              },
              {
                label: COPY.roi.labels.timeSaved,
                value: `${hoursFreed}h`,
                color: 'text-sky-400',
              },
              {
                label: COPY.roi.labels.planCost,
                value: `€${planCost}`,
                color: 'text-slate-300',
              },
              {
                label: COPY.roi.labels.netRoi,
                value: `${netRoi}x`,
                color: 'text-amber-400',
              },
            ].map((item) => (
              <div
                key={item.label}
                className="rounded-xl bg-slate-900/60 border border-slate-700/50 p-4 text-center"
              >
                <div className={`text-2xl font-black ${item.color}`}>
                  {item.value}
                </div>
                <div className="text-slate-500 text-xs mt-1">{item.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

// ─── Main Home page ───────────────────────────────────────────────────────────
export default function Home() {
  // Global scroll animation observer
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible')
          }
        })
      },
      { threshold: 0.1 },
    )
    document.querySelectorAll('.animate-on-scroll').forEach((el) => {
      observer.observe(el)
    })
    return () => observer.disconnect()
  }, [])

  return (
    <div className="min-h-screen bg-slate-950 text-slate-50">

      {/* ── Navigation ─────────────────────────────────────────────────────── */}
      <nav className="sticky top-0 z-30 border-b border-slate-800/60 bg-slate-950/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-4 flex items-center justify-between h-16">
          <span className="font-black text-xl text-white tracking-tight">
            {COPY.nav.brand}
            <span className="text-amber-400">.</span>
          </span>
          <div className="hidden md:flex items-center gap-8">
            {COPY.nav.links.map((link) => (
              <a
                key={link}
                href={`#${link.toLowerCase()}`}
                className="text-slate-400 hover:text-white text-sm transition-colors"
              >
                {link}
              </a>
            ))}
          </div>
          <a
            href="#trial"
            className="rounded-lg bg-amber-400 px-4 py-2 text-slate-900 font-semibold text-sm hover:bg-amber-300 transition-colors min-h-[40px] flex items-center"
          >
            {COPY.nav.cta}
          </a>
        </div>
      </nav>

      {/* ── Hero ───────────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden py-20 md:py-32 px-4">
        {/* Background glow */}
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="w-[600px] h-[600px] rounded-full bg-amber-400/5 blur-3xl" />
        </div>

        <div className="relative max-w-4xl mx-auto text-center">
          <div className="animate-on-scroll inline-flex items-center gap-2 rounded-full border border-amber-400/30 bg-amber-400/10 px-4 py-1.5 text-amber-400 text-sm font-medium mb-8">
            <Zap className="w-3.5 h-3.5" />
            {COPY.hero.badge}
          </div>

          <h1 className="animate-on-scroll text-5xl md:text-7xl font-black text-white leading-tight tracking-tight mb-6">
            {COPY.hero.heading.split('\n').map((line, i) => (
              <span key={i} className="block">
                {i === 1 ? (
                  <>
                    for{' '}
                    <span className="text-amber-400">€29/month</span>
                  </>
                ) : (
                  line
                )}
              </span>
            ))}
          </h1>

          <p className="animate-on-scroll text-slate-400 text-lg md:text-xl max-w-2xl mx-auto leading-relaxed mb-10">
            {COPY.hero.sub}
          </p>

          <div className="animate-on-scroll flex flex-col sm:flex-row items-center justify-center gap-4 mb-6">
            <a
              href="#trial"
              className="inline-flex items-center gap-2 rounded-xl bg-amber-400 px-8 py-4 text-slate-900 font-bold text-base hover:bg-amber-300 active:scale-[0.98] transition-all duration-150 min-h-[52px] w-full sm:w-auto justify-center"
            >
              {COPY.hero.ctaPrimary}
              <ArrowRight className="w-5 h-5" />
            </a>
            <a
              href="#features"
              className="inline-flex items-center gap-2 rounded-xl border border-slate-700 px-8 py-4 text-slate-300 font-semibold text-base hover:border-slate-500 hover:text-white transition-all duration-150 min-h-[52px] w-full sm:w-auto justify-center"
            >
              {COPY.hero.ctaSecondary}
              <ChevronRight className="w-4 h-4" />
            </a>
          </div>

          <p className="animate-on-scroll text-slate-500 text-sm">{COPY.hero.disclaimer}</p>
          <p className="animate-on-scroll text-slate-500 text-xs mt-2">
            ⭐ {COPY.hero.socialProof}
          </p>
        </div>
      </section>

      {/* ── Stats bar ──────────────────────────────────────────────────────── */}
      <div className="border-y border-slate-800/50 bg-slate-900/30 py-10 px-4">
        <div className="max-w-3xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8">
          {COPY.stats.map((stat, i) => (
            <StatCard
              key={stat.label}
              value={stat.value}
              suffix={stat.suffix}
              label={stat.label}
              delay={i * 100}
            />
          ))}
        </div>
      </div>

      {/* ── Features ───────────────────────────────────────────────────────── */}
      <section id="features" className="py-24 px-4">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16 animate-on-scroll">
            <span className="inline-block text-amber-400 text-sm font-semibold tracking-widest uppercase mb-4">
              {COPY.features.sectionLabel}
            </span>
            <h2 className="text-4xl md:text-5xl font-bold text-white mb-4">
              {COPY.features.heading}
            </h2>
            <p className="text-slate-400 text-lg max-w-2xl mx-auto">
              {COPY.features.sub}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {COPY.features.items.map((feat, i) => {
              const Icon = feat.icon
              return (
                <div
                  key={feat.title}
                  className={`animate-on-scroll stagger-${i + 1} group rounded-2xl border border-slate-700/50 bg-slate-800/40 p-6 hover:border-slate-600/70 hover:bg-slate-800/70 transition-all duration-200`}
                >
                  <div
                    className={`inline-flex items-center justify-center w-11 h-11 rounded-xl ${feat.bg} mb-4`}
                  >
                    <Icon className={`w-5 h-5 ${feat.color}`} />
                  </div>
                  <h3 className="text-white font-bold text-base mb-2">{feat.title}</h3>
                  <p className="text-slate-400 text-sm leading-relaxed">{feat.desc}</p>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      {/* ── How It Works ───────────────────────────────────────────────────── */}
      <section className="py-24 px-4 bg-slate-900/30">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-16 animate-on-scroll">
            <span className="inline-block text-amber-400 text-sm font-semibold tracking-widest uppercase mb-4">
              {COPY.howItWorks.sectionLabel}
            </span>
            <h2 className="text-4xl md:text-5xl font-bold text-white">
              {COPY.howItWorks.heading}
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {COPY.howItWorks.steps.map((step, i) => (
              <div
                key={step.num}
                className={`animate-on-scroll stagger-${i + 1} text-center`}
              >
                <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-amber-400/10 border border-amber-400/20 text-amber-400 font-black text-lg mb-5">
                  {step.num}
                </div>
                <h3 className="text-white font-bold text-lg mb-3">{step.title}</h3>
                <p className="text-slate-400 text-sm leading-relaxed">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Testimonials ───────────────────────────────────────────────────── */}
      <Testimonials />

      {/* ── ROI Calculator ─────────────────────────────────────────────────── */}
      <ROICalculator />

      {/* ── Pricing ────────────────────────────────────────────────────────── */}
      <section id="pricing" className="py-24 px-4">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16 animate-on-scroll">
            <span className="inline-block text-amber-400 text-sm font-semibold tracking-widest uppercase mb-4">
              {COPY.pricing.sectionLabel}
            </span>
            <h2 className="text-4xl md:text-5xl font-bold text-white mb-4">
              {COPY.pricing.heading}
            </h2>
            <p className="text-slate-400 text-lg">{COPY.pricing.sub}</p>
          </div>

          {/* Mobile: horizontal scroll wrapper */}
          <div className="overflow-x-auto pb-4">
            <div className="grid grid-cols-3 gap-5 min-w-[680px] md:min-w-0">
              {COPY.pricing.plans.map((plan, i) => (
                <div
                  key={plan.name}
                  className={`animate-on-scroll stagger-${i + 1} relative rounded-2xl border p-7 flex flex-col ${
                    plan.highlight
                      ? 'border-amber-400/60 bg-amber-400/5 ring-1 ring-amber-400/20'
                      : 'border-slate-700/50 bg-slate-800/40'
                  }`}
                >
                  {plan.badge && (
                    <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-amber-400 px-4 py-1 text-slate-900 text-xs font-bold whitespace-nowrap">
                      {plan.badge}
                    </span>
                  )}

                  <div className="mb-6">
                    <h3 className="text-white font-bold text-lg mb-1">{plan.name}</h3>
                    <p className="text-slate-400 text-xs mb-4 leading-snug">{plan.tagline}</p>
                    <div className="flex items-end gap-1">
                      <span className="text-4xl font-black text-white">{plan.price}</span>
                      <span className="text-slate-400 text-sm mb-1">{plan.period}</span>
                    </div>
                  </div>

                  <ul className="space-y-2.5 flex-1 mb-7">
                    {plan.features.map((feat) => (
                      <li key={feat} className="flex items-start gap-2.5">
                        <Check
                          className={`w-4 h-4 shrink-0 mt-0.5 ${
                            plan.highlight ? 'text-amber-400' : 'text-slate-400'
                          }`}
                        />
                        <span className="text-slate-300 text-sm leading-snug">{feat}</span>
                      </li>
                    ))}
                  </ul>

                  <a
                    href="#trial"
                    className={`block text-center rounded-xl px-5 py-3 font-bold text-sm transition-all duration-150 min-h-[44px] flex items-center justify-center ${
                      plan.highlight
                        ? 'bg-amber-400 text-slate-900 hover:bg-amber-300'
                        : 'border border-slate-600 text-slate-300 hover:border-slate-400 hover:text-white'
                    }`}
                  >
                    {plan.cta}
                  </a>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── FAQ ────────────────────────────────────────────────────────────── */}
      <div id="faq-section">
        <FAQ />
      </div>

      {/* ── Trust badges ───────────────────────────────────────────────────── */}
      <div className="border-y border-slate-800/50 bg-slate-900/30 py-10 px-4">
        <div className="max-w-4xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-6">
          {COPY.trust.map((item, i) => {
            const Icon = item.icon
            return (
              <div
                key={item.label}
                className={`animate-on-scroll stagger-${i + 1} flex flex-col items-center text-center gap-2`}
              >
                <div className="w-10 h-10 rounded-xl bg-amber-400/10 flex items-center justify-center">
                  <Icon className="w-5 h-5 text-amber-400" />
                </div>
                <p className="text-white font-semibold text-sm">{item.label}</p>
                <p className="text-slate-500 text-xs">{item.sub}</p>
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Email Capture ──────────────────────────────────────────────────── */}
      <EmailCapture />

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <footer className="border-t border-slate-800/50 py-10 px-4">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div>
            <span className="font-black text-white">
              {COPY.footer.brand}
              <span className="text-amber-400">.</span>
            </span>
            <p className="text-slate-500 text-sm mt-1">{COPY.footer.tagline}</p>
          </div>
          <p className="text-slate-600 text-sm">{COPY.footer.copy}</p>
        </div>
      </footer>

      {/* ── Floating Chat Demo ─────────────────────────────────────────────── */}
      <ChatDemo />
    </div>
  )
}
