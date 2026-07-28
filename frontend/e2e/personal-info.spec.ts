import { expect, test } from "@playwright/test";

test("renders categorized personal information and confirms a chat suggestion", async ({ page }) => {
  const item = {
    id: "profile_email", category: "contact", field_key: "email", label: "邮箱",
    value: "alice@example.com", aliases: ["email address"], source_type: "chat_inferred",
    confidence: 0.82, status: "proposed", updated_at: "2026-07-27T00:00:00Z",
  };
  await page.route("http://127.0.0.1:8765/personal-info**", async (route) => {
    const request = route.request();
    if (request.method() === "PUT") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...item, status: "confirmed" }) });
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      categories: { identity: "身份信息", contact: "联系方式", address: "地址信息", work: "工作信息", education: "教育经历", preference: "偏好设置", other: "其他信息" },
      items: [item],
      records: [{ id: "edu_1", category: "education", record_type: "education_experience", label: "河海大学", source_type: "form_capture", confidence: 0.96, status: "confirmed", updated_at: "2026-07-27T00:00:00Z", fields: [
        { id: "edu_school", record_id: "edu_1", field_key: "school", label: "学校", value: "河海大学", aliases: ["学校名称"], confidence: 0.98 },
        { id: "edu_major", record_id: "edu_1", field_key: "major", label: "专业", value: "地理信息系统", aliases: ["专业名称"], confidence: 0.97 },
      ] }],
    }) });
  });
  await page.goto("/?view=personal-info");
  await expect(page.getByText("个人信息库")).toBeVisible();
  await expect(page.getByRole("heading", { name: "全部信息" })).toBeVisible();
  await expect(page.locator(".personal-info-stage")).toHaveCSS("padding", "0px");
  await expect(page.locator(".personal-info-stage")).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await expect(page.getByText("alice@example.com")).toBeVisible();
  await page.getByRole("tab", { name: /身份信息/ }).click();
  await expect(page.getByText("暂无身份信息")).toBeVisible();
  await page.getByRole("tab", { name: /联系方式/ }).click();
  await expect(page.getByText("alice@example.com")).toBeVisible();
  await page.getByRole("tab", { name: /教育经历/ }).click();
  await expect(page.locator(".personal-info-record header strong", { hasText: "河海大学" })).toBeVisible();
  await expect(page.getByText("地理信息系统")).toBeVisible();
  await expect(page.getByText(/作为一条完整教育经历保存/)).toBeVisible();
  await page.getByRole("tab", { name: /待确认/ }).click();
  await expect(page.getByText(/来自聊天 · 匹配置信度 82%/)).toBeVisible();
  const confirmation = page.waitForRequest((request) => request.url().endsWith("/personal-info/profile_email") && request.method() === "PUT");
  await page.getByTitle("确认使用").click();
  expect((await confirmation).postDataJSON()).toEqual({ status: "confirmed" });
});

test("keeps personal information out of the settings account page", async ({ page }) => {
  await page.goto("/?view=settings");
  await expect(page.getByRole("heading", { name: "账号" })).toBeVisible();
  await expect(page.getByText("个人信息分类")).toHaveCount(0);
});

test("refreshes stored information whenever the persistent window opens again", async ({ page }) => {
  let hasSavedItem = false;
  await page.route("http://127.0.0.1:8765/personal-info**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      categories: { identity: "身份信息", contact: "联系方式", address: "地址信息", work: "工作信息", education: "教育经历", preference: "偏好设置", other: "其他信息" },
      items: hasSavedItem ? [{
        id: "saved-email", category: "contact", field_key: "email", label: "邮箱",
        value: "saved@example.com", aliases: [], source_type: "form_capture",
        confidence: 1, status: "confirmed", updated_at: "2026-07-27T00:00:00Z",
      }] : [],
      records: [],
    }),
  }));
  await page.goto("/?view=personal-info");
  await expect(page.getByText("暂无全部信息")).toBeVisible();

  hasSavedItem = true;
  await page.evaluate(() => window.dispatchEvent(new Event("deskpilot:personal-info-refresh")));
  await expect(page.getByText("saved@example.com")).toBeVisible();
});

test("restores visual state after repeated close cycles", async ({ page }) => {
  await page.route("http://127.0.0.1:8765/personal-info**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      categories: { identity: "身份信息", contact: "联系方式", address: "地址信息", work: "工作信息", education: "教育经历", preference: "偏好设置", other: "其他信息" },
      items: [],
    }),
  }));
  await page.goto("/?view=personal-info");
  const stage = page.locator(".personal-info-stage");
  await expect(stage).toBeVisible();
  await page.getByTitle("关闭").click();
  await page.waitForTimeout(250);
  await expect(stage).toBeVisible();
  await expect(stage).toHaveCSS("opacity", "1");
  await page.getByTitle("关闭").click();
  await page.waitForTimeout(250);
  await expect(stage).toBeVisible();
  await expect(stage).toHaveCSS("visibility", "visible");
});

test("creates a linked project record and manages confirmed fill memories", async ({ page }) => {
  const memory = {
    id: "memory-1", origin: "https://jobs.example", path_pattern: "/apply/:id",
    field_signature: "signature", field_label: "项目名称", section_key: "project",
    field_key: "project_name", action: "map", source_field_id: null, source_record_id: "project-1",
    source_field_label: null, source_field_value: null, source_record_label: "DeskPilot",
    source_record_category: "project", override_value: null, priority: 100, use_count: 2,
    updated_at: "2026-07-28T00:00:00Z",
  };
  await page.route("http://127.0.0.1:8765/personal-info**", async (route) => {
    const request = route.request();
    if (request.method() === "POST" && request.url().endsWith("/personal-info/records")) {
      return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({
        id: "project-new", category: "project", record_type: "project_record", label: "新项目",
        source_type: "user_edit", confidence: 1, status: "confirmed", updated_at: "2026-07-28T00:00:00Z", fields: [],
      }) });
    }
    if (request.method() === "PUT") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...memory, ...request.postDataJSON() }) });
    if (request.method() === "DELETE") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      categories: { identity: "身份信息", project: "项目经历", qa: "常用问答", other: "其他信息" },
      record_categories: ["project", "qa"], items: [], records: [], form_memories: [memory],
    }) });
  });
  await page.goto("/?view=personal-info");
  await page.getByRole("tab", { name: /项目经历/ }).click();
  await page.getByRole("button", { name: "新增记录" }).click();
  await page.getByLabel("字段值").nth(0).fill("DeskPilot 智能填写");
  await page.getByLabel("字段值").nth(1).fill("核心开发");
  const recordRequest = page.waitForRequest((request) => request.url().endsWith("/personal-info/records") && request.method() === "POST");
  await page.getByRole("button", { name: "保存整条记录" }).click();
  const recordPayload = (await recordRequest).postDataJSON();
  expect(recordPayload.category).toBe("project");
  expect(recordPayload.fields.map((field: { field_key: string }) => field.field_key)).toEqual(["project_name", "project_role"]);

  await page.getByRole("tab", { name: /填写记忆/ }).click();
  await expect(page.getByText("/apply/:id", { exact: false })).toBeVisible();
  await page.getByTitle("编辑记忆").click();
  await page.getByLabel("动作").selectOption("literal");
  await page.getByRole("textbox", { name: "站点专用值", exact: true }).fill("站点定制项目名称");
  const memoryRequest = page.waitForRequest((request) => request.url().endsWith("/form-memories/memory-1") && request.method() === "PUT");
  await page.getByRole("button", { name: "保存记忆" }).click();
  expect((await memoryRequest).postDataJSON()).toMatchObject({ action: "literal", override_value: "站点定制项目名称" });
  const deleteRequest = page.waitForRequest((request) => request.url().endsWith("/form-memories/memory-1") && request.method() === "DELETE");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByTitle("删除记忆").click();
  await deleteRequest;
});
