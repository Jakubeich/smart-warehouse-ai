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

test("generated warehouse → persisted two-way map → neural dispatch", async ({
  page,
  request,
}) => {
  test.setTimeout(120000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await mkdir(evidence, { recursive: true });
  await page.goto("/settings");
  await page.getByRole("spinbutton", { name: "Spotřeba při pohybu" }).fill("0.5");
  await page.getByRole("button", { name: "Uložit nastavení" }).click();
  await expect(page.getByText("Výchozí nastavení pro nové simulace bylo uloženo")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("spinbutton", { name: "Spotřeba při pohybu" })).toHaveValue("0.5");
  await page.getByRole("link", { name: "Sklady", exact: true }).click();
  await page
    .getByRole("button", { name: "Generovat sklad", exact: true })
    .click();
  await page
    .getByLabel("Název generovaného skladu", { exact: true })
    .fill("E2E průjezdy ML v2");
  await page
    .getByLabel("Šířka generovaného skladu", { exact: true })
    .fill("16");
  await page
    .getByLabel("Výška generovaného skladu", { exact: true })
    .fill("12");
  await page.getByLabel("Počet generovaných úkolů", { exact: true }).fill("8");
  await page.getByLabel("Seed generátoru", { exact: true }).fill("71000");
  await page
    .getByRole("combobox", { name: "Průjezdy mezi částmi skladu", exact: true })
    .click();
  await page
    .getByRole("option", { name: "Zúžené průjezdy", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Směr přeprav", exact: true })
    .click();
  await page.getByRole("option", { name: "Oba směry", exact: true }).click();
  await page.screenshot({
    path: evidence + "warehouse-generator.png",
    fullPage: true,
  });
  const generatedResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/generator") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Vygenerovat náhled" }).click();
  const generated = await (await generatedResponse).json();
  expect(
    generated.warehouse.cells.some((c: { type: string }) => c.type === "WALL"),
  ).toBe(true);
  expect(
    generated.tasks.filter(
      (t: { pickup: number[]; dropoff: number[] }) =>
        t.pickup[0] > t.dropoff[0],
    ),
  ).toHaveLength(4);
  await expect(
    page.getByRole("heading", { name: "E2E průjezdy ML v2", exact: true }),
  ).toBeVisible();
  await expect(page.locator("canvas")).toBeVisible();
  await page
    .getByRole("button", { name: "Uložit scénář", exact: true })
    .click();
  await expect(page.getByText("Scénář byl uložen do PostgreSQL")).toBeVisible();
  await page.reload();
  await page.getByRole("combobox", { name: "Načíst scénář" }).click();
  await page
    .getByRole("option", { name: "E2E průjezdy ML v2", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "E2E průjezdy ML v2", exact: true }),
  ).toBeVisible();
  const regenerated = await request.post("/api/generator", {
    data: JSON.parse(generated.warehouse.metadata.generator),
  });
  expect(await regenerated.json()).toEqual(generated);
  await page.screenshot({
    path: evidence + "warehouse-generated.png",
    fullPage: true,
  });

  await page
    .getByRole("button", { name: "Otevřít simulaci", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Živá simulace" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Krok", exact: true }).click();
  await expect(page.getByTestId("tick")).toHaveText("1");
  const id = await page.evaluate(() =>
    sessionStorage.getItem("warehouse-active-run"),
  );
  const current = await (await request.get(`/api/simulations/${id}`)).json();
  expect(current.config.control).toBe("neural");
  expect(current.config.move_energy).toBe(0.5);
  expect(
    current.neural_decisions.some(
      (d: { action: string }) => d.action === "task",
    ),
  ).toBeTruthy();
  expect(errors).toEqual([]);
});
