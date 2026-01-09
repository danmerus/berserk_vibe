"""Script to download card images from proberserk.ru"""
import os
import urllib.request
import ssl

# Create data folder
os.makedirs("data/cards", exist_ok=True)

# Known card image numbers (card_name -> image_number)
CARD_IMAGES = {
    # Mountains (Горы)
    "Циклоп": "01-101",
    "Гном-басаарг": "01-053",
    "Хобгоблин": "01-100",
    "Хранитель гор": "01-050",
    "Повелитель молний": "01-066",
    "Лёккен": "01-085",
    "Гобрах": "01-064",
    "Ледовый охотник": "01-045",
    "Горный великан": "01-061",
    "Мастер топора": "01-046",
    "Костедробитель": "01-062",
    "Смотритель горнила": "01-048",
    "Овражный гном": "01-037",

    # Forest (Лес)
    "Эльфийский воин": "01-097",
    "Бегущая по кронам": "01-079",
    "Кобольд": "01-092",
    "Клаэр": "01-082",
    "Борг": "01-055",
    "Ловец удачи": "01-181",
    "Матросы Аделаиды": "01-182",
    "Мразень": "01-040",
    "Друид": "01-073",
    "Корпит": "01-074",
    "Оури": "01-076",
    "Паук-пересмешник": "01-077",
    "Дракс": "01-070",
}

BASE_URL = "https://proberserk.ru/images/cards/1/"

# Disable SSL verification for simplicity
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

def download_image(card_name, image_num):
    """Download a card image."""
    url = f"{BASE_URL}{image_num}.jpg"
    # Use transliterated filename
    filename = f"data/cards/{image_num}.jpg"

    if os.path.exists(filename):
        print(f"Already exists: {filename}")
        return True

    try:
        print(f"Downloading {card_name} from {url}...")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ssl_context) as response:
            data = response.read()
            with open(filename, 'wb') as f:
                f.write(data)
        print(f"  Saved to {filename}")
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False

def main():
    print("Downloading card images...")
    success = 0
    failed = 0

    for card_name, image_num in CARD_IMAGES.items():
        if download_image(card_name, image_num):
            success += 1
        else:
            failed += 1

    print(f"\nDone! Success: {success}, Failed: {failed}")

if __name__ == "__main__":
    main()
