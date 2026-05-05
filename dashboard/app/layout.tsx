import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sahayak 1092 Command Center",
  description: "AI-first officer command center for the Sahayak 1092 helpline"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
