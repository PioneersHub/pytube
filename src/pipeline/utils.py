import markdown
from bs4 import BeautifulSoup
from pytanis.pretalx.models import Answer


def markdown_to_text(md: str) -> str:
    html = markdown.markdown(md)
    soup = BeautifulSoup(html, features="html.parser")
    return soup.get_text()


def get_answer_via_id(answers: list[Answer] | list[dict], answer_id: int) -> str | None:
    for a in answers:  # noqa
        try:
            if a.get("id", "") == int(answer_id):
                return a.get("answer")
        except AttributeError:
            if a.id == int(answer_id):
                return a.answer
