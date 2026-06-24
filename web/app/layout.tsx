import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider } from "@/components/ThemeProvider";

export const metadata: Metadata = {
  title: "Meu App",
  description: "Painel administrativo",
};

// Runs before paint so the correct theme class is on <html> with no flash.
const themeScript = `
(function () {
  try {
    var t = localStorage.getItem('app-theme');
    if (!t) t = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    if (t === 'dark') document.documentElement.classList.add('dark');
  } catch (e) {}
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body className="bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-100 antialiased">
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        {/* Providers: theme today; an AuthProvider would wrap here too. */}
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
