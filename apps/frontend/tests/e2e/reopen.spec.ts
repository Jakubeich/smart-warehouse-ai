import { expect, test } from "@playwright/test";

test("a generated warehouse opens and starts from a tab with an expired run", async ({
  page,
  request,
}) => {
  expect((await request.post("/api/demos")).ok()).toBeTruthy();
  const name = `E2E obnovení relace ${Date.now()}`;
  const failedRequests: string[] = [];
  page.on("pageerror", (error) => failedRequests.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 400 && response.url().includes("/api/"))
      failedRequests.push(response.url());
  });

  const previous = await request.post("/api/simulations", {
    data: { scenario_id: "demo-small" },
  });
  expect(previous.ok()).toBeTruthy();
  const oldId = (await previous.json()).id;

  // Keep the old tab unaware of the server-side removal until a new run opens.
  let confirmRestore!: () => void;
  const restored = new Promise<void>((resolve) => {
    confirmRestore = resolve;
  });
  await page.routeWebSocket("**/ws/simulations/**", (socket) => {
    if (socket.url().endsWith(`/${oldId}`)) confirmRestore();
    else socket.connectToServer();
  });

  await page.addInitScript((id) => {
    sessionStorage.setItem("warehouse-active-run", id);
  }, oldId);
  await page.goto("/warehouses");
  await restored;
  const generation = page.getByRole("button", { name: "Generovat sklad" });
  await generation.click();
  await page.getByLabel("Název generovaného skladu").fill(name);
  await page.getByRole("button", { name: "Náhodný seed" }).click();
  await page.getByRole("button", { name: "Vygenerovat náhled" }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await page.getByRole("button", { name: "Uložit scénář" }).click();
  await expect(page.getByText("Scénář byl uložen do PostgreSQL")).toBeVisible();
  expect((await request.delete(`/api/simulations/${oldId}`)).status()).toBe(
    204,
  );

  await page.getByRole("link", { name: "Přehled", exact: true }).click();
  await page
    .getByRole("article")
    .filter({ hasText: name })
    .getByRole("button", { name: "Otevřít simulaci" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Živá simulace" }),
  ).toBeVisible();
  await expect(page.getByTestId("tick")).toHaveText("0");
  const newId = await page.evaluate(() =>
    sessionStorage.getItem("warehouse-active-run"),
  );
  expect(newId).toBeTruthy();
  expect(newId).not.toBe(oldId);
  try {
    await page.getByRole("button", { name: "Spustit", exact: true }).click();
    await expect
      .poll(async () => Number(await page.getByTestId("tick").innerText()))
      .toBeGreaterThan(1);
    await page.getByRole("button", { name: "Pozastavit", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Spustit", exact: true }),
    ).toBeEnabled();
    expect(failedRequests).toEqual([]);
  } finally {
    if (newId) await request.delete(`/api/simulations/${newId}`);
  }
});
