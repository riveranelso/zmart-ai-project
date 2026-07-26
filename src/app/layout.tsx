import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Zmart AI",
  description: "Agentes de voz con IA para negocios, integrados con GoHighLevel",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
