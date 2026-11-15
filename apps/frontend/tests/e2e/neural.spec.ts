import { expect, test } from "@playwright/test";

test("neuronová síť řídí živý sklad a výměna pohledu nemění stav", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.goto("/learning");
  const panel = page.getByRole("region", { name: "Neuronové řízení flotily" });
  await expect(panel.getByRole("table")).toContainText("Dokončené scénáře");
  await expect(panel.getByText("Společný model flotily")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(panel.getByRole("button")).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await panel.screenshot({ path: "test-results/neural-model-mobile.png" });
  await page.setViewportSize({ width: 1536, height: 1024 });
  await panel.getByRole("button", { name: "Otevřít ukázkový sklad" }).click();
  await expect(
    page.getByRole("heading", { name: "Živá simulace" }),
  ).toBeVisible();
  const id = await page.evaluate(() =>
    sessionStorage.getItem("warehouse-active-run"),
  );
  expect(id).toBeTruthy();
  try {
    await page.getByRole("button", { name: "Krok", exact: true }).click();
    await expect(page.getByTestId("tick")).toHaveText("1");
    await page
      .getByRole("button", { name: /Podrobnosti běhu Metriky/ })
      .click();
    await expect(page.getByTestId("neural-decisions")).toContainText(
      "Převzít úkol",
    );
    await expect(page.getByTestId("neural-decisions")).toContainText("Popojet");
    const path = `/api/simulations/${id}`;
    const before = await (await request.get(path)).json();
    expect(before.config.control).toBe("neural");
    expect(before.metrics.replans).toBe(0);
    await page.getByRole("tab", { name: "3D", exact: true }).click();
    await expect(
      page.getByTestId("warehouse-3d").locator("canvas"),
    ).toBeVisible();
    expect(await (await request.get(path)).json()).toEqual(before);
    await page.screenshot({
      path: "test-results/neural-fleet-3d.png",
      fullPage: true,
    });
    await page.getByRole("button", { name: "Krok", exact: true }).click();
    await expect(page.getByTestId("tick")).toHaveText("2");
    await page.getByRole("combobox", { name: "Rychlost simulace" }).click();
    await page.getByRole("option", { name: "16×", exact: true }).click();
    await page.getByRole("button", { name: "Spustit", exact: true }).click();
    await expect
      .poll(async () => (await (await request.get(path)).json()).status, {
        timeout: 30000,
      })
      .toBe("COMPLETED");
    const final = await (await request.get(path)).json();
    expect(final.metrics.completed_tasks).toBe(before.tasks.length);
    expect(final.neural_updates).toBeGreaterThan(before.neural_updates);
    expect(final.neural_learned_samples).toBeGreaterThan(before.neural_learned_samples);
    expect(final.config.neural_model_id).not.toBe(before.config.neural_model_id);
    await page.goto("/learning");
    await expect(page.getByTestId("neural-updates")).not.toHaveText("0");
    await page.goto("/settings");
    await expect(
      page.getByRole("combobox", { name: "Výchozí řízení robotů" }),
    ).toHaveCount(0);
    expect(final.metrics.replans).toBe(0);
    expect(final.metrics.executed_collisions).toBe(0);
    expect(errors).toEqual([]);
  } finally {
    await request.delete(`/api/simulations/${id}`);
  }
});
