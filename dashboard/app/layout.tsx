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
      <body>{children}</body>
    </html>
  );
}
