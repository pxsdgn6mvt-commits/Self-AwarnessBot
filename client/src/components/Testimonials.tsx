import { Star, TrendingUp } from 'lucide-react'

const COPY = {
  sectionLabel: 'Real Results',
  heading: 'Masters who stopped doing it alone',
  subheading: 'They were skeptical too. Then they saw their first AI-booked appointment.',
}

const TESTIMONIALS = [
  {
    name: 'Anna K.',
    city: 'Helsinki',
    specialty: 'Nail Master',
    quote:
      'I was skeptical at first — I am not good with technology at all. But the setup took 20 minutes, and within the first week I had three new bookings from my AI assistant while I was asleep. In three weeks my bookings went up 34%.',
    metric: 'Bookings up 34%',
    metricSub: 'in 3 weeks',
    avatar: 'AK',
    avatarGradient: 'from-rose-500 to-pink-600',
  },
  {
    name: 'Masha R.',
    city: 'Tampere',
    specialty: 'Lash Artist',
    quote:
      'I used to spend my Sunday evenings writing Instagram posts for the whole week. Now AIBeautyKit does it automatically. I save at least 12 hours every week and my content actually looks more professional than before.',
    metric: '12 hrs saved',
    metricSub: 'every week',
    avatar: 'MR',
    avatarGradient: 'from-violet-500 to-purple-600',
  },
  {
    name: 'Elena V.',
    city: 'Espoo',
    specialty: 'Hair Stylist',
    quote:
      'In two months my Instagram went from 400 to 1,200 followers. But what really matters is these are local followers who become real clients. My salon is now fully booked two weeks in advance.',
    metric: '400 → 1,200',
    metricSub: 'followers in 2 months',
    avatar: 'EV',
    avatarGradient: 'from-amber-500 to-orange-500',
  },
]

function StarRating() {
  return (
    <div className="flex gap-0.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <Star key={i} className="w-4 h-4 fill-amber-400 text-amber-400" />
      ))}
    </div>
  )
}

export default function Testimonials() {
  return (
    <section id="testimonials" className="py-24 px-4 bg-slate-900/30">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16 animate-on-scroll">
          <span className="inline-block text-amber-400 text-sm font-semibold tracking-widest uppercase mb-4">
            {COPY.sectionLabel}
          </span>
          <h2 className="text-4xl md:text-5xl font-bold text-white mb-4">
            {COPY.heading}
          </h2>
          <p className="text-slate-400 text-lg max-w-2xl mx-auto">
            {COPY.subheading}
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {TESTIMONIALS.map((t, index) => (
            <article
              key={t.name}
              className={`animate-on-scroll stagger-${index + 1} flex flex-col gap-5 rounded-2xl border border-slate-700/50 bg-slate-800/50 p-7 hover:border-slate-600/70 transition-colors duration-200`}
            >
              {/* Avatar + identity */}
              <div className="flex items-center gap-4">
                <div
                  className={`flex items-center justify-center w-12 h-12 rounded-full bg-gradient-to-br ${t.avatarGradient} text-white font-bold text-sm shrink-0`}
                >
                  {t.avatar}
                </div>
                <div>
                  <p className="text-white font-semibold text-sm">{t.name}</p>
                  <p className="text-slate-400 text-xs">
                    {t.specialty} · {t.city}
                  </p>
                </div>
              </div>

              {/* Stars */}
              <StarRating />

              {/* Quote */}
              <blockquote className="text-slate-300 text-sm leading-relaxed flex-1">
                "{t.quote}"
              </blockquote>

              {/* Metric badge */}
              <div className="inline-flex items-center gap-2 self-start rounded-full border border-amber-400/30 bg-amber-400/10 px-3 py-1.5">
                <TrendingUp className="w-3.5 h-3.5 text-amber-400" />
                <span className="text-amber-400 font-semibold text-xs">
                  {t.metric}
                </span>
                <span className="text-amber-400/60 text-xs">{t.metricSub}</span>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}
