import { expect, test } from "@playwright/test";

test("recruiter completes a demo, reviews evidence, saves notes and exports report", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "Clarity for every hiring conversation.",
    }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("overview.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    ),
  ).toBe(true);
  await page.getByRole("link", { name: "Start an analysis" }).click();
  await page.getByRole("button", { name: "Use sample" }).click();
  await page.getByRole("button", { name: "Run demo analysis" }).click();
  await expect(page.getByRole("alert")).toContainText("Confirm");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Run demo analysis" }).click();
  await expect(
    page.getByText("MOCK / DEMO · simulated progress"),
  ).toBeVisible();
  await page.getByRole("link", { name: "Review candidate evidence" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page
    .getByRole("link", { name: "Review Candidate 01", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Requirement-by-requirement evidence" }),
  ).toBeVisible();
  await expect(page.getByText("Not executed", { exact: true })).toHaveCount(2);
  await expect(page.locator("blockquote").first()).toContainText(
    "Built production interfaces",
  );
  await page.getByLabel("Review status").selectOption("Follow-up needed");
  await page
    .getByLabel("Reviewer notes")
    .fill("Ask for testing examples and accessibility walkthrough.");
  await page.getByRole("button", { name: "Save review" }).click();
  await expect(page.getByRole("status")).toContainText("Review saved");
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("detail.png"),
    fullPage: true,
  });
  // Client navigation preserves the explicitly in-memory session.
  if (testInfo.project.name === "mobile")
    await page.getByRole("button", { name: "Toggle navigation" }).click();
  await page.getByRole("link", { name: "Reports", exact: true }).click();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON" }).first().click();
  const download = await downloaded;
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(chunk);
  const report = JSON.parse(Buffer.concat(chunks).toString());
  expect(report.data_classification).toContain("DEMO");
  expect(report.campaign.candidates[0].review).toBe("Follow-up needed");
  expect(report.campaign.candidates[0].note).toContain("testing examples");
  expect(errors).toEqual([]);
});
test("validates uploads and supports multiple candidates", async ({ page }) => {
  await page.goto("/analysis");
  await page
    .getByLabel("Upload CV text files")
    .setInputFiles({
      name: "cv.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("not parsed"),
    });
  await expect(page.getByRole("alert")).toContainText("only UTF-8 .txt");
  await page.getByRole("button", { name: "Use sample" }).click();
  await page.getByLabel("Or paste CV content").fill("");
  await page.getByLabel("Upload CV text files").setInputFiles([
    {
      name: "one.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("React\nTypeScript"),
    },
    {
      name: "two.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Automated testing"),
    },
  ]);
  await expect(page.getByText("2 added", { exact: true })).toBeVisible();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Run demo analysis" }).click();
  await page.getByRole("link", { name: "Review candidate evidence" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(2);
  await page.getByLabel("Search candidates").fill("Candidate 02");
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page.getByLabel("Review filter").selectOption("Reviewed");
  await expect(
    page.getByRole("heading", { name: "No candidates found" }),
  ).toBeVisible();
});
test("deep links, empty states, missing configuration and mobile navigation work", async ({
  page,
}, testInfo) => {
  for (const [route, title] of [
    ["/processing", "No analysis in progress"],
    ["/candidates/missing", "Candidate not available"],
    ["/does-not-exist", "This page could not be found"],
  ]) {
    await page.goto(route);
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
  }
  await page.goto("/system");
  await page.getByRole("button", { name: "Check backend" }).click();
  await expect(page.getByRole("alert")).toHaveCount(3);
  await expect(page.getByRole("alert").first()).toContainText(
    "VITE_API_BASE_URL",
  );
  if (testInfo.project.name === "mobile")
    await page.getByRole("button", { name: "Toggle navigation" }).click();
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page).toHaveURL("/");
});
