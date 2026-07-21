import { expect, test, type Page } from "@playwright/test";

const note = {
  id: "note_alpha",
  entity_type: "concept",
  title: "Alpha Knowledge",
  status: "active",
  review_state: "reviewed",
  sensitivity: "normal",
  markdown_path: "notes/concept/alpha.md",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
};

async function mockKnowledgeApi(page: Page, withProposal = false) {
  await page.route("http://127.0.0.1:8765/knowledge/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = (value: unknown) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(value) });
    if (path === "/knowledge/status") return json({ active_profile_id: "profile_default", sources: 1, snapshots: 1, notes: 1, stale_notes: 0, pending_proposals: withProposal ? 1 : 0, enabled: true, browser_connected: false, root_path: "C:/kb" });
    if (path === "/knowledge/profiles") return json({ items: [{ id: "profile_default", name: "默认知识库", description: "", is_default: 1, is_active: true, source_count: 1, note_count: 1 }], active_profile_id: "profile_default" });
    if (path === "/knowledge/notes") return json({ items: [note], total: 1 });
    if (path === "/knowledge/sources") return json({ items: [], total: 0 });
    if (path === "/knowledge/proposals") return json({ items: withProposal ? [{ id: "prop_1", operation: "update_note", target_note_id: note.id, target_title: note.title, created_at: "2026-01-03T00:00:00Z", status: "pending" }] : [] });
    if (path === `/knowledge/notes/${note.id}`) return json({ ...note, frontmatter: { aliases: [], tags: [], source_ids: [], manual_sections: [], generated_by: "deskpilot" }, sections: { Summary: "Current summary", Overview: "Current overview", Details: "Current details" }, content: "", sources: [], relations: [] });
    if (path === "/knowledge/query") {
      const body = request.postDataJSON();
      return json({ mode: body.mode, answer: `Structured ${body.mode} result`, results: [note], reading_level: "L3", comparison: { subjects: [note] } });
    }
    if (path === "/knowledge/proposals/prop_1") return json({ id: "prop_1", operation: "update_note", target_note_id: note.id, target_title: note.title, created_at: "2026-01-03T00:00:00Z", status: "pending", payload: { source_id: "src_1", snapshot_id: "snap_1", operation: { operation: "update_note", title: note.title, entity_type: "concept", summary: "Proposed summary", overview: "Proposed overview", details_markdown: "Proposed details", aliases: [], tags: [] } }, target_note: { ...note, frontmatter: { aliases: [], tags: [], source_ids: [], manual_sections: [], generated_by: "deskpilot" }, sections: { Summary: "Current summary", Overview: "Current overview", Details: "Current details" }, sources: [], relations: [], content: "" }, diff: { fields: [], unified_diff: ["--- current", "+++ proposal", "-Current summary", "+Proposed summary"], evidence: { added: [], removed: [] }, relations: { added: [], removed: [] }, base: { expected_note_sha256: "old", current_note_sha256: "new", matches: false, snapshot_id: "snap_1" }, changed_fields: ["summary"] } });
    return json({});
  });
}

test("switches to compare mode and renders the structured query response", async ({ page }) => {
  await mockKnowledgeApi(page);
  await page.goto("/?view=knowledge");
  await page.getByRole("button", { name: /问知识库/ }).click();
  await page.getByLabel("知识库查询模式").selectOption("compare");
  await page.getByPlaceholder("向知识库提问").fill("Alpha vs Beta");
  const requestPromise = page.waitForRequest((request) => request.url().endsWith("/knowledge/query"));
  await page.getByRole("button", { name: "查询 Wiki" }).click();
  const request = await requestPromise;
  expect(request.postDataJSON()).toMatchObject({ query: "Alpha vs Beta", mode: "compare" });
  await expect(page.getByText("Structured compare result")).toBeVisible();
});

test("shows proposal base conflicts and requires confirmation for force acceptance", async ({ page }) => {
  await mockKnowledgeApi(page, true);
  await page.goto("/?view=knowledge");
  await page.getByRole("button", { name: /需要确认/ }).click();
  await expect(page.getByRole("alert")).toContainText("当前页面已在提案生成后变化");
  await expect(page.getByRole("button", { name: "接受修改" })).toBeDisabled();
  const forceButton = page.getByRole("button", { name: "强制接受并覆盖" });
  await expect(forceButton).toBeEnabled();
  await expect(page.locator(".knowledge-review-unified-diff")).toContainText("+Proposed summary");
  page.once("dialog", (dialog) => dialog.accept());
  const forceRequest = page.waitForRequest((request) => request.url().endsWith("/knowledge/proposals/prop_1/resolve"));
  await forceButton.click();
  expect((await forceRequest).postDataJSON()).toEqual({ decision: "accept", force: true });
});
