import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import { robotGlbFixture } from "./glb-fixture";
const evidence = new URL("../../../../docs/screenshots/", import.meta.url)
  .pathname;

async function openRun(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Vytvořit ukázkové scénáře" }).click();
  await page
    .locator("article")
    .filter({ hasText: "Malý sklad" })
    .getByRole("button", { name: "Otevřít simulaci" })
    .click();
  await expect(page.getByTestId("tick")).toHaveText("0");
  return await page.evaluate(() =>
    sessionStorage.getItem("warehouse-active-run"),
  );
}
async function snapshot(request: APIRequestContext, id: string | null) {
  return await (await request.get(`/api/simulations/${id}`)).json();
}
test.afterEach(async ({ page, request }) => {
  const id = await page
    .evaluate(() => sessionStorage.getItem("warehouse-active-run"))
    .catch(() => null);
  if (id) await request.delete(`/api/simulations/${id}`);
});
test("2D ↔ 3D preserves the run, moves live robots, selects entities and fits mobile", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  const id = await openRun(page);
  const before = await snapshot(request, id);
  const mutations: string[] = [];
  page.on("request", (req) => {
    if (req.method() === "POST" && req.url().includes("/api/simulations"))
      mutations.push(req.url());
  });
  await page.getByRole("tab", { name: "3D", exact: true }).click();
  await expect(
    page.getByTestId("warehouse-3d").locator("canvas"),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Vybrat robota R-01", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Pohled shora" }).click();
  await page.getByRole("button", { name: "Obnovit 3D kameru" }).click();
  await page
    .getByRole("button", { name: "Vybrat robota R-01", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("Detail robota");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Zavřít", exact: true })
    .click();
  await page.getByRole("tab", { name: "2D", exact: true }).click();
  await expect(
    page
      .getByRole("application", { name: "Interaktivní mapa skladu" })
      .locator("canvas"),
  ).toBeVisible();
  expect(await snapshot(request, id)).toEqual(before);
  expect(mutations).toEqual([]);
  await page.getByRole("tab", { name: "3D", exact: true }).click();
  await page.reload();
  await expect(
    page.getByRole("tab", { name: "3D", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId("tick")).toHaveText("0");
  await page.getByRole("button", { name: "Spustit", exact: true }).click();
  await expect
    .poll(async () =>
      (await snapshot(request, id)).robots.some(
        (robot: { load: number }) => robot.load > 0,
      ),
    )
    .toBe(true);
  await page.getByRole("tab", { name: "2D", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Pozastavit", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "3D", exact: true }).click();
  await page.getByRole("button", { name: "Pozastavit", exact: true }).click();
  const after = await snapshot(request, id);
  expect(after.id).toBe(before.id);
  expect(
    after.robots.map((r: { position: number[] }) => r.position),
  ).not.toEqual(before.robots.map((r: { position: number[] }) => r.position));
  expect(after.metrics.executed_collisions).toBe(0);
  await expect(
    page.getByRole("button", { name: "3D modely", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "3D modely", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Nabíjecí stanice");
  for (const label of [
    "Mobilní robot",
    "Regál",
    "Nakládací stanice",
    "Vykládací stanice",
    "Nabíjecí stanice",
    "Paleta s nákladem",
  ]) {
    await expect(
      page.locator(".model-catalog > div").filter({ hasText: label }),
    ).toContainText("GLB načteno");
  }
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Zavřít", exact: true })
    .click();
  await page.getByRole("button", { name: "Pohled shora" }).click();
  await page.getByRole("button", { name: "Obnovit 3D kameru" }).click();
  await mkdir(evidence, { recursive: true });
  await page.screenshot({
    path: evidence + "simulation-3d-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: "Pohled shora" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: evidence + "simulation-3d-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("local GLB loads through the manifest with no render errors", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.route("**/models/manifest.json", (route) =>
    route.fulfill({
      json: { version: 1, models: { robot: "/models/robot-test.glb" } },
    }),
  );
  await page.route("**/models/robot-test.glb", (route) =>
    route.fulfill({
      contentType: "model/gltf-binary",
      body: robotGlbFixture(),
    }),
  );
  await openRun(page);
  await page.getByRole("tab", { name: "3D", exact: true }).click();
  await page.getByRole("button", { name: "3D modely", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("GLB načteno");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Zavřít", exact: true })
    .click();
  await page.getByRole("button", { name: "Krok", exact: true }).click();
  await expect(page.getByTestId("tick")).toHaveText("1");
  expect(errors).toEqual([]);
});

test("missing GLB reports its fallback and keeps the simulation usable", async ({
  page,
  request,
}) => {
  await page.route("**/models/manifest.json", (route) =>
    route.fulfill({
      json: {
        version: 1,
        models: { robot: "/models/missing.glb", shelf: "/models/missing.glb" },
      },
    }),
  );
  await page.route("**/models/missing.glb", (route) =>
    route.fulfill({ status: 404, body: "Missing test asset" }),
  );
  const id = await openRun(page);
  await page.getByRole("tab", { name: "3D", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "GLB se nepodařilo načíst",
  );
  await expect(page.getByRole("status")).toContainText("Regál");
  await expect(
    page.getByRole("button", { name: "Vybrat robota R-02", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Krok", exact: true }).click();
  await expect(page.getByTestId("tick")).toHaveText("1");
  expect((await snapshot(request, id)).tick).toBe(1);
});

test("Blender assets render in a large warehouse with 32 robots and all static model types", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  const scenario = JSON.parse(
    await readFile(
      new URL("../../../../scenarios/large.json", import.meta.url),
      "utf8",
    ),
  );
  scenario.id = "e2e-blender-32";
  scenario.name = "E2E Blender · 32 robotů";
  scenario.tasks = [];
  scenario.robots = Array.from({ length: 32 }, (_, i) => ({
    ...scenario.robots[0],
    id: `R-${String(i + 1).padStart(2, "0")}`,
    position: [i + 1, 1],
    home: [i + 1, 1],
    orientation: (i % 4) * 90,
  }));
  scenario.warehouse.cells.push(
    { x: 0, y: 0, type: "WALL" },
    { x: 1, y: 0, type: "OBSTACLE" },
  );
  const response = await request.post("/api/simulations", {
    data: { scenario },
  });
  expect(response.status()).toBe(201);
  const initial = await response.json();
  await page.addInitScript(
    (id) => sessionStorage.setItem("warehouse-active-run", id),
    initial.id,
  );
  await page.goto("/simulation");
  await page.getByRole("tab", { name: "3D", exact: true }).click();
  await expect(
    page.getByRole("tab", { name: "Roboti 32", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "3D modely", exact: true }).click();
  await expect(
    page.getByRole("dialog").getByText("GLB načteno", { exact: true }),
  ).toHaveCount(7);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Zavřít", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Vybrat robota R-32", exact: true }),
  ).toBeVisible();
  await mkdir(evidence, { recursive: true });
  await page.screenshot({
    path: evidence + "simulation-3d-large.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "2D", exact: true }).click();
  expect(await snapshot(request, initial.id)).toEqual(initial);
  expect(errors).toEqual([]);
});

test("lost WebGL context offers 2D without changing the paused snapshot", async ({
  page,
  request,
}) => {
  const id = await openRun(page);
  await page.getByRole("tab", { name: "3D", exact: true }).click();
  const canvas = page.getByTestId("warehouse-3d").locator("canvas");
  await expect(
    page.getByRole("button", { name: "Vybrat robota R-02", exact: true }),
  ).toBeVisible();
  const before = await snapshot(request, id);
  await canvas.evaluate((element: HTMLCanvasElement) => {
    const context = element.getContext("webgl2");
    const extension = context?.getExtension("WEBGL_lose_context");
    if (!extension)
      throw new Error("Test requires WebGL context loss extension");
    extension.loseContext();
  });
  await page.getByRole("button", { name: "Zpět do 2D", exact: true }).click();
  await expect(
    page
      .getByRole("application", { name: "Interaktivní mapa skladu" })
      .locator("canvas"),
  ).toBeVisible();
  expect(await snapshot(request, id)).toEqual(before);
});
