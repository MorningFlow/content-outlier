import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import SyncOnOpen from "@/components/SyncOnOpen";

export const metadata: Metadata = {
  title: "Content Outlier",
  description: "Monitor competitor Instagram Reels and surface outlier content performing above baseline.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div style={{ display: "flex", minHeight: "100vh" }}>
          <Sidebar />
          <SyncOnOpen />
          <main
            style={{
              flex: 1,
              minWidth: 0,
              overflowX: "auto",
              padding: "32px 40px 64px",
              maxWidth: 1360,
            }}
          >
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
