import { expect, test } from "@playwright/test";
import path from "node:path";

test("recognizes linked campus application fields and fills a custom select", async ({ page }) => {
  await page.setContent(`
    <style>.row{display:grid;grid-template-columns:130px 300px;margin:12px}.form-item-label{display:block}.control{width:280px;height:36px}.ant-select-selector{width:280px;height:36px;border:1px solid #ccc}.ant-select-selection-item{padding:8px}</style>
    <h2>个人信息</h2>
    <div class="row"><div class="form-item-label">姓名</div><input class="control" value="程旭升"></div>
    <div class="row"><div class="form-item-label">邮箱</div><input class="control" value="18419571168@163.com"></div>
    <div class="row"><div class="form-item-label">最高学位</div><div class="ant-select-selector" role="combobox" aria-expanded="false"><span class="ant-select-selection-item">硕士</span></div></div>
    <h2>教育经历</h2>
    <section data-index="0">
      <div class="row"><div class="form-item-label">学校名称</div><input class="control" value="河海大学"></div>
      <div class="row"><div class="form-item-label">开始时间</div><input class="control" value="2020-09"></div>
      <div class="row"><div class="form-item-label">结束时间</div><input class="control" value="2024-06"></div>
      <div class="row"><div class="form-item-label">学院名称</div><input class="control" value="地理与遥感学院"></div>
      <div class="row"><div class="form-item-label">专业类别</div><div class="ant-select-selector" role="combobox"><span class="ant-select-selection-item">地理科学类</span></div></div>
      <div class="row"><div class="form-item-label">专业名称</div><input class="control" value="地理信息系统"></div>
      <div class="row"><div class="form-item-label">学历</div><div class="ant-select-selector" role="combobox"><span class="ant-select-selection-item">本科</span></div></div>
    </section>
  `);
  await page.evaluate(() => {
    const listeners: Array<(message: unknown, sender: unknown, sendResponse: (value: unknown) => void) => boolean> = [];
    Object.assign(window, { __deskpilotListeners: listeners });
    Object.assign(globalThis, { chrome: { runtime: { onMessage: { addListener: (listener: typeof listeners[number]) => listeners.push(listener) } } } });
    document.querySelectorAll<HTMLElement>(".ant-select-selector").forEach((control) => {
      control.addEventListener("click", () => {
        document.querySelector(".test-options")?.remove();
        const options = document.createElement("div");
        options.className = "test-options";
        ["本科", "硕士", "博士"].forEach((value) => {
          const option = document.createElement("div");
          option.setAttribute("role", "option");
          option.style.cssText = "width:120px;height:28px;display:block";
          option.textContent = value;
          option.addEventListener("click", () => { const selected = control.querySelector(".ant-select-selection-item"); if (selected) selected.textContent = value; });
          options.appendChild(option);
        });
        document.body.appendChild(options);
      });
    });
  });
  await page.addScriptTag({ path: path.resolve(process.cwd(), "../browser-extension/dist/content.js") });
  const inspect = await page.evaluate(() => new Promise<any>((resolve) => {
    const listeners = (window as any).__deskpilotListeners as Array<(message: unknown, sender: unknown, sendResponse: (value: unknown) => void) => boolean>;
    listeners[0]({ type: "DESKPILOT_INSPECT_FORM" }, null, resolve);
  }));
  const byLabel = Object.fromEntries(inspect.fields.map((field: any) => [field.label, field]));
  expect(byLabel["姓名"].value).toBe("程旭升");
  expect(byLabel["邮箱"].value).toBe("18419571168@163.com");
  expect(byLabel["最高学位"].display_value).toBe("硕士");
  expect(byLabel["学校名称"]).toMatchObject({ value: "河海大学", section_title: "教育经历", record_index: 0, record_key: "教育经历:0" });
  expect(byLabel["专业类别"].display_value).toBe("地理科学类");
  expect(byLabel["学历"].type).toBe("custom_select");

  const result = await page.evaluate((fieldId) => new Promise<any>((resolve) => {
    const listeners = (window as any).__deskpilotListeners as Array<(message: unknown, sender: unknown, sendResponse: (value: unknown) => void) => boolean>;
    listeners[0]({ type: "DESKPILOT_FILL_FORM", payload: { assignments: [{ field_id: fieldId, value: "硕士", allow_overwrite: true, expected_current_value: "本科" }] } }, null, resolve);
  }), byLabel["学历"].field_id);
  expect(result).toMatchObject({ filled_count: 1, submitted: false });
  await expect(page.locator("section .ant-select-selection-item").last()).toHaveText("硕士");
});

test("never overwrites an existing value without explicit replacement and a matching preview value", async ({ page }) => {
  await page.setContent(`<label>姓名<input value="页面已有姓名"></label><button type="submit">提交</button>`);
  await page.evaluate(() => {
    const listeners: Array<(message: unknown, sender: unknown, sendResponse: (value: unknown) => void) => boolean> = [];
    Object.assign(window, { __deskpilotListeners: listeners });
    Object.assign(globalThis, { chrome: { runtime: { onMessage: { addListener: (listener: typeof listeners[number]) => listeners.push(listener) } } } });
  });
  await page.addScriptTag({ path: path.resolve(process.cwd(), "../browser-extension/dist/content.js") });
  const inspect = await page.evaluate(() => new Promise<any>((resolve) => {
    const listeners = (window as any).__deskpilotListeners;
    listeners[0]({ type: "DESKPILOT_INSPECT_FORM" }, null, resolve);
  }));
  const fieldId = inspect.fields[0].field_id;
  const invoke = (payload: Record<string, unknown>) => page.evaluate((nextPayload) => new Promise<any>((resolve) => {
    const listeners = (window as any).__deskpilotListeners;
    listeners[0]({ type: "DESKPILOT_FILL_FORM", payload: nextPayload }, null, resolve);
  }), payload);
  expect((await invoke({ assignments: [{ field_id: fieldId, value: "新姓名" }] })).filled_count).toBe(0);
  expect(await page.locator("input").inputValue()).toBe("页面已有姓名");
  expect((await invoke({ assignments: [{ field_id: fieldId, value: "新姓名", allow_overwrite: true, expected_current_value: "过期值" }] })).filled_count).toBe(0);
  expect(await page.locator("input").inputValue()).toBe("页面已有姓名");
  const result = await invoke({ expected_document_id: inspect.document_id, assignments: [{ field_id: fieldId, value: "新姓名", allow_overwrite: true, expected_current_value: "页面已有姓名" }] });
  expect(result).toMatchObject({ filled_count: 1, submitted: false });
  expect(await page.locator("input").inputValue()).toBe("新姓名");
});

test("fills sibling-labelled custom radios and keeps progress when one control throws", async ({ page }) => {
  await page.setContent(`
    <div class="field-item"><span id="gender-label">性别：男</span>
      <div class="field-item__input" role="radio" aria-labelledby="gender-label" aria-checked="false" style="width:20px;height:20px"></div>
    </div>
    <label>姓名<input style="width:200px;height:30px"></label>
    <div class="field-item"><span id="broken-label">坏控件</span>
      <div id="broken" role="radio" aria-labelledby="broken-label" style="width:20px;height:20px"></div>
    </div>
    <label>邮箱<input style="width:200px;height:30px"></label>
  `);
  await page.evaluate(() => {
    const listeners: Array<(message: unknown, sender: unknown, sendResponse: (value: unknown) => void) => boolean> = [];
    Object.assign(window, { __deskpilotListeners: listeners });
    Object.assign(globalThis, { chrome: { runtime: { onMessage: { addListener: (listener: typeof listeners[number]) => listeners.push(listener) } } } });
    const gender = document.querySelector<HTMLElement>("[aria-labelledby='gender-label']")!;
    gender.addEventListener("click", () => gender.setAttribute("aria-checked", "true"));
    document.querySelector<HTMLElement>("#broken")!.click = () => { throw new Error("widget failed"); };
  });
  await page.addScriptTag({ path: path.resolve(process.cwd(), "../browser-extension/dist/content.js") });
  const inspect = await page.evaluate(() => new Promise<any>((resolve) => {
    (window as any).__deskpilotListeners[0]({ type: "DESKPILOT_INSPECT_FORM" }, null, resolve);
  }));
  const byLabel = Object.fromEntries(inspect.fields.map((item: any) => [item.label, item]));
  expect(byLabel["性别：男"].type).toBe("custom_radio");
  expect(byLabel["姓名"].label).toBe("姓名");

  const result = await page.evaluate(({ documentId, fields }) => new Promise<any>((resolve) => {
    (window as any).__deskpilotListeners[0]({
      type: "DESKPILOT_FILL_FORM",
      payload: { expected_document_id: documentId, assignments: fields },
    }, null, resolve);
  }), {
    documentId: inspect.document_id,
    fields: [
      { field_id: byLabel["性别：男"].field_id, value: "性别：男" },
      { field_id: byLabel["姓名"].field_id, value: "Alice" },
      { field_id: byLabel["坏控件"].field_id, value: "坏控件" },
      { field_id: byLabel["邮箱"].field_id, value: "alice@example.com" },
    ],
  });
  expect(result.filled).toEqual([
    byLabel["性别：男"].field_id,
    byLabel["姓名"].field_id,
    byLabel["邮箱"].field_id,
  ]);
  expect(result.skipped).toEqual([byLabel["坏控件"].field_id]);
  expect(result.errors[0]).toMatchObject({ field_id: byLabel["坏控件"].field_id, message: "widget failed" });
  expect(await page.locator("input").nth(0).inputValue()).toBe("Alice");
  expect(await page.locator("input").nth(1).inputValue()).toBe("alice@example.com");
});

test("rejects a fill preview after SPA navigation changes the route", async ({ page }) => {
  await page.goto("/");
  await page.setContent(`<label>路由 A<input style="width:200px;height:30px"></label>`);
  await page.evaluate(() => {
    const listeners: Array<(message: unknown, sender: unknown, sendResponse: (value: unknown) => void) => boolean> = [];
    Object.assign(window, { __deskpilotListeners: listeners });
    Object.assign(globalThis, { chrome: { runtime: { onMessage: { addListener: (listener: typeof listeners[number]) => listeners.push(listener) } } } });
  });
  await page.addScriptTag({ path: path.resolve(process.cwd(), "../browser-extension/dist/content.js") });
  const inspect = await page.evaluate(() => new Promise<any>((resolve) => {
    (window as any).__deskpilotListeners[0]({ type: "DESKPILOT_INSPECT_FORM" }, null, resolve);
  }));
  const result = await page.evaluate((preview) => {
    history.pushState({}, "", "/route-b");
    document.body.innerHTML = `<label>路由 B<input data-deskpilot-field-id="${preview.fields[0].field_id}" style="width:200px;height:30px"></label>`;
    return new Promise<any>((resolve) => {
      (window as any).__deskpilotListeners[0]({
        type: "DESKPILOT_FILL_FORM",
        payload: { expected_document_id: preview.document_id, assignments: [{ field_id: preview.fields[0].field_id, value: "wrong route" }] },
      }, null, resolve);
    });
  }, inspect);
  expect(result).toMatchObject({ target_changed: true, filled_count: 0 });
  expect(result.document_id).not.toBe(inspect.document_id);
  expect(await page.locator("input").inputValue()).toBe("");
});

test("uses Phoenix semantic metadata to avoid shifted labels and preserve repeated education records", async ({ page }) => {
  const input = (section: string, label: string, group: number, value: string, structuralLabel = label) => `
    <div class="form-item"><div class="form-item__title"><label>${structuralLabel}</label></div>
      <div class="form-item__control"><input style="width:240px;height:32px" value="${value}"
        data-nc-cls="${section}" data-nc-label="${label}" data-nc-group="${group}" data-nc-filled="1"></div></div>`;
  await page.setContent(`
    <div class="sc-obfuscated-section"><div class="sc-obfuscated-title">个人信息</div>
      ${input("个人信息", "姓名", 1, "程旭升")}
      ${input("个人信息", "邮箱", 1, "alice@example.com")}
      ${input("个人信息", "手机号码", 1, "13800138000")}
      ${input("个人信息", "最高学位", 1, "硕士")}
      ${input("个人信息", "最高学位", 1, "校园招聘", "获得此职位招聘渠道（选择一个填写）")}
    </div>
    <div class="sc-obfuscated-section"><div class="sc-obfuscated-title">教育经历</div>
      ${input("教育经历", "学校名称", 1, "河海大学")}
      ${input("教育经历", "开始时间", 1, "2020-09")}
      ${input("教育经历", "结束时间", 1, "2024-06")}
      ${input("教育经历", "专业名称", 1, "地理信息系统")}
      ${input("教育经历", "学校名称", 2, "宁波大学")}
      ${input("教育经历", "开始时间", 2, "2024-09")}
      ${input("教育经历", "结束时间", 2, "2027-06")}
      ${input("教育经历", "专业名称", 2, "地理学")}
    </div>`);
  await page.evaluate(() => {
    const listeners: Array<(message: unknown, sender: unknown, sendResponse: (value: unknown) => void) => boolean> = [];
    Object.assign(window, { __deskpilotListeners: listeners });
    Object.assign(globalThis, { chrome: { runtime: { onMessage: { addListener: (listener: typeof listeners[number]) => listeners.push(listener) } } } });
  });
  await page.addScriptTag({ path: path.resolve(process.cwd(), "../browser-extension/dist/content.js") });
  const inspect = await page.evaluate(() => new Promise<any>((resolve) => {
    const listeners = (window as any).__deskpilotListeners as Array<(message: unknown, sender: unknown, sendResponse: (value: unknown) => void) => boolean>;
    listeners[0]({ type: "DESKPILOT_INSPECT_FORM" }, null, resolve);
  }));

  expect(inspect.fields.slice(0, 5).map((field: any) => [field.label, field.value])).toEqual([
    ["姓名", "程旭升"], ["邮箱", "alice@example.com"], ["手机号码", "13800138000"],
    ["最高学位", "硕士"], ["获得此职位招聘渠道（选择一个填写）", "校园招聘"],
  ]);
  const education = inspect.fields.filter((field: any) => field.section_title === "教育经历");
  expect(education.filter((field: any) => field.record_key === "教育经历:0")).toHaveLength(4);
  expect(education.filter((field: any) => field.record_key === "教育经历:1")).toHaveLength(4);
  expect(education.find((field: any) => field.value === "2020-09").label).toBe("开始时间");
  expect(education.find((field: any) => field.value === "2027-06").label).toBe("结束时间");
});
