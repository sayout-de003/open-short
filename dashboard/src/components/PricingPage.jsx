import React, { useState } from 'react';
import { ArrowDown, ArrowRight, Check, ChevronDown, MoveRight, Cpu, KeyRound, Send, Server, HardDrive, Repeat } from 'lucide-react';
import PricingSection from './PricingSection';

const FAQS = [
  {
    question: "How does the CREOVIS plan work?",
    answer: "CREOVIS provides free minutes to test the platform. Paid plans start at $12/month for 100 minutes without watermarks, and unlock full auto-posting to TikTok, Instagram, YouTube, Facebook, LinkedIn, Threads and Bluesky, plus channel Autopilot to clip and schedule new videos automatically."
  },
  {
    question: "Can CREOVIS generate YouTube thumbnails and titles?",
    answer: "Yes. CREOVIS includes an AI YouTube thumbnail generator, AI YouTube title generator, and AI YouTube description generator — all powered by Google Gemini 3.1 Flash-Lite. Upload your video and the AI suggests 10 viral title options with an interactive refinement chat. Then it generates multiple thumbnail designs using AI image generation — upload a face photo and background image for personalized results."
  },
  {
    question: "How much does it cost to generate an AI UGC video?",
    answer: "AI Shorts uses external models (fal.ai for video generation, ElevenLabs for voiceover). Low Cost mode costs approximately $0.65 per video (Flux image + ElevenLabs voice + Hailuo img2video + VEED Lipsync + b-roll). Premium mode costs approximately $2.00 per video using Kling Avatar v2 for higher quality. Both modes are significantly cheaper than hiring UGC creators ($50-500 per video) or traditional agencies."
  },
  {
    question: "Can CREOVIS post my clips to my social networks automatically?",
    answer: "Yes, on every paid plan of CREOVIS (from $12/month). Connect your TikTok, Instagram, YouTube, Facebook, LinkedIn, Threads and Bluesky accounts once from the app and each clip can be posted to all of them in one go, or scheduled, without downloading anything; posting runs on Upload-Post and is already set up for you. Autopilot goes one step further: connect your YouTube channel and every new video you upload is clipped on its own, and the best clips are scheduled to your socials, one a day at the hour you choose."
  },
  {
    question: "I only want to post videos I already have. Do I need CREOVIS?",
    answer: "No. CREOVIS is for cutting long videos into clips. If you only want to post videos or photos you already have to TikTok, Instagram, YouTube, LinkedIn, Facebook, X, Threads, Pinterest, Bluesky or Reddit, use Upload-Post (upload-post.com) directly: it is the social posting API CREOVIS publishes through."
  },
  {
    question: "Does API and MCP access cost extra?",
    answer: "No. Every plan can create API keys in the account page and use the REST API and the MCP server at mcp.creovis.app/mcp. Calls draw from the same monthly minutes as the dashboard, so automating with Claude, ChatGPT or n8n does not change the price of anything."
  }
];

const TRUST_CARDS = [
  {
    eyebrow: 'instant cloud rendering · nvidia gpu',
    body: (
      <>
        Dedicated high-performance NVIDIA GPUs process your videos in about 50 seconds.
        Zero complex hardware or manual setup required.
      </>
    ),
  },
  {
    eyebrow: 'no watermark on paid plans · no per-clip credits',
    body: (
      <>
        Paid plans export clean clips, with no watermark. Plans meter minutes of input video per billing
        period, never per-clip credits.
      </>
    ),
  },
  {
    eyebrow: 'cancel anytime',
    body: (
      <>
        Start on the free plan — test your first videos without a credit card. Billing for paid
        plans runs on Stripe — cancel anytime directly from your account.
      </>
    ),
  },
];

const FAQItem = ({ question, answer, isOpen, onClick }) => (
  <div>
    <button
      onClick={onClick}
      className="w-full flex items-center justify-between px-1 py-5 text-left"
    >
      <span className="text-ink font-medium pr-4">{question}</span>
      <ChevronDown
        size={18}
        className={`text-muted flex-shrink-0 transition-transform ${isOpen ? 'rotate-180' : ''}`}
      />
    </button>
    {isOpen && (
      <div className="px-1 pb-6">
        <p className="text-muted text-sm leading-relaxed">{answer}</p>
      </div>
    )}
  </div>
);

const DemoFigure = ({ src, label, className = '', children }) => (
  <figure className={`border border-rule rounded-card overflow-hidden bg-paper2 ${className}`}>
    <div className="relative">
      <video
        src={src}
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
        className="block w-full h-auto"
      />
      {children}
    </div>
    <figcaption className="readout px-3 py-2 border-t border-rule">{label}</figcaption>
  </figure>
);

// Conversion-focused paywall / pricing page (#/pricing). Wraps <PricingSection/>.
export default function PricingPage({ onRequireLogin }) {
  const [openFaq, setOpenFaq] = useState(null);

  const scrollToPlans = () => {
    document.getElementById('pricing-plans')?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="min-h-screen bg-paper text-ink2 animate-fade">
      {/* Header */}
      <header className="px-6 pt-20 pb-12">
        <div className="max-w-6xl mx-auto text-center">
          <p className="eyebrow mb-5">Pricing</p>
          <h1 className="font-display lowercase text-ink tracking-tight text-4xl md:text-6xl leading-[1.02] mb-5">
            start clipping in minutes.
          </h1>
          <p className="readout">first video free (up to 60 min) · then 20 min/month · no credit card</p>
        </div>
      </header>

      {/* Demo proof strip */}
      <section className="px-6 pb-16">
        <div className="max-w-4xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-5 md:gap-6">
            <DemoFigure src="/demo/clip-source.mp4" label="input · 16:9" />

            <MoveRight size={20} className="text-brass hidden md:block" aria-hidden="true" />
            <ArrowDown size={20} className="text-brass md:hidden justify-self-center" aria-hidden="true" />

            <DemoFigure
              src="/demo/clip-vertical.mp4"
              label="output · 9:16 · tracked"
              className="w-44 sm:w-48 justify-self-center md:justify-self-auto"
            />
          </div>
          <p className="text-center text-xs text-muted lowercase mt-4">
            real output from the clip generator — same footage, reframed by AI face tracking.
          </p>
        </div>
      </section>

      {/* Pricing grid */}
      <section id="pricing-plans" className="px-6 py-16 border-t border-rule scroll-mt-8">
        <div className="max-w-6xl mx-auto">
          <PricingSection onRequireLogin={onRequireLogin} />
        </div>
      </section>

      {/* Trust strip */}
      <section className="px-6 py-16 border-t border-rule">
        <div className="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-4">
          {TRUST_CARDS.map((card) => (
            <div key={card.eyebrow} className="card p-6">
              <div className="flex items-center gap-2 mb-3">
                <Check size={16} className="text-ok shrink-0" />
                <span className="eyebrow">{card.eyebrow}</span>
              </div>
              <p className="text-sm text-muted leading-relaxed">{card.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Mini FAQ */}
      <section className="px-6 py-16 border-t border-rule">
        <div className="max-w-3xl mx-auto">
          <div className="mb-10">
            <p className="eyebrow mb-3">Billing · FAQ</p>
            <h2 className="font-display text-3xl md:text-4xl lowercase text-ink tracking-tight">
              common questions
            </h2>
          </div>
          <div className="divide-y divide-rule border-y border-rule">
            {FAQS.map((faq, i) => (
              <FAQItem
                key={i}
                question={faq.question}
                answer={faq.answer}
                isOpen={openFaq === i}
                onClick={() => setOpenFaq(openFaq === i ? null : i)}
              />
            ))}
          </div>
        </div>
      </section>

      {/* Closing statement */}
      <section className="px-6 py-24 border-t border-rule">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="font-display text-4xl md:text-5xl lowercase text-ink tracking-tight mb-10">
            twenty free minutes. every month. no card until you decide.
          </h2>
          <div className="flex flex-wrap items-center justify-center gap-4">
            <button onClick={scrollToPlans} className="btn-primary whitespace-nowrap">
              start free
              <ArrowRight size={16} />
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
