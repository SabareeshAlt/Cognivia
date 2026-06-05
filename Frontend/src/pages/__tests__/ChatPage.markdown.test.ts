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
      "7. **7.** Basic Civil and Mechanical Engineering",
      "8. **8.** Basic Electrical Engineering",
      "9. **9.** Problem Solving through Python Programming",
    ].join("\n");

    const html = markdownToSafeHtml(raw, true);

    expect(html).toContain("Technical English I");
    expect(html).toContain("Engineering Mathematics I");
    expect(html).toContain("Professional Communication - English / Japanese / French II");
    expect(html).toContain("Professional Ethics");
    expect(html).toContain("Advanced Computer Architecture");
    expect(html).toContain("Basic Civil and Mechanical Engineering");
    expect(html).toContain("Basic Electrical Engineering");
    expect(html).toContain("Problem Solving through Python Programming");
    expect(html).not.toMatch(/\b191LEH201T\b/);
    expect(html).not.toMatch(/>\s*1\s+1\s+/);
    expect(html).not.toMatch(/>\s*2\s+2\s+/);
    expect(html).not.toContain("<strong>7.</strong>");
    expect(html).not.toContain("<strong>8.</strong>");
    expect(html).not.toContain("<strong>9.</strong>");
  });

  it("removes empty citation and credit placeholders from assistant output", () => {
    const raw = [
      "Semester IV:",
      "* Probability and Number Theory ( - - - , credits) [Source: RAG sample .pdf, Page: ]",
      "* Database Management Systems ( - - - , credits) [Source: RAG sample .pdf, Page ]",
    ].join("\n");

    const html = markdownToSafeHtml(raw, true);

    expect(html).toContain("Probability and Number Theory");
    expect(html).toContain("Database Management Systems");
    expect(html).not.toContain("credits");
    expect(html).not.toContain("Source:");
    expect(html).not.toContain("Page:");
    expect(html).not.toContain("- - -");
  });

  it("handles valid citations with optional colons by stripping them from the body html", () => {
    const raw = "See detail [Source: RAG sample 1.pdf, Page 12] and [Source: RAG sample 2.pdf, Page: 34]";
    const html = markdownToSafeHtml(raw, true);
    expect(html).not.toContain("p. 12");
    expect(html).not.toContain("p. 34");
    expect(html).not.toContain("RAG sample 1.pdf");
    expect(html).not.toContain("RAG sample 2.pdf");
    expect(html).toContain("See detail and");
  });

  it("correctly parses all heading levels from 1 to 6", () => {
    const raw = [
      "# Heading 1",
      "## Heading 2",
      "### Heading 3",
      "#### Heading 4",
      "##### Heading 5",
      "###### Heading 6",
    ].join("\n");

    const html = markdownToSafeHtml(raw, false);

    expect(html).toContain("<h1>Heading 1</h1>");
    expect(html).toContain("<h2>Heading 2</h2>");
    expect(html).toContain("<h3>Heading 3</h3>");
    expect(html).toContain("<p><strong>Heading 4</strong></p>");
    expect(html).toContain("<p><strong>Heading 5</strong></p>");
    expect(html).toContain("<p><strong>Heading 6</strong></p>");
    expect(html).not.toContain("#");
  });
});

