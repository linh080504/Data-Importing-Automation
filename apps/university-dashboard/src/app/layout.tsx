import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "University Data Quality",
  description: "Crawler and data quality dashboard for university import CSVs.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
