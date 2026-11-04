"""학생 페이지 주소로 prompts-qr.svg를 만든다."""
from pathlib import Path

import qrcode
import qrcode.image.svg

URL = "https://joygram.github.io/SejongLecture/handout/prompts.html"
TARGET = Path(__file__).resolve().parent / "prompts-qr.svg"


def main():
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(URL)
    qr.make(fit=True)
    qr.make_image(image_factory=qrcode.image.svg.SvgPathFillImage).save(TARGET)
    print(TARGET.name, URL)


if __name__ == "__main__":
    main()
