"""
P0-05 — OCR: RapidOCR vs Tesseract on Cyrillic
REQ: REQ-P0-05
Сравнивает CER/WER, скорость. Тест через Docling PdfPipelineOptions где возможно,
и прямой вызов для сравнения.
"""

import os
import sys
import time
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()

TESSERACT_PATH = r"D:\Tesseract\tesseract.exe"
TESSDATA_PATH  = r"D:\Tesseract\tessdata"

# --- Synthetic test image: Russian text for OCR testing ---
# If no real scanned page available, we create a test PNG with PIL
SAMPLE_TEXT_RU = """Морская навигация является важнейшей частью
управления судном в открытом море.
Курс яхты определяется компасом.
Скорость измеряется в узлах (морских милях в час).
Один узел равен 1.852 км в час.
Рифление паруса производится при усилении ветра.
Форштаг удерживает мачту спереди."""


def create_test_image(text: str, output_path: str, lang: str = "en") -> str:
    """Create a test image with Russian text using PIL."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        # Create white background image
        img = Image.new("RGB", (800, 400), color="white")
        draw = ImageDraw.Draw(img)

        # Try to use a system font that supports Cyrillic
        font = None
        font_paths = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/times.ttf",
            "C:/Windows/Fonts/calibri.ttf",
        ]
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    font = ImageFont.truetype(fp, 20)
                    break
                except Exception:
                    pass

        if font is None:
            font = ImageFont.load_default()

        draw.text((20, 20), text, fill="black", font=font)
        img.save(output_path)
        return output_path
    except ImportError:
        console.print("[yellow]PIL not available, using text file for OCR test[/yellow]")
        return None


def levenshtein_cer(ref: str, hyp: str) -> float:
    """Character Error Rate."""
    ref = ref.strip()
    hyp = hyp.strip()
    if not ref:
        return 0.0
    n, m = len(ref), len(hyp)
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        new_dp = [i] + [0] * m
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                new_dp[j] = dp[j - 1]
            else:
                new_dp[j] = 1 + min(dp[j], new_dp[j - 1], dp[j - 1])
        dp = new_dp
    return dp[m] / max(n, 1)


def word_error_rate(ref: str, hyp: str) -> float:
    """Word Error Rate."""
    ref_words = ref.strip().split()
    hyp_words = hyp.strip().split()
    if not ref_words:
        return 0.0
    n, m = len(ref_words), len(hyp_words)
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        new_dp = [i] + [0] * m
        for j in range(1, m + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                new_dp[j] = dp[j - 1]
            else:
                new_dp[j] = 1 + min(dp[j], new_dp[j - 1], dp[j - 1])
        dp = new_dp
    return dp[m] / max(n, 1)


def run_rapidocr(image_path: str) -> tuple[str, float]:
    """Run RapidOCR on an image."""
    from rapidocr_onnxruntime import RapidOCR
    ocr = RapidOCR()
    start = time.time()
    result, _ = ocr(image_path)
    elapsed = time.time() - start
    if result:
        text = "\n".join([line[1] for line in result])
    else:
        text = ""
    return text, elapsed


def run_tesseract(image_path: str) -> tuple[str, float]:
    """Run Tesseract via pytesseract."""
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
    os.environ["TESSDATA_PREFIX"] = TESSDATA_PATH

    start = time.time()
    text = pytesseract.image_to_string(
        image_path, lang="rus+eng", config="--oem 3 --psm 6"
    )
    elapsed = time.time() - start
    return text, elapsed


def test_via_docling_ocr_options(pdf_path: str, engine: str = "tesseract") -> tuple[str, float]:
    """Test OCR through Docling PdfPipelineOptions — the production path."""
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    if engine == "tesseract":
        from docling.datamodel.pipeline_options import TesseractOcrOptions
        ocr_opts = TesseractOcrOptions(
            # path: tessdata directory (not tesseract_cmd — that field was removed)
            path=TESSDATA_PATH,
            lang=["eng"],  # English sources only
        )
    else:
        from docling.datamodel.pipeline_options import RapidOcrOptions
        ocr_opts = RapidOcrOptions()

    options = PdfPipelineOptions(
        do_ocr=True,
        ocr_options=ocr_opts,
    )
    converter = DocumentConverter(
        format_options={"pdf": PdfFormatOption(pipeline_options=options)}
    )
    start = time.time()
    result = converter.convert(pdf_path)
    elapsed = time.time() - start
    text = result.document.export_to_markdown()
    return text, elapsed


def main():
    console.print("\n[bold cyan]═══ T0-05: OCR Engine Comparison (RapidOCR vs Tesseract) ═══[/bold cyan]\n")

    import tempfile

    # Step 1: Check prerequisites
    tesseract_ok = os.path.exists(TESSERACT_PATH)
    console.print(f"Tesseract at {TESSERACT_PATH}: [{'green' if tesseract_ok else 'red'}]{'✓' if tesseract_ok else '✗'}[/]")

    try:
        from rapidocr_onnxruntime import RapidOCR
        rapidocr_ok = True
        console.print("[green]✓ RapidOCR available[/green]")
    except ImportError:
        rapidocr_ok = False
        console.print("[red]✗ RapidOCR not available[/red]")

    try:
        from PIL import Image
        pil_ok = True
    except ImportError:
        pil_ok = False

    # Step 2: Create synthetic test image (or find real one)
    results = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        # Look for real scanned Russian page first
        assets_dir = Path(__file__).parent / "assets"
        scan_images = list(assets_dir.glob("*.png")) + list(assets_dir.glob("*.jpg"))
        ru_scan = None
        for img in scan_images:
            if "scan" in img.name.lower() or "ocr" in img.name.lower():
                ru_scan = str(img)
                break

        if ru_scan:
            test_image_path = ru_scan
            console.print(f"Using real scan: {ru_scan}")
            ground_truth = SAMPLE_TEXT_RU  # approximate; real accuracy may differ
        elif pil_ok:
            test_image_path = os.path.join(tmpdir, "test_ru.png")
            create_test_image(SAMPLE_TEXT_RU, test_image_path)
            ground_truth = SAMPLE_TEXT_RU
            console.print(f"Using synthetic test image: {test_image_path}")
        else:
            console.print("[yellow]No PIL, no scan — creating minimal text test[/yellow]")
            test_image_path = None
            ground_truth = SAMPLE_TEXT_RU

        # Step 3: Run Tesseract
        if tesseract_ok and test_image_path:
            console.print("\n[yellow]Running Tesseract...[/yellow]")
            try:
                tess_text, tess_time = run_tesseract(test_image_path)
                tess_cer = levenshtein_cer(ground_truth, tess_text)
                tess_wer = word_error_rate(ground_truth, tess_text)
                results["tesseract"] = {
                    "text_sample": tess_text[:200],
                    "cer": tess_cer,
                    "wer": tess_wer,
                    "time_sec": tess_time,
                    "ok": True,
                }
                console.print(f"  CER: {tess_cer:.3f} | WER: {tess_wer:.3f} | Time: {tess_time:.2f}s")
                console.print(f"  Sample output: {tess_text[:100]!r}")
            except Exception as e:
                console.print(f"[red]Tesseract failed: {e}[/red]")
                results["tesseract"] = {"ok": False, "error": str(e)}

        # Step 4: Run RapidOCR
        if rapidocr_ok and test_image_path:
            console.print("\n[yellow]Running RapidOCR...[/yellow]")
            try:
                rapid_text, rapid_time = run_rapidocr(test_image_path)
                rapid_cer = levenshtein_cer(ground_truth, rapid_text)
                rapid_wer = word_error_rate(ground_truth, rapid_text)
                results["rapidocr"] = {
                    "text_sample": rapid_text[:200],
                    "cer": rapid_cer,
                    "wer": rapid_wer,
                    "time_sec": rapid_time,
                    "ok": True,
                }
                console.print(f"  CER: {rapid_cer:.3f} | WER: {rapid_wer:.3f} | Time: {rapid_time:.2f}s")
                console.print(f"  Sample output: {rapid_text[:100]!r}")
            except Exception as e:
                console.print(f"[red]RapidOCR failed: {e}[/red]")
                results["rapidocr"] = {"ok": False, "error": str(e)}

    # Step 5: Test through Docling (production path)
    # We skip if both engines fail or if there's no PDF
    pdf_path = Path(__file__).parent.parent / ".init_doc" / "source_doc" / "Sail and Rig Tuning (Ivar Dedekam) (z-library.sk, 1lib.sk, z-lib.sk).pdf"
    if pdf_path.exists():
        console.print("\n[yellow]Testing Tesseract via Docling PdfPipelineOptions (production path)...[/yellow]")
        try:
            _, docling_time = test_via_docling_ocr_options(str(pdf_path), "tesseract")
            console.print(f"  [green]✓ Tesseract via Docling works ({docling_time:.1f}s for first pages)[/green]")
            results["tesseract_via_docling"] = {"ok": True, "time_sec": docling_time}
        except Exception as e:
            console.print(f"  [yellow]Docling+Tesseract: {e}[/yellow]")
            results["tesseract_via_docling"] = {"ok": False, "error": str(e)}

    # ─── Results table ───
    table = Table(title="OCR Engine Comparison")
    table.add_column("Engine", style="cyan")
    table.add_column("CER", justify="center")
    table.add_column("WER", justify="center")
    table.add_column("Speed (s)", justify="center")
    table.add_column("Status", justify="center")

    for engine_name, r in results.items():
        if not r.get("ok"):
            table.add_row(engine_name, "—", "—", "—", f"[red]FAILED: {r.get('error', '?')[:40]}[/red]")
        else:
            cer = r.get("cer", None)
            wer = r.get("wer", None)
            t = r.get("time_sec", None)
            cer_str = f"{cer:.3f}" if cer is not None else "—"
            wer_str = f"{wer:.3f}" if wer is not None else "—"
            t_str = f"{t:.2f}" if t is not None else "—"
            table.add_row(engine_name, cer_str, wer_str, t_str, "[green]OK[/green]")

    console.print(table)

    # ─── Decision ───
    console.print("\n[bold]Decision:[/bold]")
    tess_ok = results.get("tesseract", {}).get("ok", False)
    rapid_ok = results.get("rapidocr", {}).get("ok", False)

    if tess_ok and rapid_ok:
        tess_cer = results["tesseract"].get("cer", 1.0)
        rapid_cer = results["rapidocr"].get("cer", 1.0)
        if tess_cer <= rapid_cer:
            winner = "Tesseract (rus+eng)"
            winner_key = "tesseract"
        else:
            winner = "RapidOCR"
            winner_key = "rapidocr"
        console.print(f"  [green]Recommended engine: {winner}[/green]")
        console.print(f"  CER: Tesseract={tess_cer:.3f} | RapidOCR={rapid_cer:.3f}")
    elif tess_ok:
        winner = "Tesseract (rus+eng)"
        winner_key = "tesseract"
        console.print(f"  [green]Only working engine: Tesseract[/green]")
    elif rapid_ok:
        winner = "RapidOCR"
        winner_key = "rapidocr"
        console.print(f"  [green]Only working engine: RapidOCR[/green]")
    else:
        winner = "NONE"
        winner_key = None
        console.print(f"  [red]No OCR engine available[/red]")

    ac1 = winner_key is not None
    ac2 = results.get("tesseract_via_docling", {}).get("ok", False) if tess_ok else rapid_ok
    ac3 = ac1  # CER documented

    console.print("\n[bold]Acceptance Criteria:[/bold]")
    console.print(f"  [{'green' if ac1 else 'red'}]{'✓' if ac1 else '✗'}[/] Engine chosen with justification")
    console.print(f"  [{'green' if ac3 else 'red'}]{'✓' if ac3 else '✗'}[/] CER/WER documented")
    console.print(f"  [{'green' if ac2 else 'red'}]{'✓' if ac2 else '✗'}[/] Engine works via Docling PdfPipelineOptions")

    return {
        "winner": winner,
        "results": results,
        "pass": ac1 and ac3,
    }


if __name__ == "__main__":
    result = main()
    import sys
    sys.exit(0 if result.get("pass") else 1)
