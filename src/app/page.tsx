import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-24 text-center">
      <h1 className="text-4xl font-bold">Zmart AI</h1>
      <p className="max-w-xl text-lg text-gray-500">
        Agentes de voz con IA para negocios, integrados con GoHighLevel:
        llamadas, contactos, citas, calificación de leads y reportes en un
        solo dashboard.
      </p>
      <Link
        href="/dashboard"
        className="rounded-lg bg-black px-6 py-3 text-white hover:bg-gray-800"
      >
        Ir al dashboard
      </Link>
    </main>
  );
}
