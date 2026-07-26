import Link from "next/link";
import { PhoneCall, Target, BarChart3 } from "lucide-react";

const features = [
  {
    icon: PhoneCall,
    title: "Call answering",
    description:
      "Agentes de voz con IA que contestan y atienden llamadas de tus clientes las 24 horas.",
  },
  {
    icon: Target,
    title: "Lead qualification",
    description:
      "Cada llamada se registra y califica en tu pipeline de GoHighLevel, sin trabajo manual.",
  },
  {
    icon: BarChart3,
    title: "Reporting",
    description:
      "Visibilidad de contactos, citas y leads en un dashboard simple, directo desde tu CRM.",
  },
];

export default function Home() {
  return (
    <div>
      <header className="flex items-center justify-between px-6 py-6 sm:px-12">
        <span className="text-lg font-bold">Zmart AI</span>
        <Link
          href="/dashboard"
          className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 dark:bg-white dark:text-neutral-900 dark:hover:bg-neutral-200"
        >
          Ir al dashboard
        </Link>
      </header>

      <main className="mx-auto flex max-w-3xl flex-col items-center gap-6 px-6 py-24 text-center sm:py-32">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          Zmart AI
        </h1>
        <p className="max-w-xl text-lg text-neutral-500 dark:text-neutral-400">
          Agentes de voz con IA para negocios, integrados con GoHighLevel:
          llamadas, contactos, citas, calificación de leads y reportes en un
          solo dashboard.
        </p>
        <Link
          href="/dashboard"
          className="rounded-lg bg-brand-600 px-6 py-3 font-medium text-white hover:bg-brand-700"
        >
          Ir al dashboard
        </Link>
      </main>

      <section className="mx-auto grid max-w-5xl grid-cols-1 gap-6 px-6 pb-24 sm:grid-cols-3">
        {features.map((feature) => (
          <div
            key={feature.title}
            className="rounded-xl border border-neutral-200 p-6 dark:border-neutral-800"
          >
            <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-500">
              <feature.icon size={20} />
            </div>
            <h2 className="mb-2 font-semibold">{feature.title}</h2>
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              {feature.description}
            </p>
          </div>
        ))}
      </section>
    </div>
  );
}
