import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { ThemeProvider } from '@/components/theme-provider'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Boses Berde — Empowering Youth into Green & Sustainable Careers',
  description:
    'An AI-powered guide for climate-positive careers. Boses Berde uses AWS Strands and Bedrock to match interests, suggest training, and open pathways into sustainable jobs for young people.',
  openGraph: {
    title: 'Boses Berde — Empowering Youth into Green & Sustainable Careers',
    description:
      'AI assistant matching skills to green opportunities, part of the Green Rising initiative.',
  },
  icons: {
    icon: '/bosesberder.svg',
    shortcut: '/bosesberder.svg',
    apple: '/bosesberder.svg',
  },
}


export const viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          {children}
        </ThemeProvider>
      </body>
    </html>
  )
}
