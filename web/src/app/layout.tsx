import type { Metadata } from "next";
import { Outfit } from "next/font/google";
import localFont from "next/font/local";
import "./globals.css";

const outfit = Outfit({
  subsets: ["latin"],
  variable: "--font-outfit",
});

const maswen = localFont({
  src: "../../public/fonts/Maswen-ItalicStencil.otf",
  variable: "--font-maswen",
});

export const metadata: Metadata = {
  title: "HyperPhonk Universe",
  description: "A 2D Interactive Map of Music Topology",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${outfit.variable} ${maswen.variable} font-sans antialiased bg-black text-white overflow-hidden`}>
        {children}
      </body>
    </html>
  );
}
