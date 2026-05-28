import { describe, expect, it } from "vitest";

import { markdownToSafeHtml } from "@/pages/ChatPage";

describe("ChatPage markdown cleanup", () => {
  it("removes duplicated numeric prefixes and subject codes for assistant output", () => {
    const raw = [
      "1. 1 1 Technical English I",
      "2. 2 2 Engineering Mathematics I",
      "3. 1 7 Professional Communication - English / Japanese / French II",
      "4. 1 21 Professional Ethics",
      "5. 10 30 Advanced Computer Architecture",
      "6. 191LEH201T Technical English I",
    ].join("\n");

    const html = markdownToSafeHtml(raw, true);

    expect(html).toContain("Technical English I");
    expect(html).toContain("Engineering Mathematics I");
    expect(html).toContain("Professional Communication - English / Japanese / French II");
    expect(html).toContain("Professional Ethics");
    expect(html).toContain("Advanced Computer Architecture");
    expect(html).not.toMatch(/\b191LEH201T\b/);
    expect(html).not.toMatch(/>\s*1\s+1\s+/);
    expect(html).not.toMatch(/>\s*2\s+2\s+/);
  });

  it("removes empty citation and credit placeholders from assistant output", () => {
    const raw = [
      "Semester IV:",
      "* Probability and Number Theory ( - - - , credits) [Source: RAG sample .pdf, Page: ]",
      "* Database Management Systems ( - - - , credits) [Source: RAG sample .pdf, Page: ]",
    ].join("\n");

    const html = markdownToSafeHtml(raw, true);

    expect(html).toContain("Probability and Number Theory");
    expect(html).toContain("Database Management Systems");
    expect(html).not.toContain("credits");
    expect(html).not.toContain("Source:");
    expect(html).not.toContain("Page:");
    expect(html).not.toContain("- - -");
  });
});
