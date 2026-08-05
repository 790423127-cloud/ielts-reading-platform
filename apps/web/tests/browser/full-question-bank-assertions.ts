import { expect, type Page } from "@playwright/test";

export async function assertPartLayout(page: Page, title: string, partNumber: number) {
  const layout = await page.evaluate(() => {
    const passageCopy = document.querySelector<HTMLElement>(".passage-copy");
    const questionsPane = document.querySelector<HTMLElement>(".questions-pane");
    const divider = document.querySelector<HTMLElement>(".exam-divider");
    const dock = document.querySelector<HTMLElement>(".exam-question-dock");
    const passageStyle = passageCopy ? getComputedStyle(passageCopy) : null;
    const questionStyle = questionsPane ? getComputedStyle(questionsPane) : null;
    const overflowing = [
      ...document.querySelectorAll<HTMLElement>(
        ".questions-scroll,.matching-text-group,.matching-matrix-group,.matching-interactive-bank"
      )
    ]
      .filter((element) => element.scrollWidth > element.clientWidth + 2)
      .map((element) => ({
        className: element.className,
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth
      }));
    const matrixSignatures = [
      ...document.querySelectorAll<HTMLTableElement>(".matching-answer-matrix")
    ].map((table) => ({
      headerCells: table.tHead?.rows[0]?.cells.length || 0,
      radioCells: table.tBodies[0]?.rows[0]?.querySelectorAll('input[type="radio"]').length || 0,
      rowHeight: Math.round(table.tBodies[0]?.rows[0]?.getBoundingClientRect().height || 0)
    }));
    const descriptiveMatching = [
      ...document.querySelectorAll<HTMLElement>(".matching-text-group")
    ].map((group) => {
      const list = group.querySelector<HTMLElement>(".matching-question-list");
      const bank = group.querySelector<HTMLElement>(".matching-interactive-bank");
      return {
        columns: getComputedStyle(group).gridTemplateColumns.split(" ").filter(Boolean).length,
        questionWidth: Math.round(list?.getBoundingClientRect().width || 0),
        bankWidth: Math.round(bank?.getBoundingClientRect().width || 0)
      };
    });
    const sectionLetters = [
      ...document.querySelectorAll<HTMLElement>(".passage-section-letter")
    ].map((element) => {
      const style = getComputedStyle(element);
      return {
        background: style.backgroundColor,
        borderWidth: style.borderTopWidth,
        fontWeight: style.fontWeight
      };
    });
    const sourceTableFontSizes = [
      ...document.querySelectorAll<HTMLElement>(".passage-source-table")
    ].map((element) => Number.parseFloat(getComputedStyle(element).fontSize));
    return {
      documentOverflow:
        document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
      dividerWidth: Math.round(divider?.getBoundingClientRect().width || 0),
      dockHeight: Math.round(dock?.getBoundingClientRect().height || 0),
      passageFontSize: Number.parseFloat(passageStyle?.fontSize || "0"),
      passageFontWeight: passageStyle?.fontWeight || "",
      sourceHtmlPassage: passageCopy?.classList.contains("passage-source-html") || false,
      questionFontSize: Number.parseFloat(questionStyle?.fontSize || "0"),
      questionPaneWidth: Math.round(questionsPane?.getBoundingClientRect().width || 0),
      overflowing,
      matrixSignatures,
      descriptiveMatching,
      sectionLetters,
      sourceTableFontSizes,
      unresolvedTemplateFallbacks: [
        ...document.querySelectorAll<HTMLElement>(".structured-completion")
      ].filter((element) => element.innerText.includes("_____")).length
    };
  });

  const label = `${title} Part ${partNumber}`;
  expect(layout.documentOverflow, `${label} document overflow`).toBe(false);
  expect(layout.dividerWidth, `${label} divider width`).toBe(8);
  expect(layout.dockHeight, `${label} bottom navigator height`).toBe(40);
  expect(layout.passageFontSize, `${label} article font size`).toBe(17);
  expect(layout.passageFontWeight, `${label} article font weight`).toBe(
    layout.sourceHtmlPassage ? "400" : "500"
  );
  expect(layout.questionFontSize, `${label} question font size`).toBeGreaterThanOrEqual(16);
  expect(layout.questionFontSize, `${label} question font size`).toBeLessThanOrEqual(19);
  expect(layout.overflowing, `${label} component overflow`).toEqual([]);
  for (const matrix of layout.matrixSignatures) {
    expect(matrix.headerCells, `${label} matrix prompt plus answers`).toBe(matrix.radioCells + 1);
    expect(matrix.rowHeight, `${label} matrix minimum row density`).toBeGreaterThanOrEqual(49);
  }
  for (const matching of layout.descriptiveMatching) {
    if (layout.questionPaneWidth <= 920) {
      expect(matching.columns, `${label} medium desktop matching stack`).toBe(1);
      expect(matching.questionWidth, `${label} matching question width`).toBeLessThanOrEqual(440);
      expect(matching.bankWidth, `${label} matching option-bank width`).toBeLessThanOrEqual(520);
    } else {
      expect(matching.columns, `${label} wide desktop matching columns`).toBe(2);
    }
  }
  for (const letter of layout.sectionLetters) {
    expect(letter.background, `${label} section-letter background`).toBe("rgba(0, 0, 0, 0)");
    expect(letter.borderWidth, `${label} section-letter border`).toBe("0px");
    expect(letter.fontWeight, `${label} section-letter weight`).toBe("700");
  }
  for (const fontSize of layout.sourceTableFontSizes) {
    expect(fontSize, `${label} source-table font size`).toBeGreaterThanOrEqual(15);
  }
  expect(layout.unresolvedTemplateFallbacks, `${label} unresolved template placeholders`).toBe(0);
}
