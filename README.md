# Throng: Swarm Overlord V2

Throng adalah platform riset keamanan siber otonom untuk lingkungan yang diizinkan (lab siber, server pribadi). **HANYA UNTUK RISET LEGAL**.

## Fitur
- **Pemindaian Proaktif**: Memindai subnet untuk kerentanan.
- **Otonomi**: Agent membuat keputusan sendiri menggunakan heuristik dan AI ringan.
- **Eksploitasi**: Pengujian SSH dan web (XSS, SQLi) untuk riset.
- **Peta Jaringan**: Visualisasi 3D dengan Vis.js.
- **Grafik Ancaman**: Heatmap dan grafik batang untuk ancaman.
- **Ringan**: Dioptimalkan untuk deployment di Railway.

## Prasyarat
- Python 3.9
- Docker
- Kafka (single broker)
- Railway CLI

## Instalasi
1. Clone repositori:
   ```bash
   git clone https://github.com/username/throng.git
   cd throng