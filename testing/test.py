import requests
from bs4 import BeautifulSoup


def get_canonical(url: str) -> str | None:
    response = requests.get(url, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    tag = soup.find(
        "link",
        rel=lambda value: value and "canonical" in value
    )

    if not tag:
        return None

    return tag.get("href")


urls = [
    "https://docs.python.org/3/tutorial/",
    "https://docs.python.org/3/tutorial/index.html",
]

for url in urls:
    print("URL:", url)
    print("Canonical:", get_canonical(url))
    print()