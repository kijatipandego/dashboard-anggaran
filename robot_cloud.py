import os
import json
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

# Mengambil kredensial dengan aman dari GitHub Secrets
SATUDJA_USER = os.environ.get("SATUDJA_USER")
SATUDJA_PASS = os.environ.get("SATUDJA_PASS")

TARGET_URLS = [
    "https://kemenkeu.go.id",
    "https://kemenkeu.go.id",
    "https://kemenkeu.go.id",
    "https://kemenkeu.go.id",
    "https://kemenkeu.go.id",
    "https://kemenkeu.go.id",
]

def jalankan_robot():
    daftar_kelompok_satker = []
    total_pagu_angka = 0
    total_realisasi_angka = 0

    with sync_playwright() as p:
        # Di server GitHub wajib headless=True (tanpa layar)
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print("Membuka halaman login SatuDJA...")
        page.goto("https://kemenkeu.go.id")

        page.fill('input[type="text"]', SATUDJA_USER)
        page.fill('input[type="password"]', SATUDJA_PASS)
        page.click('button[type="submit"]')

        page.wait_for_selector("text=T.A.", timeout=60000)
        print("Berhasil masuk ke SatuDJA!")

        for link in TARGET_URLS:
            print(f"Mengambil data dari: {link}")
            page.goto(link)
            page.wait_for_selector("table tbody tr", timeout=30000)
            page.wait_for_timeout(3000)

            baris_tabel = page.query_selector_all("table tbody tr")
            judul_satker = "Kegiatan / Satker"
            pagu_induk_num = 0
            realisasi_induk_num = 0
            rincian_output = []
            induk_sudah_diambil = False

            for baris in baris_tabel:
                kolom = baris.query_selector_all("td")
                if len(kolom) >= 6:
                    kode = kolom[0].inner_text().strip()
                    uraian = kolom[1].inner_text().strip()
                    pagu_teks = kolom[2].inner_text().strip()
                    realisasi_teks = kolom[3].inner_text().strip()
                    persen_teks = kolom[-1].inner_text().strip()

                    if "jumlah" in kode.lower() or "total" in kode.lower() or "jumlah" in uraian.lower():
                        continue

                    if "7229.AEG" in kode.upper():
                        pagu_aeg = int(pagu_teks.replace(".", "").replace(",", ""))
                        real_aeg = int(realisasi_teks.replace(".", "").replace(",", ""))
                        pagu_induk_num -= pagu_aeg
                        realisasi_induk_num -= real_aeg
                        total_pagu_angka -= pagu_aeg
                        total_realisasi_angka -= real_aeg
                        continue

                    if "." not in kode and not induk_sudah_diambil:
                        judul_satker = f"[{kode}] {uraian}"
                        pagu_induk_num = int(pagu_teks.replace(".", "").replace(",", ""))
                        realisasi_induk_num = int(realisasi_teks.replace(".", "").replace(",", ""))
                        total_pagu_angka += pagu_induk_num
                        total_realisasi_angka += realisasi_induk_num
                        induk_sudah_diambil = True
                    else:
                        rincian_output.append({
                            "nama": f"[{kode}] {uraian}",
                            "pagu": pagu_teks,
                            "realisasi": realisasi_teks,
                            "persen": persen_teks
                        })

            persen_induk_num = (realisasi_induk_num / pagu_induk_num * 100) if pagu_induk_num > 0 else 0
            daftar_kelompok_satker.append({
                "judul_header": judul_satker,
                "pagu_satker": f"{pagu_induk_num:,.0f}".replace(",", "."),
                "realisasi_satker": f"{realisasi_induk_num:,.0f}".replace(",", "."),
                "persen_satker": f"{persen_induk_num:.2f} %".replace(".", ","),
                "rincian": rincian_output
            })

        browser.close()

    persen_total = (total_realisasi_angka / total_pagu_angka * 100) if total_pagu_angka > 0 else 0
    
    # Menggunakan waktu WIB (UTC+7)
    wib = timezone(timedelta(hours=7))
    waktu_sekarang = datetime.now(wib).strftime("%d %B %Y, Pukul %H:%M WIB")

    data_final = {
        "terakhir_update": waktu_sekarang,
        "pagu_total": f"Rp {total_pagu_angka:,.0f}".replace(",", "."),
        "realisasi_total": f"Rp {total_realisasi_angka:,.0f}".replace(",", "."),
        "persentase": f"{persen_total:.2f}%",
        "kelompok_satker": daftar_kelompok_satker
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data_final, f, indent=2)
    print("File data.json berhasil diperbarui!")

if __name__ == "__main__":
    jalankan_robot()
