import { expect, test } from "@playwright/test";

test("extracts a real PDF, allows correcting evidence and rejects corrupt PDFs", async ({
  page,
}) => {
  await page.setContent(
    "<h1>Candidate CV</h1><p>React and TypeScript development experience.</p>",
  );
  const pdf = await page.pdf();
  await page.goto("/analysis");
  await page
    .getByLabel("Upload CV files")
    .setInputFiles({
      name: "cv.pdf",
      mimeType: "application/pdf",
      buffer: pdf,
    });
  await expect(page.getByText("1 added", { exact: true })).toBeVisible({
    timeout: 30000,
  });
  await page.getByText("Review / edit Candidate 01 text").click();
  const text = page.getByLabel("Extracted text for Candidate 1");
  await expect(text).toContainText("React and TypeScript");
  await text.fill("React\nTypeScript");
  await page
    .getByLabel("Upload CV files")
    .setInputFiles({
      name: "broken.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("not a pdf"),
    });
  await expect(page.getByRole("alert")).toContainText("broken.pdf");
  await expect(text).toHaveValue("React\nTypeScript");
});

test("reads image text using real OCR and a scanned PDF page", async ({
  page,
}) => {
  test.setTimeout(180000);
  await page.setContent(
    '<div style="width:900px;height:300px;background:white;color:black;padding:40px;font:32px Arial">Candidate CV<br><br>React and TypeScript<br>Software engineer experience</div>',
  );
  const png = await page.locator("div").screenshot();
  await page.setContent(
    `<img style="width:700px" src="data:image/png;base64,${png.toString("base64")}">`,
  );
  const scanned = await page.pdf();
  await page.goto("/analysis");
  await page
    .getByLabel("Upload CV files")
    .setInputFiles({ name: "image.png", mimeType: "image/png", buffer: png });
  await expect(page.getByText("1 added", { exact: true })).toBeVisible({
    timeout: 125000,
  });
  await page.getByText("Review / edit Candidate 01 text").click();
  await expect(page.getByLabel("Extracted text for Candidate 1")).toContainText(
    "React",
  );
  await page
    .getByLabel("Upload CV files")
    .setInputFiles({
      name: "scan.pdf",
      mimeType: "application/pdf",
      buffer: scanned,
    });
  await expect(page.getByText("2 added", { exact: true })).toBeVisible({
    timeout: 125000,
  });
  await page.getByText("Review / edit Candidate 02 text").click();
  await expect(page.getByLabel("Extracted text for Candidate 2")).toContainText(
    "TypeScript",
  );
});
