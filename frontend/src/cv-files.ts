export const CV_ACCEPT =
  ".txt,.pdf,.png,.jpg,.jpeg,.webp,text/plain,application/pdf,image/png,image/jpeg,image/webp";
const MAX_CHARS = 50000;
const MAX_FILE = 10 * 1024 * 1024;
export type Progress = (message: string) => void;

function readable(text: string) {
  if (
    !text.trim() ||
    text.length > MAX_CHARS ||
    Array.from(text).some((c) => {
      const n = c.charCodeAt(0);
      return n < 9 || (n > 13 && n < 32);
    })
  ) {
    throw new Error(
      "No usable text found, or text exceeds 50,000 characters. Try a clearer file or paste the text.",
    );
  }
  return text;
}

async function recognize(
  image: HTMLCanvasElement,
  progress: Progress,
  signal: AbortSignal,
) {
  const { createWorker } = await import("tesseract.js");
  const { default: workerPath } =
    await import("tesseract.js/dist/worker.min.js?url");
  progress("Loading English OCR…");
  signal.throwIfAborted();
  const pending = createWorker("eng", 1, {
    workerPath,
    logger: (m) =>
      progress(`OCR: ${m.status} ${Math.round(m.progress * 100)}%`),
    errorHandler: () => {},
  });
  const stop = () => {
    void pending.then((worker) => worker.terminate()).catch(() => {});
  };
  signal.addEventListener("abort", stop, { once: true });
  try {
    const worker = await pending;
    signal.throwIfAborted();
    const result = await worker.recognize(image);
    signal.throwIfAborted();
    return result.data.text;
  } finally {
    signal.removeEventListener("abort", stop);
    await pending.then((worker) => worker.terminate()).catch(() => {});
  }
}

async function imageText(file: File, progress: Progress, signal: AbortSignal) {
  const bitmap = await createImageBitmap(file);
  try {
    if (bitmap.width * bitmap.height > 25000000)
      throw new Error(
        "Image is too large. Resize it to at most 25 megapixels.",
      );
    const scale = Math.min(1, 3000 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return await recognize(canvas, progress, signal);
  } finally {
    bitmap.close();
  }
}

async function pdfText(file: File, progress: Progress, signal: AbortSignal) {
  const pdfjs = await import("pdfjs-dist");
  const { default: workerSrc } =
    await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
  pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;
  signal.throwIfAborted();
  const task = pdfjs.getDocument({ data: await file.arrayBuffer() });
  const stop = () => {
    void task.destroy();
  };
  signal.addEventListener("abort", stop, { once: true });
  try {
    const pdf = await task.promise;
    if (pdf.numPages > 10)
      throw new Error(
        "PDFs may contain at most 10 pages. Upload a shorter CV.",
      );
    const pages: string[] = [];
    for (let i = 1; i <= pdf.numPages; i++) {
      signal.throwIfAborted();
      progress(`Reading PDF page ${i} of ${pdf.numPages}…`);
      const page = await pdf.getPage(i);
      const content = await page.getTextContent();
      let text = content.items
        .map((item) =>
          "str" in item ? item.str + (item.hasEOL ? "\n" : " ") : "",
        )
        .join("");
      if (text.trim().length < 15) {
        const original = page.getViewport({ scale: 1 });
        const scale = Math.min(
          2,
          2500 / Math.max(original.width, original.height),
        );
        const viewport = page.getViewport({ scale });
        const canvas = document.createElement("canvas");
        canvas.width = Math.ceil(viewport.width);
        canvas.height = Math.ceil(viewport.height);
        await page.render({ canvas, viewport }).promise;
        text = await recognize(
          canvas,
          (m) => progress(`Page ${i}/${pdf.numPages} · ${m}`),
          signal,
        );
        if (!text.trim())
          throw new Error(
            `No text could be read on page ${i}. Remove blank pages or use a clearer scan.`,
          );
      }
      pages.push(text);
      page.cleanup();
      if (pages.join("\n\n").length > MAX_CHARS)
        throw new Error(
          "Extracted text exceeds 50,000 characters. Upload a shorter CV.",
        );
    }
    return pages.join("\n\n");
  } finally {
    signal.removeEventListener("abort", stop);
    await task.destroy();
  }
}

export async function readCVFile(
  file: File,
  progress: Progress = () => {},
  externalSignal?: AbortSignal,
): Promise<string> {
  const ext = file.name.split(".").pop()?.toLowerCase();
  if (!ext || !["txt", "pdf", "png", "jpg", "jpeg", "webp"].includes(ext))
    throw new Error(
      `${file.name}: supported types are PDF, PNG, JPG, WebP and TXT.`,
    );
  if (file.size > (ext === "txt" ? 200000 : MAX_FILE))
    throw new Error(
      `${file.name}: maximum file size is ${ext === "txt" ? "200 KB" : "10 MB"}.`,
    );
  const controller = new AbortController();
  const cancel = () =>
    controller.abort(new Error("File extraction cancelled."));
  externalSignal?.addEventListener("abort", cancel, { once: true });
  if (externalSignal?.aborted) cancel();
  const timer = setTimeout(
    () =>
      controller.abort(
        new Error(
          "Extraction timed out. Try a smaller file, check your connection for OCR downloads, or paste text.",
        ),
      ),
    120000,
  );
  let stopWaiting: (() => void) | undefined;
  try {
    const signal = controller.signal;
    signal.throwIfAborted();
    const extraction = (async () => {
      if (ext === "txt")
        return new TextDecoder("utf-8", { fatal: true }).decode(
          await file.arrayBuffer(),
        );
      return ext === "pdf"
        ? pdfText(file, progress, signal)
        : imageText(file, progress, signal);
    })();
    const aborted = new Promise<never>((_, reject) => {
      stopWaiting = () => reject(signal.reason);
      signal.addEventListener("abort", stopWaiting, { once: true });
    });
    return readable(await Promise.race([extraction, aborted]));
  } catch (e) {
    const message =
      e instanceof Error ? e.message : "Could not read this file.";
    throw new Error(
      `${file.name}: ${message} If necessary, paste extracted text instead.`,
    );
  } finally {
    clearTimeout(timer);
    externalSignal?.removeEventListener("abort", cancel);
    if (stopWaiting)
      controller.signal.removeEventListener("abort", stopWaiting);
  }
}
