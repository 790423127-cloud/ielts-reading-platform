import type { Metadata } from "next";
import AppShell from "@/components/AppShell";
import ReadingAnnotationLayer from "@/components/ReadingAnnotationLayer";
import "./globals.css";
import "./learning.css";
import "./plan-sentences.css";
import "./vocabulary.css";
import "./ai-teacher.css";
import "./reading-annotations.css";

export const metadata: Metadata = {
  title: "IELTS G类阅读学习平台",
  description: "确定性判分、错题学习闭环与证据约束 AI 教学平台"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <AppShell>{children}</AppShell>
        <ReadingAnnotationLayer />
      </body>
    </html>
  );
}
