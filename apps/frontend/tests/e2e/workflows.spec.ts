import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
const evidence = new URL("../../../../docs/screenshots/", import.meta.url)
  .pathname;
test.afterEach(async ({ page, request }) => {
  const id = await page
    .evaluate(() => sessionStorage.getItem("warehouse-active-run"))
    .catch(() => null);
  if (id) await request.delete(`/api/simulations/${id}`);
});
test("dashboard → live robots → pause → new task → archived experiment → actual results", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page).toHaveTitle("Smart Warehouse AI");
  await expect(page.locator("html")).toHaveAttribute("lang", "cs");
  await page.getByRole("button", { name: "Vytvořit ukázkové scénáře" }).click();
  const small = page.locator("article").filter({ hasText: "Malý sklad" });
  await expect(small).toBeVisible();
  await small.getByRole("button", { name: "Otevřít simulaci" }).click();
  await expect(
    page.getByRole("heading", { name: "Živá simulace" }),
  ).toBeVisible();
  await expect(page.locator("canvas")).toBeVisible();
  await page.getByRole("button", { name: "Spustit", exact: true }).click();
  await expect
    .poll(async () => Number(await page.getByTestId("tick").innerText()))
    .toBeGreaterThan(3);
  await page.getByRole("button", { name: "Pozastavit", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Spustit", exact: true }),
  ).toBeEnabled();
  const paused = await page.getByTestId("tick").innerText();
  await page.waitForTimeout(700);
  expect(await page.getByTestId("tick").innerText()).toBe(paused);
  await page.reload();
  await expect(page.getByTestId("tick")).toHaveText(paused);
  await page.getByRole("button", { name: /R-01/ }).click();
  await expect(
    page.getByRole("heading", { name: "Detail robota", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Zavřít", exact: true })
    .click();
  await page.getByRole("button", { name: "Přidat úkol", exact: true }).click();
  await page
    .getByRole("button", { name: "Vytvořit úkol", exact: true })
    .click();
  await expect(page.getByText("0 / 13", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Spustit", exact: true }).click();
  await expect
    .poll(async () => Number(await page.getByTestId("tick").innerText()))
    .toBeGreaterThan(Number(paused) + 2);
  await page.getByRole("button", { name: "Pozastavit", exact: true }).click();
  await mkdir(evidence, { recursive: true });
  await page.screenshot({
    path: evidence + "simulation-desktop.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "Roboti", exact: true }).click();
  await page.getByRole("textbox", { name: "Filtrovat záznamy" }).fill("R-02");
  await expect(page.getByRole("row").filter({ hasText: "R-02" })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "R-01" })).toHaveCount(0);
  await page.getByRole("link", { name: "Úkoly", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Přepravní úkoly" })).toBeVisible();
  await expect(page.getByRole("table").getByRole("row")).toHaveCount(14);
  await page.getByRole("link", { name: "Analýza", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Dokončené úkoly v čase" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Teplotní mapa obsazenosti" })).toBeVisible();
  const experiment = await request.post("/api/experiments", {
    data: {
      name: "E2E archiv",
      algorithms: ["astar", "prioritized", "cbs", "adaptive"],
      repetitions: 1,
      robot_counts: [2],
    },
  });
  expect(experiment.ok()).toBeTruthy();
  const { id } = await experiment.json();
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/experiments/${id}`)).json()).status,
      { timeout: 30000 },
    )
    .toBe("COMPLETED");
  await page.goto(`/experiments?id=${id}`);
  await expect(
    page.getByText("Naměřené běhy: 4 / 4", { exact: false }),
  ).toBeVisible({ timeout: 30000 });
  await page.getByRole("tab", { name: "Jednotlivé běhy", exact: true }).click();
  await expect(
    page.getByText("Optimální statický SoC", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Grafy", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Doba plánování" })).toBeVisible();
  await page.getByRole("tab", { name: "Přehled", exact: true }).click();
  await page.screenshot({
    path: evidence + "experiments-desktop.png",
    fullPage: true,
  });
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "CSV", exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain(".csv");
  expect(errors).toEqual([]);
});
test("editor saves, reloads, undoes placement and validates the map", async ({
  page,
}) => {
  await page.goto("/warehouses");
  await page.getByRole("button", { name: "Nový sklad", exact: true }).click();
  await page.getByLabel("Název skladu", { exact: true }).fill("E2E sklad");
  await page
    .getByRole("button", { name: "Vytvořit sklad", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "E2E sklad", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Regál", exact: true }).click();
  const canvas = page.getByRole("application", {
    name: "Interaktivní mapa skladu",
  });
  const box = await canvas.boundingBox();
  if (!box) throw new Error("Map absent");
  await canvas.click({ position: { x: box.width / 2, y: box.height / 2 } });
  await expect(page.getByRole("button", { name: "Zpět" })).toBeEnabled();
  await page.getByRole("button", { name: "Zpět" }).click();
  await page.getByRole("button", { name: "Znovu" }).click();
  await page
    .getByRole("button", { name: "Uložit scénář", exact: true })
    .click();
  await expect(page.getByText("Scénář byl uložen do PostgreSQL")).toBeVisible();
  await page.reload();
  await page.getByRole("combobox", { name: "Načíst scénář" }).click();
  await page
    .getByRole("option", { name: "E2E sklad", exact: true })
    .last()
    .click();
  await expect(
    page.getByRole("heading", { name: "E2E sklad", exact: true }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exportovat JSON", exact: true }).click();
  const saved = await download;
  expect(saved.suggestedFilename()).toBe("E2E sklad.json");
  await page.locator('input[type="file"]').setInputFiles(await saved.path());
  await expect(page.getByText("Scénář byl importován.", { exact: false })).toBeVisible();
});
test("mobile layout keeps primary controls reachable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Vytvořit ukázkové scénáře" }).click();
  await page
    .locator("article")
    .filter({ hasText: "Malý sklad" })
    .getByRole("button", { name: "Otevřít simulaci" })
    .click();
  await expect(
    page.getByRole("button", { name: "Spustit", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.getByRole("button", { name: "Spustit", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Pozastavit", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.getByRole("button", { name: "Pozastavit", exact: true }).click();
  await page.getByRole("button", { name: "Otevřít navigaci" }).click();
  await expect(
    page
      .getByRole("dialog")
      .getByRole("link", { name: "Experimenty", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Zavřít", exact: true })
    .click();
  await page.screenshot({
    path: evidence + "simulation-mobile.png",
    fullPage: true,
  });
});

test("simulation exposes map layers and details without a control switch", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .locator("article")
    .filter({ hasText: "Malý sklad" })
    .getByRole("button", { name: "Otevřít simulaci" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Záznam událostí", exact: true }),
  ).not.toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Řízení robotů" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Vrstvy", exact: true }).click();
  const heatmap = page.getByRole("menuitemcheckbox", {
    name: "Teplotní mapa",
    exact: true,
  });
  await heatmap.click();
  await expect(heatmap).toBeChecked();
  await heatmap.click();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Krok", exact: true }).click();
  await expect(page.getByTestId("tick")).toHaveText("1");
  await page.getByRole("button", { name: /Podrobnosti běhu Metriky/ }).click();
  await expect(
    page.getByRole("heading", { name: "Záznam událostí", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Simulace byla spuštěna", { exact: true }),
  ).not.toBeVisible();
  await expect(page.getByText(/Scénář je připraven/)).toBeVisible();
  await page.getByRole("tab", { name: /Úkoly 12/ }).click();
  await expect(page.getByRole("tabpanel", { name: /Úkoly/ })).toContainText(
    "Priorita",
  );
  await page.getByLabel("Filtrovat roboty nebo úkoly").fill("ceka");
  await expect(page.getByRole("tabpanel", { name: /Úkoly/ })).toContainText(
    "Čeká na přiřazení",
  );
  await expect(page.getByTestId("neural-decisions")).toContainText("Popojet");
});
