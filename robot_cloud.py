import os
import re
import json
import time
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# Penyambungan string URL agar 100% aman dari pemotongan format
BASE_URL = "https://kemenkeu.go.id"
LOGIN_URL = BASE_URL + "/login?q=0e8b2"
REPORT_URL = BASE_URL + "/laporan?q=Realisasi&l=Dept-Output&w=147"

SATUDJA_USER = os.environ.get("SATUDJA_USER", "")
SATUDJA_PASS = os.environ.get("SATUDJA_PASS", "")

TARGET_KEGIATAN = {"7228", "7229", "7230", "7231", "7832", "7245"}
EXCLUDE_SUBOUTPUT = "7229.AEG"

def clean_number(text):
    if not text:
        return 0
    cleaned = re.sub(r"[^\d-]", "", str(text).split(",")[0])
    try:
        return int(cleaned) if cleaned else 0
    except ValueError:
        return 0

def get_wib_timestamp():
    wib = timezone(timedelta(hours=7))
    return datetime.now(wib).strftime("%d %b %Y, %H:%M WIB")

def run_scraper():
    if not SATUDJA_USER or not SATUDJA_PASS:
        raise ValueError("SATUDJA_USER atau SATUDJA_PASS kosong di GitHub Secrets.")

    with sync_playwright() as p:
        # 1. Penyamaran identitas browser Windows asli
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--window-size=1920,1080"
            ]
        )

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="id-ID",
            timezone_id="Asia/Jakarta"
        )

        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = context.new_page()

        try:
            # TAHAP 1: Buka Halaman Login
            print(f"[{get_wib_timestamp()}] Membuka halaman login: {LOGIN_URL}")
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)  # Beri waktu ekstra jika ada loading JS/redirect
            page.screenshot(path="bukti1_layar.png", full_page=True)
            print("Foto layar tahap 1 disimpan: bukti1_layar.png")

            # Cari kolom username dan password
            user_input = page.locator('input[type="text"], input[name*="user"], input[id*="user"]').first
            user_input.wait_for(state="visible", timeout=35000)
            pass_input = page.locator('input[type="password"]').first

            print("Mengisi username dan password...")
            user_input.fill(SATUDJA_USER)
            pass_input.fill(SATUDJA_PASS)

            submit_btn = page.locator(
                'button[type="submit"], input[type="submit"], '
                'button:has-text("Login"), button:has-text("Masuk")'
            ).first
            if submit_btn.count() > 0:
                submit_btn.click()
            else:
                pass_input.press("Enter")

            # TAHAP 2: Verifikasi Hasil Login
            time.sleep(6)
            page.screenshot(path="bukti2_layar.png", full_page=True)
            print("Foto layar tahap 2 disimpan: bukti2_layar.png")

            if "login" in page.url.lower():
                raise RuntimeError("Masih tertahan di halaman login. Cek bukti1_layar.png dan bukti2_layar.png.")

            # TAHAP 3: Buka Halaman Laporan Induk & Auto-Scroll
            print(f"[{get_wib_timestamp()}] Membuka halaman laporan induk...")
            page.goto(REPORT_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("table tbody tr", timeout=45000)
            time.sleep(3)

            print("Melakukan auto-scroll ke bawah...")
            previous_height = 0
            for i in range(25):
                page.evaluate("""
                    window.scrollTo(0, document.body.scrollHeight);
                    document.querySelectorAll('div, table').forEach(el => {
                        if (el.scrollHeight > el.clientHeight) {
                            el.scrollTop = el.scrollHeight;
                        }
                    });
                """)
                time.sleep(1.2)
                current_height = page.evaluate("document.body.scrollHeight")
                if current_height == previous_height and i > 4:
                    break
                previous_height = current_height

            page.screenshot(path="bukti3_layar.png", full_page=True)
            print("Foto layar tahap 3 disimpan: bukti3_layar.png")

            # TAHAP 4: Ekstraksi & Filter Data
            raw_rows = page.evaluate("""
                () => Array.from(document.querySelectorAll('table tbody tr')).map(tr =>
                    Array.from(tr.querySelectorAll('td, th')).map(td => td.innerText.trim())
                )
            """)

            kegiatan_data = {
                kode: {
                    "kode": kode,
                    "nama": f"Kegiatan {kode}",
                    "pagu": 0,
                    "realisasi": 0,
                    "rincian": []
                } for kode in TARGET_KEGIATAN
            }

            excluded_pagu_7229 = 0
            excluded_real_7229 = 0

            for cells in raw_rows:
                if len(cells) < 3:
                    continue

                row_text = " ".join(cells)
                match_sub = re.search(r"\b(7228|7229|7230|7231|7832|7245)\.([A-Z0-9]+)\b", row_text)
                match_induk = re.search(r"^\s*(7228|7229|7230|7231|7832|7245)\b", cells[0])

                numeric_vals = [clean_number(c) for c in cells[1:] if clean_number(c) > 0]

                if match_induk and not match_sub:
                    kode_keg = match_induk.group(1)
                    nama_keg = cells[1] if len(cells) > 1 and not cells[1].replace(".", "").isdigit() else cells[0]
                    kegiatan_data[kode_keg]["nama"] = nama_keg
                    if len(numeric_vals) >= 2:
                        kegiatan_data[kode_keg]["pagu"] = numeric_vals[0]
                        kegiatan_data[kode_keg]["realisasi"] = numeric_vals[1]

                elif match_sub:
                    kode_keg = match_sub.group(1)
                    kode_full = f"{kode_keg}.{match_sub.group(2)}"
                    uraian = cells[1] if len(cells) > 1 else kode_full
                    pagu_item = numeric_vals[0] if len(numeric_vals) >= 1 else 0
                    real_item = numeric_vals[1] if len(numeric_vals) >= 2 else 0

                    # Pengecualian 7229.AEG
                    if kode_full == EXCLUDE_SUBOUTPUT:
                        excluded_pagu_7229 += pagu_item
                        excluded_real_7229 += real_item
                        continue

                    persen_item = round((real_item / pagu_item * 100), 2) if pagu_item > 0 else 0.0
                    kegiatan_data[kode_keg]["rincian"].append({
                        "kode": kode_full,
                        "uraian": uraian,
                        "pagu": pagu_item,
                        "realisasi": real_item,
                        "persen": persen_item
                    })

            total_pagu_all = 0
            total_real_all = 0
            hasil_list = []

            for kode in ["7228", "7229", "7230", "7231", "7832", "7245"]:
                item = kegiatan_data[kode]
                if item["pagu"] > 0:
                    if kode == "7229":
                        item["pagu"] = max(0, item["pagu"] - excluded_pagu_7229)
                        item["realisasi"] = max(0, item["realisasi"] - excluded_real_7229)
                else:
                    item["pagu"] = sum(r["pagu"] for r in item["rincian"])
                    item["realisasi"] = sum(r["realisasi"] for r in item["rincian"])

                item["persen"] = round((item["realisasi"] / item["pagu"] * 100), 2) if item["pagu"] > 0 else 0.0
                total_pagu_all += item["pagu"]
                total_real_all += item["realisasi"]
                hasil_list.append(item)

            persen_total_all = round((total_real_all / total_pagu_all * 100), 2) if total_pagu_all > 0 else 0.0

            output_payload = {
                "last_updated": get_wib_timestamp(),
                "summary": {
                    "total_pagu": total_pagu_all,
                    "total_realisasi": total_real_all,
                    "persen_serapan": persen_total_all
                },
                "kegiatan": hasil_list
            }

            with open("data.json", "w", encoding="utf-8") as f:
                json.dump(output_payload, f, indent=2, ensure_ascii=False)

            print(f"[{get_wib_timestamp()}] Sukses! Total Pagu: Rp {total_pagu_all:,}")

        except Exception as e:
            print(f"[ERROR] Terjadi kendala: {e}")
            page.screenshot(path="bukti_error_layar.png", full_page=True)
            raise e
        finally:
            browser.close()

if __name__ == "__main__":
    run_scraper()
