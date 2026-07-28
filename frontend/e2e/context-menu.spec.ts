import { expect, test } from "@playwright/test";

test.describe("DeskPilot context menu", () => {
  test("shows only actionable entries in a logical order", async ({ page }) => {
    await page.setViewportSize({ width: 224, height: 230 });
    await page.goto("/?view=context-menu");

    const menu = page.getByRole("menu", { name: "DeskPilot 快捷菜单" });
    await expect(menu).toBeVisible();
    await expect(menu.getByRole("menuitem")).toHaveText([
      "打开主面板",
      "知识库",
      "个人信息",
      "设置",
      "退出 DeskPilot"
    ]);
    await expect(page.getByText("任务历史", { exact: true })).toHaveCount(0);
  });

  test("supports conventional menu keyboard navigation", async ({ page }) => {
    await page.setViewportSize({ width: 224, height: 230 });
    await page.goto("/?view=context-menu");

    const items = page.getByRole("menuitem");
    await expect(items.first()).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(items.nth(1)).toBeFocused();
    await page.keyboard.press("End");
    await expect(items.last()).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(items.first()).toBeFocused();
    await page.keyboard.press("ArrowUp");
    await expect(items.last()).toBeFocused();
    await page.keyboard.press("Home");
    await expect(items.first()).toBeFocused();
  });
});
