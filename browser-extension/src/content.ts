const INSTALL_FLAG = "__DESKPILOT_CONTENT_INSTALLED__";
const globalState = globalThis as typeof globalThis & Record<string, boolean>;

if (!globalState[INSTALL_FLAG]) {
  globalState[INSTALL_FLAG] = true;

  function collectVisibleText(maxChars: number): string {
    return document.body?.innerText?.slice(0, maxChars) ?? "";
  }

  function pageMetadata() {
    const meta = (name: string) =>
      document.querySelector(`meta[name="${name}"],meta[property="${name}"]`)?.getAttribute("content") ?? "";
    const canonical = (document.querySelector("link[rel='canonical']") as HTMLLinkElement | null)?.href ?? location.href;
    return {
      canonical_url: canonical,
      language: document.documentElement.lang || meta("og:locale"),
      description: meta("description") || meta("og:description"),
      author: meta("author") || meta("article:author"),
      published_at: meta("article:published_time") || document.querySelector("time[datetime]")?.getAttribute("datetime") || "",
      modified_at: meta("article:modified_time"),
      site_name: meta("og:site_name"),
    };
  }

  function jsonLdBlocks() {
    return Array.from(document.querySelectorAll("script[type='application/ld+json']"))
      .slice(0, 20)
      .flatMap((script) => {
        try {
          const value = JSON.parse(script.textContent || "null");
          return Array.isArray(value) ? value : value ? [value] : [];
        } catch {
          return [];
        }
      });
  }

  function readableCandidate(element: Element) {
    const clone = element.cloneNode(true) as Element;
    clone.querySelectorAll("script,style,noscript,nav,footer,header,aside,form,button,[aria-hidden='true'],.advertisement,.ads,.cookie,.modal").forEach((node) => node.remove());
    const text = (clone.textContent ?? "").replace(/\s+/g, " ").trim();
    const paragraphText = Array.from(clone.querySelectorAll("p,li,blockquote,pre")).map((node) => (node.textContent ?? "").trim()).filter(Boolean).join("\n\n");
    const links = Array.from(clone.querySelectorAll("a")).reduce((sum, link) => sum + (link.textContent ?? "").length, 0);
    const score = paragraphText.length + text.length * 0.2 + clone.querySelectorAll("h1,h2,h3").length * 80 - links * 0.8;
    return { text: paragraphText || text, score, selector: cssPath(element) || element.tagName.toLowerCase() };
  }

  function collectOpenShadowText(root: Document | ShadowRoot = document): string[] {
    const values: string[] = [];
    root.querySelectorAll("*").forEach((element) => {
      const shadow = (element as HTMLElement).shadowRoot;
      if (!shadow) return;
      const text = (shadow.textContent ?? "").replace(/\s+/g, " ").trim();
      if (text.length >= 20) values.push(text);
      values.push(...collectOpenShadowText(shadow));
    });
    return values;
  }

  function collectFrameText(): Array<{ url: string; title: string; text: string }> {
    return Array.from(document.querySelectorAll("iframe")).slice(0, 20).flatMap((frame) => {
      try {
        const child = (frame as HTMLIFrameElement).contentDocument;
        const text = child?.body?.innerText?.trim() ?? "";
        return text ? [{ url: (frame as HTMLIFrameElement).src, title: child?.title ?? "", text: text.slice(0, 10000) }] : [];
      } catch {
        return [];
      }
    });
  }

  async function waitForDomSettled(quietMs = 250, timeoutMs = 1500): Promise<void> {
    await new Promise<void>((resolve) => {
      let quietTimer = window.setTimeout(done, quietMs);
      const timeout = window.setTimeout(done, timeoutMs);
      const observer = new MutationObserver(() => {
        window.clearTimeout(quietTimer);
        quietTimer = window.setTimeout(done, quietMs);
      });
      function done() {
        observer.disconnect();
        window.clearTimeout(quietTimer);
        window.clearTimeout(timeout);
        resolve();
      }
      observer.observe(document.documentElement, { subtree: true, childList: true, characterData: true });
    });
  }

  async function collectRichPage(maxChars: number) {
    await waitForDomSettled();
    const candidates = Array.from(document.querySelectorAll("article,main,[role='main'],.post,.article,.entry-content,.content"));
    if (document.body) candidates.push(document.body);
    const best = candidates.map(readableCandidate).sort((a, b) => b.score - a.score)[0];
    const frames = collectFrameText();
    const shadowText = collectOpenShadowText();
    const primary = best?.text || collectVisibleText(maxChars);
    const supplements = [...frames.map((frame) => frame.text), ...shadowText];
    const contentText = [primary, ...supplements].filter(Boolean).join("\n\n").slice(0, maxChars);
    const visibleText = collectVisibleText(maxChars);
    const quality = {
      characters: contentText.length,
      visible_characters: visibleText.length,
      paragraph_count: contentText.split(/\n\s*\n/).filter(Boolean).length,
      frame_count: frames.length,
      shadow_root_count: shadowText.length,
      score: best?.score ?? 0,
      truncated: contentText.length >= maxChars,
    };
    return {
      url: location.href,
      title: document.title,
      visible_text: visibleText,
      content_text: contentText,
      dom_summary: collectDomSummary(),
      metadata: pageMetadata(),
      headings: Array.from(document.querySelectorAll("h1,h2,h3")).slice(0, 100).map((heading) => ({ level: Number(heading.tagName.slice(1)), text: normalizeCellText(heading.textContent ?? "", 300) })),
      json_ld: jsonLdBlocks(),
      frames: frames.map(({ text, ...frame }) => ({ ...frame, characters: text.length })),
      extraction_method: best?.selector === "body" ? "document_fallback" : "readability_heuristic",
      content_quality: quality,
      captured_at: new Date().toISOString(),
    };
  }

  function collectDomSummary() {
    return Array.from(document.querySelectorAll("h1,h2,h3,button,a,input,textarea,select"))
      .slice(0, 200)
      .map((element) => ({
        tag: element.tagName.toLowerCase(),
        text: (element.textContent ?? "").trim().slice(0, 120),
        ariaLabel: element.getAttribute("aria-label"),
        role: element.getAttribute("role"),
      }));
  }

  function normalizeCellText(value: string, maxChars: number): string {
    return value.replace(/\s+/g, " ").trim().slice(0, maxChars);
  }

  function extractHtmlTables(payload: Record<string, unknown>) {
    const maxTables = Number(payload.max_tables ?? 10);
    const maxRowsPerTable = Number(payload.max_rows_per_table ?? 500);
    const maxCellChars = Number(payload.max_cell_chars ?? 300);

    const tables = Array.from(document.querySelectorAll("table"))
      .slice(0, Number.isFinite(maxTables) && maxTables > 0 ? maxTables : 10)
      .map((table, index) => {
        const rows = Array.from(table.querySelectorAll("tr"))
          .slice(0, Number.isFinite(maxRowsPerTable) && maxRowsPerTable > 0 ? maxRowsPerTable : 500)
          .map((row) =>
            Array.from(row.querySelectorAll("th,td")).map((cell) =>
              normalizeCellText(cell.textContent ?? "", Number.isFinite(maxCellChars) ? maxCellChars : 300),
            ),
          )
          .filter((row) => row.some((cell) => cell.length > 0));
        const caption = normalizeCellText(
          table.querySelector("caption")?.textContent ?? `Table ${index + 1}`,
          80,
        );
        const headerCells = Array.from(table.querySelectorAll("thead th"));
        // Without an explicit thead, treat the first non-empty row as a practical header guess.
        const headers =
          headerCells.length > 0
            ? headerCells.map((cell) => normalizeCellText(cell.textContent ?? "", 300))
            : rows[0] ?? [];
        return {
          index,
          caption,
          headers,
          rows,
          row_count: rows.length,
          column_count: rows.reduce((max, row) => Math.max(max, row.length), 0),
        };
      })
      .filter((table) => table.row_count > 0 && table.column_count > 0);

    return {
      url: location.href,
      title: document.title,
      tables,
      captured_at: new Date().toISOString(),
    };
  }

  function elementText(element: Element, maxChars: number): string {
    return normalizeCellText(element.textContent ?? "", maxChars);
  }

  function firstNonEmptyText(elements: Element[], maxChars: number): string {
    for (const element of elements) {
      const text = elementText(element, maxChars);
      if (text) return text;
    }
    return "";
  }

  function cssPath(element: Element): string {
    const parts: string[] = [];
    let current: Element | null = element;
    while (current && current !== document.body && parts.length < 4) {
      let part = current.tagName.toLowerCase();
      if (current.id) {
        part += `#${current.id}`;
        parts.unshift(part);
        break;
      }
      const className = Array.from(current.classList).slice(0, 2).join(".");
      if (className) part += `.${className}`;
      parts.unshift(part);
      current = current.parentElement;
    }
    return parts.join(" > ");
  }

  function hasAncestor(element: Element, selector: string): boolean {
    return Boolean(element.closest(selector));
  }

  function candidateSignals(items: Element[]) {
    const texts = items.map((item) => elementText(item, 2000));
    const links = items.flatMap((item) => Array.from(item.querySelectorAll("a[href]")) as HTMLAnchorElement[]);
    const articleLinks = links.filter((link) =>
      /\/article\/details\/|\/posts\/|\/blog\/|\/p\/|\/news\//i.test(link.href),
    );
    const firstItem = items[0];
    const insideFooter = firstItem
      ? hasAncestor(firstItem, "footer, [role='contentinfo'], .footer, [class*='footer'], [class*='copyright']")
      : false;
    const insideNavigation = firstItem
      ? hasAncestor(firstItem, "nav, header, [role='navigation'], [role='banner'], .nav, .menu, [class*='menu']")
      : false;
    const insideMain = firstItem ? hasAncestor(firstItem, "main, [role='main'], .main, [class*='content'], [class*='feed']") : false;
    const avgTextLength =
      texts.length > 0 ? Math.round(texts.reduce((sum, text) => sum + text.length, 0) / texts.length) : 0;
    const hasTime = items.some((item) => item.querySelector("time") || /\d{4}[-/年]\d{1,2}/.test(elementText(item, 500)));
    const score =
      Math.min(items.length, 30) * 2 +
      Math.min(avgTextLength, 500) / 10 +
      (insideMain ? 30 : 0) +
      (hasTime ? 15 : 0) +
      (links.length > 0 ? 8 : 0) +
      (articleLinks.length / Math.max(links.length, 1)) * 35 -
      (insideFooter ? 80 : 0) -
      (insideNavigation ? 45 : 0);
    return {
      inside_main: insideMain,
      inside_footer: insideFooter,
      inside_navigation: insideNavigation,
      item_count: items.length,
      avg_text_length: avgTextLength,
      link_count: links.length,
      article_link_ratio: links.length > 0 ? articleLinks.length / links.length : 0,
      has_time: hasTime,
      score: Math.round(score * 10) / 10,
    };
  }

  function directChildItems(selector: string): Element[] {
    const items = new Set<Element>();
    document.querySelectorAll(selector).forEach((container) => {
      Array.from(container.children).forEach((child) => {
        const text = elementText(child, 2000);
        if (text.length >= 8) items.add(child);
      });
    });
    return Array.from(items);
  }

  function collectCandidateItems(): Element[] {
    const items = new Set<Element>();
    [
      "li",
      "article",
      "[role='listitem']",
      ".card",
      ".item",
      ".list-item",
      ".result",
      ".job",
      ".product",
    ].forEach((selector) => {
      document.querySelectorAll(selector).forEach((element) => {
        const text = elementText(element, 2000);
        if (text.length >= 8) items.add(element);
      });
    });
    directChildItems("main, [role='main'], section, ul, ol, [role='list']").forEach((element) => items.add(element));
    return Array.from(items)
      .filter((element) => !element.closest("table"))
      .filter((element) => {
        const nestedCandidates = element.querySelectorAll("li, article, [role='listitem'], .card, .item, .list-item");
        return nestedCandidates.length <= 12;
      });
  }

  function extractStructuredItem(element: Element, maxTextChars: number, maxMetaItems: number) {
    const title = firstNonEmptyText(
      Array.from(element.querySelectorAll("h1,h2,h3,h4,[role='heading'],strong,b,a")),
      180,
    );
    const links = Array.from(element.querySelectorAll("a[href]"))
      .slice(0, 5)
      .map((link) => {
        const anchor = link as HTMLAnchorElement;
        return {
          text: elementText(anchor, 160),
          href: anchor.href,
        };
      })
      .filter((link) => link.text || link.href);
    const meta = Array.from(element.querySelectorAll("time,small,span,em"))
      .map((metaElement) => elementText(metaElement, 120))
      .filter((text, index, values) => text && values.indexOf(text) === index)
      .slice(0, maxMetaItems);
    const description = elementText(element, maxTextChars);
    return {
      title: title || description.slice(0, 120),
      description,
      links,
      first_link_text: links[0]?.text ?? "",
      first_link_url: links[0]?.href ?? "",
      meta,
    };
  }

  function extractStructuredBlocks(payload: Record<string, unknown>) {
    const maxBlocks = Number(payload.max_blocks ?? 20);
    const maxItemsPerBlock = Number(payload.max_items_per_block ?? 200);
    const maxTextChars = Number(payload.max_text_chars ?? 1000);
    const maxMetaItems = Number(payload.max_meta_items ?? 8);
    const blockLimit = Number.isFinite(maxBlocks) && maxBlocks > 0 ? maxBlocks : 20;
    const itemLimit = Number.isFinite(maxItemsPerBlock) && maxItemsPerBlock > 0 ? maxItemsPerBlock : 200;

    const groups = new Map<string, Element[]>();
    collectCandidateItems().forEach((item) => {
      const parent = item.parentElement;
      if (!parent) return;
      const key = cssPath(parent);
      const siblings = groups.get(key) ?? [];
      siblings.push(item);
      groups.set(key, siblings);
    });

    const blocks = Array.from(groups.entries())
      .map(([selectorHint, items], candidateIndex) => {
        const uniqueItems = Array.from(new Set(items)).slice(0, itemLimit);
        const signals = candidateSignals(uniqueItems);
        return {
          candidate_id: `c${candidateIndex + 1}`,
          source: selectorHint || "document",
          selector_hint: selectorHint,
          item_count: uniqueItems.length,
          signals,
          items: uniqueItems.map((item) =>
            extractStructuredItem(
              item,
              Number.isFinite(maxTextChars) ? maxTextChars : 1000,
              Number.isFinite(maxMetaItems) ? maxMetaItems : 8,
            ),
          ),
        };
      })
      .filter((block) => block.item_count >= 2)
      .sort((a, b) => b.signals.score - a.signals.score)
      .slice(0, blockLimit);

    return {
      url: location.href,
      title: document.title,
      blocks,
      captured_at: new Date().toISOString(),
    };
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === "DESKPILOT_EXTRACT_STRUCTURED_BLOCKS") {
      sendResponse(extractStructuredBlocks(message.payload ?? {}));
      return true;
    }
    if (message?.type === "DESKPILOT_EXTRACT_TABLE") {
      sendResponse(extractHtmlTables(message.payload ?? {}));
      return true;
    }
    if (message?.type !== "DESKPILOT_COLLECT_PAGE") {
      return false;
    }
    const requested = Number(message.payload?.max_text_chars ?? 100000);
    const maxTextChars = Number.isFinite(requested) ? Math.min(Math.max(requested, 1000), 200000) : 100000;
    void collectRichPage(maxTextChars).then(sendResponse).catch((error) => sendResponse({
      url: location.href,
      title: document.title,
      visible_text: collectVisibleText(maxTextChars),
      content_text: collectVisibleText(maxTextChars),
      dom_summary: collectDomSummary(),
      extraction_method: "document_fallback",
      content_quality: { characters: collectVisibleText(maxTextChars).length, error: error instanceof Error ? error.message : String(error) },
      captured_at: new Date().toISOString(),
    }));
    return true;
  });
}
