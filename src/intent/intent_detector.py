"""Katılım Bankacılığı Intent Detection Modülü
"""


class IntentDetector:
    def __init__(self):
        self.intents = {
            "BANKA_BILGISI": [
                "hangi bankalar",
                "katılım bankaları",
                "banka hakkında",
                "ziraat katılım",
                "kuveyt türk",
                "albaraka"
            ],
            "URUN_BILGISI": [
                "murabaha",
                "icara",
                "müşaraka",
                "finansman",
                "ürün"
            ],
            "KAMPANYA_SORUSU": [
                "kampanya",
                "indirim",
                "avantaj",
                "fırsat"
            ],
            "GENEL_SORU": [
                "nedir",
                "nasıl",
                "ne demek"
            ]
        }

    def detect(self, text):
        text = text.lower()

        for intent, keywords in self.intents.items():
            for keyword in keywords:
                if keyword in text:
                    return intent

        return "BILINMEYEN"


if __name__ == "__main__":
    detector = IntentDetector()

    sorular = [
        "Murabaha nedir?",
        "Ziraat Katılım kampanyaları neler?",
        "Türkiye'deki katılım bankaları hangileri?"
    ]

    for soru in sorular:
        print(
            soru,
            "---->",
            detector.detect(soru)
        )
