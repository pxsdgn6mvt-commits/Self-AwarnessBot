import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import clsx from 'clsx'

const COPY = {
  sectionLabel: 'Got Questions?',
  heading: 'Everything you need to know',
  subheading: "Beauty pros ask us these every day. Here are honest answers — no fluff.",
}

const FAQ_ITEMS = [
  {
    q: 'Do I need to know how to use ChatGPT or any AI tools?',
    a: 'Not at all. AIBeautyKit is built for busy beauty professionals, not tech experts. You set it up once in about 20 minutes, and the AI does the rest. No prompts, no configurations, no technical knowledge required.',
  },
  {
    q: 'Will it post automatically to Instagram and other social media?',
    a: 'Yes! On the Pro and Agency plans, AIBeautyKit connects to your Instagram and posts content automatically — Reels scripts, captions, hashtags, and Stories. On Starter, you get content drafts ready to copy-paste in one tap.',
  },
  {
    q: 'Does it work in Finnish AND Russian?',
    a: 'Absolutely. AIBeautyKit supports both Finnish and Russian out of the box. Your AI receptionist automatically detects which language a client is writing in and replies accordingly. All content is generated in your chosen language.',
  },
  {
    q: 'What if I already use Timma or Vello for booking?',
    a: 'AIBeautyKit integrates seamlessly with Timma and Vello. Your AI receptionist connects to your existing booking calendar, so clients book through your usual system — just with an AI handling the conversation 24/7.',
  },
  {
    q: 'Is there a free trial before I commit?',
    a: 'Yes! We offer a 7-day free trial with full access to all Pro features. No credit card required. You will see real results — real bookings, real content — before you pay anything.',
  },
  {
    q: 'How long until I see real results?',
    a: 'Most masters report their first automated bookings within 48 hours. Content results (Instagram growth, engagement) typically appear in 2–4 weeks. Full ROI — 10–15x your subscription cost — usually shows by the end of month one.',
  },
  {
    q: 'Do I need to create content myself, or does the AI handle it?',
    a: 'The AI handles everything. It creates Instagram captions, Reels scripts, hashtag sets, seasonal promotions, and Google Business posts — all in your brand voice. On Pro you just approve or let it auto-post. On Starter you copy-paste the ready drafts.',
  },
  {
    q: 'Can I cancel anytime?',
    a: 'Yes, cancel anytime with one click from your dashboard. No long contracts, no cancellation fees. Your subscription runs until the end of the current billing period, then stops. We are confident you will not want to leave once you see the results.',
  },
  {
    q: 'Is my client data safe and GDPR compliant?',
    a: '100% GDPR compliant. All data is stored on EU servers located in Helsinki, Finland. Client data is encrypted at rest and in transit and is never shared with third parties. We operate under Finnish data protection law.',
  },
  {
    q: "What's the difference between Starter, Pro, and Agency?",
    a: 'Starter (€29/mo) covers AI content creation — posts, captions, hashtags. Pro (€59/mo) adds the full AI team: receptionist, booking, SEO, and Instagram auto-posting — this is what most solo masters choose. Agency (€99/mo) supports up to 5 masters with white-label options and a dedicated account manager.',
  },
  {
    q: 'How does the AI receptionist actually work?',
    a: 'When a client sends you a message — Instagram DM, WhatsApp, or your website — the AI instantly replies 24/7, even at 2am. It checks your real-time calendar, offers available slots, and confirms bookings. All in your language, all in your tone.',
  },
  {
    q: 'What if I have questions or need help setting it up?',
    a: 'Every plan includes onboarding support via chat. Pro and Agency plans get priority support with a 2-hour response guarantee. We also provide a setup guide and a video walkthrough in both Finnish and Russian.',
  },
]

export default function FAQ() {
  const [openIndex, setOpenIndex] = useState<number | null>(null)

  return (
    <section id="faq" className="py-24 px-4">
      <div className="max-w-3xl mx-auto">
        <div className="text-center mb-16 animate-on-scroll">
          <span className="inline-block text-amber-400 text-sm font-semibold tracking-widest uppercase mb-4">
            {COPY.sectionLabel}
          </span>
          <h2 className="text-4xl md:text-5xl font-bold text-white mb-4">
            {COPY.heading}
          </h2>
          <p className="text-slate-400 text-lg">{COPY.subheading}</p>
        </div>

        <div className="space-y-3">
          {FAQ_ITEMS.map((item, index) => {
            const isOpen = openIndex === index
            return (
              <div
                key={index}
                className={clsx(
                  'animate-on-scroll rounded-xl border transition-colors duration-200',
                  isOpen
                    ? 'border-amber-400/40 bg-amber-400/5'
                    : 'border-slate-700/50 bg-slate-800/40 hover:border-slate-600/70',
                )}
              >
                <button
                  onClick={() => setOpenIndex(isOpen ? null : index)}
                  className="w-full flex items-center justify-between gap-4 px-6 py-5 text-left min-h-[56px]"
                  aria-expanded={isOpen}
                >
                  <h3
                    className={clsx(
                      'text-base font-medium leading-snug transition-colors duration-200',
                      isOpen ? 'text-amber-400' : 'text-slate-100',
                    )}
                  >
                    {item.q}
                  </h3>
                  <ChevronDown
                    className={clsx(
                      'shrink-0 w-5 h-5 transition-all duration-300',
                      isOpen ? 'rotate-180 text-amber-400' : 'text-slate-500',
                    )}
                  />
                </button>

                <div
                  className={clsx(
                    'overflow-hidden transition-all duration-300 ease-out',
                    isOpen ? 'max-h-96 opacity-100' : 'max-h-0 opacity-0',
                  )}
                >
                  <p className="px-6 pb-5 text-slate-300 leading-relaxed text-sm">
                    {item.a}
                  </p>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
