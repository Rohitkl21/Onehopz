import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OneHopz — Development Scaffold (Milestone 1.3)",
  description:
    "Next-generation perishable inventory recovery marketplace scaffold.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
