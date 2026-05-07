import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sahayak 1092 Command Center",
  description: "AI-first officer command center for the Sahayak 1092 helpline",
  icons: {
    icon: [
      { url: "/sahayak_logo.svg", type: "image/svg+xml" },
      { url: "/sahayak_logo.png", type: "image/png" }
    ],
    shortcut: "/sahayak_logo.svg",
    apple: "/sahayak_logo.png"
  }
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* Space Grotesk + JetBrains Mono – used by the dashboard (was previously @imported in globals.css) */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700;900&family=JetBrains+Mono:wght@400;600&family=Public+Sans:wght@400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
        {/* Material Symbols Outlined – used by the landing page icons .*/}
        <link
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
